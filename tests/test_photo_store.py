"""Unit tests for backend/photo_store.py (MemoryPhotoStore and Neo4jPhotoStore)."""

from unittest.mock import MagicMock

from backend.photo_store import MemoryPhotoStore, Neo4jPhotoStore


def test_album_binding_updates_search_eligibility_after_analysis_and_during_claim():
    store = MemoryPhotoStore()
    store.create('owner', {'id': 'photo', 'status': 'ready', 'searchable': False,
                           'embedding_status': 'completed', 'embedding_version': 1})
    store.bind('owner', 'photo', 'conversation', 'chat')
    assert store.get('owner', 'photo')['searchable'] is False
    store.bind('owner', 'photo', 'trip', 'trip')
    assert store.get('owner', 'photo')['searchable'] is True
    store.unbind('owner', 'photo', 'trip', 'trip')
    assert store.get('owner', 'photo')['searchable'] is False

    current = store.get('owner', 'photo')
    updated = store.update('owner', 'photo', current['version'], {'status': 'pending'})
    assert store.claim('owner', 'photo', updated['version'])
    store.bind('owner', 'photo', 'event', 'event', trip_id='trip')
    assert store.finish_analysis('owner', 'photo', updated['version'], {},
                                 extra_fields={'searchable': False})
    assert store.get('owner', 'photo')['searchable'] is True


def test_memory_store_crud():
    store = MemoryPhotoStore()
    record = {
        "id": "p1",
        "caption": "A sunset",
        "version": 1,
        "width": 100,
        "height": 100,
        "size_bytes": 500,
        "thumbnail_size_bytes": 100,
        "created_at": "2026-11-17T12:00:00Z",
    }
    created = store.create("user1", record)
    assert created["id"] == "p1"
    assert created["owner_id"] == "user1"

    # Get
    assert store.get("user1", "p1") is not None
    assert store.get("user2", "p1") is None  # Owner isolation
    assert store.get(None, "p1") is not None  # Worker access

    # Update atomic CAS
    # Version mismatch
    assert store.update("user1", "p1", expected_version=99, changes={"caption": "Wrong"}) is None
    # Version match
    updated = store.update("user1", "p1", expected_version=1, changes={"caption": "Updated"})
    assert updated is not None
    assert updated["caption"] == "Updated"
    assert updated["version"] == 2

    # Remove
    assert not store.remove("user2", "p1")
    assert store.remove("user1", "p1")
    assert store.get("user1", "p1") is None


def test_memory_store_bindings_and_filters():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "created_at": "2026-11-17T12:00:00Z",
        "size_bytes": 1000,
        "thumbnail_size_bytes": 200,
    }
    p2 = {
        "id": "p2",
        "created_at": "2026-11-17T13:00:00Z",
        "size_bytes": 2000,
        "thumbnail_size_bytes": 300,
    }
    store.create("user1", p1)
    store.create("user1", p2)

    # Bind
    store.bind("user1", "p1", "trip", "trip-123")
    store.bind("user1", "p1", "event", "event-456", trip_id="trip-123")
    store.bind("user1", "p2", "conversation", "conv-789")

    # Filter by trip_id
    trip_photos = store.list("user1", trip_id="trip-123")
    assert len(trip_photos) == 1
    assert trip_photos[0]["id"] == "p1"

    # Filter by conversation_id
    conv_photos = store.list("user1", conversation_id="conv-789")
    assert len(conv_photos) == 1
    assert conv_photos[0]["id"] == "p2"

    # Unbind
    store.unbind("user1", "p1", "event", "event-456")
    rec = store.get("user1", "p1")
    assert len(rec["bindings"]) == 1
    assert rec["bindings"][0]["kind"] == "trip"


def test_memory_store_covers_and_order():
    store = MemoryPhotoStore()
    p1 = {"id": "p1", "created_at": "2026-11-17T10:00:00Z"}
    p2 = {"id": "p2", "created_at": "2026-11-17T11:00:00Z"}
    p3 = {"id": "p3", "created_at": "2026-11-17T12:00:00Z"}
    for p in (p1, p2, p3):
        store.create("user1", p)
        store.bind("user1", p["id"], "trip", "t1")

    # Cover
    assert store.get_cover("user1", "t1") is None
    store.set_cover("user1", "t1", "p2")
    assert store.get_cover("user1", "t1") == "p2"

    # Order
    store.set_order("user1", "t1", ["p3", "p1", "p2"])
    assert store.get_order("user1", "t1") == ["p3", "p1", "p2"]

    # Listing trip photos should respect order
    listed = store.list("user1", trip_id="t1")
    assert [x["id"] for x in listed] == ["p3", "p1", "p2"]

    # Removing a photo cleans covers and orders
    store.remove("user1", "p2")
    assert store.get_cover("user1", "t1") is None
    assert store.get_order("user1", "t1") == ["p3", "p1"]


