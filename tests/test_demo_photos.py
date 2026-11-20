from contextlib import contextmanager
from copy import deepcopy

import pytest
from PIL import Image

from backend.demo_photos import import_photos
from backend.photo_store import MemoryPhotoStore
from backend.photos import PhotoService
from backend.travel_store import MemoryTravelRepository


class Ledger:
    def __init__(self):
        self.states = {}

    @contextmanager
    def locked(self, key):
        state = deepcopy(self.states.get(key, {}))
        yield state
        self.states[key] = state


@pytest.fixture
def album(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    Image.new("RGB", (400, 300), "green").save(root / "card.png")
    repository = MemoryTravelRepository()
    trip = repository.create_trip("owner", {"name": "Demo", "start_date": "2026-01-01",
                                           "end_date": "2026-01-02"})
    event = repository.create_event("owner", trip["id"], {
        "place_name": "Cafe", "date": "2026-01-01", "category": "Coffee",
    })
    store = MemoryPhotoStore()
    from types import SimpleNamespace
    service = PhotoService(SimpleNamespace(media_root=str(tmp_path / "media")), store, repository)
    service.initialize()
    plan = {"owner_id": "owner", "package_root": str(root), "photos": [{
        "key": "card", "file": "card.png", "caption": "合成圖卡", "trip_id": trip["id"],
        "event_id": event["id"], "cover": True,
    }]}
    return service, repository, Ledger(), plan, store


def test_demo_photos_resume_without_overwriting_edits_or_recreating_deleted_photos(album):
    service, repository, ledger, plan, store = album
    assert import_photos(service, repository, ledger, plan) == {"imported": 1, "skipped": 0}
    photo_id = ledger.states["card"]["photo_id"]
    photo = service.get("owner", photo_id)
    assert photo["caption"] == "合成圖卡"
    assert {b["kind"] for b in photo["bindings"]} == {"trip", "event"}
    assert service.get_trip_cover("owner", plan["photos"][0]["trip_id"]) == photo_id
    service.update("owner", photo_id, photo["version"], "自己修改")
    assert import_photos(service, repository, ledger, plan)["skipped"] == 1
    assert service.get("owner", photo_id)["caption"] == "自己修改"
    assert len(store.photos) == 1
    del store.photos[photo_id]
    import_photos(service, repository, ledger, plan)
    assert not store.photos


def test_demo_photos_retry_uses_uploaded_pointer_after_binding_failure(album, monkeypatch):
    service, repository, ledger, plan, store = album
    bind = service.bind
    monkeypatch.setattr(service, "bind", lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        import_photos(service, repository, ledger, plan)
    photo_id = ledger.states["card"]["photo_id"]
    assert ledger.states["card"]["status"] == "uploaded"
    monkeypatch.setattr(service, "bind", bind)
    assert import_photos(service, repository, ledger, plan)["imported"] == 1
    assert list(store.photos) == [photo_id]


def test_demo_photos_skip_missing_owned_targets_and_reject_path_escape(album):
    service, repository, ledger, plan, store = album
    plan["owner_id"] = "someone-else"
    assert import_photos(service, repository, ledger, plan)["skipped"] == 1
    assert not store.photos
    plan["photos"][0]["file"] = "../outside.png"
    with pytest.raises(ValueError):
        import_photos(service, repository, Ledger(), plan)


def test_unfinished_expired_upload_can_be_replaced(album, monkeypatch):
    service, repository, ledger, plan, store = album
    bind = service.bind
    monkeypatch.setattr(service, "bind", lambda *args: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        import_photos(service, repository, ledger, plan)
    store.photos.clear()  # Simulate the regular orphan retention cleanup before resuming.
    monkeypatch.setattr(service, "bind", bind)
    assert import_photos(service, repository, ledger, plan)["imported"] == 1
    assert len(store.photos) == 1
