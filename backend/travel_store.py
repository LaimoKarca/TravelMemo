from threading import RLock
from uuid import NAMESPACE_URL, uuid4, uuid5

from neo4j import Driver


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
        "trip_id": e["trip_id"],
        "place_id": e["place_id"],
        "place_name": e["place_name"],
        "city": e.get("city", ""),
        "address": e.get("address", ""),
        "category": e["category"],
        "date": e["date"],
        "time": e.get("time"),
        "notes": e.get("notes", ""),
        "position": e.get("position", 0),
        "version": e["version"],
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

    def initialize(self):
        pass

    def close(self):
        pass

    def get_trips(self, owner_id: str) -> list[dict]:
        with self.lock:
            user_trips = [
                format_trip(t) for t in self.trips.values() if t.get("owner_id") == owner_id
            ]
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
            trip = self.trips.get(event["trip_id"])
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

    def update_event(self, owner_id: str, event_id: str, data: dict) -> dict:
        with self.lock:
            event = self.events.get(event_id)
            if not event or event.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的事件。")
            if event["version"] != data["version"]:
                raise TravelConflictError("事件已被修改，請重新整理後再試。")

            trip = self.trips.get(event["trip_id"])
            if not trip or trip.get("owner_id") != owner_id:
                raise TravelNotFoundError("找不到指定的旅程。")

            if data["date"] < trip["start_date"] or data["date"] > trip["end_date"]:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")

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

    def close(self):
        pass

    def get_trips(self, owner_id: str) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            res = session.run(
                """
                MATCH (u:User {id: $owner_id})-[:OWNS]->(t:Trip)
                RETURN t.id AS id, t.name AS name, t.start_date AS start_date, t.end_date AS end_date,
                       t.timezone AS timezone, t.description AS description, t.version AS version
                ORDER BY t.start_date DESC, t.id ASC
                """,
                owner_id=owner_id,
            )
            return [dict(record) for record in res]

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
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event)
                    RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                           e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                           e.time AS time, e.notes AS notes, e.position AS position, e.version AS version
                    ORDER BY e.position ASC, e.id ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            events = [dict(r) for r in events_res]

            next_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e1:Event)-[:NEXT]->(e2:Event)
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
                MATCH (t:Trip {owner_id: $owner_id})-[:HAS_EVENT]->(e:Event {id: $event_id, owner_id: $owner_id})
                RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                       e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                       e.time AS time, e.notes AS notes, e.position AS position, e.version AS version,
                       t.name AS trip_name
                """,
                owner_id=owner_id,
                event_id=event_id,
            ).single()
            return dict(res) if res else None

    def create_event(self, owner_id: str, trip_id: str, data: dict) -> dict:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            # Lock trip node
            trip_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    RETURN t.version AS version, t.start_date AS start_date, t.end_date AS end_date
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            ).single()
            if not trip_res:
                raise TravelNotFoundError("找不到指定的旅程。")

            start_date = trip_res["start_date"]
            end_date = trip_res["end_date"]
            if data["date"] < start_date or data["date"] > end_date:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")

            # Resolve Place
            place_id = data.get("place_id")
            if place_id:
                p_res = tx.run(
                    """
                        MATCH (p:Place {id: $place_id, owner_id: $owner_id})
                        RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                        """,
                    owner_id=owner_id,
                    place_id=place_id,
                ).single()
                if not p_res:
                    raise TravelNotFoundError("找不到指定的地點。")
                place = dict(p_res)
            else:
                new_place_id = str(uuid4())
                p_res = tx.run(
                    """
                        MERGE (u:User {id: $owner_id})
                        CREATE (p:Place {
                            id: $id,
                            owner_id: $owner_id,
                            name: $name,
                            city: $city,
                            address: $address
                        })
                        CREATE (u)-[:OWNS_PLACE]->(p)
                        RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                        """,
                    owner_id=owner_id,
                    id=new_place_id,
                    name=data["place_name"],
                    city=data.get("city", ""),
                    address=data.get("address", ""),
                ).single()
                place = dict(p_res)

            # Resolve Category deterministically under owner
            norm = data["category"].strip()
            cat_id = deterministic_category_id(owner_id, norm)
            tx.run(
                """
                    MERGE (u:User {id: $owner_id})
                    MERGE (c:Category {id: $cat_id})
                    ON CREATE SET c.owner_id = $owner_id, c.name = $name, c.normalized_name = $norm
                    MERGE (u)-[:OWNS_CATEGORY]->(c)
                    """,
                owner_id=owner_id,
                cat_id=cat_id,
                name=data["category"],
                norm=norm,
            ).consume()

            # Get existing events ordered by position
            ev_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event)
                    RETURN e.id AS id, e.date AS date, e.position AS position
                    ORDER BY e.position ASC, e.id ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            existing_events = [dict(r) for r in ev_res]

            insert_idx = find_event_insert_index(existing_events, data["date"])

            event_id = str(uuid4())
            new_event_meta = {"id": event_id, "date": data["date"], "position": insert_idx}
            existing_events.insert(insert_idx, new_event_meta)

            # Create event node and relationships
            created_ev = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})
                    MATCH (p:Place {id: $place_id, owner_id: $owner_id})
                    MATCH (c:Category {id: $cat_id})
                    CREATE (e:Event {
                        id: $id,
                        trip_id: $trip_id,
                        owner_id: $owner_id,
                        place_id: $place_id,
                        place_name: $place_name,
                        city: $city,
                        address: $address,
                        category: $category,
                        date: $date,
                        time: $time,
                        notes: $notes,
                        position: $position,
                        version: 1,
                        embedding_status: 'pending',
                        embedded_version: 0
                    })
                    CREATE (t)-[:HAS_EVENT]->(e)
                    CREATE (e)-[:AT]->(p)
                    CREATE (e)-[:HAS_CATEGORY]->(c)
                    RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                           e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                           e.time AS time, e.notes AS notes, e.position AS position, e.version AS version
                    """,
                trip_id=trip_id,
                owner_id=owner_id,
                place_id=place["id"],
                cat_id=cat_id,
                id=event_id,
                place_name=place["name"],
                city=place["city"],
                address=place["address"],
                category=data["category"],
                date=data["date"],
                time=data.get("time"),
                notes=data.get("notes", ""),
                position=insert_idx,
            ).single()

            # Update positions
            pos_updates = [
                {"id": ev["id"], "position": idx}
                for idx, ev in enumerate(existing_events)
                if ev["position"] != idx or ev["id"] == event_id
            ]
            if pos_updates:
                tx.run(
                    """
                        UNWIND $updates AS u
                        MATCH (e:Event {id: u.id})
                        SET e.position = u.position
                        """,
                    updates=pos_updates,
                ).consume()

            # Rebuild NEXT edges in this trip
            tx.run(
                """
                    MATCH (t:Trip {id: $trip_id})-[:HAS_EVENT]->(e1:Event)-[r:NEXT]->(e2:Event)
                    DELETE r
                    """,
                trip_id=trip_id,
            ).consume()

            pairs = [
                {"from_id": existing_events[i]["id"], "to_id": existing_events[i + 1]["id"]}
                for i in range(len(existing_events) - 1)
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
            return dict(created_ev)

    def update_event(self, owner_id: str, event_id: str, data: dict) -> dict:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            check_res = tx.run(
                """
                    MATCH (e:Event {id: $event_id, owner_id: $owner_id})
                    MATCH (t:Trip {id: e.trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    RETURN e.version AS event_version, e.trip_id AS trip_id, e.date AS old_date,
                           t.start_date AS start_date, t.end_date AS end_date
                    """,
                owner_id=owner_id,
                event_id=event_id,
            ).single()
            if not check_res:
                raise TravelNotFoundError("找不到指定的事件。")
            if check_res["event_version"] != data["version"]:
                raise TravelConflictError("事件已被修改，請重新整理後再試。")

            trip_id = check_res["trip_id"]
            old_date = check_res["old_date"]
            start_date = check_res["start_date"]
            end_date = check_res["end_date"]

            if data["date"] < start_date or data["date"] > end_date:
                raise TravelValidationError("事件日期必須在旅程日期範圍內。")

            # Place resolution
            place_id = data.get("place_id")
            if place_id:
                p_res = tx.run(
                    """
                        MATCH (p:Place {id: $place_id, owner_id: $owner_id})
                        RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                        """,
                    owner_id=owner_id,
                    place_id=place_id,
                ).single()
                if not p_res:
                    raise TravelNotFoundError("找不到指定的地點。")
                place = dict(p_res)
            else:
                new_place_id = str(uuid4())
                p_res = tx.run(
                    """
                        MERGE (u:User {id: $owner_id})
                        CREATE (p:Place {
                            id: $id,
                            owner_id: $owner_id,
                            name: $name,
                            city: $city,
                            address: $address
                        })
                        CREATE (u)-[:OWNS_PLACE]->(p)
                        RETURN p.id AS id, p.name AS name, p.city AS city, p.address AS address
                        """,
                    owner_id=owner_id,
                    id=new_place_id,
                    name=data["place_name"],
                    city=data.get("city", ""),
                    address=data.get("address", ""),
                ).single()
                place = dict(p_res)

            # Resolve Category deterministically under owner
            norm = data["category"].strip()
            cat_id = deterministic_category_id(owner_id, norm)
            tx.run(
                """
                    MERGE (u:User {id: $owner_id})
                    MERGE (c:Category {id: $cat_id})
                    ON CREATE SET c.owner_id = $owner_id, c.name = $name, c.normalized_name = $norm
                    MERGE (u)-[:OWNS_CATEGORY]->(c)
                    """,
                owner_id=owner_id,
                cat_id=cat_id,
                name=data["category"],
                norm=norm,
            ).consume()

            # Ordering
            ev_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event)
                    RETURN e.id AS id, e.date AS date, e.position AS position
                    ORDER BY e.position ASC, e.id ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            existing_events = [dict(r) for r in ev_res]

            new_date = data["date"]
            if old_date != new_date:
                # Move to end of new date group
                existing_events = [e for e in existing_events if e["id"] != event_id]
                insert_idx = find_event_insert_index(existing_events, new_date)
                existing_events.insert(insert_idx, {"id": event_id, "date": new_date})

            pos_map = {ev["id"]: idx for idx, ev in enumerate(existing_events)}

            # Update event node
            upd_ev = tx.run(
                """
                    MATCH (e:Event {id: $event_id, owner_id: $owner_id})
                    MATCH (p:Place {id: $place_id, owner_id: $owner_id})
                    MATCH (c:Category {id: $cat_id})
                    SET e.place_id = $place_id,
                        e.place_name = $place_name,
                        e.city = $city,
                        e.address = $address,
                        e.category = $category,
                        e.date = $date,
                        e.time = $time,
                        e.notes = $notes,
                        e.position = $position,
                        e.version = e.version + 1,
                        e.embedding_status = 'pending'
                    WITH e, p, c
                    OPTIONAL MATCH (e)-[r1:AT]->(:Place)
                    DELETE r1
                    WITH e, p, c
                    OPTIONAL MATCH (e)-[r2:HAS_CATEGORY]->(:Category)
                    DELETE r2
                    CREATE (e)-[:AT]->(p)
                    CREATE (e)-[:HAS_CATEGORY]->(c)
                    RETURN e.id AS id, e.trip_id AS trip_id, e.place_id AS place_id, e.place_name AS place_name,
                           e.city AS city, e.address AS address, e.category AS category, e.date AS date,
                           e.time AS time, e.notes AS notes, e.position AS position, e.version AS version
                    """,
                event_id=event_id,
                owner_id=owner_id,
                place_id=place["id"],
                cat_id=cat_id,
                place_name=place["name"],
                city=place["city"],
                address=place["address"],
                category=data["category"],
                date=new_date,
                time=data.get("time"),
                notes=data.get("notes", ""),
                position=pos_map[event_id],
            ).single()

            if old_date != new_date:
                pos_updates = [{"id": eid, "position": pos} for eid, pos in pos_map.items()]
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
                    {
                        "from_id": existing_events[i]["id"],
                        "to_id": existing_events[i + 1]["id"],
                    }
                    for i in range(len(existing_events) - 1)
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
            return dict(upd_ev)

    def delete_event(self, owner_id: str, event_id: str, version: int) -> None:
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            check_res = tx.run(
                """
                    MATCH (e:Event {id: $event_id, owner_id: $owner_id})
                    MATCH (t:Trip {id: e.trip_id, owner_id: $owner_id})
                    SET t.__lock = coalesce(t.__lock, 0) + 1
                    RETURN e.version AS event_version, e.trip_id AS trip_id
                    """,
                owner_id=owner_id,
                event_id=event_id,
            ).single()
            if not check_res:
                raise TravelNotFoundError("找不到指定的事件。")
            if check_res["event_version"] != version:
                raise TravelConflictError("事件已被修改，請重新整理後再試。")

            trip_id = check_res["trip_id"]

            # Delete event (Place is preserved)
            tx.run(
                """
                    MATCH (e:Event {id: $event_id})
                    DETACH DELETE e
                    """,
                event_id=event_id,
            ).consume()

            # Remaining events
            ev_res = tx.run(
                """
                    MATCH (t:Trip {id: $trip_id, owner_id: $owner_id})-[:HAS_EVENT]->(e:Event)
                    RETURN e.id AS id, e.position AS position
                    ORDER BY e.position ASC, e.id ASC
                    """,
                owner_id=owner_id,
                trip_id=trip_id,
            )
            remaining = [dict(r) for r in ev_res]

            pos_updates = [{"id": ev["id"], "position": idx} for idx, ev in enumerate(remaining)]
            if pos_updates:
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
                {"from_id": remaining[i]["id"], "to_id": remaining[i + 1]["id"]}
                for i in range(len(remaining) - 1)
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