def test_memory_store_worker_claim_and_analysis_lifecycle():
    store = MemoryPhotoStore()
    p = {
        "id": "p1",
        "version": 1,
        "status": "pending",
        "created_at": "2026-11-17T12:00:00Z",
    }
    store.create("user1", p)

    # list_pending
    pending = store.list_pending(limit=4)
    assert len(pending) == 1
    assert pending[0]["id"] == "p1"

    # Claim CAS: version mismatch fails
    assert not store.claim("user1", "p1", version=99)

    # Claim CAS: succeeds with version=1
    assert store.claim("user1", "p1", version=1)
    rec = store.get("user1", "p1")
    assert rec["status"] == "processing"
    assert rec["claimed_version"] == 1
    assert rec["version"] == 1  # version NOT incremented by background job

    # Cannot claim again while processing
    assert not store.claim("user1", "p1", version=1)

    # Finish analysis CAS: version mismatch fails
    assert not store.finish_analysis("user1", "p1", expected_version=99, analysis={"summary": "OK"})

    # Finish analysis CAS: version match succeeds with expected_version=1
    analysis_data = {
        "summary": "Beautiful landscape",
        "visible_text": ["Tokyo"],
        "tags": ["nature"],
        "place_candidates": ["Tokyo"],
        "date_candidate": "2024-05-01",
        "uncertainties": [],
    }
    assert store.finish_analysis(
        "user1",
        "p1",
        expected_version=1,
        analysis=analysis_data,
        status="ready",
        extra_fields={
            "search_text": "Tokyo landscape",
            "embedding": [0.1, 0.2],
            "embedding_version": 1,
            "embedding_status": "ready",
            "searchable": True,
        },
    )
    ready_rec = store.get("user1", "p1")
    assert ready_rec["status"] == "ready"
    assert ready_rec["analysis"]["summary"] == "Beautiful landscape"
    assert ready_rec["analysis"]["visible_text"] == ["Tokyo"]
    assert ready_rec["search_text"] == "Tokyo landscape"
    assert ready_rec["embedding_status"] == "ready"
    assert ready_rec["searchable"] is False  # Unbound images are not journal evidence.
    assert ready_rec["analysis_version"] == 1
    assert ready_rec["claimed_version"] is None
    assert ready_rec["version"] == 1  # version NOT incremented by background finish


def test_memory_store_fail_analysis():
    store = MemoryPhotoStore()
    p = {
        "id": "p1",
        "version": 1,
        "status": "pending",
        "created_at": "2026-11-17T12:00:00Z",
    }
    store.create("user1", p)
    store.claim("user1", "p1", version=1)

    assert store.fail_analysis("user1", "p1", expected_version=1, reason_code="timeout")
    rec = store.get("user1", "p1")
    assert rec["status"] == "failed"
    assert rec["failure_reason"] == "timeout"
    assert rec["version"] == 1  # version preserved
    assert rec["failure_reason"] == "timeout"


def test_memory_store_quotas_and_cleanup():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "size_bytes": 100,
        "thumbnail_size_bytes": 20,
        "created_at": "2026-11-17T10:00:00Z",
        "bindings": [],
    }
    p2 = {
        "id": "p2",
        "size_bytes": 200,
        "thumbnail_size_bytes": 30,
        "created_at": "2026-11-17T12:00:00Z",
        "bindings": [{"kind": "trip", "target_id": "t1"}],
    }
    store.create("user1", p1)
    store.create("user2", p2)

    assert store.get_user_disk_usage("user1") == 120
    assert store.get_user_disk_usage("user2") == 230
    assert store.get_global_disk_usage() == 350

    # list_expired_unbound
    cutoff = "2026-11-17T11:00:00Z"
    expired = store.list_expired_unbound(cutoff)
    assert len(expired) == 1
    assert expired[0]["id"] == "p1"

    # recover_stuck_jobs
    p3 = {
        "id": "p3",
        "status": "processing",
        "claimed_at": 1000.0,
        "version": 2,
    }
    store.create("user1", p3)
    recovered = store.recover_stuck_jobs(timeout_seconds=300, now=1400.0)
    assert len(recovered) == 1
    assert recovered[0]["id"] == "p3"
    rec3 = store.get("user1", "p3")
    assert rec3["status"] == "pending"


def test_neo4j_photo_store_mock():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    store = Neo4jPhotoStore(mock_driver, database="neo4j")
    store.initialize()
    assert mock_session.run.call_count >= 4

    # Test create
    store.create("u1", {"id": "p1", "version": 1, "caption": "Test"})
    assert mock_session.run.called

    # Test get cover / set cover
    mock_session.run.return_value.single.return_value = {"cover_id": "p1"}
    cover = store.get_cover("u1", "t1")
    assert cover == "p1"

    store.set_cover("u1", "t1", "p2")
    assert mock_session.run.called


