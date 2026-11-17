"""Comprehensive tests for PhotoService and Photo API endpoints."""

import io
import shutil
import tempfile
import time
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.auth import AuthService
from backend.photo_store import MemoryPhotoStore
from backend.photos import PhotoService, create_photo_router
from backend.store import MemoryStore


class DummySettings:
    session_secret = "supersecretkeyatleast32characterslong123456"
    session_days = 7
    cookie_secure = False
    emails: ClassVar[set[str]] = {"tester@example.com"}
    allowed_emails = "tester@example.com"
    otp_seconds = 600
    resend_seconds = 60
    otp_attempts = 5
    ip_hourly_limit = 20
    email_hourly_limit = 5
    verify_ip_hourly_limit = 100
    media_root = "data/test_photos"
    media_user_quota_bytes = 1024 * 1024  # 1 MiB for testing
    media_global_quota_bytes = 2 * 1024 * 1024  # 2 MiB for testing
    media_upload_max_bytes = 512 * 1024  # 512 KiB
    photo_storage_dir = "data/test_photos"
    photo_user_quota_bytes = 1024 * 1024
    photo_global_quota_bytes = 2 * 1024 * 1024
    photo_max_upload_bytes = 512 * 1024


def make_jpeg_bytes(width=100, height=100, color="green") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def temp_storage():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def photo_service(temp_storage):
    settings = DummySettings()
    settings.photo_storage_dir = temp_storage
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store, clock=time.time)
    svc.initialize()
    return svc


def test_photo_service_upload_get_list(photo_service):
    raw = make_jpeg_bytes(200, 150)
    dto = photo_service.upload("user1", raw, "image/jpeg")

    assert dto["id"] is not None
    assert dto["status"] == "pending"
    assert dto["version"] == 1
    assert dto["width"] == 200
    assert dto["height"] == 150
    assert dto["url"] == f"/api/v1/photos/{dto['id']}/content"
    assert dto["thumbnail_url"] == f"/api/v1/photos/{dto['id']}/thumbnail"

    # Get
    fetched = photo_service.get("user1", dto["id"])
    assert fetched is not None
    assert fetched["id"] == dto["id"]

    # Other user cannot access
    assert photo_service.get("user2", dto["id"]) is None

    # List
    items = photo_service.list("user1")
    assert len(items) == 1
    assert items[0]["id"] == dto["id"]
    assert len(photo_service.list("user2")) == 0


def test_photo_service_quota_enforcement(temp_storage):
    settings = DummySettings()
    settings.media_root = temp_storage
    settings.photo_storage_dir = temp_storage
    settings.media_user_quota_bytes = 2000  # Very small quota
    settings.photo_user_quota_bytes = 2000
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)

    raw = make_jpeg_bytes(100, 100)
    store.create("user1", {
        "id": "existing",
        "size_bytes": 1900,
        "thumbnail_size_bytes": 100,
    })

    with pytest.raises(HTTPException) as exc_info:
        svc.upload("user1", raw, "image/jpeg")
    assert exc_info.value.status_code == 413
    assert "使用者相片儲存配額已滿" in exc_info.value.detail


def test_photo_service_global_quota_enforcement(temp_storage):
    settings = DummySettings()
    settings.media_root = temp_storage
    settings.photo_storage_dir = temp_storage
    settings.media_user_quota_bytes = 100000
    settings.photo_user_quota_bytes = 100000
    settings.media_global_quota_bytes = 2000  # Very small global quota
    settings.photo_global_quota_bytes = 2000
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)

    store.create("user_other", {
        "id": "existing",
        "size_bytes": 1900,
        "thumbnail_size_bytes": 100,
    })

    raw = make_jpeg_bytes(100, 100)
    with pytest.raises(HTTPException) as exc_info:
        svc.upload("user1", raw, "image/jpeg")
    assert exc_info.value.status_code == 507
    assert "系統相片儲存空間已滿" in exc_info.value.detail


