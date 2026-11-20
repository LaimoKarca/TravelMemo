"""FastAPI router for search and event retrieval."""

import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth import AuthError, AuthService
from backend.dependencies import authenticate
from backend.travel import Event


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=500)
    photo_ids: list[str] = Field(default_factory=list, max_length=4)
    trip_id: str | None = Field(default=None, max_length=100)
    record_scope: Literal["all", "standalone", "trip"] = "all"
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    city: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        trimmed = v.strip()
        return trimmed

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                datetime.date.fromisoformat(v)
            except ValueError as exc:
                raise ValueError("日期格式無效。") from exc
        return v

    @model_validator(mode="after")
    def validate_date_range(self):
        if not self.query and not self.photo_ids:
            raise ValueError("查詢字串不得為空白，或請選擇圖片。")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("起始日期不得晚於結束日期。")
        if self.record_scope == "standalone" and self.trip_id:
            raise ValueError("日常足跡範圍不能同時指定旅程手記。")
        return self


class RelationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_id: str
    direction: str
    anchor_date: str
    target_date: str


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Event
    score: float
    reasons: list[str]
    relation: RelationContext | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SearchResultItem]
    clarification: str | None = None
    vector_status: str
    photo_items: list[dict] = Field(default_factory=list)


class EventDetailResponse(Event):
    model_config = ConfigDict(extra="forbid")
    trip_name: str | None = None


def create_search_router(auth: AuthService, service: Any, prefix: str = "/api/v1", photo_search: Any = None) -> APIRouter:
    router = APIRouter(prefix=prefix)

    def _auth(request: Request, write: bool = False) -> str:
        try:
            return authenticate(auth, request, write=write)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message)

    @router.post("/search", response_model=SearchResponse)
    def search(body: SearchInput, request: Request):
        owner_id = _auth(request, write=True)
        filters = {
            "trip_id": body.trip_id,
            "date_from": body.date_from,
            "date_to": body.date_to,
            "city": body.city,
            "category": body.category,
        }
        if body.record_scope != "all":
            filters["record_scope"] = body.record_scope
        query = body.query
        if body.photo_ids:
            if photo_search is None:
                raise HTTPException(status_code=503, detail="圖片搜尋暫時無法使用。")
            photo_search.photo_service.ready_evidence(owner_id, body.photo_ids)
            clues = photo_search.get_query_text(owner_id, body.photo_ids)
            query = f"{query}\n{clues}".strip()[:2000]
        res = service.search(
            owner_id=owner_id,
            query=query,
            filters=filters,
            limit=body.limit,
        )
        if photo_search is not None:
            res["photo_items"] = photo_search.search(owner_id, query, limit=body.limit, **filters)
        return res

    @router.get("/search/status")
    def search_status(request: Request):
        owner_id = _auth(request, write=False)
        return service.index_status(owner_id)

    @router.get("/events/{id}", response_model=EventDetailResponse)
    def get_event(id: str, request: Request):
        owner_id = _auth(request, write=False)
        event_dict = service.get_event(owner_id, id)
        if not event_dict:
            raise HTTPException(status_code=404, detail="找不到指定的事件。")
        return event_dict

    return router
