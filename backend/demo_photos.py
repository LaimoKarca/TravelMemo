"""Resume the small public demo album through the regular private photo service."""

from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from backend.photo_store import Neo4jPhotoStore
from backend.photos import PhotoService
from backend.travel_store import Neo4jTravelRepository


class PhotoImportLedger:
    def __init__(self, store, owner, pack):
        self.store, self.owner, self.pack = store, owner, pack

    def initialize(self):
        with self.store.driver.session(database=self.store.database) as session:
            session.run(
                "CREATE CONSTRAINT demo_photo_import_id IF NOT EXISTS "
                "FOR (n:DemoPhotoImport) REQUIRE n.id IS UNIQUE"
            ).consume()

    @contextmanager
    def locked(self, key):
        identity = str(uuid5(NAMESPACE_URL, f"travelmemo:demo-photo:{self.owner}:{self.pack}:{key}"))
        with (
            self.store.driver.session(database=self.store.database) as session,
            session.begin_transaction() as tx,
        ):
            record = tx.run(
                "MERGE (n:DemoPhotoImport {id:$id}) "
                "ON CREATE SET n.owner_id=$owner, n.pack_id=$pack, n.fixture_key=$key "
                "SET n.lock=coalesce(n.lock,0)+1 RETURN n.status AS status, n.photo_id AS photo_id",
                id=identity, owner=self.owner, pack=self.pack, key=key,
            ).single()
            state = dict(record)
            yield state
            tx.run(
                "MATCH (n:DemoPhotoImport {id:$id, owner_id:$owner}) "
                "SET n.status=$status, n.photo_id=$photo_id",
                id=identity, owner=self.owner, status=state.get("status"),
                photo_id=state.get("photo_id"),
            ).consume()
            tx.commit()


def import_photos(service, repository, ledger, plan):
    """Keep an uploaded id before bindings; a retry never creates a second visible copy."""
    owner = plan["owner_id"]
    package_root = Path(plan["package_root"]).resolve()
    counts = {"imported": 0, "skipped": 0}
    for item in plan["photos"]:
        source = (package_root / item["file"]).resolve()
        if not source.is_relative_to(package_root) or source.suffix.lower() != ".png":
            raise ValueError("Demo image must be a PNG within the package")
        with ledger.locked(item["key"]) as state:
            if state.get("status") in {"complete", "skipped"}:
                counts["skipped"] += 1
                continue
            if not repository.get_trip(owner, item["trip_id"]) or (
                item.get("event_id") and not repository.get_event(owner, item["event_id"])
            ):
                state["status"] = "skipped"
                counts["skipped"] += 1
                continue
            if not state.get("photo_id") or not service.get(owner, state["photo_id"]):
                # An unfinished, still-unbound upload may have expired during an interruption.
                # Completed entries were skipped above, so user deletions are never restored.
                photo = service.upload(owner, source.read_bytes(), "image/png")
                state.update(photo_id=photo["id"], status="uploaded")

        # A durable pointer now exists even if binding/captioning fails or the process stops.
        with ledger.locked(item["key"]) as state:
            if state.get("status") in {"complete", "skipped"}:
                counts["skipped"] += 1
                continue
            photo = service.get(owner, state["photo_id"])
            if not photo:
                state["status"] = "skipped"
                counts["skipped"] += 1
                continue
            if not photo.get("caption"):
                photo = service.update(owner, photo["id"], photo["version"], item["caption"])
            for kind, target in (("trip", item["trip_id"]), ("event", item.get("event_id"))):
                if target and not any(
                    b["kind"] == kind and b["target_id"] == target for b in photo.get("bindings", [])
                ):
                    photo = service.bind(owner, photo["id"], kind, target)
            if item.get("cover") and not service.get_trip_cover(owner, item["trip_id"]):
                service.set_trip_cover(owner, item["trip_id"], photo["id"])
            state["status"] = "complete"
            counts["imported"] += 1
    return counts


def seed_photos(settings, store, plan):
    repository = Neo4jTravelRepository(store.driver, store.database)
    service = PhotoService(settings, Neo4jPhotoStore(store.driver, store.database), repository)
    service.initialize()
    ledger = PhotoImportLedger(store, plan["owner_id"], plan["pack_id"])
    ledger.initialize()
    return import_photos(service, repository, ledger, plan)
