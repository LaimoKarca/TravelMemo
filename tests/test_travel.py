import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import AuthService
from backend.config import Settings
from backend.store import MemoryStore
from backend.travel import create_travel_router
from backend.travel_store import MemoryTravelRepository


class MockAuthService(AuthService):
    """Auth service helper for testing that allows controlling session records."""

    def __init__(self, settings, store):
        super().__init__(settings, store, sender=lambda e, c: None)


@pytest.fixture
def travel_app():
    settings = Settings(
        _env_file=None,
        session_secret="travel-secret-" * 4,
        allowed_emails="alice@example.com,bob@example.com",
        cookie_secure=False,
    )
    store = MemoryStore()
    auth = MockAuthService(settings, store)
    repo = MemoryTravelRepository()

    app = FastAPI(title="TravelMemo Test")
    router = create_travel_router(auth, repo)
    app.include_router(router)

    with TestClient(app) as client:
        yield client, auth, repo, settings, store


def sign_in(auth, email="alice@example.com", user_id="user-alice"):
    token = "session-token-" + email
    csrf = "csrf-token-" + email
    auth.store.user(user_id, email)
    auth.store.put(
        "session:" + auth.digest(token),
        {
            "user": {"id": user_id, "email": email},
            "csrf_token": csrf,
            "expires_at": auth.clock() + 3600,
        },
    )
    return token, csrf, user_id


def test_auth_and_csrf_enforcement(travel_app):
    client, auth, _repo, _, _ = travel_app

    # Unauthenticated GET
    res = client.get("/api/v1/trips")
    assert res.status_code == 401
    assert res.json() == {"detail": "請先登入。"}

    # Authenticate Alice
    token, csrf, _ = sign_in(auth, "alice@example.com", "user-alice")
    client.cookies.set("travelmemo_session", token)

    # Authenticated GET without CSRF is allowed
    res = client.get("/api/v1/trips")
    assert res.status_code == 200
    assert res.json() == {"items": []}

    # Write without CSRF header is rejected with 403
    trip_data = {
        "name": "Kyoto Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "Visiting Kyoto temples",
    }
    res = client.post("/api/v1/trips", json=trip_data)
    assert res.status_code == 403

    # Write with wrong CSRF header is rejected with 403
    res = client.post("/api/v1/trips", json=trip_data, headers={"X-CSRF-Token": "bad-csrf"})
    assert res.status_code == 403

    # Write with valid CSRF token succeeds
    res = client.post("/api/v1/trips", json=trip_data, headers={"X-CSRF-Token": csrf})
    assert res.status_code == 201
    trip = res.json()
    assert trip["name"] == "Kyoto Trip"
    assert trip["version"] == 1


