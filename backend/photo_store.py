"""Storage implementations for photos (Memory and Neo4j)."""

from __future__ import annotations

import copy
import datetime
import json
import time
from threading import RLock
from typing import Any

TARGET_LABELS: dict[str, str] = {
    "trip": "Trip",
    "event": "Event",
    "conversation": "Conversation",
    "message": "Message",
}


class MemoryPhotoStore:
    """In-memory thread-safe store for photo metadata, bindings, and orders."""

    def __init__(self) -> None:
        self.photos: dict[str, dict[str, Any]] = {}
        self.covers: dict[tuple[str, str], str | None] = {}
        self.orders: dict[tuple[str, str], list[str]] = {}
        self.lock = RLock()

    def initialize(self) -> None:
        """No-op for memory store."""

    def close(self) -> None:
        """No-op for memory store."""

    def create(self, owner: str, record: dict[str, Any]) -> dict[str, Any]:
        """Creates a photo record."""
        rec = copy.deepcopy(record)
        rec["owner_id"] = owner
        rec.setdefault("caption", "")
        rec.setdefault("version", 1)
        rec.setdefault("analysis_version", 0)
        rec.setdefault("status", "pending")
        rec.setdefault("analysis", {})
        rec.setdefault("bindings", [])
        with self.lock:
            self.photos[rec["id"]] = copy.deepcopy(rec)
        return copy.deepcopy(rec)

    def get(self, owner: str | None, id: str) -> dict[str, Any] | None:
        """Retrieves photo by id.

        If owner is provided, ensures owner matches.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return None
            if owner is not None and rec.get("owner_id") != owner:
                return None
            return copy.deepcopy(rec)

    def list(
        self,
        owner: str | None = None,
        trip_id: str | None = None,
        event_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lists photo records matching given filters.

        When listing for a trip_id, results are ordered according to the trip's
        order.
        """
        with self.lock:
            matched = []
            for p in self.photos.values():
                if owner is not None and p.get("owner_id") != owner:
                    continue
                if status is not None and p.get("status") != status:
                    continue

                bindings = p.get("bindings", [])
                if trip_id is not None:
                    has_trip = any(
                        (b.get("kind") == "trip" and b.get("target_id") == trip_id)
                        or (b.get("trip_id") == trip_id)
                        for b in bindings
                    )
                    if not has_trip:
                        continue
                if event_id is not None:
                    has_event = any(
                        b.get("kind") == "event" and b.get("target_id") == event_id
                        for b in bindings
                    )
                    if not has_event:
                        continue
                if conversation_id is not None:
                    has_conv = any(
                        b.get("kind") == "conversation" and b.get("target_id") == conversation_id
                        for b in bindings
                    )
                    if not has_conv:
                        continue
                if message_id is not None:
                    has_msg = any(
                        b.get("kind") == "message" and b.get("target_id") == message_id
                        for b in bindings
                    )
                    if not has_msg:
                        continue

                matched.append(copy.deepcopy(p))

            if trip_id is not None and owner is not None:
                order = self.orders.get((owner, trip_id), [])
                order_map = {pid: idx for idx, pid in enumerate(order)}
                matched.sort(
                    key=lambda x: (
                        order_map.get(x["id"], len(order_map)),
                        -(
                            datetime.datetime.fromisoformat(x["created_at"]).timestamp()
                            if x.get("created_at")
                            else 0
                        ),
                    )
                )
            else:
                matched.sort(
                    key=lambda x: (
                        -(
                            datetime.datetime.fromisoformat(x["created_at"]).timestamp()
                            if x.get("created_at")
                            else 0
                        ),
                        x.get("id", ""),
                    )
                )

            return matched

    def update(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Atomic CAS update of photo fields (increments version)."""
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return None
            if owner is not None and rec.get("owner_id") != owner:
                return None
            if rec.get("version") != expected_version:
                return None

            for k, v in changes.items():
                if k == "analysis":
                    rec["analysis"] = copy.deepcopy(v)
                elif k == "bindings":
                    rec["bindings"] = copy.deepcopy(v)
                else:
                    rec[k] = copy.deepcopy(v)

            if "caption" in changes:
                rec["claimed_version"] = None
                rec["claimed_at"] = None
                if rec.get("status") == "processing":
                    rec["status"] = "pending"

            rec["version"] = rec.get("version", expected_version) + 1
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return copy.deepcopy(rec)

    def remove(
        self,
        owner: str | None,
        id: str,
        expected_version: int | None = None,
        only_if_unbound: bool = False,
    ) -> bool:
        """Removes a photo record by id with atomic expected_version and only_if_unbound checks."""
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return False
            if owner is not None and rec.get("owner_id") != owner:
                return False
            if expected_version is not None and rec.get("version") != expected_version:
                return False
            if only_if_unbound and rec.get("bindings"):
                return False

            self.photos.pop(id, None)

            owner_id = rec.get("owner_id")
            if owner_id:
                for k, v in list(self.covers.items()):
                    if k[0] == owner_id and v == id:
                        self.covers[k] = None
                for k, v in list(self.orders.items()):
                    if k[0] == owner_id and id in v:
                        self.orders[k] = [x for x in v if x != id]

            return True

    def bind(
        self,
        owner: str,
        id: str,
        kind: str,
        target_id: str,
        trip_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Binds a photo to a target (trip, event, conversation, message).

        Advances embedding_version if embedding is ready, since content is unchanged.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec or rec.get("owner_id") != owner:
                return None

            bindings = rec.setdefault("bindings", [])
            for b in bindings:
                if b.get("kind") == kind and b.get("target_id") == target_id:
                    if trip_id is not None:
                        b["trip_id"] = trip_id
                    return copy.deepcopy(rec)

            new_binding = {"kind": kind, "target_id": target_id}
            if trip_id is not None:
                new_binding["trip_id"] = trip_id
            bindings.append(new_binding)
            rec["searchable"] = rec.get("status") == "ready" and any(
                b.get("kind") in ("trip", "event") for b in bindings
            )

            new_version = rec.get("version", 1) + 1
            rec["version"] = new_version
            if rec.get("embedding_status") in ("completed", "ready"):
                rec["embedding_version"] = new_version
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return copy.deepcopy(rec)

    def unbind(
        self,
        owner: str,
        id: str,
        kind: str,
        target_id: str,
        cascade_if_unbound: bool = True,
    ) -> dict[str, Any] | None:
        """Unbinds a photo from a target.

        If cascade_if_unbound and no bindings remain, atomically removes the photo inside lock.
        Advances embedding_version if remaining and embedding is ready.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec or rec.get("owner_id") != owner:
                return None

            bindings = rec.get("bindings", [])
            initial_len = len(bindings)
            bindings = [
                b
                for b in bindings
                if not (b.get("kind") == kind and b.get("target_id") == target_id)
            ]
            if len(bindings) == initial_len:
                return {"deleted": False, "photo": copy.deepcopy(rec)}

            rec["bindings"] = bindings
            rec["searchable"] = rec.get("status") == "ready" and any(
                b.get("kind") in ("trip", "event") for b in bindings
            )
            if cascade_if_unbound and not bindings:
                self.photos.pop(id, None)
                owner_id = rec.get("owner_id")
                if owner_id:
                    for k, v in list(self.covers.items()):
                        if k[0] == owner_id and v == id:
                            self.covers[k] = None
                    for k, v in list(self.orders.items()):
                        if k[0] == owner_id and id in v:
                            self.orders[k] = [x for x in v if x != id]
                return {
                    "deleted": True,
                    "stored_path": rec.get("stored_path"),
                    "thumbnail_path": rec.get("thumbnail_path"),
                }

            new_version = rec.get("version", 1) + 1
            rec["version"] = new_version
            if rec.get("embedding_status") in ("completed", "ready"):
                rec["embedding_version"] = new_version
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return {"deleted": False, "photo": copy.deepcopy(rec)}

    def list_pending(self, limit: int = 4) -> list[dict[str, Any]]:
        """Internal worker method: lists photos with status='pending'."""
        with self.lock:
            pending = [
                copy.deepcopy(p) for p in self.photos.values() if p.get("status") == "pending"
            ]
            pending.sort(key=lambda x: x.get("created_at", ""))
            return pending[:limit]

    def claim(self, owner: str | None, id: str, version: int) -> bool:
        """Internal worker method: CAS claims photo for processing.

        Does NOT increment version so user edit expected_version remains valid.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return False
            if owner is not None and rec.get("owner_id") != owner:
                return False
            if rec.get("version") != version or rec.get("status") != "pending":
                return False

            rec["status"] = "processing"
            rec["claimed_version"] = version
            rec["claimed_at"] = time.time()
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return True

    def finish_analysis(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        analysis: dict[str, Any],
        status: str = "ready",
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """Internal worker method: CAS finishes vision analysis and updates search fields atomically.

        Does NOT increment version so user edit expected_version remains valid.
        Accepts finish when version matches expected_version OR when claimed_version matches
        expected_version while in processing status (e.g. when bindings advanced version).
        Atomically aligns resulting embedding_version to current Photo.version.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return False
            if owner is not None and rec.get("owner_id") != owner:
                return False

            current_version = rec.get("version", 1)
            version_match = current_version == expected_version
            claim_match = (
                rec.get("claimed_version") == expected_version
                and rec.get("status") == "processing"
            )
            if not (version_match or claim_match):
                return False

            rec["status"] = status
            rec["analysis"] = copy.deepcopy(analysis)
            rec["analysis_version"] = current_version
            rec["claimed_version"] = None
            rec["claimed_at"] = None
            if extra_fields:
                for k, v in extra_fields.items():
                    rec[k] = copy.deepcopy(v)
            # Bindings can change while vision is running; use their current state.
            rec["searchable"] = status == "ready" and any(
                b.get("kind") in ("trip", "event") for b in rec.get("bindings", [])
            )
            if rec.get("embedding_status") in ("completed", "ready"):
                rec["embedding_version"] = current_version
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return True

    def fail_analysis(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        reason_code: str,
    ) -> bool:
        """Internal worker method: CAS marks photo analysis failed without incrementing version.

        Accepts failure when version matches expected_version OR when claimed_version matches
        expected_version while in processing status.
        """
        with self.lock:
            rec = self.photos.get(id)
            if not rec:
                return False
            if owner is not None and rec.get("owner_id") != owner:
                return False

            current_version = rec.get("version", 1)
            version_match = current_version == expected_version
            claim_match = (
                rec.get("claimed_version") == expected_version
                and rec.get("status") == "processing"
            )
            if not (version_match or claim_match):
                return False

            rec["status"] = "failed"
            rec["failure_reason"] = reason_code
            rec["claimed_version"] = None
            rec["claimed_at"] = None
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return True
            rec["updated_at"] = (
                datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
            )
            return True

    def get_cover(self, owner: str, trip_id: str) -> str | None:
        """Returns cover photo id for a trip."""
        with self.lock:
            return self.covers.get((owner, trip_id))

    def set_cover(self, owner: str, trip_id: str, photo_id: str | None) -> None:
        """Sets cover photo id for a trip."""
        with self.lock:
            self.covers[(owner, trip_id)] = photo_id

    def get_order(self, owner: str, trip_id: str) -> list[str]:
        """Returns ordered list of photo ids for a trip."""
        with self.lock:
            return list(self.orders.get((owner, trip_id), []))

    def set_order(self, owner: str, trip_id: str, photo_ids: list[str]) -> list[str]:
        """Sets and returns ordered list of photo ids for a trip."""
        with self.lock:
            self.orders[(owner, trip_id)] = list(photo_ids)
            return list(photo_ids)

    def get_user_disk_usage(self, owner: str) -> int:
        """Returns total bytes used by owner on disk."""
        with self.lock:
            return sum(
                p.get("size_bytes", 0) + p.get("thumbnail_size_bytes", 0)
                for p in self.photos.values()
                if p.get("owner_id") == owner
            )

    def get_global_disk_usage(self) -> int:
        """Returns total bytes used globally on disk."""
        with self.lock:
            return sum(
                p.get("size_bytes", 0) + p.get("thumbnail_size_bytes", 0)
                for p in self.photos.values()
            )

    def list_expired_unbound(self, cutoff_iso: str) -> list[dict[str, Any]]:
        """Lists unbound photos created at or before cutoff_iso."""
        with self.lock:
            expired = []
            for p in self.photos.values():
                if not p.get("bindings") and p.get("created_at", "") <= cutoff_iso:
                    expired.append(copy.deepcopy(p))
            return expired

    def recover_stuck_jobs(self, timeout_seconds: float, now: float) -> list[dict[str, Any]]:
        """Recovers stuck processing jobs back to pending."""
        with self.lock:
            recovered = []
            for p in self.photos.values():
                if p.get("status") == "processing":
                    claimed_at = p.get("claimed_at")
                    if claimed_at is not None and (now - claimed_at) >= timeout_seconds:
                        p["status"] = "pending"
                        p["claimed_version"] = None
                        p["claimed_at"] = None
                        p["updated_at"] = (
                            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
                        )
                        recovered.append(copy.deepcopy(p))
            return recovered


class Neo4jPhotoStore:
    """Neo4j graph database store for photo metadata and relationships."""

    def __init__(self, driver: Any, database: str = "neo4j") -> None:
        self.driver = driver
        self.database = database

    def initialize(self) -> None:
        """Creates unique constraints and indexes for Photo nodes."""
        with self.driver.session(database=self.database) as session:
            for query in [
                "CREATE CONSTRAINT photo_id IF NOT EXISTS FOR (p:Photo) REQUIRE p.id IS UNIQUE",
                "CREATE INDEX photo_owner IF NOT EXISTS FOR (p:Photo) ON (p.owner_id)",
                "CREATE INDEX photo_owner_status IF NOT EXISTS FOR (p:Photo) ON (p.owner_id, p.status)",
                "CREATE INDEX photo_status IF NOT EXISTS FOR (p:Photo) ON (p.status)",
            ]:
                session.run(query).consume()

    def close(self) -> None:
        """Closes the underlying driver if needed."""

    def _record_from_node(self, node: dict[str, Any]) -> dict[str, Any]:
        rec = dict(node)
        if "analysis_json" in rec:
            try:
                rec["analysis"] = json.loads(rec.pop("analysis_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                rec["analysis"] = {}
        elif "analysis" not in rec:
            rec["analysis"] = {}

        if "bindings_json" in rec:
            try:
                rec["bindings"] = json.loads(rec.pop("bindings_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                rec["bindings"] = []
        elif "bindings" not in rec:
            rec["bindings"] = []

        return rec

    def create(self, owner: str, record: dict[str, Any]) -> dict[str, Any]:
        """Creates a photo node in Neo4j."""
        rec = copy.deepcopy(record)
        rec["owner_id"] = owner
        rec.setdefault("caption", "")
        rec.setdefault("version", 1)
        rec.setdefault("analysis_version", 0)
        rec.setdefault("status", "pending")
        analysis = rec.get("analysis") or {}
        bindings = rec.get("bindings") or []

        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MERGE (u:User {id: $owner_id})
                CREATE (p:Photo {
                    id: $id,
                    owner_id: $owner_id,
                    caption: $caption,
                    version: $version,
                    analysis_version: $analysis_version,
                    status: $status,
                    analysis_json: $analysis_json,
                    width: $width,
                    height: $height,
                    size_bytes: $size_bytes,
                    thumbnail_size_bytes: $thumbnail_size_bytes,
                    stored_path: $stored_path,
                    thumbnail_path: $thumbnail_path,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    claimed_version: $claimed_version,
                    claimed_at: $claimed_at,
                    analysis_model: $analysis_model,
                    embedding: $embedding,
                    embedding_status: $embedding_status,
                    embedding_version: $embedding_version,
                    search_text: $search_text,
                    bindings_json: $bindings_json
                })
                CREATE (u)-[:OWNS]->(p)
                """,
                owner_id=owner,
                id=rec["id"],
                caption=rec["caption"],
                version=rec["version"],
                analysis_version=rec["analysis_version"],
                status=rec["status"],
                analysis_json=json.dumps(analysis),
                width=rec.get("width", 0),
                height=rec.get("height", 0),
                size_bytes=rec.get("size_bytes", 0),
                thumbnail_size_bytes=rec.get("thumbnail_size_bytes", 0),
                stored_path=rec.get("stored_path", ""),
                thumbnail_path=rec.get("thumbnail_path", ""),
                created_at=rec.get("created_at", ""),
                updated_at=rec.get("updated_at", ""),
                claimed_version=rec.get("claimed_version"),
                claimed_at=rec.get("claimed_at"),
                analysis_model=rec.get("analysis_model"),
                embedding=rec.get("embedding"),
                embedding_status=rec.get("embedding_status"),
                embedding_version=rec.get("embedding_version"),
                search_text=rec.get("search_text"),
                bindings_json=json.dumps(bindings),
            ).consume()

        return rec

    def get(self, owner: str | None, id: str) -> dict[str, Any] | None:
        """Retrieves photo node by id."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                RETURN p
                """,
                id=id,
                owner=owner,
            ).single()
            if not result:
                return None
            return self._record_from_node(result["p"])

    def list(
        self,
        owner: str | None = None,
        trip_id: str | None = None,
        event_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lists photo records matching filters."""
        with self.driver.session(database=self.database) as session:
            query = """
            MATCH (p:Photo)
            WHERE ($owner IS NULL OR p.owner_id = $owner)
              AND ($status IS NULL OR p.status = $status)
            RETURN p
            ORDER BY p.created_at DESC
            """
            result = session.run(query, owner=owner, status=status)
            records = [self._record_from_node(row["p"]) for row in result]

            filtered = []
            for r in records:
                bindings = r.get("bindings", [])
                if trip_id is not None:
                    has_trip = any(
                        (b.get("kind") == "trip" and b.get("target_id") == trip_id)
                        or (b.get("trip_id") == trip_id)
                        for b in bindings
                    )
                    if not has_trip:
                        continue
                if event_id is not None:
                    has_event = any(
                        b.get("kind") == "event" and b.get("target_id") == event_id
                        for b in bindings
                    )
                    if not has_event:
                        continue
                if conversation_id is not None:
                    has_conv = any(
                        b.get("kind") == "conversation" and b.get("target_id") == conversation_id
                        for b in bindings
                    )
                    if not has_conv:
                        continue
                if message_id is not None:
                    has_msg = any(
                        b.get("kind") == "message" and b.get("target_id") == message_id
                        for b in bindings
                    )
                    if not has_msg:
                        continue
                filtered.append(r)

            if trip_id is not None and owner is not None:
                order = self.get_order(owner, trip_id)
                order_map = {pid: idx for idx, pid in enumerate(order)}
                filtered.sort(
                    key=lambda x: (
                        order_map.get(x["id"], len(order_map)),
                        -(
                            datetime.datetime.fromisoformat(x["created_at"]).timestamp()
                            if x.get("created_at")
                            else 0
                        ),
                    )
                )

            return filtered

    def update(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Atomic CAS update of photo properties (increments version)."""
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        ch = dict(changes)
        analysis_json = json.dumps(ch.pop("analysis")) if "analysis" in ch else None
        bindings_json = json.dumps(ch.pop("bindings")) if "bindings" in ch else None
        caption_change = "caption" in ch

        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id, version: $expected_version})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                SET p += $changes,
                    p.version = p.version + 1,
                    p.updated_at = $updated_at
                FOREACH (_ IN CASE WHEN $analysis_json IS NOT NULL THEN [1] ELSE [] END |
                    SET p.analysis_json = $analysis_json
                )
                FOREACH (_ IN CASE WHEN $bindings_json IS NOT NULL THEN [1] ELSE [] END |
                    SET p.bindings_json = $bindings_json
                )
                FOREACH (_ IN CASE WHEN $caption_change THEN [1] ELSE [] END |
                    SET p.claimed_version = null,
                        p.claimed_at = null
                )
                FOREACH (_ IN CASE WHEN $caption_change AND p.status = 'processing' THEN [1] ELSE [] END |
                    SET p.status = 'pending'
                )
                RETURN p
                """,
                id=id,
                expected_version=expected_version,
                owner=owner,
                changes=ch,
                updated_at=now_iso,
                analysis_json=analysis_json,
                bindings_json=bindings_json,
                caption_change=caption_change,
            ).single()
            if not result:
                return None
            return self._record_from_node(result["p"])

    def remove(
        self,
        owner: str | None,
        id: str,
        expected_version: int | None = None,
        only_if_unbound: bool = False,
    ) -> bool:
        """Removes a photo node and relationships atomically with version and unbound locks."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                  AND ($expected_version IS NULL OR p.version = $expected_version)
                  AND (NOT $only_if_unbound OR p.bindings_json = '[]' OR p.bindings_json IS NULL)
                DETACH DELETE p
                RETURN count(p) AS cnt
                """,
                id=id,
                owner=owner,
                expected_version=expected_version,
                only_if_unbound=only_if_unbound,
            ).single()
            if not result or result["cnt"] == 0:
                return False

            session.run(
                """
                MATCH (t:Trip {cover_photo_id: $id})
                SET t.cover_photo_id = null
                """,
                id=id,
            ).consume()

            return True

    def bind(
        self,
        owner: str,
        id: str,
        kind: str,
        target_id: str,
        trip_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically binds a photo node to a target in a single write transaction.

        Creates (Target)-[:HAS_PHOTO]->(Photo) alongside bindings_json under owner+version lock.
        Advances embedding_version if embedding is already ready (content unchanged).
        """
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        label = TARGET_LABELS.get(kind)
        if not label:
            return None

        with self.driver.session(database=self.database) as session:  # noqa: SIM117
            with session.begin_transaction() as tx:
                p_res = tx.run(
                    """
                    MATCH (u:User {id: $owner})-[:OWNS]->(p:Photo {id: $id})
                    RETURN p
                    """,
                    owner=owner,
                    id=id,
                ).single()
                if not p_res:
                    return None

                rec = self._record_from_node(p_res["p"])
                current_ver = rec["version"]
                bindings = rec.get("bindings", [])

                already_bound = False
                for b in bindings:
                    if b.get("kind") == kind and b.get("target_id") == target_id:
                        if trip_id is not None:
                            b["trip_id"] = trip_id
                        already_bound = True
                        break

                if not already_bound:
                    new_b = {"kind": kind, "target_id": target_id}
                    if trip_id is not None:
                        new_b["trip_id"] = trip_id
                    bindings.append(new_b)

                # Atomically verify target ownership and create (Target)-[:HAS_PHOTO]->(Photo)
                if kind == "trip":
                    t_match = tx.run(
                        """
                        MATCH (u:User {id: $owner})-[:OWNS]->(target:Trip {id: $target_id})
                        MATCH (u)-[:OWNS]->(p:Photo {id: $id, version: $ver})
                        MERGE (target)-[:HAS_PHOTO]->(p)
                        RETURN target.id AS tid
                        """,
                        owner=owner,
                        target_id=target_id,
                        id=id,
                        ver=current_ver,
                    ).single()
                    if not t_match:
                        return None
                elif kind == "event":
                    e_match = tx.run(
                        """
                        MATCH (u:User {id: $owner})-[:OWNS]->(:Trip)-[:HAS_EVENT]->(target:Event {id: $target_id})
                        MATCH (u)-[:OWNS]->(p:Photo {id: $id, version: $ver})
                        MERGE (target)-[:HAS_PHOTO]->(p)
                        RETURN target.id AS eid
                        """,
                        owner=owner,
                        target_id=target_id,
                        id=id,
                        ver=current_ver,
                    ).single()
                    if not e_match:
                        return None
                elif kind == "conversation":
                    c_match = tx.run(
                        """
                        MATCH (target:Conversation {id: $target_id})
                        WHERE target.owner_id = $owner OR EXISTS { MATCH (:User {id: $owner})-[:OWNS]->(target) }
                        MATCH (p:Photo {id: $id, owner_id: $owner, version: $ver})
                        MERGE (target)-[:HAS_PHOTO]->(p)
                        RETURN target.id AS cid
                        """,
                        owner=owner,
                        target_id=target_id,
                        id=id,
                        ver=current_ver,
                    ).single()
                    if not c_match:
                        return None
                elif kind == "message":
                    m_match = tx.run(
                        """
                        MATCH (c:Conversation)-[:HAS_MESSAGE]->(target:Message {id: $target_id})
                        WHERE c.owner_id = $owner OR EXISTS { MATCH (:User {id: $owner})-[:OWNS]->(c) }
                        MATCH (p:Photo {id: $id, owner_id: $owner, version: $ver})
                        MERGE (target)-[:HAS_PHOTO]->(p)
                        RETURN target.id AS mid
                        """,
                        owner=owner,
                        target_id=target_id,
                        id=id,
                        ver=current_ver,
                    ).single()
                    if not m_match:
                        return None

                adv_emb = rec.get("embedding_status") in ("completed", "ready")
                new_ver = current_ver + 1
                upd_res = tx.run(
                    """
                    MATCH (p:Photo {id: $id, version: $current_ver, owner_id: $owner})
                    SET p.bindings_json = $bindings_json,
                        p.version = $new_ver,
                        p.updated_at = $updated_at,
                        p.searchable = p.status = 'ready' AND $attached
                    FOREACH (_ IN CASE WHEN $adv_emb THEN [1] ELSE [] END |
                        SET p.embedding_version = $new_ver
                    )
                    RETURN p
                    """,
                    id=id,
                    current_ver=current_ver,
                    new_ver=new_ver,
                    owner=owner,
                    bindings_json=json.dumps(bindings),
                    attached=any(b.get("kind") in ("trip", "event") for b in bindings),
                    updated_at=now_iso,
                    adv_emb=adv_emb,
                ).single()

                if not upd_res:
                    return None

                tx.commit()
                return self._record_from_node(upd_res["p"])

    def unbind(
        self,
        owner: str,
        id: str,
        kind: str,
        target_id: str,
        cascade_if_unbound: bool = True,
    ) -> dict[str, Any] | None:
        """Atomically unbinds target and deletes (Target)-[:HAS_PHOTO]->(Photo) in one write transaction.

        If cascade_if_unbound and no bindings remain, atomically DETACH DELETEs the photo node.
        """
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        with self.driver.session(database=self.database) as session:  # noqa: SIM117
            with session.begin_transaction() as tx:
                p_res = tx.run(
                    """
                    MATCH (u:User {id: $owner})-[:OWNS]->(p:Photo {id: $id})
                    RETURN p
                    """,
                    owner=owner,
                    id=id,
                ).single()
                if not p_res:
                    return None

                rec = self._record_from_node(p_res["p"])
                current_ver = rec["version"]
                bindings = rec.get("bindings", [])
                initial_len = len(bindings)
                remaining = [
                    b
                    for b in bindings
                    if not (b.get("kind") == kind and b.get("target_id") == target_id)
                ]
                if len(remaining) == initial_len:
                    return {"deleted": False, "photo": rec}

                tx.run(
                    """
                    MATCH (target {id: $target_id})-[r:HAS_PHOTO]->(p:Photo {id: $id, owner_id: $owner})
                    DELETE r
                    """,
                    target_id=target_id,
                    id=id,
                    owner=owner,
                )

                if cascade_if_unbound and not remaining:
                    tx.run(
                        """
                        MATCH (p:Photo {id: $id, version: $current_ver, owner_id: $owner})
                        DETACH DELETE p
                        """,
                        id=id,
                        current_ver=current_ver,
                        owner=owner,
                    )
                    tx.run(
                        """
                        MATCH (t:Trip {cover_photo_id: $id})
                        SET t.cover_photo_id = null
                        """,
                        id=id,
                    )
                    tx.commit()
                    return {
                        "deleted": True,
                        "stored_path": rec.get("stored_path"),
                        "thumbnail_path": rec.get("thumbnail_path"),
                    }

                new_ver = current_ver + 1
                adv_emb = rec.get("embedding_status") in ("completed", "ready")
                upd_res = tx.run(
                    """
                    MATCH (p:Photo {id: $id, version: $current_ver, owner_id: $owner})
                    SET p.bindings_json = $bindings_json,
                        p.version = $new_ver,
                        p.updated_at = $updated_at,
                        p.searchable = p.status = 'ready' AND $attached
                    FOREACH (_ IN CASE WHEN $adv_emb THEN [1] ELSE [] END |
                        SET p.embedding_version = $new_ver
                    )
                    RETURN p
                    """,
                    id=id,
                    current_ver=current_ver,
                    new_ver=new_ver,
                    owner=owner,
                    bindings_json=json.dumps(remaining),
                    attached=any(b.get("kind") in ("trip", "event") for b in remaining),
                    updated_at=now_iso,
                    adv_emb=adv_emb,
                ).single()
                if not upd_res:
                    return None

                tx.commit()
                return {"deleted": False, "photo": self._record_from_node(upd_res["p"])}

    def list_pending(self, limit: int = 4) -> list[dict[str, Any]]:
        """Internal worker method: lists photos with status='pending'."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {status: 'pending'})
                RETURN p
                ORDER BY p.created_at ASC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [self._record_from_node(row["p"]) for row in result]

    def claim(self, owner: str | None, id: str, version: int) -> bool:
        """Internal worker method: CAS claims photo for processing without incrementing version."""
        now_ts = time.time()
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id, version: $version, status: 'pending'})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                SET p.status = 'processing',
                    p.claimed_version = $version,
                    p.claimed_at = $claimed_at,
                    p.updated_at = $updated_at
                RETURN p.id AS id
                """,
                id=id,
                version=version,
                owner=owner,
                claimed_at=now_ts,
                updated_at=now_iso,
            ).single()
            return bool(result)

    def finish_analysis(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        analysis: dict[str, Any],
        status: str = "ready",
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """Internal worker method: CAS finishes vision analysis and updates search fields atomically.

        Does NOT increment version so user edit expected_version remains valid.
        Accepts finish when version matches expected_version OR when claimed_version matches
        expected_version while in processing status (e.g. when bindings advanced version).
        Atomically aligns resulting embedding_version to current Photo.version.
        """
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        ef = dict(extra_fields or {})
        has_ready_embedding = ef.get("embedding_status") in ("completed", "ready")
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                  AND (p.version = $expected_version OR (p.claimed_version = $expected_version AND p.status = 'processing'))
                SET p.status = $status,
                    p.analysis_json = $analysis_json,
                    p.analysis_version = p.version,
                    p.claimed_version = null,
                    p.claimed_at = null,
                    p.updated_at = $updated_at,
                    p += $extra_fields
                SET p.searchable = $status = 'ready' AND (
                    EXISTS { MATCH (:Trip)-[:HAS_PHOTO]->(p) }
                    OR EXISTS { MATCH (:Event)-[:HAS_PHOTO]->(p) }
                )
                FOREACH (_ IN CASE WHEN $has_ready_embedding THEN [1] ELSE [] END |
                    SET p.embedding_version = p.version
                )
                RETURN p.id AS id
                """,
                id=id,
                expected_version=expected_version,
                owner=owner,
                status=status,
                analysis_json=json.dumps(analysis),
                updated_at=now_iso,
                extra_fields=ef,
                has_ready_embedding=has_ready_embedding,
            ).single()
            return bool(result)

    def fail_analysis(
        self,
        owner: str | None,
        id: str,
        expected_version: int,
        reason_code: str,
    ) -> bool:
        """Internal worker method: CAS marks photo analysis failed without incrementing version.

        Accepts failure when version matches expected_version OR when claimed_version matches
        expected_version while in processing status.
        """
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {id: $id})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                  AND (p.version = $expected_version OR (p.claimed_version = $expected_version AND p.status = 'processing'))
                SET p.status = 'failed',
                    p.failure_reason = $reason_code,
                    p.claimed_version = null,
                    p.claimed_at = null,
                    p.updated_at = $updated_at
                RETURN p.id AS id
                """,
                id=id,
                expected_version=expected_version,
                owner=owner,
                reason_code=reason_code,
                updated_at=now_iso,
            ).single()
            return bool(result)

    def get_cover(self, owner: str, trip_id: str) -> str | None:
        """Returns cover photo id for trip."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (u:User {id: $owner})-[:OWNS]->(t:Trip {id: $trip_id})
                RETURN t.cover_photo_id AS cover_id
                """,
                owner=owner,
                trip_id=trip_id,
            ).single()
            if not result:
                return None
            return result["cover_id"]

    def set_cover(self, owner: str, trip_id: str, photo_id: str | None) -> None:
        """Sets cover photo id for trip."""
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (u:User {id: $owner})-[:OWNS]->(t:Trip {id: $trip_id})
                SET t.cover_photo_id = $photo_id
                """,
                owner=owner,
                trip_id=trip_id,
                photo_id=photo_id,
            ).consume()

    def get_order(self, owner: str, trip_id: str) -> list[str]:
        """Returns photo order list for trip."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (u:User {id: $owner})-[:OWNS]->(t:Trip {id: $trip_id})
                RETURN coalesce(t.photo_order, []) AS photo_order
                """,
                owner=owner,
                trip_id=trip_id,
            ).single()
            if not result:
                return []
            return list(result["photo_order"])

    def set_order(self, owner: str, trip_id: str, photo_ids: list[str]) -> list[str]:
        """Sets and returns photo order list for trip."""
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                MATCH (u:User {id: $owner})-[:OWNS]->(t:Trip {id: $trip_id})
                SET t.photo_order = $photo_ids
                """,
                owner=owner,
                trip_id=trip_id,
                photo_ids=list(photo_ids),
            ).consume()
            return list(photo_ids)

    def get_user_disk_usage(self, owner: str) -> int:
        """Returns total bytes used by owner on disk."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {owner_id: $owner})
                RETURN coalesce(sum(p.size_bytes + p.thumbnail_size_bytes), 0) AS total
                """,
                owner=owner,
            ).single()
            return int(result["total"]) if result else 0

    def get_global_disk_usage(self) -> int:
        """Returns total bytes used globally on disk."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo)
                RETURN coalesce(sum(p.size_bytes + p.thumbnail_size_bytes), 0) AS total
                """
            ).single()
            return int(result["total"]) if result else 0

    def list_expired_unbound(self, cutoff_iso: str) -> list[dict[str, Any]]:
        """Lists unbound photos created at or before cutoff_iso."""
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo)
                WHERE (p.bindings_json = '[]' OR p.bindings_json IS NULL)
                  AND p.created_at <= $cutoff_iso
                RETURN p
                """,
                cutoff_iso=cutoff_iso,
            )
            return [self._record_from_node(row["p"]) for row in result]

    def recover_stuck_jobs(self, timeout_seconds: float, now: float) -> list[dict[str, Any]]:
        """Recovers stuck processing jobs back to pending."""
        now_iso = (
            datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
        )
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (p:Photo {status: 'processing'})
                WHERE p.claimed_at IS NOT NULL AND ($now - p.claimed_at) >= $timeout_seconds
                SET p.status = 'pending',
                    p.claimed_version = null,
                    p.claimed_at = null,
                    p.updated_at = $updated_at
                RETURN p
                """,
                now=now,
                timeout_seconds=timeout_seconds,
                updated_at=now_iso,
            )
            return [self._record_from_node(row["p"]) for row in result]
