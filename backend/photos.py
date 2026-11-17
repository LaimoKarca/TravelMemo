"""Photo management service and private media HTTP endpoints."""

from __future__ import annotations

import asyncio
import datetime
import hmac
import secrets
import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, BinaryIO
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.auth import AuthError
from backend.image_codec import ImageCodecError, ProcessedImage, process_image


class PhotoAnalysisDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    visible_text: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    place_candidates: list[Any] = Field(default_factory=list)
    date_candidate: str | None = None
    uncertainties: list[str] = Field(default_factory=list)


class PhotoBindingDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str
    target_id: str
    trip_id: str | None = None


class PhotoDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    caption: str = ""
    version: int
    analysis_version: int = 0
    status: str
    analysis: PhotoAnalysisDTO
    width: int
    height: int
    size_bytes: int
    thumbnail_size_bytes: int
    created_at: str
    updated_at: str
    bindings: list[PhotoBindingDTO] = Field(default_factory=list)
    url: str
    thumbnail_url: str


class PhotoListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[PhotoDTO]


class PhotoUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    caption: str = Field(default="", max_length=10000)


class PhotoRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int


class PhotoBindInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^(trip|event|conversation|message)$")
    target_id: str = Field(min_length=1, max_length=200)


class PhotoOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_ids: list[str]


class PhotoCoverInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_id: str | None = None


class PhotoCoverResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_id: str | None = None


def _save_atomic(path: Path, data: bytes) -> None:
    temp_path = path.with_suffix(f".tmp.{secrets.token_hex(8)}")
    try:
        temp_path.write_bytes(data)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