def test_memory_store_remove_atomic_guards():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "version": 1,
        "bindings": [{"kind": "trip", "target_id": "t1"}],
    }
    store.create("user1", p1)

    # 1. only_if_unbound fails because photo has bindings
    assert not store.remove("user1", "p1", expected_version=1, only_if_unbound=True)
    assert store.get("user1", "p1") is not None

    # 2. expected_version mismatch fails
    store.photos["p1"]["bindings"] = []
    assert not store.remove("user1", "p1", expected_version=99, only_if_unbound=True)
    assert store.get("user1", "p1") is not None

    # 3. Matching version and unbound succeeds
    assert store.remove("user1", "p1", expected_version=1, only_if_unbound=True)
    assert store.get("user1", "p1") is None


def test_rebinding_preserves_ready_embedding_and_advances_embedding_version():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "version": 1,
        "status": "ready",
        "embedding_status": "completed",
        "embedding": [0.1, 0.2, 0.3],
        "embedding_version": 1,
        "search_text": "sample text",
        "bindings": [],
    }
    store.create("user1", p1)

    # Bind to trip: embedding remains completed, version bumps to 2, embedding_version advances to 2
    res = store.bind("user1", "p1", "trip", "t1")
    assert res is not None
    assert res["version"] == 2
    assert res["embedding_status"] == "completed"
    assert res["embedding"] == [0.1, 0.2, 0.3]
    assert res["embedding_version"] == 2

    # Bind to event: embedding remains completed, version bumps to 3, embedding_version advances to 3
    res2 = store.bind("user1", "p1", "event", "e1", trip_id="t1")
    assert res2 is not None
    assert res2["version"] == 3
    assert res2["embedding_status"] == "completed"
    assert res2["embedding_version"] == 3

    # Unbind event: embedding remains completed, version bumps to 4, embedding_version advances to 4
    unbind_res = store.unbind("user1", "p1", "event", "e1", cascade_if_unbound=True)
    assert unbind_res["deleted"] is False
    photo = unbind_res["photo"]
    assert photo["version"] == 4
    assert photo["embedding_status"] == "completed"
    assert photo["embedding_version"] == 4


def test_store_claim_bind_finish_aligns_embedding_version():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "version": 1,
        "status": "pending",
        "bindings": [],
    }
    store.create("user1", p1)

    # 1. Claim job
    assert store.claim("user1", "p1", version=1)
    rec = store.get("user1", "p1")
    assert rec["status"] == "processing"
    assert rec["claimed_version"] == 1
    assert rec["version"] == 1

    # 2. User binds to trip while analyzing: bumps version to 2
    res = store.bind("user1", "p1", "trip", "t1")
    assert res["version"] == 2
    assert res["status"] == "processing"
    assert res["claimed_version"] == 1  # Claim preserved!

    # 3. Worker finishes analysis with expected_version=1 (claimed version)
    finished = store.finish_analysis(
        "user1",
        "p1",
        expected_version=1,
        analysis={"summary": "Sunrise", "visible_text": []},
        status="ready",
        extra_fields={
            "search_text": "Sunrise",
            "embedding": [0.5, 0.6],
            "embedding_version": 1,
            "embedding_status": "completed",
            "searchable": True,
        },
    )
    assert finished is True

    # 4. Check photo state: ready, analysis_version=2, embedding_version aligned to 2
    rec_finished = store.get("user1", "p1")
    assert rec_finished["status"] == "ready"
    assert rec_finished["version"] == 2
    assert rec_finished["analysis_version"] == 2
    assert rec_finished["claimed_version"] is None
    assert rec_finished["embedding_status"] == "completed"
    assert rec_finished["embedding_version"] == 2

    # 5. Subsequent bind keeps completed embedding valid and advances embedding_version
    res_bind = store.bind("user1", "p1", "event", "e1", trip_id="t1")
    assert res_bind["version"] == 3
    assert res_bind["embedding_status"] == "completed"
    assert res_bind["embedding_version"] == 3
    assert res_bind["embedding_version"] == 3


def test_store_caption_edit_clears_claim_and_protects_stale_caption():
    store = MemoryPhotoStore()
    p1 = {
        "id": "p1",
        "version": 1,
        "status": "pending",
        "caption": "Old caption",
        "bindings": [],
    }
    store.create("user1", p1)

    # Claim job
    assert store.claim("user1", "p1", version=1)

    # User edits caption while analyzing
    updated = store.update("user1", "p1", expected_version=1, changes={"caption": "New caption"})
    assert updated["version"] == 2
    assert updated["status"] == "pending"
    assert updated["claimed_version"] is None

    # Worker finishing analysis with old expected_version=1 MUST be rejected!
    finished = store.finish_analysis(
        "user1",
        "p1",
        expected_version=1,
        analysis={"summary": "Old caption analysis"},
        status="ready",
    )
    assert finished is False

    # Photo remains pending so worker can re-claim and analyze with new caption
    rec = store.get("user1", "p1")
    assert rec["status"] == "pending"
    assert rec["caption"] == "New caption"
