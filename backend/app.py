import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from pydantic import BaseModel, EmailStr, Field

from backend.auth import AuthError, AuthService
from backend.config import get_settings
from backend.mail import smtp_sender
from backend.store import Neo4jStore


class EmailInput(BaseModel):
    email: EmailStr = Field(max_length=254)


class CodeInput(EmailInput):
    code: str = Field(pattern=r"^\d{6}$")


def create_app(
    settings=None,
    store=None,
    sender=None,
    clock=time.time,
    travel_repository=None,
    search_service=None,
    conversation_store=None,
    llm=None,
    embedder=None,
    photo_service=None,
    photo_analyzer=None,
):
    settings = settings or get_settings()
    owned = store is None
    store = store if store is not None else Neo4jStore(settings)
    auth = AuthService(settings, store, sender or smtp_sender(settings), clock)
    from backend.conversation import ConversationService, create_conversation_router
    from backend.conversation_store import MemoryConversationStore, Neo4jConversationStore
    from backend.photo_analysis import PhotoAnalysisWorker
    from backend.photo_search import PhotoSearchService
    from backend.photo_store import MemoryPhotoStore, Neo4jPhotoStore
    from backend.photos import PhotoService, create_photo_router
    from backend.retrieval import SearchService
    from backend.search import create_search_router
    from backend.travel import create_travel_router
    from backend.travel_store import MemoryTravelRepository, Neo4jTravelRepository

    if travel_repository is None:
        travel_repository = (
            Neo4jTravelRepository(store.driver, store.database)
            if isinstance(store, Neo4jStore)
            else MemoryTravelRepository()
        )

    search_service = search_service or SearchService(settings, travel_repository, embedder=embedder)
    if conversation_store is None:
        conversation_store = (
            Neo4jConversationStore(store.driver, store.database)
            if isinstance(store, Neo4jStore)
            else MemoryConversationStore()
        )
    if photo_service is None:
        photo_store = Neo4jPhotoStore(store.driver, store.database) if isinstance(store, Neo4jStore) else MemoryPhotoStore()
        photo_service = PhotoService(settings, photo_store, travel_repository, conversation_store, clock=clock)
    shared_embedder = getattr(search_service, "embedder", embedder)
    photo_search = PhotoSearchService(settings, photo_service, embedder=shared_embedder)
    photo_worker = PhotoAnalysisWorker(settings, photo_service, analyzer=photo_analyzer, embedder=shared_embedder)
    search_service.photo_search = photo_search
    conversations = ConversationService(
        settings, search_service, conversation_store, clock=clock, llm=llm
    )
    conversations.photo_service = photo_service
    conversations.photo_analyzer = photo_worker.analyzer

    async def cleanup():
        while True:
            await asyncio.sleep(3600)
            try:
                await asyncio.to_thread(store.cleanup, clock())
                await asyncio.to_thread(photo_service.cleanup)
            except (Neo4jError, ServiceUnavailable, OSError):
                logging.getLogger(__name__).warning("Auth cleanup unavailable")

    @asynccontextmanager
    async def lifespan(app):
        tasks = []
        if owned:
            await asyncio.to_thread(store.initialize)
            await asyncio.to_thread(travel_repository.initialize)
            tasks.append(asyncio.create_task(cleanup()))
        await asyncio.to_thread(search_service.initialize)
        await asyncio.to_thread(conversation_store.initialize)
        await asyncio.to_thread(photo_service.initialize)
        await asyncio.to_thread(photo_search.initialize)
        if owned:
            tasks.append(asyncio.create_task(search_service.run_worker()))
            tasks.append(asyncio.create_task(photo_worker.run_worker()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if owned:
                store.close()

    app = FastAPI(
        title="TravelMemo",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env == "development" else None,
        openapi_url="/openapi.json" if settings.app_env == "development" else None,
        redoc_url=None,
    )
    app.state.search = search_service
    app.state.conversations = conversations
    app.state.travel = travel_repository
    app.state.photos = photo_service
    app.state.photo_worker = photo_worker

    @app.middleware("http")
    async def origin_check(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != settings.origin
        ):
            return JSONResponse({"detail": "不允許此來源的請求。"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return JSONResponse(
            {"detail": exc.message},
            status_code=exc.status,
            headers={"Retry-After": str(settings.resend_seconds)} if exc.status == 429 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        detail = (
            "請檢查信箱格式及六位數驗證碼。"
            if request.url.path.startswith("/api/v1/auth/")
            else "請檢查旅程日期、地點及欄位內容。"
        )
        return JSONResponse({"detail": detail}, status_code=422)

    async def database_error(request, exc):
        return JSONResponse({"detail": "資料服務暫時無法使用，請稍後再試。"}, status_code=503)

    app.add_exception_handler(Neo4jError, database_error)
    app.add_exception_handler(ServiceUnavailable, database_error)

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    def ready():
        try:
            database = bool(store.ping())
        except (Neo4jError, ServiceUnavailable, OSError):
            database = False
        smtp = bool(settings.smtp_host)
        ok = database and smtp
        return JSONResponse(
            {
                "status": "ready" if ok else "not_ready",
                "database": database,
                "smtp_configured": smtp,
            },
            status_code=200 if ok else 503,
        )

    @app.post("/api/v1/auth/request-code", status_code=202)
    def request_code(body: EmailInput, request: Request):
        auth.request_code(
            str(body.email).casefold(), request.client.host if request.client else "unknown"
        )
        return {
            "message": "若此信箱符合登入資格，將會收到驗證碼。",
            "retry_after": settings.resend_seconds,
        }

    @app.post("/api/v1/auth/verify-code")
    def verify_code(body: CodeInput, request: Request, response: Response):
        token, user, csrf = auth.verify(
            str(body.email).casefold(),
            body.code,
            request.client.host if request.client else "unknown",
        )
        response.set_cookie(
            "travelmemo_session",
            token,
            max_age=settings.session_days * 86400,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return {"user": user, "csrf_token": csrf}

    @app.get("/api/v1/auth/me")
    def me(request: Request):
        session = auth.session(request.cookies.get("travelmemo_session"))
        return {"user": session["user"], "csrf_token": session["csrf_token"]}

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request):
        auth.logout(request.cookies.get("travelmemo_session"), request.headers.get("X-CSRF-Token"))
        response = Response(status_code=204)
        response.delete_cookie(
            "travelmemo_session",
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    app.include_router(create_travel_router(auth, travel_repository, photo_service=photo_service))
    app.include_router(create_search_router(auth, search_service, photo_search=photo_search))
    app.include_router(create_photo_router(auth, photo_service))
    app.include_router(create_conversation_router(auth, conversations))
    return app
