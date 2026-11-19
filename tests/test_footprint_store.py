"""Private draft ownership, job recovery, and atomic journal insertion."""

import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.footprint_store import FootprintStore
from backend.travel_store import (
    MemoryTravelRepository,
    TravelConflictError,
    TravelNotFoundError,
    TravelValidationError,
)


@pytest.fixture
def draft_store():
    repo = MemoryTravelRepository()
    trip = repo.create_trip("owner", {"name": "Trip", "start_date": "2026-01-01", "end_date": "2026-01-03"})
    store = FootprintStore(repo)
    draft = store.create("owner", trip["id"], "2026-01-01", "River then cafe")
    return repo, trip, store, draft


def item(name="River", date="2026-01-01"):
    return {"place_name": name, "date": date, "category": "景點", "city": "", "address": "", "notes": "", "time": None}


def test_generation_is_idempotent_and_recovery_rejects_stale_finish(draft_store):
    repo, trip, store, draft = draft_store
    args = ("owner", trip["id"], draft["id"])
    queued = store.queue(*args, 1, "generation", "2026-01-01", "River")
    assert queued["version"] == 2 and queued["status"] == "queued"
    assert store.queue(*args, 1, "generation", "2026-01-01", "River") == queued
    with pytest.raises(TravelConflictError):
        store.queue(*args, 2, "generation", "2026-01-01", "Cafe")
    assert store.claim(*args, queued["version"], "generation")["status"] == "running"
    assert store.claim(*args, queued["version"], "generation") is None
    store.recover()
    assert store.pending()[0]["status"] == "queued"
    assert store.finish(*args, 2, "generation", [item()]) is None
    assert store.claim(*args, 2, "generation")
    ready = store.finish(*args, 2, "generation", [item()])
    assert ready["version"] == 3 and ready["status"] == "ready"
    assert not repo.get_trip_detail("owner", trip["id"])["events"]
    updated = store.update(*args, 3, {"items": [item("Cafe")]})
    assert updated["version"] == 4
    assert store.finish(*args, 2, "generation", [item("Stale")]) is None
    assert store.get(*args)["items"][0]["place_name"] == "Cafe"


def test_failed_generation_preserves_previous_draft_and_blocks_busy_edits(draft_store):
    _, trip, store, draft = draft_store
    args = ("owner", trip["id"], draft["id"])
    saved = store.update(*args, 1, {"items": [item()]})
    queued = store.queue(*args, saved["version"], "generation", "2026-01-01", "More")
    with pytest.raises(TravelConflictError):
        store.update(*args, queued["version"], {"items": []})
    store.claim(*args, queued["version"], "generation")
    failed = store.finish(*args, queued["version"], "generation", [], error="unavailable")
    assert failed["items"] == [item()]
    assert failed["status"] == "failed"


def test_owner_trip_scope_and_discard_during_generation(draft_store):
    _, trip, store, draft = draft_store
    for operation in (lambda: store.get("friend", trip["id"], draft["id"]),
                      lambda: store.latest("friend", trip["id"]),
                      lambda: store.update("friend", trip["id"], draft["id"], 1, {"text": "attack"})):
        with pytest.raises(TravelNotFoundError):
            operation()
    args = ("owner", trip["id"], draft["id"])
    queued = store.queue(*args, 1, "generation", "2026-01-01", "River")
    store.claim(*args, queued["version"], "generation")
    store.discard(*args, queued["version"])
    assert store.finish(*args, queued["version"], "generation", [item()]) is None
    assert store.latest("owner", trip["id"]) is None


def test_atomic_commit_preserves_old_order_and_separate_repeat_visits(draft_store):
    repo, trip, store, draft = draft_store
    old = repo.create_event("owner", trip["id"], item("Existing"))
    current_trip = repo.get_trip("owner", trip["id"])
    rows = [item("Cafe", "2026-01-02"), item("River"), item("River")]
    result = store.commit("owner", trip["id"], draft["id"], 1, current_trip["version"], rows, "commit")
    assert result["trip_version"] == current_trip["version"] + 1
    detail = repo.get_trip_detail("owner", trip["id"])
    assert [e["place_name"] for e in detail["events"]] == ["Existing", "River", "River", "Cafe"]
    assert detail["events"][0]["id"] == old["id"]
    rivers = [e for e in detail["events"] if e["place_name"] == "River"]
    assert rivers[0]["id"] != rivers[1]["id"]
    assert rivers[0]["place_id"] != rivers[1]["place_id"]
    assert len(detail["next_edges"]) == 3
    assert [e["position"] for e in result["events"]] == [3, 1, 2]
    assert all(repo.events[e["id"]]["embedding_status"] == "pending" for e in result["events"])
    assert store.commit("owner", trip["id"], draft["id"], 1, 1, rows, "different-request") == result
    assert len(repo.events) == 4
    assert store.latest("owner", trip["id"]) is None


