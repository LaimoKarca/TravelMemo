from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import AuthService
from backend.conversation import ConversationService, create_conversation_router
from backend.conversation_store import MemoryConversationStore
from backend.llm import MockLLM
from backend.store import MemoryStore


class FakeSearchService:
    def __init__(self, events=None):
        self.events = events or {}

    def search(
        self,
        owner_id: str,
        query: str,
        limit: int = 10,
        anchor_id: str | None = None,
    ):
        items = []
        for ev in self.events.values():
            if ev.get("owner_id") == owner_id:
                items.append({"event": ev, "score": 1.0, "reasons": ["命中"]})
        return {"items": items, "clarification": None}

    def get_event(self, owner_id: str, event_id: str):
        ev = self.events.get(event_id)
        if ev and ev.get("owner_id") == owner_id:
            return ev
        return None


def create_test_api():
    settings = SimpleNamespace(
        session_secret="test-secret-at-least-32-chars-long!",
        session_days=7,
        allowed_emails="alice@example.com,bob@example.com",
        emails={"alice@example.com", "bob@example.com"},
        ip_hourly_limit=100,
        email_hourly_limit=100,
        resend_seconds=1,
        otp_attempts=5,
        cookie_secure=False,
        openai_model="gpt-6-luna",
        openai_api_key="test-key",
    )
    auth_store = MemoryStore()
    auth_service = AuthService(settings, auth_store, lambda e, c: None)

    events = {
        "evt-tokyo": {
            "id": "evt-tokyo",
            "owner_id": "alice-id",
            "trip_id": "trip-1",
            "place_name": "東京晴空塔",
            "date": "2026-11-01",
            "version": 1,
            "category": "景點",
            "notes": "展望台門票已預約",
        }
    }
    search_service = FakeSearchService(events=events)
    conv_store = MemoryConversationStore()
    llm = MockLLM(
        default_status="answered",
        default_content="您在11月1日造訪了東京晴空塔。",
        default_cited_event_ids=["evt-tokyo"],
        input_tokens=20,
        output_tokens=30,
    )
    conv_service = ConversationService(
        settings, search_service, store=conv_store, llm=llm
    )

    app = FastAPI()
    router = create_conversation_router(auth_service, conv_service)
    app.include_router(router)

    return app, auth_service, conv_service, events


def login_user(client: TestClient, auth_service: AuthService, email: str, user_id: str):
    import secrets

    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    with auth_service.store.atomic() as tx:
        tx.user(user_id, email)
        tx.put(
            "session:" + auth_service.digest(token),
            {
                "user": {"id": user_id, "email": email},
                "csrf_token": csrf,
                "expires_at": auth_service.clock() + 86400 * 7,
            },
        )
    client.cookies.set("travelmemo_session", token)
    return csrf


def test_unauthenticated_requests():
    app, _, _, _ = create_test_api()
    with TestClient(app) as client:
        # GET conversations without auth -> 401
        res = client.get("/api/v1/conversations")
        assert res.status_code == 401

        # POST conversations without auth -> 401
        res = client.post("/api/v1/conversations", json={"title": "test"})
        assert res.status_code == 401

        # GET usage without auth -> 401
        res = client.get("/api/v1/usage/me")
        assert res.status_code == 401


def test_csrf_protection_on_write_endpoints():
    app, auth_service, _, _ = create_test_api()
    with TestClient(app) as client:
        csrf = login_user(client, auth_service, "alice@example.com", "alice-id")

        # POST /conversations without CSRF token -> 403
        res = client.post("/api/v1/conversations", json={"title": "test"})
        assert res.status_code == 403

        # POST /conversations with invalid CSRF token -> 403
        res = client.post(
            "/api/v1/conversations",
            json={"title": "test"},
            headers={"X-CSRF-Token": "invalid-csrf"},
        )
        assert res.status_code == 403

        # POST /conversations with valid CSRF token -> 201
        res = client.post(
            "/api/v1/conversations",
            json={"title": "東京五日遊"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 201
        cid = res.json()["id"]

        # POST message without CSRF token -> 403
        res = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "晴空塔在哪？"},
        )
        assert res.status_code == 403

        # DELETE conversation without CSRF token -> 403
        res = client.delete(f"/api/v1/conversations/{cid}")
        assert res.status_code == 403