def test_photo_service_content_paths(photo_service):
    raw = make_jpeg_bytes(100, 100)
    dto = photo_service.upload("user1", raw, "image/jpeg")

    main_path = photo_service.content("user1", dto["id"], thumbnail=False)
    thumb_path = photo_service.content("user1", dto["id"], thumbnail=True)

    assert isinstance(main_path, Path)
    assert main_path.exists()
    assert thumb_path.exists()

    with pytest.raises(HTTPException) as exc_info:
        photo_service.content("user2", dto["id"])
    assert exc_info.value.status_code == 404


def test_photo_service_caption_update_and_retry(photo_service):
    raw = make_jpeg_bytes(100, 100)
    dto = photo_service.upload("user1", raw, "image/jpeg")

    # Version mismatch on update
    with pytest.raises(HTTPException) as exc:
        photo_service.update("user1", dto["id"], version=99, caption="New caption")
    assert exc.value.status_code == 409

    # Valid update
    updated = photo_service.update("user1", dto["id"], version=1, caption="New caption")
    assert updated["caption"] == "New caption"
    assert updated["version"] == 2

    # Retry resets status to pending
    # First simulate failed
    photo_service.store.update("user1", dto["id"], expected_version=2, changes={"status": "failed"})
    retried = photo_service.retry("user1", dto["id"], version=3)
    assert retried["status"] == "pending"
    assert retried["version"] == 4


def test_photo_service_binding_lifecycle_and_cascade_delete(photo_service):
    raw = make_jpeg_bytes(100, 100)
    dto = photo_service.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Bind to trip
    bound = photo_service.bind("user1", pid, "trip", "trip-1")
    assert len(bound["bindings"]) == 1
    assert bound["bindings"][0]["kind"] == "trip"
    assert bound["bindings"][0]["target_id"] == "trip-1"

    # Bind to event
    bound2 = photo_service.bind("user1", pid, "event", "event-1")
    assert len(bound2["bindings"]) == 2

    # Unbind event -> photo still has trip binding, so it is NOT cascade deleted
    photo_service.unbind("user1", pid, "event", "event-1")
    assert photo_service.get("user1", pid) is not None

    # Unbind trip -> 0 bindings remain -> cascade only unreferenced deletes the photo
    photo_service.unbind("user1", pid, "trip", "trip-1")
    assert photo_service.get("user1", pid) is None


def test_photo_service_delete_with_version(photo_service):
    raw = make_jpeg_bytes(100, 100)
    dto = photo_service.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Conflict on wrong version
    with pytest.raises(HTTPException) as exc:
        photo_service.delete("user1", pid, version=99)
    assert exc.value.status_code == 409

    # Delete with correct version
    main_path = photo_service.content("user1", pid)
    assert main_path.exists()

    photo_service.delete("user1", pid, version=1)
    assert not main_path.exists()
    assert photo_service.get("user1", pid) is None


def test_photo_service_ready_evidence(photo_service):
    raw = make_jpeg_bytes(100, 100)
    dto = photo_service.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # When pending -> 409
    with pytest.raises(HTTPException) as exc:
        photo_service.ready_evidence("user1", [pid])
    assert exc.value.status_code == 409

    # Not owned -> 404
    with pytest.raises(HTTPException) as exc:
        photo_service.ready_evidence("user2", [pid])
    assert exc.value.status_code == 404

    # Mark ready
    photo_service.store.claim("user1", pid, version=1)
    photo_service.store.finish_analysis("user1", pid, expected_version=1, analysis={"summary": "Ready photo"})

    evidence = photo_service.ready_evidence("user1", [pid])
    assert len(evidence) == 1
    assert evidence[0]["id"] == pid
    assert evidence[0]["analysis"]["summary"] == "Ready photo"