class PhotoService:
    """Service managing photo compression, storage quotas, and binding lifecycles."""

    def __init__(
        self,
        settings: Any = None,
        store: Any = None,
        travel_repository: Any = None,
        conversation_store: Any = None,
        clock: Any = time.time,
    ) -> None:
        self.settings = settings if settings is not None else SimpleNamespace()
        self.store = store
        self.travel_repository = travel_repository
        self.conversation_store = conversation_store
        self.clock = clock

        # Application media settings with defaults for lightweight test settings.
        self.media_root = Path(
            getattr(self.settings, "media_root", getattr(self.settings, "photo_storage_dir", "data/media"))
        )
        self.media_upload_max_bytes: int = int(
            getattr(
                self.settings,
                "media_upload_max_bytes",
                getattr(self.settings, "photo_max_upload_bytes", 20 * 1024 * 1024),
            )
        )
        self.media_max_pixels: int = int(
            getattr(
                self.settings,
                "media_max_pixels",
                getattr(self.settings, "photo_max_pixels", 50_000_000),
            )
        )
        self.media_max_dimension: int = int(
            getattr(
                self.settings,
                "media_max_dimension",
                getattr(self.settings, "photo_max_dimension", 2048),
            )
        )
        self.media_image_max_bytes: int = int(
            getattr(
                self.settings,
                "media_image_max_bytes",
                getattr(self.settings, "photo_image_max_bytes", 512 * 1024),
            )
        )
        self.media_thumbnail_max_bytes: int = int(
            getattr(
                self.settings,
                "media_thumbnail_max_bytes",
                getattr(self.settings, "photo_thumbnail_max_bytes", 64 * 1024),
            )
        )
        self.media_user_quota_bytes: int = int(
            getattr(
                self.settings,
                "media_user_quota_bytes",
                getattr(self.settings, "photo_user_quota_bytes", 250 * 1024 * 1024),
            )
        )
        self.media_global_quota_bytes: int = int(
            getattr(
                self.settings,
                "media_global_quota_bytes",
                getattr(self.settings, "photo_global_quota_bytes", 5 * 1024 * 1024 * 1024),
            )
        )
        self.media_poll_seconds: float = float(
            getattr(
                self.settings,
                "media_poll_seconds",
                getattr(self.settings, "photo_poll_seconds", 3.0),
            )
        )
        self.media_orphan_seconds: int = int(
            getattr(
                self.settings,
                "media_orphan_seconds",
                getattr(self.settings, "photo_orphan_seconds", 3600),
            )
        )

        # Backward compatibility properties
        self.storage_dir = self.media_root
        self.user_quota_bytes = self.media_user_quota_bytes
        self.global_quota_bytes = self.media_global_quota_bytes
        self.max_upload_bytes = self.media_upload_max_bytes
        self.prefix = "/api/v1"

        self._reservation_lock = threading.Lock()
        self._reserved_user: dict[str, int] = defaultdict(int)
        self._reserved_global: int = 0

    def initialize(self) -> None:
        """Initializes storage directory and backing store."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self.store, "initialize"):
            self.store.initialize()

    def to_dto(self, record: dict[str, Any]) -> dict[str, Any]:
        """Formats an internal photo record into a public PhotoDTO dict."""
        photo_id = record["id"]
        analysis = record.get("analysis") or {}

        vt = analysis.get("visible_text")
        if isinstance(vt, list):
            visible_text = [str(x) for x in vt]
        elif isinstance(vt, str):
            visible_text = [vt] if vt.strip() else []
        else:
            visible_text = []

        return {
            "id": photo_id,
            "caption": record.get("caption", ""),
            "version": record.get("version", 1),
            "analysis_version": record.get("analysis_version", 0),
            "status": record.get("status", "pending"),
            "analysis": {
                "summary": analysis.get("summary", ""),
                "visible_text": visible_text,
                "tags": list(analysis.get("tags") or []),
                "place_candidates": list(analysis.get("place_candidates") or []),
                "date_candidate": analysis.get("date_candidate", None),
                "uncertainties": list(analysis.get("uncertainties") or []),
            },
            "width": record.get("width", 0),
            "height": record.get("height", 0),
            "size_bytes": record.get("size_bytes", 0),
            "thumbnail_size_bytes": record.get("thumbnail_size_bytes", 0),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
            "bindings": [
                {
                    "kind": b.get("kind"),
                    "target_id": b.get("target_id"),
                    **({"trip_id": b["trip_id"]} if b.get("trip_id") is not None else {}),
                }
                for b in record.get("bindings", [])
            ],
            "url": f"{self.prefix}/photos/{photo_id}/content",
            "thumbnail_url": f"{self.prefix}/photos/{photo_id}/thumbnail",
        }

    def upload(
        self,
        owner: str,
        stream: Iterable[bytes] | bytes | BinaryIO,
        content_type: str,
    ) -> dict[str, Any]:
        """Validates quotas, compresses photo and thumbnail to WebP, and stores record."""
        if hasattr(stream, "read"):
            raw_bytes = stream.read()
        elif isinstance(stream, bytes):
            raw_bytes = stream
        else:
            raw_bytes = b"".join(stream)

        if len(raw_bytes) > self.media_upload_max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"圖片檔案大小 ({len(raw_bytes)} bytes) 超過限制 ({self.media_upload_max_bytes} bytes)。",
            )
        if len(raw_bytes) == 0:
            raise HTTPException(status_code=422, detail="圖片檔案內容為空。")

        # Initial reservation covers incoming_size or expected minimum compressed footprint,
        # bounded by user quota so small-quota tests and environments function properly.
        estimated_bound = min(
            self.media_user_quota_bytes,
            max(len(raw_bytes), min(16384, self.media_image_max_bytes + self.media_thumbnail_max_bytes)),
        )
        initial_reservation = estimated_bound

        with self._reservation_lock:
            user_disk = self.store.get_user_disk_usage(owner)
            if user_disk + self._reserved_user[owner] + initial_reservation > self.media_user_quota_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"使用者相片儲存配額已滿（上限 {self.media_user_quota_bytes} bytes）。",
                )
            global_disk = self.store.get_global_disk_usage()
            if global_disk + self._reserved_global + initial_reservation > self.media_global_quota_bytes:
                raise HTTPException(
                    status_code=507,
                    detail=f"系統相片儲存空間已滿（上限 {self.media_global_quota_bytes} bytes）。",
                )
            self._reserved_user[owner] += initial_reservation
            self._reserved_global += initial_reservation
            current_reserved = initial_reservation

        photo_id = str(uuid4())
        owner_dir = self.storage_dir / owner
        stored_path = owner_dir / f"{photo_id}.webp"
        thumb_path = owner_dir / f"{photo_id}_thumb.webp"

        try:
            try:
                processed: ProcessedImage = process_image(
                    raw_bytes,
                    max_dimension=self.media_max_dimension,
                    max_size_bytes=self.media_image_max_bytes,
                    thumb_max_dimension=384,
                    thumb_max_size_bytes=self.media_thumbnail_max_bytes,
                    max_upload_bytes=self.media_upload_max_bytes,
                    max_megapixels=self.media_max_pixels,
                )
            except ImageCodecError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

            actual_size = processed.size_bytes + processed.thumbnail_size_bytes

            # Adjust reservation to actual compressed size under lock before writing files
            with self._reservation_lock:
                diff = actual_size - current_reserved
                self._reserved_user[owner] += diff
                self._reserved_global += diff
                current_reserved = actual_size

                user_disk = self.store.get_user_disk_usage(owner)
                if user_disk + self._reserved_user[owner] > self.media_user_quota_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"使用者相片儲存配額已滿（上限 {self.media_user_quota_bytes} bytes）。",
                    )
                global_disk = self.store.get_global_disk_usage()
                if global_disk + self._reserved_global > self.media_global_quota_bytes:
                    raise HTTPException(
                        status_code=507,
                        detail=f"系統相片儲存空間已滿（上限 {self.media_global_quota_bytes} bytes）。",
                    )

            owner_dir.mkdir(parents=True, exist_ok=True)
            try:
                _save_atomic(stored_path, processed.main_bytes)
                _save_atomic(thumb_path, processed.thumbnail_bytes)

                now_iso = (
                    datetime.datetime.fromtimestamp(self.clock(), tz=datetime.UTC)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                record = {
                    "id": photo_id,
                    "owner_id": owner,
                    "caption": "",
                    "version": 1,
                    "analysis_version": 0,
                    "status": "pending",
                    "analysis": {
                        "summary": "",
                        "visible_text": [],
                        "tags": [],
                        "place_candidates": [],
                        "date_candidate": processed.date_candidate,
                        "uncertainties": [],
                    },
                    "width": processed.width,
                    "height": processed.height,
                    "size_bytes": processed.size_bytes,
                    "thumbnail_size_bytes": processed.thumbnail_size_bytes,
                    "stored_path": str(stored_path),
                    "thumbnail_path": str(thumb_path),
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "claimed_version": None,
                    "claimed_at": None,
                    "analysis_model": None,
                    "embedding": None,
                    "embedding_status": None,
                    "embedding_version": None,
                    "search_text": None,
                    "bindings": [],
                }
                created = self.store.create(owner, record)
                return self.to_dto(created)
            except Exception:
                stored_path.unlink(missing_ok=True)
                thumb_path.unlink(missing_ok=True)
                raise
        finally:
            with self._reservation_lock:
                self._reserved_user[owner] = max(0, self._reserved_user[owner] - current_reserved)
                self._reserved_global = max(0, self._reserved_global - current_reserved)

    def get(self, owner: str, id: str) -> dict[str, Any] | None:
        """Retrieves a photo as DTO, or returns None if not found/owned."""
        record = self.store.get(owner, id)
        if not record:
            return None
        return self.to_dto(record)

    def list(
        self,
        owner: str,
        trip_id: str | None = None,
        event_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lists photos for owner matching filters.

        Gallery queries for trip_id are returned in custom order.
        """
        records = self.store.list(
            owner=owner,
            trip_id=trip_id,
            event_id=event_id,
            conversation_id=conversation_id,
        )
        return [self.to_dto(r) for r in records]

    def bind(self, owner: str, id: str, kind: str, target_id: str) -> dict[str, Any]:
        """Binds a photo to a trip, event, conversation, or message."""
        if kind not in {"trip", "event", "conversation", "message"}:
            raise HTTPException(status_code=422, detail="無效的綁定類型。")

        trip_id = None
        if kind == "trip" and self.travel_repository:
            trip = self.travel_repository.get_trip(owner, target_id)
            if not trip:
                raise HTTPException(status_code=404, detail="找不到指定的旅程。")
            trip_id = target_id
        elif kind == "event" and self.travel_repository:
            event = None
            if hasattr(self.travel_repository, "get_event"):
                event = self.travel_repository.get_event(owner, target_id)
            if not event and hasattr(self.travel_repository, "get_trips"):
                trips = self.travel_repository.get_trips(owner)
                for t in trips:
                    detail = self.travel_repository.get_trip_detail(owner, t["id"])
                    if detail:
                        for ev in detail.get("events", []):
                            if ev.get("id") == target_id:
                                event = ev
                                trip_id = t["id"]
                                break
                    if event:
                        break
            if not event:
                raise HTTPException(status_code=404, detail="找不到指定的事件。")
            if not trip_id:
                trip_id = event.get("trip_id")
        elif kind == "conversation" and self.conversation_store:
            conv = self.conversation_store.get_conversation(owner, target_id)
            if not conv:
                raise HTTPException(status_code=404, detail="找不到指定的對話。")

        updated = self.store.bind(owner, id, kind, target_id, trip_id=trip_id)
        if not updated:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")
        return self.to_dto(updated)

    def unbind(self, owner: str, id: str, kind: str, target_id: str) -> None:
        """Removes a binding.

        If the photo becomes unreferenced (0 bindings), cascade deletes it atomically.
        """
        record = self.store.get(owner, id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")

        result = self.store.unbind(
            owner,
            id,
            kind,
            target_id,
            cascade_if_unbound=True,
        )
        if not result:
            return

        if result.get("deleted"):
            stored_path = result.get("stored_path")
            if stored_path:
                Path(stored_path).unlink(missing_ok=True)
            thumbnail_path = result.get("thumbnail_path")
            if thumbnail_path:
                Path(thumbnail_path).unlink(missing_ok=True)
        else:
            updated_photo = result.get("photo") or {}
            remaining_bindings = updated_photo.get("bindings", [])
            if kind in ("trip", "event"):
                trip_id = target_id if kind == "trip" else None
                if not trip_id:
                    for b in record.get("bindings", []):
                        if b.get("kind") == "event" and b.get("target_id") == target_id:
                            trip_id = b.get("trip_id")
                            break
                if trip_id and self.store.get_cover(owner, trip_id) == id:
                    still_in_trip = any(
                        (b.get("kind") == "trip" and b.get("target_id") == trip_id)
                        or (b.get("trip_id") == trip_id)
                        for b in remaining_bindings
                    )
                    if not still_in_trip:
                        self.store.set_cover(owner, trip_id, None)

    def delete(self, owner: str, id: str, version: int | None = None) -> None:
        """Deletes photo files, bindings, and record explicitly with atomic CAS."""
        record = self.store.get(owner, id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")
        if version is not None and record.get("version") != version:
            raise HTTPException(status_code=409, detail="相片已被修改，請重新整理後再試。")

        # Atomic store removal with expected_version lock
        removed = self.store.remove(owner, id, expected_version=version)
        if not removed:
            fresh = self.store.get(owner, id)
            if fresh:
                raise HTTPException(status_code=409, detail="相片已被修改，請重新整理後再試。")
            raise HTTPException(status_code=404, detail="找不到指定的相片。")

        # Only unlink physical files after atomic removal succeeds!
        stored_path = record.get("stored_path")
        if stored_path:
            Path(stored_path).unlink(missing_ok=True)
        thumbnail_path = record.get("thumbnail_path")
        if thumbnail_path:
            Path(thumbnail_path).unlink(missing_ok=True)

    def update(self, owner: str, id: str, version: int, caption: str) -> dict[str, Any]:
        """Atomic CAS update of photo caption.

        Reuses existing vision analysis and sets embedding_status='pending'
        without forcing new vision.
        """
        rec = self.store.get(owner, id)
        if not rec:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")
        if rec.get("version") != version:
            raise HTTPException(status_code=409, detail="相片已被修改，請重新整理後再試。")

        changes = {
            "caption": caption,
            "embedding_status": "pending",
        }
        if rec.get("status") == "processing":
            changes["status"] = "pending"
            changes["claimed_version"] = None
            changes["claimed_at"] = None

        updated = self.store.update(
            owner,
            id,
            expected_version=version,
            changes=changes,
        )
        if not updated:
            raise HTTPException(status_code=409, detail="資料已被修改，請重新整理後再試。")
        return self.to_dto(updated)

    def retry(self, owner: str, id: str, version: int) -> dict[str, Any]:
        """Atomic CAS manual retry: increments version, resets status='pending', and clears analysis."""
        rec = self.store.get(owner, id)
        if not rec:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")
        if rec.get("version") != version:
            raise HTTPException(status_code=409, detail="相片已被修改，請重新整理後再試。")

        date_cand = (rec.get("analysis") or {}).get("date_candidate")
        cleared_analysis = {
            "summary": "",
            "visible_text": [],
            "tags": [],
            "place_candidates": [],
            "date_candidate": date_cand,
            "uncertainties": [],
        }

        updated = self.store.update(
            owner,
            id,
            expected_version=version,
            changes={
                "status": "pending",
                "analysis": cleared_analysis,
                "analysis_version": 0,
                "claimed_version": None,
                "claimed_at": None,
                "embedding": None,
                "embedding_status": None,
                "embedding_version": None,
                "search_text": None,
            },
        )
        if not updated:
            raise HTTPException(status_code=409, detail="資料已被修改，請重新整理後再試。")
        return self.to_dto(updated)

    def content(self, owner: str, id: str, thumbnail: bool = False) -> Path:
        """Returns the private filesystem Path of the main image or thumbnail."""
        record = self.store.get(owner, id)
        if not record:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")

        path_str = record.get("thumbnail_path") if thumbnail else record.get("stored_path")
        if not path_str:
            raise HTTPException(status_code=404, detail="找不到相片檔案路徑。")
        path = Path(path_str)
        if not path.exists():
            raise HTTPException(status_code=404, detail="找不到相片檔案。")
        return path

    def ready_evidence(self, owner: str, photo_ids: list[str]) -> list[dict[str, Any]]:
        """Returns validated internal photo records for the owner.

        Rejects not owned with 404, non-ready with 409.
        """
        records = []
        for pid in photo_ids:
            rec = self.store.get(owner, pid)
            if not rec:
                raise HTTPException(status_code=404, detail=f"找不到相片或無存取權限: {pid}")
            if rec.get("status") != "ready":
                raise HTTPException(
                    status_code=409,
                    detail=f"相片尚未完成分析: {pid} (狀態: {rec.get('status')})",
                )
            records.append(rec)
        return records

    def detach_target(self, owner: str, kind: str, target_id: str) -> None:
        """Removes binding to target for all photos owned by owner, cleaning orphans."""
        photos = self.store.list(owner=owner)
        for p in photos:
            bindings = p.get("bindings", [])
            has_match = any(
                b.get("kind") == kind and b.get("target_id") == target_id for b in bindings
            )
            if has_match:
                self.unbind(owner, p["id"], kind, target_id)

        if kind == "trip":
            self.store.set_cover(owner, target_id, None)
            self.store.set_order(owner, target_id, [])

    def cleanup(self) -> dict[str, int]:
        """Cleans up expired unbound photos (>media_orphan_seconds),

        reconciles stale bindings for deleted targets, and recovers stuck jobs.
        Never uses fresh version with stale snapshot.
        """
        now = self.clock()
        cutoff_ts = now - self.media_orphan_seconds
        cutoff_iso = (
            datetime.datetime.fromtimestamp(cutoff_ts, tz=datetime.UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )

        stale_reconciled = 0
        orphan_cleaned = 0

        # 1. Reconcile stale bindings to deleted targets
        all_photos = self.store.list(owner=None)
        for p in all_photos:
            owner = p.get("owner_id")
            pid = p.get("id")
            if not owner or not pid:
                continue

            # CAS retry loop to safely reconcile bindings without race conditions
            for _ in range(3):
                fresh_rec = self.store.get(owner, pid)
                if not fresh_rec:
                    break

                expected_ver = fresh_rec["version"]
                current_bindings = list(fresh_rec.get("bindings", []))
                valid_bindings = []
                has_stale = False

                for b in current_bindings:
                    kind = b.get("kind")
                    target_id = b.get("target_id")
                    target_exists = True

                    if kind == "trip" and self.travel_repository:
                        try:
                            target_exists = bool(self.travel_repository.get_trip(owner, target_id))
                        except (KeyError, AttributeError, TypeError, ValueError, OSError):
                            target_exists = True
                    elif kind == "event" and self.travel_repository:
                        try:
                            ev = None
                            if hasattr(self.travel_repository, "get_event"):
                                ev = self.travel_repository.get_event(owner, target_id)
                            if not ev and hasattr(self.travel_repository, "get_trips"):
                                for t in self.travel_repository.get_trips(owner):
                                    dtl = self.travel_repository.get_trip_detail(owner, t["id"])
                                    if dtl and any(e.get("id") == target_id for e in dtl.get("events", [])):
                                        ev = True
                                        break
                            target_exists = bool(ev)
                        except (KeyError, AttributeError, TypeError, ValueError, OSError):
                            target_exists = True
                    elif kind == "conversation" and self.conversation_store:
                        try:
                            target_exists = bool(self.conversation_store.get_conversation(owner, target_id))
                        except (KeyError, AttributeError, TypeError, ValueError, OSError):
                            target_exists = True

                    if target_exists:
                        valid_bindings.append(b)
                    else:
                        has_stale = True

                if not has_stale:
                    break

                stale_reconciled += 1
                if not valid_bindings:
                    updated = self.store.update(
                        owner,
                        pid,
                        expected_version=expected_ver,
                        changes={"bindings": []},
                    )
                    if not updated:
                        continue
                    removed = self.store.remove(
                        owner,
                        pid,
                        expected_version=updated["version"],
                        only_if_unbound=True,
                    )
                    if removed:
                        orphan_cleaned += 1
                        stored = fresh_rec.get("stored_path")
                        thumb = fresh_rec.get("thumbnail_path")
                        if stored:
                            Path(stored).unlink(missing_ok=True)
                        if thumb:
                            Path(thumb).unlink(missing_ok=True)
                    break
                else:
                    changes = {"bindings": valid_bindings}
                    if fresh_rec.get("embedding_status") in ("completed", "ready"):
                        changes["embedding_version"] = expected_ver + 1
                    updated = self.store.update(
                        owner,
                        pid,
                        expected_version=expected_ver,
                        changes=changes,
                    )
                    if updated:
                        break

        # 2. Cleanup expired unbound uploads (>media_orphan_seconds)
        expired = self.store.list_expired_unbound(cutoff_iso)
        for rec in expired:
            removed = self.store.remove(
                rec["owner_id"],
                rec["id"],
                expected_version=rec.get("version"),
                only_if_unbound=True,
            )
            if removed:
                orphan_cleaned += 1
                stored = rec.get("stored_path")
                thumb = rec.get("thumbnail_path")
                if stored:
                    Path(stored).unlink(missing_ok=True)
                if thumb:
                    Path(thumb).unlink(missing_ok=True)

        # 3. Recover stuck jobs (>300s)
        stuck = self.store.recover_stuck_jobs(timeout_seconds=300, now=now)
        stuck_count = len(stuck)

        return {
            "expired_unbound_cleaned": orphan_cleaned,
            "stale_bindings_reconciled": stale_reconciled,
            "stuck_jobs_recovered": stuck_count,
        }

    def get_trip_cover(self, owner: str, trip_id: str) -> str | None:
        """Returns cover photo id for trip."""
        return self.store.get_cover(owner, trip_id)

    def set_trip_cover(self, owner: str, trip_id: str, photo_id: str | None) -> str | None:
        """Sets cover photo for trip."""
        if photo_id is not None:
            rec = self.store.get(owner, photo_id)
            if not rec:
                raise HTTPException(status_code=404, detail="找不到指定的相片。")
        self.store.set_cover(owner, trip_id, photo_id)
        return photo_id

    def get_trip_order(self, owner: str, trip_id: str) -> list[str]:
        """Returns ordered list of photo ids for trip."""
        return self.store.get_order(owner, trip_id)

    def set_trip_order(self, owner: str, trip_id: str, photo_ids: list[str]) -> list[dict[str, Any]]:
        """Sets ordered list of photo ids for trip and returns ordered PhotoDTO items."""
        for pid in photo_ids:
            rec = self.store.get(owner, pid)
            if not rec:
                raise HTTPException(status_code=404, detail=f"找不到相片: {pid}")
        self.store.set_order(owner, trip_id, photo_ids)
        return self.list(owner, trip_id=trip_id)


def create_photo_router(
    auth: Any,
    service: PhotoService,
    prefix: str = "/api/v1",
) -> APIRouter:
    """Creates FastAPI router for photo endpoints."""
    service.prefix = prefix
    router = APIRouter(prefix=prefix, tags=["photos"])
    decode_semaphore = asyncio.Semaphore(1)

    def authenticate_request(request: Request, require_csrf: bool = False) -> str:
        session_token = request.cookies.get("travelmemo_session")
        try:
            session_record = auth.session(session_token)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message) from exc

        if require_csrf:
            csrf = request.headers.get("X-CSRF-Token")
            if not csrf or not hmac.compare_digest(session_record["csrf_token"], csrf):
                raise HTTPException(status_code=403, detail="登入驗證已變更，請重新整理頁面。")

        return session_record["user"]["id"]

    @router.post("/photos", response_model=PhotoDTO, status_code=201)
    async def upload_photo(request: Request):
        owner_id = authenticate_request(request, require_csrf=True)
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="不支援的圖片格式。")

        max_upload = service.media_upload_max_bytes
        chunks = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > max_upload:
                raise HTTPException(
                    status_code=413,
                    detail=f"圖片檔案大小超過限制（最大 {max_upload} bytes）。",
                )
            chunks.append(chunk)

        raw_bytes = b"".join(chunks)
        if not raw_bytes:
            raise HTTPException(status_code=422, detail="圖片檔案內容為空。")

        # Limit actual decode concurrency to 1 and offload CPU-bound image work from event loop
        async with decode_semaphore:
            dto = await asyncio.to_thread(service.upload, owner_id, raw_bytes, content_type)
        return dto

    @router.get("/photos", response_model=PhotoListResponse)
    def list_photos(
        request: Request,
        trip_id: str | None = Query(default=None),
        event_id: str | None = Query(default=None),
        conversation_id: str | None = Query(default=None),
    ):
        owner_id = authenticate_request(request, require_csrf=False)
        items = service.list(
            owner_id,
            trip_id=trip_id,
            event_id=event_id,
            conversation_id=conversation_id,
        )
        return {"items": items}

    @router.get("/photos/{id}", response_model=PhotoDTO)
    def get_photo(id: str, request: Request):
        owner_id = authenticate_request(request, require_csrf=False)
        photo = service.get(owner_id, id)
        if not photo:
            raise HTTPException(status_code=404, detail="找不到指定的相片。")
        return photo

    @router.get("/photos/{id}/content")
    def get_photo_content(id: str, request: Request):
        owner_id = authenticate_request(request, require_csrf=False)
        path = service.content(owner_id, id, thumbnail=False)
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @router.get("/photos/{id}/thumbnail")
    def get_photo_thumbnail(id: str, request: Request):
        owner_id = authenticate_request(request, require_csrf=False)
        path = service.content(owner_id, id, thumbnail=True)
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @router.patch("/photos/{id}", response_model=PhotoDTO)
    def update_photo(id: str, body: PhotoUpdateInput, request: Request):
        owner_id = authenticate_request(request, require_csrf=True)
        return service.update(owner_id, id, body.version, body.caption)

    @router.delete("/photos/{id}", status_code=204)
    def delete_photo(
        id: str,
        request: Request,
        version: int | None = Query(default=None),
    ):
        owner_id = authenticate_request(request, require_csrf=True)
        service.delete(owner_id, id, version=version)
        return Response(status_code=204)

    @router.post("/photos/{id}/retry", response_model=PhotoDTO)
    def retry_photo(id: str, body: PhotoRetryInput, request: Request):
        owner_id = authenticate_request(request, require_csrf=True)
        return service.retry(owner_id, id, body.version)

    @router.post("/photos/{id}/bindings", response_model=PhotoDTO)
    def bind_photo(id: str, body: PhotoBindInput, request: Request):
        owner_id = authenticate_request(request, require_csrf=True)
        return service.bind(owner_id, id, body.kind, body.target_id)

    @router.delete("/photos/{id}/bindings", status_code=204)
    def unbind_photo(
        id: str,
        request: Request,
        kind: str = Query(...),
        target_id: str = Query(...),
    ):
        owner_id = authenticate_request(request, require_csrf=True)
        service.unbind(owner_id, id, kind, target_id)
        return Response(status_code=204)

    @router.put("/trips/{trip_id}/photos/order", response_model=PhotoListResponse)
    def set_trip_photos_order(
        trip_id: str,
        body: PhotoOrderInput,
        request: Request,
    ):
        owner_id = authenticate_request(request, require_csrf=True)
        items = service.set_trip_order(owner_id, trip_id, body.photo_ids)
        return {"items": items}

    @router.put("/trips/{trip_id}/photos/cover", response_model=PhotoCoverResponse)
    def set_trip_photos_cover(
        trip_id: str,
        body: PhotoCoverInput,
        request: Request,
    ):
        owner_id = authenticate_request(request, require_csrf=True)
        photo_id = service.set_trip_cover(owner_id, trip_id, body.photo_id)
        return {"photo_id": photo_id}

    @router.get("/trips/{trip_id}/photos/cover", response_model=PhotoCoverResponse)
    def get_trip_photos_cover(
        trip_id: str,
        request: Request,
    ):
        owner_id = authenticate_request(request, require_csrf=False)
        photo_id = service.get_trip_cover(owner_id, trip_id)
        return {"photo_id": photo_id}

    return router