def test_trip_crud_validation_and_bounds(travel_app):
    client, auth, _repo, _, _ = travel_app
    token, csrf, _user_id = sign_in(auth)
    client.cookies.set("travelmemo_session", token)
    headers = {"X-CSRF-Token": csrf}

    # Validation: start_date > end_date -> 422
    res = client.post(
        "/api/v1/trips",
        json={
            "name": "Invalid Dates",
            "start_date": "2026-06-10",
            "end_date": "2026-06-05",
            "timezone": "Asia/Taipei",
            "description": "",
        },
        headers=headers,
    )
    assert res.status_code == 422

    # Validation: extra fields forbidden
    res = client.post(
        "/api/v1/trips",
        json={
            "name": "Extra",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "timezone": "Asia/Taipei",
            "description": "",
            "extra_field": "disallowed",
        },
        headers=headers,
    )
    assert res.status_code == 422

    # Create two trips
    trip1 = client.post(
        "/api/v1/trips",
        json={
            "name": "Earlier Trip",
            "start_date": "2026-04-01",
            "end_date": "2026-04-05",
            "timezone": "Asia/Taipei",
            "description": "April",
        },
        headers=headers,
    ).json()

    trip2 = client.post(
        "/api/v1/trips",
        json={
            "name": "Later Trip",
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "timezone": "Asia/Taipei",
            "description": "July",
        },
        headers=headers,
    ).json()

    # GET /trips sorts start_date descending
    res = client.get("/api/v1/trips")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] == trip2["id"]
    assert items[1]["id"] == trip1["id"]

    # GET /trips/{id}
    res = client.get(f"/api/v1/trips/{trip1['id']}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["trip"]["id"] == trip1["id"]
    assert detail["events"] == []
    assert detail["next_edges"] == []

    # PUT /trips/{id} update trip
    res = client.put(
        f"/api/v1/trips/{trip1['id']}",
        json={
            "name": "Earlier Trip Updated",
            "start_date": "2026-04-01",
            "end_date": "2026-04-06",
            "timezone": "Asia/Taipei",
            "description": "Updated description",
            "version": 1,
        },
        headers=headers,
    )
    assert res.status_code == 200
    updated_trip = res.json()
    assert updated_trip["version"] == 2
    assert updated_trip["end_date"] == "2026-04-06"

    # PUT /trips/{id} with outdated version -> 409
    res = client.put(
        f"/api/v1/trips/{trip1['id']}",
        json={
            "name": "Conflict Attempt",
            "start_date": "2026-04-01",
            "end_date": "2026-04-06",
            "timezone": "Asia/Taipei",
            "description": "Old version 1",
            "version": 1,
        },
        headers=headers,
    )
    assert res.status_code == 409

    # Add an event to trip1 to test shrinking bounds validation
    event_res = client.post(
        f"/api/v1/trips/{trip1['id']}/events",
        json={
            "place_name": "Taipei 101",
            "city": "Taipei",
            "address": "Xinyi District",
            "category": "Sightseeing",
            "date": "2026-04-02",
            "time": "10:00",
            "notes": "Tower visit",
        },
        headers=headers,
    )
    assert event_res.status_code == 201

    # Adding an event increments trip version: now trip version is 3
    # Try shrinking start_date past existing event (2026-04-03 > 2026-04-02) -> 422
    res = client.put(
        f"/api/v1/trips/{trip1['id']}",
        json={
            "name": "Shrunk Trip",
            "start_date": "2026-04-03",
            "end_date": "2026-04-06",
            "timezone": "Asia/Taipei",
            "description": "Should fail",
            "version": 3,
        },
        headers=headers,
    )
    assert res.status_code == 422

    # DELETE /trips/{id} with wrong version -> 409
    res = client.delete(f"/api/v1/trips/{trip2['id']}?version=99", headers=headers)
    assert res.status_code == 409

    # DELETE /trips/{id} with correct version -> 204
    res = client.delete(f"/api/v1/trips/{trip2['id']}?version=1", headers=headers)
    assert res.status_code == 204
    assert client.get(f"/api/v1/trips/{trip2['id']}").status_code == 404


def test_event_crud_places_and_next_edges(travel_app):
    client, auth, _repo, _, _ = travel_app
    token, csrf, _user_id = sign_in(auth)
    client.cookies.set("travelmemo_session", token)
    headers = {"X-CSRF-Token": csrf}

    trip = client.post(
        "/api/v1/trips",
        json={
            "name": "Tokyo Trip",
            "start_date": "2026-10-01",
            "end_date": "2026-10-05",
            "timezone": "Asia/Tokyo",
            "description": "Tokyo exploration",
        },
        headers=headers,
    ).json()
    trip_id = trip["id"]

    # 1. Create first event on 2026-10-02 without place_id
    ev1 = client.post(
        f"/api/v1/trips/{trip_id}/events",
        json={
            "place_name": "Senso-ji",
            "city": "Tokyo",
            "address": "Asakusa",
            "category": "Temple",
            "date": "2026-10-02",
            "time": "09:00",
            "notes": "Morning visit",
        },
        headers=headers,
    ).json()
    assert ev1["position"] == 0
    assert ev1["version"] == 1
    place1_id = ev1["place_id"]

    # 2. Create second event on 2026-10-02 (same date): must append after ev1
    ev2 = client.post(
        f"/api/v1/trips/{trip_id}/events",
        json={
            "place_name": "Tokyo Skytree",
            "city": "Tokyo",
            "address": "Oshiage",
            "category": "Sightseeing",
            "date": "2026-10-02",
            "time": None,  # Unknown time remains null
            "notes": "Afternoon tower",
        },
        headers=headers,
    ).json()
    assert ev2["position"] == 1
    assert ev2["time"] is None

    # Check NEXT edge: ev1 -> ev2
    detail = client.get(f"/api/v1/trips/{trip_id}").json()
    assert [e["id"] for e in detail["events"]] == [ev1["id"], ev2["id"]]
    assert detail["next_edges"] == [{"from_id": ev1["id"], "to_id": ev2["id"]}]

    # 3. Create third event on 2026-10-01 (earlier date): inserted before ev1
    ev3 = client.post(
        f"/api/v1/trips/{trip_id}/events",
        json={
            "place_name": "Narita Airport",
            "city": "Narita",
            "address": "Chiba",
            "category": "Transport",
            "date": "2026-10-01",
            "time": "14:00",
            "notes": "Arrival",
        },
        headers=headers,
    ).json()
    assert ev3["position"] == 0

    # NEXT edges must now be: ev3 -> ev1 -> ev2
    detail = client.get(f"/api/v1/trips/{trip_id}").json()
    assert [e["id"] for e in detail["events"]] == [ev3["id"], ev1["id"], ev2["id"]]
    assert detail["next_edges"] == [
        {"from_id": ev3["id"], "to_id": ev1["id"]},
        {"from_id": ev1["id"], "to_id": ev2["id"]},
    ]

    # 4. Explicit Place reuse: create fourth event using place1_id (Senso-ji)
    ev4 = client.post(
        f"/api/v1/trips/{trip_id}/events",
        json={
            "place_id": place1_id,
            "place_name": "Ignored Name",  # authoritative place fields must win
            "city": "Ignored City",
            "address": "Ignored Address",
            "category": "Temple",
            "date": "2026-10-03",
            "notes": "Revisiting Senso-ji",
        },
        headers=headers,
    ).json()
    assert ev4["place_id"] == place1_id
    assert ev4["place_name"] == "Senso-ji"
    assert ev4["city"] == "Tokyo"
    assert ev4["address"] == "Asakusa"

    # Verify GET /places only has distinct places
    places = client.get("/api/v1/places").json()["items"]
    # Senso-ji, Skytree, Narita -> 3 distinct places created so far
    place_ids = {p["id"] for p in places}
    assert place1_id in place_ids
    assert len(places) == 3

    # 5. Editing event without place_id creates fresh Place rather than mutate existing
    ev4_updated = client.put(
        f"/api/v1/events/{ev4['id']}",
        json={
            "place_id": None,
            "place_name": "Senso-ji Night",
            "city": "Tokyo",
            "address": "Asakusa Street",
            "category": "Temple",
            "date": "2026-10-03",
            "time": "20:00",
            "notes": "Night stroll",
            "version": 1,
        },
        headers=headers,
    ).json()
    assert ev4_updated["version"] == 2
    assert ev4_updated["place_id"] != place1_id
    # Original place1 must remain untouched
    original_place = client.get("/api/v1/places").json()["items"]
    p1 = next(p for p in original_place if p["id"] == place1_id)
    assert p1["name"] == "Senso-ji"

    # 6. Edit event date change moves it to the end of the new date group
    # Currently order: ev3(10-01), ev1(10-02), ev2(10-02), ev4(10-03)
    # Move ev3 from 10-01 to 10-02: must go to END of 10-02 group, so: ev1(10-02), ev2(10-02), ev3(10-02), ev4(10-03)
    ev3_updated = client.put(
        f"/api/v1/events/{ev3['id']}",
        json={
            "place_name": ev3["place_name"],
            "city": ev3["city"],
            "address": ev3["address"],
            "category": ev3["category"],
            "date": "2026-10-02",
            "time": ev3["time"],
            "notes": "Delayed arrival",
            "version": 1,
        },
        headers=headers,
    ).json()
    assert ev3_updated["version"] == 2
    detail = client.get(f"/api/v1/trips/{trip_id}").json()
    assert [e["id"] for e in detail["events"]] == [ev1["id"], ev2["id"], ev3["id"], ev4["id"]]
    assert detail["next_edges"] == [
        {"from_id": ev1["id"], "to_id": ev2["id"]},
        {"from_id": ev2["id"], "to_id": ev3["id"]},
        {"from_id": ev3["id"], "to_id": ev4["id"]},
    ]

    # 7. Same-day reordering via PUT /trips/{id}/event-order
    # Swap ev1 and ev2 (both on 10-02)
    current_trip_version = detail["trip"]["version"]
    new_order = [ev2["id"], ev1["id"], ev3["id"], ev4["id"]]
    reorder_res = client.put(
        f"/api/v1/trips/{trip_id}/event-order",
        json={"version": current_trip_version, "event_ids": new_order},
        headers=headers,
    )
    assert reorder_res.status_code == 200
    reorder_detail = reorder_res.json()
    assert [e["id"] for e in reorder_detail["events"]] == new_order
    assert reorder_detail["next_edges"][0] == {"from_id": ev2["id"], "to_id": ev1["id"]}
    assert reorder_detail["trip"]["version"] == current_trip_version + 1

    # Cross-date reorder attempt: placing ev4 (10-03) before ev1 (10-02) -> 422
    bad_order = [ev4["id"], ev2["id"], ev1["id"], ev3["id"]]
    res = client.put(
        f"/api/v1/trips/{trip_id}/event-order",
        json={"version": reorder_detail["trip"]["version"], "event_ids": bad_order},
        headers=headers,
    )
    assert res.status_code == 422

    # Incomplete list -> 422
    res = client.put(
        f"/api/v1/trips/{trip_id}/event-order",
        json={"version": reorder_detail["trip"]["version"], "event_ids": [ev2["id"], ev1["id"]]},
        headers=headers,
    )
    assert res.status_code == 422

    # 8. Delete event: deletes event, preserves Place, rebuilds NEXT
    del_res = client.delete(f"/api/v1/events/{ev1['id']}?version=1", headers=headers)
    assert del_res.status_code == 204
    detail = client.get(f"/api/v1/trips/{trip_id}").json()
    assert [e["id"] for e in detail["events"]] == [ev2["id"], ev3["id"], ev4["id"]]
    assert detail["next_edges"] == [
        {"from_id": ev2["id"], "to_id": ev3["id"]},
        {"from_id": ev3["id"], "to_id": ev4["id"]},
    ]
    # Place of ev1 is still retained!
    places_after = client.get("/api/v1/places").json()["items"]
    assert any(p["id"] == place1_id for p in places_after)


def test_cross_owner_isolation(travel_app):
    client, auth, _repo, _, _ = travel_app

    # Alice creates a trip and an event
    token_alice, csrf_alice, _alice_id = sign_in(auth, "alice@example.com", "user-alice")
    client.cookies.set("travelmemo_session", token_alice)
    headers_alice = {"X-CSRF-Token": csrf_alice}

    trip_alice = client.post(
        "/api/v1/trips",
        json={
            "name": "Alice Private Trip",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "timezone": "Asia/Taipei",
            "description": "Secret",
        },
        headers=headers_alice,
    ).json()

    ev_alice = client.post(
        f"/api/v1/trips/{trip_alice['id']}/events",
        json={
            "place_name": "Alice Hideout",
            "city": "Secret City",
            "address": "Secret Rd",
            "category": "Private",
            "date": "2026-08-02",
        },
        headers=headers_alice,
    ).json()

    # Bob signs in
    token_bob, csrf_bob, _bob_id = sign_in(auth, "bob@example.com", "user-bob")
    client.cookies.set("travelmemo_session", token_bob)
    headers_bob = {"X-CSRF-Token": csrf_bob}

    # Bob lists trips: empty
    assert client.get("/api/v1/trips").json()["items"] == []

    # Bob accesses Alice's trip -> 404
    assert client.get(f"/api/v1/trips/{trip_alice['id']}").status_code == 404

    # Bob tries to mutate Alice's trip -> 404
    res = client.put(
        f"/api/v1/trips/{trip_alice['id']}",
        json={
            "name": "Hacked",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "timezone": "Asia/Taipei",
            "description": "",
            "version": 1,
        },
        headers=headers_bob,
    )
    assert res.status_code == 404

    # Bob tries to delete Alice's trip -> 404
    assert (
        client.delete(
            f"/api/v1/trips/{trip_alice['id']}?version=1", headers=headers_bob
        ).status_code
        == 404
    )

    # Bob tries to create event in Alice's trip -> 404
    res = client.post(
        f"/api/v1/trips/{trip_alice['id']}/events",
        json={
            "place_name": "Invasion",
            "city": "City",
            "address": "Addr",
            "category": "Cat",
            "date": "2026-08-02",
        },
        headers=headers_bob,
    )
    assert res.status_code == 404

    # Bob tries to edit or delete Alice's event -> 404
    res = client.put(
        f"/api/v1/events/{ev_alice['id']}",
        json={
            "place_name": "Mutated",
            "city": "City",
            "address": "Addr",
            "category": "Cat",
            "date": "2026-08-02",
            "version": 1,
        },
        headers=headers_bob,
    )
    assert res.status_code == 404
    assert (
        client.delete(f"/api/v1/events/{ev_alice['id']}?version=1", headers=headers_bob).status_code
        == 404
    )

    # Bob lists places: empty
    assert client.get("/api/v1/places").json()["items"] == []

    # Bob tries to reuse Alice's place_id -> 404
    bob_trip = client.post(
        "/api/v1/trips",
        json={
            "name": "Bob Trip",
            "start_date": "2026-09-01",
            "end_date": "2026-09-05",
            "timezone": "Asia/Taipei",
            "description": "",
        },
        headers=headers_bob,
    ).json()

    res = client.post(
        f"/api/v1/trips/{bob_trip['id']}/events",
        json={
            "place_id": ev_alice["place_id"],
            "place_name": "Stealing Place",
            "city": "City",
            "address": "Addr",
            "category": "Cat",
            "date": "2026-09-02",
        },
        headers=headers_bob,
    )
    assert res.status_code == 404