def test_photo_service_detach_target(photo_service):
    raw = make_jpeg_bytes(100, 100)
    d1 = photo_service.upload("user1", raw, "image/jpeg")
    d2 = photo_service.upload("user1", raw, "image/jpeg")

    photo_service.bind("user1", d1["id"], "trip", "trip-A")
    photo_service.bind("user1", d2["id"], "trip", "trip-A")
    photo_service.bind("user1", d2["id"], "event", "event-B")

    photo_service.detach_target("user1", "trip", "trip-A")

    # d1 had only trip-A, so now it is an orphan and cleaned up
    assert photo_service.get("user1", d1["id"]) is None

    # d2 still had event-B, so it remains
    rec2 = photo_service.get("user1", d2["id"])
    assert rec2 is not None
    assert len(rec2["bindings"]) == 1
    assert rec2["bindings"][0]["kind"] == "event"


def test_photo_service_cleanup(photo_service):
    # Expired unbound (>1h)
    p_unbound = photo_service.upload("user1", make_jpeg_bytes(100, 100), "image/jpeg")
    # Simulate created 2 hours ago
    two_hours_ago = "2020-01-01T00:00:00Z"
    photo_service.store.update("user1", p_unbound["id"], expected_version=1, changes={"created_at": two_hours_ago})

    # Stuck job
    p_stuck = photo_service.upload("user1", make_jpeg_bytes(100, 100), "image/jpeg")
    photo_service.store.claim("user1", p_stuck["id"], version=1)
    # Set claimed_at to 1000s ago
    rec_stuck = photo_service.store.get("user1", p_stuck["id"])
    photo_service.store.update("user1", p_stuck["id"], expected_version=rec_stuck["version"], changes={"claimed_at": time.time() - 1000})

    stats = photo_service.cleanup()
    assert stats["expired_unbound_cleaned"] >= 1
    assert stats["stuck_jobs_recovered"] >= 1

    assert photo_service.get("user1", p_unbound["id"]) is None
    recovered_stuck = photo_service.get("user1", p_stuck["id"])
    assert recovered_stuck["status"] == "pending"


def test_trip_cover_and_ordering(photo_service):
    d1 = photo_service.upload("user1", make_jpeg_bytes(100, 100), "image/jpeg")
    d2 = photo_service.upload("user1", make_jpeg_bytes(100, 100), "image/jpeg")
    photo_service.bind("user1", d1["id"], "trip", "t1")
    photo_service.bind("user1", d2["id"], "trip", "t1")

    # Cover
    assert photo_service.get_trip_cover("user1", "t1") is None
    photo_service.set_trip_cover("user1", "t1", d1["id"])
    assert photo_service.get_trip_cover("user1", "t1") == d1["id"]

    # Order
    ordered = photo_service.set_trip_order("user1", "t1", [d2["id"], d1["id"]])
    assert [x["id"] for x in ordered] == [d2["id"], d1["id"]]
    assert photo_service.get_trip_order("user1", "t1") == [d2["id"], d1["id"]]


# -------------------------------------------------------------
# HTTP Router Integration Tests
# -------------------------------------------------------------

def setup_test_app(temp_storage):
    settings = DummySettings()
    settings.photo_storage_dir = temp_storage
    auth_store = MemoryStore()
    photo_store = MemoryPhotoStore()
    auth = AuthService(settings, auth_store, sender=lambda to, code: None)
    service = PhotoService(settings, photo_store)
    service.initialize()

    # Pre-create authenticated user session
    user = {"id": "test-user-id", "email": "tester@example.com"}
    auth_store.user(user["id"], user["email"])
    session_token = "valid-session-token-12345"
    csrf_token = "valid-csrf-token-12345"
    auth_store.put(
        "session:" + auth.digest(session_token),
        {
            "user": user,
            "csrf_token": csrf_token,
            "expires_at": time.time() + 86400,
        },
    )

    app = FastAPI()
    router = create_photo_router(auth, service, prefix="/api/v1")
    app.include_router(router)

    return app, session_token, csrf_token


