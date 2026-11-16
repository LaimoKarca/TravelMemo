"""Public API integration, with an injected store for fast ownership checks."""

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.store import MemoryStore


def test_private_crud_order_and_optimistic_conflicts():
    settings = Settings(
        _env_file=None, session_secret="test-" * 10, allowed_emails="a@example.com,b@example.com"
    )
    sent = {}
    app = create_app(settings, MemoryStore(), lambda email, code: sent.update({email: code}))
    with TestClient(app) as a, TestClient(app) as b:
        for client, email in [(a, "a@example.com"), (b, "b@example.com")]:
            assert (
                client.post("/api/v1/auth/request-code", json={"email": email}).status_code == 202
            )
            response = client.post(
                "/api/v1/auth/verify-code", json={"email": email, "code": sent[email]}
            )
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]

        payload = {
            "name": "東京旅程",
            "start_date": "2026-11-01",
            "end_date": "2026-11-03",
            "timezone": "Asia/Tokyo",
            "description": "測試",
        }
        response = a.post("/api/v1/trips", json=payload)
        assert response.status_code == 201, response.text
        trip = response.json()
        url = "/api/v1/trips/" + trip["id"]
        assert b.get(url).status_code == 404
        assert b.put(url, json={**payload, "version": trip["version"]}).status_code == 404
        assert b.get("/api/v1/trips").json()["items"] == []

        event = {
            "date": "2026-11-01",
            "time": None,
            "place_name": "同名咖啡店",
            "city": "東京",
            "address": "",
            "category": "咖啡店",
            "notes": "時間不詳",
        }
        first = a.post(url + "/events", json=event).json()
        second = a.post(url + "/events", json={**event, "place_id": first["place_id"]}).json()
        third = a.post(url + "/events", json={**event, "date": "2026-11-02"}).json()
        assert first["id"] != second["id"]
        assert first["place_id"] == second["place_id"]
        assert third["place_id"] != first["place_id"]
        assert first["time"] is None
        detail = a.get(url).json()
        assert len(detail["next_edges"]) == 2
        assert b.get("/api/v1/places").json()["items"] == []
        assert b.delete("/api/v1/events/" + first["id"], params={"version": 1}).status_code == 404

        order = [second["id"], first["id"], third["id"]]
        revision = detail["trip"]["version"]
        assert (
            a.put(url + "/event-order", json={"version": revision, "event_ids": order}).status_code
            == 200
        )
        assert (
            a.put(url + "/event-order", json={"version": revision, "event_ids": order}).status_code
            == 409
        )
        assert [e["id"] for e in a.get(url).json()["events"]] == order

        version = a.get(url).json()["trip"]["version"]
        assert (
            a.put(
                url + "/event-order", json={"version": version, "event_ids": order[::-1]}
            ).status_code
            == 422
        )
        assert a.delete("/api/v1/events/" + first["id"], params={"version": 999}).status_code == 409
        assert a.delete("/api/v1/events/" + first["id"], params={"version": 1}).status_code == 204
        detail = a.get(url).json()
        assert detail["next_edges"] == [{"from_id": second["id"], "to_id": third["id"]}]
        assert (
            a.put(
                url,
                json={**payload, "end_date": "2026-11-01", "version": detail["trip"]["version"]},
            ).status_code
            == 422
        )
        assert a.delete(url, params={"version": detail["trip"]["version"]}).status_code == 204
        assert a.get(url).status_code == 404


def test_travel_write_requires_auth_and_csrf():
    settings = Settings(_env_file=None, session_secret="test-" * 10)
    with TestClient(create_app(settings, MemoryStore())) as client:
        assert client.get("/api/v1/trips").status_code == 401
        assert (
            client.post(
                "/api/v1/trips",
                json={
                    "name": "x",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-02",
                    "timezone": "Asia/Taipei",
                    "description": "",
                },
            ).status_code
            == 401
        )