def test_batch_failure_rolls_back_all_places_categories_positions_and_version(draft_store, monkeypatch):
    repo, trip, store, draft = draft_store
    repo.create_event("owner", trip["id"], item("Existing"))
    snapshot = copy.deepcopy((repo.trips, repo.events, repo.places, repo.categories))
    original = repo.create_event
    calls = 0
    def fail_second(*args):
        nonlocal calls
        calls += 1
        result = original(*args)
        if calls == 2:
            raise RuntimeError("simulated transaction failure")
        return result
    monkeypatch.setattr(repo, "create_event", fail_second)
    with pytest.raises(RuntimeError):
        store.commit("owner", trip["id"], draft["id"], 1, repo.get_trip("owner", trip["id"])["version"], [item(), item("Cafe")], "commit")
    assert (repo.trips, repo.events, repo.places, repo.categories) == snapshot
    assert store.get("owner", trip["id"], draft["id"])["status"] == "editing"


def test_commit_rejects_stale_versions_and_out_of_range_without_mutation(draft_store):
    repo, trip, store, draft = draft_store
    args = ("owner", trip["id"], draft["id"])
    with pytest.raises(TravelConflictError):
        store.commit(*args, 2, trip["version"], [item()], "commit")
    with pytest.raises(TravelConflictError):
        store.commit(*args, 1, 99, [item()], "commit")
    with pytest.raises(TravelValidationError):
        store.commit(*args, 1, trip["version"], [item(date="2025-01-01")], "commit")
    assert not repo.events and not repo.places and not repo.categories


def test_concurrent_commit_returns_one_snapshot_and_one_batch(draft_store):
    repo, trip, store, draft = draft_store
    def commit(index):
        return store.commit("owner", trip["id"], draft["id"], 1, trip["version"], [item()], f"commit-{index}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, range(2)))
    assert results[0] == results[1]
    assert len(repo.events) == 1 and repo.get_trip("owner", trip["id"])["version"] == 2


def test_deleted_trip_cannot_be_read_or_processed(draft_store):
    repo, trip, store, draft = draft_store
    other_trip = repo.create_trip("owner", {"name": "Other", "start_date": "2026-01-01", "end_date": "2026-01-03"})
    other_draft = store.create("owner", other_trip["id"], "2026-01-01", "Private other draft")
    store.queue("owner", trip["id"], draft["id"], 1, "generation", "2026-01-01", "River")
    repo.delete_trip("owner", trip["id"], trip["version"])
    assert draft["id"] not in store.records
    assert other_draft["id"] in store.records
    assert store.pending() == []
    with pytest.raises(TravelNotFoundError):
        store.get("owner", trip["id"], draft["id"])


def test_generation_rechecks_date_after_trip_range_changes(draft_store):
    repo, trip, store, draft = draft_store
    repo.update_trip("owner", trip["id"], {**trip, "start_date": "2026-01-02"})
    with pytest.raises(TravelValidationError):
        store.queue("owner", trip["id"], draft["id"], 1, "generation", "2026-01-01", "River")
    assert store.pending() == []


def test_create_rechecks_current_trip_date_range_before_writing(draft_store):
    repo, trip, store, _ = draft_store
    # The service may have validated Jan 1 before another tab changes the range.
    repo.update_trip("owner", trip["id"], {**trip, "start_date": "2026-01-02"})
    original_count = len(store.records)
    with pytest.raises(TravelValidationError):
        store.create("owner", trip["id"], "2026-01-01", "Previously valid date")
    assert len(store.records) == original_count
    assert store.create("owner", trip["id"], None, "Date not selected")["record_date"] is None


def test_patch_rechecks_current_trip_date_range_without_losing_saved_draft(draft_store):
    repo, trip, store, draft = draft_store
    repo.update_trip("owner", trip["id"], {**trip, "start_date": "2026-01-02"})
    args = ("owner", trip["id"], draft["id"])
    before = store.get(*args)
    with pytest.raises(TravelValidationError):
        store.update(*args, 1, {"record_date": "2026-01-01", "text": "Invalid after date edit"})
    assert store.get(*args) == before
    changed = store.update(*args, 1, {"record_date": "2026-01-02"})
    assert changed["record_date"] == "2026-01-02" and changed["version"] == 2