def test_conversation_flow_and_usage():
    app, auth_service, _, _ = create_test_api()
    with TestClient(app) as client:
        csrf = login_user(client, auth_service, "alice@example.com", "alice-id")
        headers = {"X-CSRF-Token": csrf}

        # 1. Create conversation
        res = client.post("/api/v1/conversations", json={"title": "東京秋天行"}, headers=headers)
        assert res.status_code == 201
        conv = res.json()
        cid = conv["id"]
        assert conv["title"] == "東京秋天行"
        assert "created_at" in conv

        # 2. List conversations
        res = client.get("/api/v1/conversations")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == cid

        # 3. Post message
        res = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "我哪天去晴空塔？"},
            headers=headers,
        )
        assert res.status_code == 200
        msg = res.json()
        assert msg["role"] == "assistant"
        assert msg["status"] == "answered"
        assert len(msg["citations"]) == 1
        assert msg["citations"][0]["event_id"] == "evt-tokyo"
        assert msg["citations"][0]["state"] == "current"

        # 4. List messages
        res = client.get(f"/api/v1/conversations/{cid}/messages")
        assert res.status_code == 200
        messages = res.json()["items"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

        # 5. Check usage
        res = client.get("/api/v1/usage/me")
        assert res.status_code == 200
        usage = res.json()
        assert usage["requests"] == 1
        assert usage["input_tokens"] == 20
        assert usage["output_tokens"] == 30
        assert usage["daily_limit"] == 50
        assert usage["model"] == "gpt-6-luna"

        # 6. Delete conversation
        res = client.delete(f"/api/v1/conversations/{cid}", headers=headers)
        assert res.status_code == 204

        # 7. Verify deletion
        res = client.get("/api/v1/conversations")
        assert res.json()["items"] == []


def test_cross_account_isolation_in_api():
    app, auth_service, _, _ = create_test_api()
    with TestClient(app) as client_a, TestClient(app) as client_b:
        csrf_a = login_user(client_a, auth_service, "alice@example.com", "alice-id")
        csrf_b = login_user(client_b, auth_service, "bob@example.com", "bob-id")

        # Alice creates a conversation
        res = client_a.post(
            "/api/v1/conversations",
            json={"title": "Alice 的秘密旅程"},
            headers={"X-CSRF-Token": csrf_a},
        )
        cid = res.json()["id"]

        # Bob attempts to get messages of Alice's conversation -> 404
        res = client_b.get(f"/api/v1/conversations/{cid}/messages")
        assert res.status_code == 404

        # Bob attempts to post message to Alice's conversation -> 404
        res = client_b.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "Hello Alice"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res.status_code == 404

        # Bob attempts to delete Alice's conversation -> 404
        res = client_b.delete(f"/api/v1/conversations/{cid}", headers={"X-CSRF-Token": csrf_b})
        assert res.status_code == 404

        # Bob's conversation list is empty
        res = client_b.get("/api/v1/conversations")
        assert res.json()["items"] == []


def test_extra_forbidden_fields():
    app, auth_service, _, _ = create_test_api()
    with TestClient(app) as client:
        csrf = login_user(client, auth_service, "alice@example.com", "alice-id")
        headers = {"X-CSRF-Token": csrf}

        # Extra field on create conversation -> 422
        res = client.post(
            "/api/v1/conversations",
            json={"title": "行程", "disallowed": 123},
            headers=headers,
        )
        assert res.status_code == 422

        # Create valid conversation
        res = client.post(
            "/api/v1/conversations",
            json={"title": "行程"},
            headers=headers,
        )
        cid = res.json()["id"]

        # Extra field on send message -> 422
        res = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "你好", "owner_id": "hacker"},
            headers=headers,
        )
        assert res.status_code == 422


import threading


def test_concurrent_messages_api_user_concurrency():
    app, auth_service, conv_service, _ = create_test_api()

    in_call = threading.Event()
    release_call = threading.Event()

    def slow_handler(instructions, text):
        in_call.set()
        release_call.wait(timeout=3)
        return conv_service.llm.__class__(
            default_status="answered",
            default_content="慢慢回答",
            default_cited_event_ids=["evt-tokyo"],
        ).generate(instructions, text)

    conv_service.llm.handler = slow_handler

    with TestClient(app) as client:
        csrf = login_user(client, auth_service, "alice@example.com", "alice-id")
        headers = {"X-CSRF-Token": csrf}

        res = client.post("/api/v1/conversations", json={"title": "並行測試"}, headers=headers)
        cid = res.json()["id"]

        responses = {}

        def send_first():
            with TestClient(app, cookies=client.cookies) as c1:
                responses["first"] = c1.post(
                    f"/api/v1/conversations/{cid}/messages",
                    json={"content": "第一個問題"},
                    headers=headers,
                )

        def send_second():
            in_call.wait(timeout=2)
            with TestClient(app, cookies=client.cookies) as c2:
                responses["second"] = c2.post(
                    f"/api/v1/conversations/{cid}/messages",
                    json={"content": "第二個問題（並行）"},
                    headers=headers,
                )

        t1 = threading.Thread(target=send_first)
        t2 = threading.Thread(target=send_second)

        t1.start()
        t2.start()

        t2.join(timeout=3)
        release_call.set()
        t1.join(timeout=3)

        assert responses["first"].status_code == 200
        assert responses["second"].status_code == 429
        assert "進行中" in responses["second"].json()["detail"]