def test_http_photo_endpoints(temp_storage):
    app, token, csrf = setup_test_app(temp_storage)
    client = TestClient(app, cookies={"travelmemo_session": token})

    # 1. POST /photos without CSRF -> 403
    raw_img = make_jpeg_bytes(150, 100)
    resp_no_csrf = client.post("/api/v1/photos", content=raw_img, headers={"Content-Type": "image/jpeg"})
    assert resp_no_csrf.status_code == 403

    # 2. POST /photos with CSRF -> 201 PhotoDTO
    resp = client.post(
        "/api/v1/photos",
        content=raw_img,
        headers={"Content-Type": "image/jpeg", "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201
    dto = resp.json()
    assert dto["id"] is not None
    assert dto["status"] == "pending"
    pid = dto["id"]

    # 3. GET /photos
    list_resp = client.get("/api/v1/photos")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1

    # 4. GET /photos/{id}
    get_resp = client.get(f"/api/v1/photos/{pid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == pid

    # 5. GET /photos/{id}/content and /thumbnail
    content_resp = client.get(f"/api/v1/photos/{pid}/content")
    assert content_resp.status_code == 200
    assert content_resp.headers["content-type"] == "image/webp"

    thumb_resp = client.get(f"/api/v1/photos/{pid}/thumbnail")
    assert thumb_resp.status_code == 200
    assert thumb_resp.headers["content-type"] == "image/webp"

    # 6. PATCH /photos/{id}
    patch_resp = client.patch(
        f"/api/v1/photos/{pid}",
        json={"version": 1, "caption": "Trip memory"},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["caption"] == "Trip memory"
    assert patch_resp.json()["version"] == 2

    # 7. POST /photos/{id}/bindings
    bind_resp = client.post(
        f"/api/v1/photos/{pid}/bindings",
        json={"kind": "trip", "target_id": "trip-99"},
        headers={"X-CSRF-Token": csrf},
    )
    assert bind_resp.status_code == 200
    assert len(bind_resp.json()["bindings"]) == 1

    # 8. PUT & GET /trips/{trip_id}/photos/cover
    cover_put = client.put(
        "/api/v1/trips/trip-99/photos/cover",
        json={"photo_id": pid},
        headers={"X-CSRF-Token": csrf},
    )
    assert cover_put.status_code == 200
    assert cover_put.json()["photo_id"] == pid

    cover_get = client.get("/api/v1/trips/trip-99/photos/cover")
    assert cover_get.status_code == 200
    assert cover_get.json()["photo_id"] == pid

    # 9. PUT /trips/{trip_id}/photos/order
    order_put = client.put(
        "/api/v1/trips/trip-99/photos/order",
        json={"photo_ids": [pid]},
        headers={"X-CSRF-Token": csrf},
    )
    assert order_put.status_code == 200
    assert len(order_put.json()["items"]) == 1

    # 10. POST /photos/{id}/retry
    retry_resp = client.post(
        f"/api/v1/photos/{pid}/retry",
        json={"version": bind_resp.json()["version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "pending"

    # 11. DELETE /photos/{id}
    del_resp = client.delete(
        f"/api/v1/photos/{pid}?version={retry_resp.json()['version']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_resp.status_code == 204

    # Confirm 404 after deletion
    assert client.get(f"/api/v1/photos/{pid}").status_code == 404


def test_reconcile_stale_bindings_in_cleanup(temp_storage):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_upload_max_bytes=10 * 1024 * 1024,
        media_max_pixels=50_000_000,
        media_max_dimension=2048,
        media_image_max_bytes=512 * 1024,
        media_thumbnail_max_bytes=64 * 1024,
        media_user_quota_bytes=250 * 1024 * 1024,
        media_global_quota_bytes=5 * 1024 * 1024 * 1024,
        media_poll_seconds=3.0,
        media_orphan_seconds=3600,
    )

    class MockTravelRepo:
        def __init__(self):
            self.trips = {"t1": {"id": "t1"}}

        def get_trip(self, owner, tid):
            return self.trips.get(tid)

    class MockConvStore:
        def __init__(self):
            self.convs = {}

        def get_conversation(self, owner, cid):
            return self.convs.get(cid)

    travel_repo = MockTravelRepo()
    conv_store = MockConvStore()
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store, travel_repository=travel_repo, conversation_store=conv_store)
    svc.initialize()

    # Upload photo
    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Bind to t1 and conv1 (conv1 is already deleted / does not exist)
    svc.bind("user1", pid, "trip", "t1")
    # artificially add stale binding to conv1
    store.bind("user1", pid, "conversation", "conv1")

    # Before cleanup, photo has 2 bindings
    rec = store.get("user1", pid)
    assert len(rec["bindings"]) == 2

    # Run cleanup
    res = svc.cleanup()
    assert res["stale_bindings_reconciled"] >= 1

    # Stale binding was pruned, valid binding t1 preserved
    rec_after = store.get("user1", pid)
    assert rec_after is not None
    assert len(rec_after["bindings"]) == 1
    assert rec_after["bindings"][0]["kind"] == "trip"

    # Now delete trip t1 from travel repo
    travel_repo.trips.clear()
    res2 = svc.cleanup()
    assert res2["stale_bindings_reconciled"] >= 1
    # Because all bindings to targets are now gone, photo is an orphan and cleaned up
    assert svc.get("user1", pid) is None


def test_finish_analysis_does_not_increment_version(temp_storage):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)
    svc.initialize()

    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]
    assert dto["version"] == 1

    # Worker B claims with version 1
    assert store.claim("user1", pid, version=1)

    # Worker B finishes analysis with expected_version 1
    analysis_data = {
        "summary": "Photo summary",
        "visible_text": ["看板文字"],
        "tags": ["travel"],
        "place_candidates": ["Kyoto"],
        "date_candidate": "2024-04-10",
        "uncertainties": [],
    }
    extra_fields = {
        "search_text": "看板文字 travel Kyoto",
        "embedding": [0.1, 0.2, 0.3],
        "embedding_version": 1,
        "embedding_status": "completed",
        "searchable": True,
    }
    assert store.finish_analysis(
        "user1",
        pid,
        expected_version=1,
        analysis=analysis_data,
        status="ready",
        extra_fields=extra_fields,
    )

    # Version should STILL be 1!
    ready_dto = svc.get("user1", pid)
    assert ready_dto["version"] == 1
    assert ready_dto["analysis_version"] == 1
    assert ready_dto["status"] == "ready"
    assert ready_dto["analysis"]["visible_text"] == ["看板文字"]

    # User edits caption using version 1 - it succeeds because version wasn't bumped!
    updated_dto = svc.update("user1", pid, version=1, caption="User added caption")
    assert updated_dto["version"] == 2
    assert updated_dto["caption"] == "User added caption"
    # Existing analysis is preserved (not reset)
    assert updated_dto["analysis"]["summary"] == "Photo summary"
    # embedding_status set to pending for background search re-index without forcing new vision
    rec = store.get("user1", pid)
    assert rec["embedding_status"] == "pending"


def test_race1_concurrent_bind_during_unbind_prevents_deletion(temp_storage):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)
    svc.initialize()

    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Bind to t1 and t2
    svc.bind("user1", pid, "trip", "t1")
    svc.bind("user1", pid, "trip", "t2")

    # Unbind t1: photo still bound to t2, must NOT be deleted
    svc.unbind("user1", pid, "trip", "t1")
    rem = svc.get("user1", pid)
    assert rem is not None
    assert len(rem["bindings"]) == 1
    assert rem["bindings"][0]["target_id"] == "t2"

    # Now verify atomic store.remove guard: if a photo is bound, only_if_unbound=True refuses deletion
    assert not store.remove("user1", pid, expected_version=rem["version"], only_if_unbound=True)
    assert svc.get("user1", pid) is not None

    # Unbind last binding t2: cascade delete removes photo
    svc.unbind("user1", pid, "trip", "t2")
    assert svc.get("user1", pid) is None


def test_race2_concurrent_bind_during_cleanup_does_not_overwrite_or_delete(temp_storage):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )

    class MockTravelRepo:
        def __init__(self):
            self.trips = {}  # t1 is deleted / does not exist

        def get_trip(self, owner, tid):
            return self.trips.get(tid)

    class MockConvStore:
        def __init__(self):
            self.convs = {"conv1": {"id": "conv1"}}

        def get_conversation(self, owner, cid):
            return self.convs.get(cid)

    travel_repo = MockTravelRepo()
    conv_store = MockConvStore()
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store, travel_repository=travel_repo, conversation_store=conv_store)
    svc.initialize()

    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Initial state: photo is bound to t1 (which is deleted)
    store.bind("user1", pid, "trip", "t1")
    initial_rec = store.get("user1", pid)
    assert len(initial_rec["bindings"]) == 1
    assert initial_rec["version"] == 2

    # Intercept travel_repo.get_trip so that when cleanup checks t1,
    # a concurrent request binds "conv1" to this photo BEFORE cleanup applies CAS update!
    concurrent_bound = False
    orig_get_trip = travel_repo.get_trip

    def get_trip_with_race_hook(owner, tid):
        nonlocal concurrent_bound
        if not concurrent_bound:
            concurrent_bound = True
            # Simulate concurrent user action: bind photo to conv1
            store.bind("user1", pid, "conversation", "conv1")
        return orig_get_trip(owner, tid)

    travel_repo.get_trip = get_trip_with_race_hook

    # Run cleanup:
    # 1. Cleanup reads snapshot at version 2 with [t1]
    # 2. Hook triggers: concurrent bind runs, version becomes 3, bindings become [t1, conv1]
    # 3. Cleanup tries CAS update with expected_version=2 -> FAILS due to version mismatch!
    # 4. Cleanup CAS retry loop reads fresh record (version 3), evaluates [t1 (deleted), conv1 (valid)]
    # 5. Cleanup successfully preserves conv1 and reconciles stale t1!
    res = svc.cleanup()
    assert res["stale_bindings_reconciled"] >= 1

    # Photo must NOT be deleted!
    photo_after = svc.get("user1", pid)
    assert photo_after is not None
    # conv1 binding must be intact and NOT overwritten by stale snapshot!
    bindings = photo_after["bindings"]
    assert len(bindings) == 1
    assert bindings[0]["kind"] == "conversation"
    assert bindings[0]["target_id"] == "conv1"


def test_explicit_delete_cas_expected_version(temp_storage):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)
    svc.initialize()

    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]
    assert dto["version"] == 1

    # Simulate concurrent edit: caption update bumps version to 2
    svc.update("user1", pid, version=1, caption="Updated by someone else")
    current_rec = svc.get("user1", pid)
    assert current_rec["version"] == 2

    # Client tries to delete with old version 1 -> 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        svc.delete("user1", pid, version=1)
    assert exc_info.value.status_code == 409

    # Photo and physical files must still exist!
    assert svc.get("user1", pid) is not None
    assert svc.content("user1", pid).exists()

    # Client deletes with matching version 2 -> succeeds
    svc.delete("user1", pid, version=2)
    assert svc.get("user1", pid) is None
    with pytest.raises(HTTPException) as exc_info:
        svc.content("user1", pid)
    assert exc_info.value.status_code == 404


