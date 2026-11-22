import datetime
from functools import wraps
from threading import RLock
from uuid import NAMESPACE_URL, uuid4, uuid5

from neo4j import Driver
from neo4j.exceptions import TransientError

from backend.timezones import normalize_timezone


def deterministic_category_id(owner_id: str, normalized_name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"travelmemo:category:{owner_id}:{normalized_name}"))


class TravelNotFoundError(Exception):
    def __init__(self, message: str = "找不到指定的資源。"):
        super().__init__(message)
        self.status = 404
        self.message = message


class TravelConflictError(Exception):
    def __init__(self, message: str = "資料已被修改，請重新整理後再試。"):
        super().__init__(message)
        self.status = 409
        self.message = message


class TravelValidationError(Exception):
    def __init__(self, message: str = "資料驗證失敗。"):
        super().__init__(message)
        self.status = 422
        self.message = message


def optimistic_write(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except TransientError as exc:
            # A competing attach/bind can also contend on relationship group locks.
            # The failed transaction is rolled back before returning a retryable 409.
            if exc.code == "Neo.TransientError.Transaction.DeadlockDetected":
                raise TravelConflictError("資料正在其他頁面更新，請重新整理後再試。") from exc
            raise
    return wrapped


def find_event_insert_index(events: list[dict], new_date: str) -> int:
    """Finds index to append after existing same-date events while keeping dates nondecreasing."""
    for idx, ev in enumerate(events):
        if ev["date"] > new_date:
            return idx
    return len(events)


def build_next_edges(events: list[dict]) -> list[dict]:
    """Builds next edges between adjacent events."""
    return [
        {"from_id": events[i]["id"], "to_id": events[i + 1]["id"]} for i in range(len(events) - 1)
    ]


def validate_attachment(event: dict, trip: dict, events: list[dict], before_id: str | None) -> int:
    if not trip["start_date"] <= event["date"] <= trip["end_date"]:
        raise TravelValidationError("足跡日期不在手記日期範圍內。")
    if normalize_timezone(event.get("timezone", "Asia/Taipei")) != normalize_timezone(trip.get("timezone", "Asia/Taipei")):
        raise TravelValidationError("足跡與手記時區不同，請先調整足跡的日期與時區。")
    if before_id is not None:
        for position, row in enumerate(events):
            if row["id"] == before_id and row["date"] == event["date"]:
                return position
        raise TravelValidationError("指定的前置位置必須是同本手記、同一天的足跡。")
    return find_event_insert_index(events, event["date"])


def format_trip(t: dict) -> dict:
    return {
        "id": t["id"],
        "name": t["name"],
        "start_date": t["start_date"],
        "end_date": t["end_date"],
        "timezone": t.get("timezone", "Asia/Taipei"),
        "description": t.get("description", ""),
        "version": t["version"],
    }


def format_event(e: dict) -> dict:
    return {
        "id": e["id"],
        "trip_id": e.get("trip_id"),
        "place_id": e["place_id"],
        "place_name": e["place_name"],
        "city": e.get("city", ""),
        "address": e.get("address", ""),
        "category": e["category"],
        "date": e["date"],
        "time": e.get("time"),
        "notes": e.get("notes", ""),
        "position": e.get("position", 0) if e.get("trip_id") else None,
        "version": e["version"],
        "timezone": e.get("timezone", "Asia/Taipei"),
        "record_scope": "trip" if e.get("trip_id") else "standalone",
    }


def format_place(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "city": p.get("city", ""),
        "address": p.get("address", ""),
    }


class MemoryTravelRepository:
    """In-memory thread-safe Travel Repository for testing."""

    def __init__(self):
        self.trips: dict[str, dict] = {}
        self.events: dict[str, dict] = {}
        self.places: dict[str, dict] = {}
        self.categories: dict[str, dict] = {}
        self.lock = RLock()
        self.photo_store = None

    def initialize(self):
        pass

    def close(self):
        pass

    def get_trips(self, owner_id: str, *, include_cover: bool = False) -> list[dict]:
        with self.lock:
            user_trips = [
                format_trip(t) for t in self.trips.values() if t.get("owner_id") == owner_id
            ]
            if include_cover:
                photo_store = self.photo_store
                for trip in user_trips:
                    cover_id = photo_store.get_cover(owner_id, trip["id"]) if photo_store else None
                    photo = photo_store.get(owner_id, cover_id) if cover_id else None
                    trip["cover_photo_id"] = cover_id if photo and photo.get("thumbnail_path") else None
            # sort start_date descending, id ascending
            user_trips.sort(key=lambda t: (-int(t["start_date"].replace("-", "")), t["id"]))
            return user_trips

    def get_trip(self, owner_id: str, trip_id: str) -> dict | None:
        with self.lock:
            trip = self.trips.get(trip_id)
            if trip and trip.get("owner_id") == owner_id:
                return format_trip(trip)
            return None

    def get_trip_detail(self, owner_id: str, trip_id: str) -> dict | None:
        with self.lock:
            trip = self.get_trip(owner_id, trip_id)
            if not trip:
                return None
            trip_events = [
                format_event(e)
                for e in self.events.values()
                if e.get("trip_id") == trip_id and e.get("owner_id") == owner_id
            ]
            trip_events.sort(key=lambda e: (e.get("position", 0), e["id"]))
            next_edges = build_next_edges(trip_events)
            return {"trip": trip, "events": trip_events, "next_edges": next_edges}

    def create_trip(self, owner_id: str, data: dict) -> dict:
        with self.lock:
            trip_id = str(uuid4())
            record = {
                "id": trip_id,
                "owner_id": owner_id,
                "name": data["name"],
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "timezone": data.get("timezone", "Asia/Taipei"),
                "description": data.get("description", ""),
                "version": 1,
            }
            self.trips[trip_id] = record
            return format_trip(record)

    def update_trip(self, owner_id: str, trip_id: str, data: dict) -> dict:
        with self.lock:
            trip = self.trips.get(trip_id)
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")
            if trip["version"] != data["version"]:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            # Check shrinking bounds excluding existing events
            trip_events = [
                e
                for e in self.events.values()
                if e.get("trip_id") == trip_id and e.get("owner_id") == owner_id
            ]
            if trip_events:
                min_date = min(e["date"] for e in trip_events)
                max_date = max(e["date"] for e in trip_events)
                if data["start_date"] > min_date or data["end_date"] < max_date:
                    raise TravelValidationError("旅程日期範圍不能縮小到排除現有事件。")

            trip["name"] = data["name"]
            trip["start_date"] = data["start_date"]
            trip["end_date"] = data["end_date"]
            trip["timezone"] = data.get("timezone", "Asia/Taipei")
            for event in trip_events:
                event["timezone"] = trip["timezone"]
            trip["description"] = data.get("description", "")
            trip["version"] += 1
            return format_trip(trip)

    def delete_trip(self, owner_id: str, trip_id: str, version: int) -> None:
        with self.lock:
            trip = self.trips.get(trip_id)
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")
            if trip["version"] != version:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            # Delete own events (Places are preserved)
            event_ids_to_delete = [
                eid
                for eid, e in self.events.items()
                if e.get("trip_id") == trip_id and e.get("owner_id") == owner_id
            ]
            for eid in event_ids_to_delete:
                del self.events[eid]

            drafts = getattr(self, "_footprint_drafts", {})
            for draft_id, draft in list(drafts.items()):
                if draft.get("owner_id") == owner_id and draft.get("trip_id") == trip_id:
                    del drafts[draft_id]

            del self.trips[trip_id]

    def get_places(self, owner_id: str) -> list[dict]:
        with self.lock:
            places = [
                format_place(p) for p in self.places.values() if p.get("owner_id") == owner_id
            ]
            places.sort(key=lambda p: (p["name"], p["id"]))
            return places

    def get_place(self, owner_id: str, place_id: str) -> dict | None:
        with self.lock:
            place = self.places.get(place_id)
            if place and place.get("owner_id") == owner_id:
                return format_place(place)
            return None

    def get_event(self, owner_id: str, event_id: str) -> dict | None:
        with self.lock:
            event = self.events.get(event_id)
            if not event or event.get("owner_id") != owner_id:
                return None
            res = format_event(event)
            trip = self.trips.get(event.get("trip_id"))
            if trip:
                res["trip_name"] = trip.get("name", "")
            return res

    def _resolve_place_on_create(self, owner_id: str, data: dict) -> dict:
        place_id = data.get("place_id")
        if place_id:
            place = self.get_place(owner_id, place_id)
            if not place:
                raise TravelNotFoundError("找不到指定的地點。")
            return place
        # Without place_id create fresh Place
        new_place_id = str(uuid4())
        new_place = {
            "id": new_place_id,
            "owner_id": owner_id,
            "name": data["place_name"],
            "city": data.get("city", ""),
            "address": data.get("address", ""),
        }
        self.places[new_place_id] = new_place
        return new_place

    def _resolve_category(self, owner_id: str, category_name: str) -> str:
        norm = category_name.strip()
        cat_id = deterministic_category_id(owner_id, norm)
        if cat_id not in self.categories:
            self.categories[cat_id] = {
                "id": cat_id,
                "owner_id": owner_id,
                "name": category_name,
                "normalized_name": norm,
            }
        return self.categories[cat_id]["name"]

    def create_event(self, owner_id: str, trip_id: str, data: dict) -> dict:
        with self.lock:
            trip = self.trips.get(trip_id)
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")

            # Validate date in trip bounds
            if data["date"] < trip["start_date"] or data["date"] > trip["end_date"]:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")

            place = self._resolve_place_on_create(owner_id, data)
            cat_name = self._resolve_category(owner_id, data["category"])

            # Find existing events sorted by position
            trip_events = [
                e
                for e in self.events.values()
                if e.get("trip_id") == trip_id and e.get("owner_id") == owner_id
            ]
            trip_events.sort(key=lambda e: (e.get("position", 0), e["id"]))

            insert_idx = find_event_insert_index(trip_events, data["date"])

            event_id = str(uuid4())
            new_event = {
                "id": event_id,
                "trip_id": trip_id,
                "timezone": trip.get("timezone", "Asia/Taipei"),
                "record_scope": "trip",
                "owner_id": owner_id,
                "place_id": place["id"],
                "place_name": place["name"],
                "city": place["city"],
                "address": place["address"],
                "category": cat_name,
                "date": data["date"],
                "time": data.get("time"),
                "notes": data.get("notes", ""),
                "position": insert_idx,
                "version": 1,
                "embedding_status": "pending",
                "embedded_version": 0,
            }

            trip_events.insert(insert_idx, new_event)
            for idx, ev in enumerate(trip_events):
                ev["position"] = idx

            self.events[event_id] = new_event
            trip["version"] += 1
            return format_event(new_event)

    def list_standalone_events(self, owner_id: str, *, q: str = "", city: str | None = None,
                               category: str | None = None, date_from: str | None = None,
                               date_to: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        with self.lock:
            query = q.strip().casefold()
            events = [e for e in self.events.values() if e.get("owner_id") == owner_id
                      and not e.get("trip_id")
                      and (not city or e.get("city") == city)
                      and (not category or e.get("category") == category)
                      and (not date_from or e["date"] >= date_from)
                      and (not date_to or e["date"] <= date_to)
                      and (not query or query in " ".join(str(e.get(k, "")) for k in
                           ("place_name", "city", "address", "category", "notes")).casefold())]
            events.sort(key=lambda e: e["id"])
            events.sort(key=lambda e: (e["date"], e.get("time") or "", e.get("created_at") or ""), reverse=True)
            page = events[offset:offset + limit + 1]
            return {"items": [format_event(e) for e in page[:limit]],
                    "next_offset": offset + limit if len(page) > limit else None}

    def create_standalone_event(self, owner_id: str, data: dict) -> dict:
        with self.lock:
            place = self._resolve_place_on_create(owner_id, data)
            event = {"id": str(uuid4()), "owner_id": owner_id, "trip_id": None,
                     "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds"),
                     "record_scope": "standalone", "timezone": normalize_timezone(data.get("timezone", "Asia/Taipei")),
                     "place_id": place["id"], "place_name": place["name"],
                     "city": place.get("city", ""), "address": place.get("address", ""),
                     "category": self._resolve_category(owner_id, data.get("category", "未分類")),
                     "date": data["date"], "time": data.get("time"), "notes": data.get("notes", ""),
                     "position": None, "version": 1, "embedding_status": "pending", "embedded_version": 0}
            self.events[event["id"]] = event
            return format_event(event)

    def attach_event_to_trip(self, owner_id: str, event_id: str, data: dict) -> dict:
        with self.lock:
            event = self.events.get(event_id)
            trip = self.trips.get(data["trip_id"])
            if not event or event.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的足跡。")
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的手記。")
            if event["version"] != data["version"] or event.get("trip_id") or trip["version"] != data["trip_version"]:
                raise TravelConflictError("足跡或手記已變更，請重新整理後再試。")
            events = [e for e in self.events.values() if e.get("owner_id") == owner_id and e.get("trip_id") == trip["id"]]
            events.sort(key=lambda e: (e.get("position", 0), e["id"]))
            insert_at = validate_attachment(event, trip, events, data.get("before_event_id"))
            if self.photo_store is not None:
                self.photo_store.sync_event_trip(owner_id, event_id, trip["id"])
            event.update(trip_id=trip["id"], record_scope="trip", timezone=trip.get("timezone", "Asia/Taipei"),
                         version=event["version"] + 1, embedding_status="pending")
            events.insert(insert_at, event)
            for position, row in enumerate(events):
                row["position"] = position
            trip["version"] += 1
            return format_event(event)

    def update_event(self, owner_id: str, event_id: str, data: dict) -> dict:
        with self.lock:
            event = self.events.get(event_id)
            if not event or event.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的事件。")
            if event["version"] != data["version"]:
                raise TravelConflictError("事件已被修改，請重新整理後再試。")

            if not event.get("trip_id"):
                place = self._resolve_place_on_create(owner_id, data)
                event.update(place_id=place["id"], place_name=place["name"], city=place.get("city", ""),
                             address=place.get("address", ""), category=self._resolve_category(owner_id, data["category"]),
                             date=data["date"], time=data.get("time"), notes=data.get("notes", ""),
                             timezone=normalize_timezone(data.get("timezone") or event.get("timezone", "Asia/Taipei")),
                             version=event["version"] + 1, embedding_status="pending")
                return format_event(event)
            trip = self.trips.get(event["trip_id"])
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")

            if data["date"] < trip["start_date"] or data["date"] > trip["end_date"]:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")
            if data.get("timezone") and normalize_timezone(data["timezone"]) != trip.get("timezone", "Asia/Taipei"):
                raise TravelValidationError("手記足跡使用手記的時區，請於編輯手記調整。")

            # Place resolution:
            # If supplied place_id, use authoritative existing place fields.
            # Without place_id create a new Place rather than mutate one used by another event.
            place_id = data.get("place_id")
            if place_id:
                place = self.get_place(owner_id, place_id)
                if not place:
                    raise TravelNotFoundError("找不到指定的地點。")
            else:
                new_place_id = str(uuid4())
                place = {
                    "id": new_place_id,
                    "owner_id": owner_id,
                    "name": data["place_name"],
                    "city": data.get("city", ""),
                    "address": data.get("address", ""),
                }
                self.places[new_place_id] = place

            cat_name = self._resolve_category(owner_id, data["category"])

            old_date = event["date"]
            new_date = data["date"]

            event["place_id"] = place["id"]
            event["place_name"] = place["name"]
            event["city"] = place["city"]
            event["address"] = place["address"]
            event["category"] = cat_name
            event["date"] = new_date
            event["time"] = data.get("time")
            event["notes"] = data.get("notes", "")
            event["version"] += 1
            event["embedding_status"] = "pending"
            event["timezone"] = trip.get("timezone", "Asia/Taipei")

            trip_events = [
                e
                for e in self.events.values()
                if e.get("trip_id") == trip["id"] and e.get("owner_id") == owner_id
            ]
            trip_events.sort(key=lambda e: (e.get("position", 0), e["id"]))

            if old_date != new_date:
                # Edit date: move to end of new date group
                trip_events.remove(event)
                insert_idx = find_event_insert_index(trip_events, new_date)
                trip_events.insert(insert_idx, event)

            for idx, ev in enumerate(trip_events):
                ev["position"] = idx

            trip["version"] += 1
            return format_event(event)

    def delete_event(self, owner_id: str, event_id: str, version: int) -> None:
        with self.lock:
            event = self.events.get(event_id)
            if not event or event.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的事件。")
            if event["version"] != version:
                raise TravelConflictError("事件已被修改，請重新整理後再試。")

            if not event.get("trip_id"):
                del self.events[event_id]
                return
            trip = self.trips.get(event["trip_id"])
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")

            del self.events[event_id]

            trip_events = [
                e
                for e in self.events.values()
                if e.get("trip_id") == trip["id"] and e.get("owner_id") == owner_id
            ]
            trip_events.sort(key=lambda e: (e.get("position", 0), e["id"]))
            for idx, ev in enumerate(trip_events):
                ev["position"] = idx

            trip["version"] += 1

    def reorder_events(
        self, owner_id: str, trip_id: str, version: int, event_ids: list[str]
    ) -> dict:
        with self.lock:
            trip = self.trips.get(trip_id)
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")
            if trip["version"] != version:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            trip_events = [
                e
                for e in self.events.values()
                if e.get("trip_id") == trip_id and e.get("owner_id") == owner_id
            ]
            existing_ids = {e["id"] for e in trip_events}

            if set(event_ids) != existing_ids or len(event_ids) != len(existing_ids):
                raise TravelValidationError("重排事件清單必須包含旅程中所有事件且不得重複。")

            events_by_id = {e["id"]: e for e in trip_events}
            # Dates nondecreasing; within day arbitrary. No cross-date reorder allowed.
            for i in range(len(event_ids) - 1):
                d1 = events_by_id[event_ids[i]]["date"]
                d2 = events_by_id[event_ids[i + 1]]["date"]
                if d1 > d2:
                    raise TravelValidationError("重排事件不得跨日期倒序。")

            for idx, eid in enumerate(event_ids):
                events_by_id[eid]["position"] = idx

            trip["version"] += 1
            return self.get_trip_detail(owner_id, trip_id)


class Neo4jTravelRepository:
    """Production Neo4j Travel Repository using pure Cypher and graph schema.

    No APOC, no travel data in AuthRecord JSON.
    Nodes: User, Trip, Event, Place, Category.
    Relationships: User-OWNS->Trip, Trip-HAS_EVENT->Event, Event-AT->Place,
                   User-OWNS_PLACE->Place, Event-HAS_CATEGORY->Category,
                   User-OWNS_CATEGORY->Category, Event-NEXT->Event.
    """

    def __init__(self, driver: Driver, database: str = "neo4j"):
        self.driver = driver
        self.database = database

    def initialize(self):
        with self.driver.session(database=self.database) as session:
            for label, prop in [
                ("Trip", "id"),
                ("Event", "id"),
                ("Place", "id"),
                ("Category", "id"),
            ]:
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                ).consume()
            # Backfill only ownership paths whose IDs and properties agree. Never infer
            # ownership from an unverified Event.owner_id property alone.
            session.run("""
                MATCH (u:User)-[:OWNS]->(t:Trip)-[:HAS_EVENT]->(e:Event)
                WHERE u.id = t.owner_id AND e.owner_id = u.id AND e.trip_id = t.id
                  AND NOT EXISTS { MATCH (other:Trip)-[:HAS_EVENT]->(e) WHERE other <> t }
                  AND NOT EXISTS { MATCH (other:User)-[:OWNS_EVENT]->(e) WHERE other <> u }
                MERGE (u)-[:OWNS_EVENT]->(e)
                SET e.record_scope = 'trip', e.timezone = coalesce(t.timezone, 'Asia/Taipei')
                """).consume()
            session.run("""
                CREATE INDEX event_owner_scope IF NOT EXISTS
                FOR (e:Event) ON (e.owner_id, e.record_scope, e.date)
                """).consume()

    def close(self):
        pass

    def get_trips(self, owner_id: str, *, include_cover: bool = False) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (u:User {id: $owner_id})-[:OWNS]->(t:Trip)
                RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                       t.timezone AS timezone, t.description AS description, t.version AS version,
                       CASE WHEN $include_cover AND EXISTS {
                           MATCH (u)-[:OWNS]->(cover:Photo {id: t.cover_photo_id, owner_id: $owner_id})
                           WHERE cover.thumbnail_path <> ''
                       } THEN t.cover_photo_id END AS cover_photo_id
                ORDER BY t.start_date DESC, t.id ASC
                """,
                owner_id=owner_id,
                include_cover=include_cover,
            )
            trips = [dict(record) for record in res]
            if not include_cover:
                for trip in trips:
                    trip.pop("cover_photo_id")
            return trips

    def get_trip(self, owner_id: str, trip_id: str) -> dict | None:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (u:User {id: $owner_id})-[:OWNS]->(t:Trip {id: $trip_id})
                RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                       t.timezone AS timezone, t.description AS description, t.version AS version
                """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            return dict(res) if res else None

    def get_trip_detail(self, owner_id: str, trip_id: str) -> dict | None:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            trip_res = tx.run(
                """
                    MATCH (u:User {id: $owner_id})-[:OWNS]->(t:Trip {id: $trip_id})
                    RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                           t.timezone AS timezone, t.description AS description, t.version AS version
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            if not trip_res:
                return None
            trip = dict(trip_res)

            events_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event {owner_id: $owner_id, trip_id: $trip_id})
                    MATCH (:User {id:$owner_id})-[:OWNS_EVENT]->(e)
                    RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                           e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                           e.time AS time, e.notes AS notes, e.position AS position, e.version AS version,
                           coalesce(t.timezone, 'Asia/Taipei') AS timezone, 'trip' AS record_scope
                    ORDER BY e.position ASC, e.id ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            events = [dict(r) for r in events_res]

            next_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e1:Event {owner_id:$owner_id, trip_id:$trip_id})-[:NEXT]->(e2:Event {owner_id:$owner_id, trip_id:$trip_id})
                    MATCH (t)-[:HAS_EVENT]->(e2)
                    RETURN e1.id AS from_id, e2.id AS to_id
                    ORDER BY e1.position ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            next_edges = [dict(r) for r in next_res]
            return {"trip": trip, "events": events, "next_edges": next_edges}

    def create_trip(self, owner_id: str, data: dict) -> dict:
        trip_id = str(uuid4())
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MERGE (u:User {id: $owner_id})
                CREATE (t:Trip {
                    id: $id,
                    owner_id: $owner_id,
                    name: $name,
                    start_date: $start_date,
                    end_date: $end_date,
                    timezone: $timezone,
                    description: $description,
                    version: 1
                })
                CREATE (u)-[:OWNS]->(t)
                RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                       t.timezone AS timezone, t.description AS description, t.version AS version
                """,
                owner_id=owner_id,
                id=trip_id,
                name=data["name"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                timezone=data.get("timezone", "Asia/Taipei"),
                description=data.get("description", ""),
            ).single()
            return dict(res)

    def update_trip(self, owner_id: str, trip_id: str, data: dict) -> dict:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            # Lock trip node and check version + event bounds
            check_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    WITH t
                    OPTIONAL MATCH (t)-[:HAS_EVENT]->(e:Event)
                    RETURN t.version AS version, min(e.date) AS min_date, max(e.date) AS max_date
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            if not check_res:
                raise TravelNotFoundError("找不到指定的旅程。")
            if check_res["version"] != data["version"]:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            min_date = check_res["min_date"]
            max_date = check_res["max_date"]
            if min_date is not None and (
                data["start_date"] > min_date or data["end_date"] < max_date
            ):
                raise TravelValidationError("旅程日期範圍不能縮小到排除現有事件。")

            upd = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.name = $name,
                        t.start_date = $start_date,
                        t.end_date = $end_date,
                        t.timezone = $timezone,
                        t.description = $description,
                        t.version = t.version + 1
                    RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                           t.timezone AS timezone, t.description AS description, t.version AS version
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
                name=data["name"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                timezone=data.get("timezone", "Asia/Taipei"),
                description=data.get("description", ""),
            ).single()
            tx.run("""
                MATCH (:Trip {id:$trip, owner_id:$owner})-[:HAS_EVENT]->(e:Event {owner_id:$owner, trip_id:$trip})
                SET e.timezone=$zone
                """, owner=owner_id, trip=trip_id, zone=data.get("timezone", "Asia/Taipei")).consume()
            tx.commit()
            return dict(upd)

    def delete_trip(self, owner_id: str, trip_id: str, version: int) -> None:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            check_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    RETURN t.version AS version
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            if not check_res:
                raise TravelNotFoundError("找不到指定的旅程。")
            if check_res["version"] != version:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            # Remove private draft text in the same transaction as its journal.
            tx.run(
                """
                    MATCH (:Trip {id: $trip_id, owner_id: $owner_id})
                          -[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {owner_id: $owner_id})
                    DETACH DELETE d
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).consume()
            # Delete events and NEXT edges; retain reusable Places
            tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    OPTIONAL MATCH (t)-[:HAS_EVENT]->(e:Event)
                    DETACH DELETE e
                    DETACH DELETE t
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).consume()
            tx.commit()

    def get_places(self, owner_id: str) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (p:Place {owner_id: $owner_id})
                RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                ORDER BY p.name ASC, p.id ASC
                """,
                owner_id=owner_id,
            )
            return [dict(r) for r in res]

    def get_place(self, owner_id: str, place_id: str) -> dict | None:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (p:Place {id: $place_id, owner_id: $owner_id})
                RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                """,
                owner_id=owner_id,
                place_id=place_id,
            ).single()
            return dict(res) if res else None

    def get_event(self, owner_id: str, event_id: str) -> dict | None:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (:User {id: $owner_id})-[:OWNS_EVENT]->(e:Event {id: $event_id, owner_id: $owner_id})
                OPTIONAL MATCH (:User {id: $owner_id})-[:OWNS]->(t:Trip {owner_id: $owner_id})-[:HAS_EVENT]->(e)
                WITH e, t WHERE (e.trip_id IS NULL AND NOT EXISTS { MATCH (:Trip)-[:HAS_EVENT]->(e) }) OR e.trip_id = t.id
                RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                       e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                       e.time AS time, e.notes AS notes, e.position AS position, e.version AS version,
                       t.name AS trip_name, coalesce(t.timezone, e.timezone, 'Asia/Taipei') AS timezone,
                       CASE WHEN e.trip_id IS NULL THEN 'standalone' ELSE 'trip' END AS record_scope
                """,
                owner_id=owner_id,
                event_id=event_id,
            ).single()
            return dict(res) if res else None

    @staticmethod
    def _locked_trip(tx, owner_id: str, trip_id: str) -> dict:
        row = tx.run("""
            MATCH (:User {id:$owner})-[:OWNS]->(t:Trip {id:$id, owner_id:$owner})
            SET t.__lock = coalesce(t.__lock, 0) + 1
            RETURN properties(t) AS trip
            """, owner=owner_id, id=trip_id).single()
        if not row:
            raise TravelNotFoundError("找不到指定的手記。")
        return dict(row["trip"])

    @staticmethod
    def _locked_event(tx, owner_id: str, event_id: str) -> dict:
        # SET establishes a node write lock before the following query reads state.
        locked = tx.run("""
            MATCH (e:Event {id:$id, owner_id:$owner})
            SET e.__standalone_lock = coalesce(e.__standalone_lock, 0) + 1
            RETURN e.id AS id
            """, owner=owner_id, id=event_id).single()
        if not locked:
            raise TravelNotFoundError("找不到指定的足跡。")
        row = tx.run("MATCH (:User {id:$owner})-[:OWNS_EVENT]->(e:Event {id:$id, owner_id:$owner}) RETURN properties(e) AS event",
                     owner=owner_id, id=event_id).single()
        if not row:
            raise TravelNotFoundError("找不到指定的足跡。")
        return dict(row["event"])

    @staticmethod
    def _event_links(tx, owner_id: str, data: dict) -> tuple[dict, str]:
        if data.get("place_id"):
            row = tx.run("""MATCH (:User {id:$owner})-[:OWNS_PLACE]->(p:Place {id:$id, owner_id:$owner})
                            RETURN properties(p) AS place""", owner=owner_id, id=data["place_id"]).single()
            if not row:
                raise TravelNotFoundError("找不到指定的地點。")
            place = dict(row["place"])
        else:
            place = {"id": str(uuid4()), "owner_id": owner_id, "name": data["place_name"],
                     "city": data.get("city", ""), "address": data.get("address", "")}
            tx.run("""MERGE (u:User {id:$owner}) CREATE (p:Place) SET p=$place
                      CREATE (u)-[:OWNS_PLACE]->(p)""", owner=owner_id, place=place).consume()
        category = data.get("category", "未分類")
        cat_id = deterministic_category_id(owner_id, category.strip())
        tx.run("""MERGE (u:User {id:$owner}) MERGE (c:Category {id:$id})
                  ON CREATE SET c.owner_id=$owner, c.name=$name, c.normalized_name=$norm
                  MERGE (u)-[:OWNS_CATEGORY]->(c)""",
               owner=owner_id, id=cat_id, name=category, norm=category.strip()).consume()
        return place, cat_id

    @staticmethod
    def _trip_event_rows(tx, owner_id: str, trip_id: str) -> list[dict]:
        return [dict(row) for row in tx.run("""
            MATCH (:User {id:$owner})-[:OWNS_EVENT]->(e:Event {owner_id:$owner, trip_id:$trip})
                  <-[:HAS_EVENT]-(:Trip {id:$trip, owner_id:$owner})
            RETURN e.id AS id, e.date AS date, e.position AS position
            ORDER BY e.position, e.id
            """, owner=owner_id, trip=trip_id)]

    @staticmethod
    def _set_trip_order(tx, owner_id: str, trip_id: str, rows: list[dict]):
        updates = [{"id": row["id"], "position": pos} for pos, row in enumerate(rows)]
        tx.run("""UNWIND $updates AS row
                  MATCH (:Trip {id:$trip, owner_id:$owner})-[:HAS_EVENT]->(e:Event {id:row.id, owner_id:$owner})
                  SET e.position=row.position""", updates=updates, owner=owner_id, trip=trip_id).consume()
        tx.run("""MATCH (:Trip {id:$trip, owner_id:$owner})-[:HAS_EVENT]->(e:Event {owner_id:$owner})-[r:NEXT]->()
                  DELETE r""", trip=trip_id, owner=owner_id).consume()
        tx.run("""UNWIND $pairs AS pair
                  MATCH (t:Trip {id:$trip, owner_id:$owner})-[:HAS_EVENT]->(a:Event {id:pair.from_id, owner_id:$owner})
                  MATCH (t)-[:HAS_EVENT]->(b:Event {id:pair.to_id, owner_id:$owner})
                  CREATE (a)-[:NEXT]->(b)""",
               pairs=build_next_edges(rows), trip=trip_id, owner=owner_id).consume()
        tx.run("""MATCH (t:Trip {id:$trip, owner_id:$owner}) SET t.version=t.version+1""",
               trip=trip_id, owner=owner_id).consume()

    def list_standalone_events(self, owner_id: str, *, q: str = "", city: str | None = None,
                               category: str | None = None, date_from: str | None = None,
                               date_to: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        with self.driver.session(database=self.database) as session:
            rows = list(session.run("""
                MATCH (:User {id:$owner})-[:OWNS_EVENT]->(e:Event {owner_id:$owner, record_scope:'standalone'})
                WHERE e.trip_id IS NULL AND NOT EXISTS { MATCH (:Trip)-[:HAS_EVENT]->(e) }
                  AND ($city IS NULL OR e.city=$city) AND ($category IS NULL OR e.category=$category)
                  AND ($date_from IS NULL OR e.date >= $date_from) AND ($date_to IS NULL OR e.date <= $date_to)
                  AND ($q='' OR toLower(coalesce(e.place_name,'')+' '+coalesce(e.city,'')+' '+coalesce(e.address,'')+' '+
                       coalesce(e.category,'')+' '+coalesce(e.notes,'')) CONTAINS $q)
                RETURN properties(e) AS event ORDER BY e.date DESC, coalesce(e.time,'') DESC,
                    coalesce(e.created_at,'') DESC, e.id ASC
                SKIP $offset LIMIT $limit
                """, owner=owner_id, city=city or None, category=category or None,
                date_from=date_from, date_to=date_to, q=q.strip().lower(), offset=offset, limit=limit+1))
            return {"items": [format_event(dict(row["event"])) for row in rows[:limit]],
                    "next_offset": offset+limit if len(rows)>limit else None}

    def create_standalone_event(self, owner_id: str, data: dict) -> dict:
        return self._create_event(owner_id, None, data)

    def create_event(self, owner_id: str, trip_id: str, data: dict) -> dict:
        return self._create_event(owner_id, trip_id, data)

    def _create_event(self, owner_id: str, trip_id: str | None, data: dict) -> dict:
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip = self._locked_trip(tx, owner_id, trip_id) if trip_id else None
            if trip and not trip["start_date"] <= data["date"] <= trip["end_date"]:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")
            place, cat_id = self._event_links(tx, owner_id, data)
            event = {"id": str(uuid4()), "owner_id": owner_id, "trip_id": trip_id,
                     "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds"),
                     "record_scope": "trip" if trip else "standalone",
                     "timezone": normalize_timezone(trip.get("timezone", "Asia/Taipei") if trip else data.get("timezone", "Asia/Taipei")),
                     "place_id": place["id"], "place_name": place["name"], "city": place.get("city", ""),
                     "address": place.get("address", ""), "category": data.get("category", "未分類"),
                     "date": data["date"], "time": data.get("time"), "notes": data.get("notes", ""),
                     "position": None, "version": 1, "embedding_status": "pending", "embedded_version": 0}
            rows = self._trip_event_rows(tx, owner_id, trip_id) if trip else []
            if trip:
                event["position"] = find_event_insert_index(rows, event["date"])
                rows.insert(event["position"], event)
            tx.run("""MATCH (u:User {id:$owner})
                      MATCH (p:Place {id:$place, owner_id:$owner}), (c:Category {id:$category, owner_id:$owner})
                      CREATE (e:Event) SET e=$event
                      CREATE (u)-[:OWNS_EVENT]->(e), (e)-[:AT]->(p), (e)-[:HAS_CATEGORY]->(c)""",
                   owner=owner_id, place=place["id"], category=cat_id, event=event).consume()
            if trip:
                tx.run("""MATCH (t:Trip {id:$trip, owner_id:$owner}), (e:Event {id:$event, owner_id:$owner})
                          CREATE (t)-[:HAS_EVENT]->(e)""", trip=trip_id, event=event["id"], owner=owner_id).consume()
                self._set_trip_order(tx, owner_id, trip_id, rows)
            tx.commit()
            return format_event(event)

    @optimistic_write
    def update_event(self, owner_id: str, event_id: str, data: dict) -> dict:
        current = self.get_event(owner_id, event_id)
        if not current:
            raise TravelNotFoundError("找不到指定的足跡。")
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip_id = current.get("trip_id")
            trip = self._locked_trip(tx, owner_id, trip_id) if trip_id else None
            event = self._locked_event(tx, owner_id, event_id)
            if event.get("trip_id") != trip_id or event["version"] != data["version"]:
                raise TravelConflictError("足跡已被修改，請重新整理後再試。")
            if trip and not trip["start_date"] <= data["date"] <= trip["end_date"]:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")
            zone = normalize_timezone((trip or {}).get("timezone") or data.get("timezone") or event.get("timezone", "Asia/Taipei"))
            if trip and data.get("timezone") and normalize_timezone(data["timezone"]) != zone:
                raise TravelValidationError("手記足跡使用手記的時區，請於編輯手記調整。")
            place, cat_id = self._event_links(tx, owner_id, data)
            rows = self._trip_event_rows(tx, owner_id, trip_id) if trip else []
            if trip and data["date"] != event["date"]:
                rows = [row for row in rows if row["id"] != event_id]
                rows.insert(find_event_insert_index(rows, data["date"]), {"id":event_id,"date":data["date"]})
            event.update(place_id=place["id"], place_name=place["name"], city=place.get("city", ""),
                         address=place.get("address", ""), category=data["category"], date=data["date"],
                         time=data.get("time"), notes=data.get("notes", ""), timezone=zone,
                         version=event["version"]+1, embedding_status="pending",
                         position=next((pos for pos,row in enumerate(rows) if row["id"]==event_id), None))
            event.pop("__standalone_lock", None)
            tx.run("""MATCH (e:Event {id:$id, owner_id:$owner}) SET e=$event
                      WITH e OPTIONAL MATCH (e)-[r:AT|HAS_CATEGORY]->() DELETE r""",
                   id=event_id, owner=owner_id, event=event).consume()
            tx.run("""MATCH (e:Event {id:$id, owner_id:$owner}), (p:Place {id:$place, owner_id:$owner}),
                            (c:Category {id:$category, owner_id:$owner})
                      CREATE (e)-[:AT]->(p), (e)-[:HAS_CATEGORY]->(c)""",
                   id=event_id, owner=owner_id, place=place["id"], category=cat_id).consume()
            if trip:
                self._set_trip_order(tx, owner_id, trip_id, rows)
            tx.commit()
            return format_event(event)

    @optimistic_write
    def delete_event(self, owner_id: str, event_id: str, version: int) -> None:
        current = self.get_event(owner_id, event_id)
        if not current:
            raise TravelNotFoundError("找不到指定的足跡。")
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip_id = current.get("trip_id")
            if trip_id:
                self._locked_trip(tx, owner_id, trip_id)
            event = self._locked_event(tx, owner_id, event_id)
            if event.get("trip_id") != trip_id or event["version"] != version:
                raise TravelConflictError("足跡已被修改，請重新整理後再試。")
            tx.run("MATCH (e:Event {id:$id, owner_id:$owner}) DETACH DELETE e",
                   id=event_id, owner=owner_id).consume()
            if trip_id:
                self._set_trip_order(tx, owner_id, trip_id, self._trip_event_rows(tx, owner_id, trip_id))
            tx.commit()

    @optimistic_write
    def attach_event_to_trip(self, owner_id: str, event_id: str, data: dict) -> dict:
        from backend.photo_store import sync_event_photo_trip

        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            event = self._locked_event(tx, owner_id, event_id)
            if event.get("trip_id") or event["version"] != data["version"]:
                raise TravelConflictError("足跡已被修改或已屬於手記，請重新整理後再試。")
            trip_id = data["trip_id"]
            trip = self._locked_trip(tx, owner_id, trip_id)
            if trip["version"] != data["trip_version"]:
                raise TravelConflictError("手記已被修改，請重新整理後再試。")
            rows = self._trip_event_rows(tx, owner_id, trip_id)
            position = validate_attachment(event, trip, rows, data.get("before_event_id"))
            rows.insert(position, {"id":event_id,"date":event["date"]})
            tx.run("""MATCH (t:Trip {id:$trip, owner_id:$owner}), (e:Event {id:$id, owner_id:$owner})
                      CREATE (t)-[:HAS_EVENT]->(e)
                      SET e.trip_id=$trip, e.record_scope='trip', e.timezone=$zone,
                          e.version=e.version+1, e.embedding_status='pending'
                      REMOVE e.__standalone_lock""",
                   owner=owner_id, id=event_id, trip=trip_id, zone=trip.get("timezone", "Asia/Taipei")).consume()
            sync_event_photo_trip(tx, owner_id, event_id, trip_id)
            self._set_trip_order(tx, owner_id, trip_id, rows)
            event.update(trip_id=trip_id, timezone=trip.get("timezone", "Asia/Taipei"), record_scope="trip",
                         version=event["version"]+1, position=position, embedding_status="pending")
            tx.commit()
            return format_event(event)

    def reorder_events(
        self, owner_id: str, trip_id: str, version: int, event_ids: list[str]
    ) -> dict:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            trip_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    RETURN t.version AS version
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            if not trip_res:
                raise TravelNotFoundError("找不到指定的旅程。")
            if trip_res["version"] != version:
                raise TravelConflictError("旅程已被修改，請重新整理後再試。")

            ev_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event)
                    RETURN e.id AS id, e.date AS date, e.position AS position
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            existing_events = [dict(r) for r in ev_res]
            existing_ids = {e["id"] for e in existing_events}

            if set(event_ids) != existing_ids or len(event_ids) != len(existing_ids):
                raise TravelValidationError("重排事件清單必須包含旅程中所有事件且不得重複。")

            events_by_id = {e["id"]: e for e in existing_events}
            for i in range(len(event_ids) - 1):
                d1 = events_by_id[event_ids[i]]["date"]
                d2 = events_by_id[event_ids[i + 1]]["date"]
                if d1 > d2:
                    raise TravelValidationError("重排事件不得跨日期倒序。")

            pos_updates = [{"id": eid, "position": idx} for idx, eid in enumerate(event_ids)]
            tx.run(
                """
                    UNWIND $updates AS u
                    MATCH (e:Event {id: u.id})
                    SET e.position = u.position
                    """,
                updates=pos_updates,
            ).consume()

            # Rebuild NEXT edges
            tx.run(
                """
                    MATCH (t:Trip {id: $trip_id})-[:HAS_EVENT]->(e1:Event)-[r:NEXT]->(e2:Event)
                    DELETE r
                    """,
                trip_id=trip_id,
            ).consume()

            pairs = [
                {"from_id": event_ids[i], "to_id": event_ids[i + 1]}
                for i in range(len(event_ids) - 1)
            ]
            if pairs:
                tx.run(
                    """
                        UNWIND $pairs AS p
                        MATCH (e1:Event {id: p.from_id})
                        MATCH (e2:Event {id: p.to_id})
                        CREATE (e1)-[:NEXT]->(e2)
                        """,
                    pairs=pairs,
                ).consume()

            # Increment trip version
            tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.version = t.version + 1
                    """,
                trip_id=trip_id,
                owner_id=owner_id,
            ).consume()

            tx.commit()

        return self.get_trip_detail(owner_id, trip_id)
