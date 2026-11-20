import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import AuthService
from backend.config import Settings
from backend.store import MemoryStore
from backend.timezones import resolve_timezone
from backend.travel import create_travel_router
from backend.travel_store import MemoryTravelRepository, TravelConflictError, TravelValidationError


def event_data(**changes):
    return {"place_name": "海邊", "city": "臺南", "category": "散步", "date": "2026-11-20", "timezone": "Asia/Taipei", **changes}


def trip_data(**changes):
    return {"name": "臺南小旅行", "start_date": "2026-11-19", "end_date": "2026-11-22", "timezone": "Asia/Taipei", **changes}


def test_standalone_crud_is_private_and_never_creates_trip_or_next():
    repo = MemoryTravelRepository()
    first = repo.create_standalone_event("alice", event_data())
    second = repo.create_standalone_event("bob", event_data())
    assert first["trip_id"] is None and first["position"] is None
    assert first["timezone"] == "Asia/Taipei" and first["record_scope"] == "standalone"
    assert not repo.trips
    assert repo.get_event("bob", first["id"]) is None
    assert [e["id"] for e in repo.list_standalone_events("alice")["items"]] == [first["id"]]
    updated = repo.update_event("alice", first["id"], event_data(notes="看夕陽", version=first["version"]))
    assert updated["notes"] == "看夕陽" and updated["version"] == 2
    with pytest.raises(TravelConflictError):
        repo.delete_event("alice", first["id"], first["version"])
    repo.delete_event("alice", first["id"], updated["version"])
    assert repo.get_event("alice", first["id"]) is None
    assert repo.get_event("bob", second["id"])


def test_standalone_listing_filters_and_pages_stably():
    repo = MemoryTravelRepository()
    old = repo.create_standalone_event("a", event_data(date="2026-11-19", time="18:00"))
    new = repo.create_standalone_event("a", event_data(notes="夕陽", time="17:00"))
    other = repo.create_standalone_event("a", event_data(city="高雄", category="美食"))
    page = repo.list_standalone_events("a", city="臺南", limit=1)
    assert page["items"][0]["id"] == new["id"] and page["next_offset"] == 1
    assert repo.list_standalone_events("a", city="臺南", limit=1, offset=1)["items"][0]["id"] == old["id"]
    assert repo.list_standalone_events("a", q="夕陽", date_from="2026-11-20")["items"][0]["id"] == new["id"]
    assert repo.list_standalone_events("a", category="美食")["items"][0]["id"] == other["id"]


def test_standalone_same_time_prefers_latest_created_and_tolerates_legacy_timestamp():
    repo = MemoryTravelRepository()
    legacy = repo.create_standalone_event("a", event_data())
    older = repo.create_standalone_event("a", event_data())
    newest = repo.create_standalone_event("a", event_data())
    repo.events[legacy["id"]].pop("created_at")
    repo.events[older["id"]]["created_at"] = "2026-11-20T01:00:00+00:00"
    repo.events[newest["id"]]["created_at"] = "2026-11-20T02:00:00+00:00"
    assert [e["id"] for e in repo.list_standalone_events("a")["items"]] == [newest["id"], older["id"], legacy["id"]]


def test_attach_keeps_id_validates_versions_timezone_and_same_day_position():
    repo = MemoryTravelRepository()
    trip = repo.create_trip("a", trip_data())
    existing = repo.create_event("a", trip["id"], event_data())
    single = repo.create_standalone_event("a", event_data())
    data = {"trip_id": trip["id"], "version": 1, "trip_version": 1, "before_event_id": existing["id"]}
    with pytest.raises(TravelConflictError):
        repo.attach_event_to_trip("a", single["id"], data)
    data["trip_version"] = 2
    result = repo.attach_event_to_trip("a", single["id"], data)
    assert result["id"] == single["id"] and result["version"] == 2
    assert result["trip_id"] == trip["id"] and result["record_scope"] == "trip"
    detail = repo.get_trip_detail("a", trip["id"])
    assert [e["id"] for e in detail["events"]] == [single["id"], existing["id"]]
    assert detail["next_edges"] == [{"from_id": single["id"], "to_id": existing["id"]}]
    assert not repo.list_standalone_events("a")["items"]
    with pytest.raises(TravelConflictError):
        repo.attach_event_to_trip("a", single["id"], {**data, "version": 2, "trip_version": 3})
    wrong_zone = repo.create_standalone_event("a", event_data(timezone="Asia/Tokyo"))
    with pytest.raises(TravelValidationError):
        repo.attach_event_to_trip("a", wrong_zone["id"], {**data, "trip_version": 3})
    wrong_date = repo.create_standalone_event("a", event_data(date="2026-11-21"))
    with pytest.raises(TravelValidationError):
        repo.attach_event_to_trip("a", wrong_date["id"], {**data, "trip_version": 3})


def test_standalone_api_defaults_validation_and_owner_is_server_derived():
    settings = Settings(_env_file=None, session_secret="private-test-" * 4, allowed_emails="tester@example.com", cookie_secure=False)
    auth = AuthService(settings, MemoryStore(), sender=lambda *_: None)
    token, csrf = "session", "csrf"
    auth.store.put("session:" + auth.digest(token), {"user": {"id": "owner", "email": "tester@example.com"}, "csrf_token": csrf, "expires_at": auth.clock() + 3600})
    repo = MemoryTravelRepository()
    app = FastAPI()
    app.include_router(create_travel_router(auth, repo))
    with TestClient(app) as client:
        assert client.get("/api/v1/events").status_code == 401
        client.cookies.set("travelmemo_session", token)
        assert client.post("/api/v1/events", json={"place_name": "公園"}).status_code == 403
        headers = {"X-CSRF-Token": csrf}
        response = client.post("/api/v1/events", json={"place_name": "公園", "timezone": "UTC+8"}, headers=headers)
        assert response.status_code == 201
        event = response.json()
        assert event["category"] == "未分類" and event["timezone"] == "UTC+08:00"
        assert event["date"] == datetime.datetime.now(resolve_timezone(event["timezone"])).date().isoformat()
        assert client.get("/api/v1/events").json() == {"items": [event], "next_offset": None}
        assert client.get("/api/v1/events?date_from=2026-11-22&date_to=2026-11-20").status_code == 422
        assert client.post("/api/v1/events", json={"place_name": "公園", "date": "bad"}, headers=headers).status_code == 422
        assert client.post("/api/v1/events", json={"place_name": "公園", "owner_id": "other"}, headers=headers).status_code == 422