def test_service_claim_bind_finish_race_and_ready_embedding(temp_storage):
    """Verifies that binding-only updates while background analyzing do not get photo stuck.

    Claim -> bind -> finish succeeds, aligns embedding_version, and subsequent bind keeps embedding ready.
    """
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)
    svc.initialize()

    # 1. Upload photo: version 1, status pending
    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]
    assert dto["version"] == 1
    assert dto["status"] == "pending"

    # 2. Worker claims job with version 1
    assert store.claim("user1", pid, version=1)
    proc_dto = svc.get("user1", pid)
    assert proc_dto["status"] == "processing"

    # 3. User binds photo to album/trip while background analyzing: bumps version to 2
    bound_dto = svc.bind("user1", pid, "trip", "trip-101")
    assert bound_dto["version"] == 2
    assert bound_dto["status"] == "processing"  # Still processing

    # 4. Worker finishes vision analysis with claimed expected_version=1
    analysis_data = {
        "summary": "Kyoto Temple at twilight",
        "visible_text": ["清水寺"],
        "tags": ["temple", "japan"],
        "place_candidates": ["Kyoto"],
        "date_candidate": "2024-04-12",
        "uncertainties": [],
    }
    extra_fields = {
        "search_text": "Kyoto Temple 清水寺 twilight japan",
        "embedding": [0.12, 0.34, 0.56],
        "embedding_version": 1,
        "embedding_status": "completed",
        "searchable": True,
    }
    finished = store.finish_analysis(
        "user1",
        pid,
        expected_version=1,
        analysis=analysis_data,
        status="ready",
        extra_fields=extra_fields,
    )
    assert finished is True  # Must NOT fail or leave photo stuck!

    # 5. Preview GET: photo is ready (NOT stuck in processing!)
    ready_dto = svc.get("user1", pid)
    assert ready_dto["status"] == "ready"
    assert ready_dto["version"] == 2
    assert ready_dto["analysis_version"] == 2
    assert ready_dto["analysis"]["visible_text"] == ["清水寺"]

    # Verify embedding is aligned to current version 2
    internal_rec = store.get("user1", pid)
    assert internal_rec["embedding_status"] == "completed"
    assert internal_rec["embedding_version"] == 2
    assert internal_rec["claimed_version"] is None

    # 6. Subsequent bind to event preserves ready embedding and advances embedding_version to 3
    bound_event = svc.bind("user1", pid, "event", "event-202")
    assert bound_event["version"] == 3
    assert bound_event["status"] == "ready"

    internal_after = store.get("user1", pid)
    assert internal_after["embedding_status"] == "completed"
    assert internal_after["embedding_version"] == 3


def test_service_caption_edit_clears_claim_and_protects_stale_caption(temp_storage):
    """Verifies that caption edit while analyzing clears claim and resets to pending.

    Worker finish with old claimed version is rejected, preventing stale caption overwriting.
    """
    from types import SimpleNamespace

    settings = SimpleNamespace(
        media_root=temp_storage,
        media_orphan_seconds=3600,
    )
    store = MemoryPhotoStore()
    svc = PhotoService(settings, store)
    svc.initialize()

    raw = make_jpeg_bytes(100, 100)
    dto = svc.upload("user1", raw, "image/jpeg")
    pid = dto["id"]

    # Worker claims
    assert store.claim("user1", pid, version=1)

    # User edits caption while analyzing
    updated = svc.update("user1", pid, version=1, caption="User new caption")
    assert updated["version"] == 2
    assert updated["caption"] == "User new caption"
    assert updated["status"] == "pending"  # Reset to pending for re-analysis/indexing

    # Worker finishes analysis with old version 1 -> rejected!
    finished = store.finish_analysis(
        "user1",
        pid,
        expected_version=1,
        analysis={"summary": "Old stale analysis"},
        status="ready",
    )
    assert finished is False

    # Photo remains pending with new caption intact
    rec = svc.get("user1", pid)
    assert rec["status"] == "pending"
    assert rec["caption"] == "User new caption"
