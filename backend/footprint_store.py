"""Private footprint drafts and atomic, idempotent journal additions."""

import copy
import datetime
import json
from uuid import uuid4

from backend.locations import stored_location
from backend.travel_store import (
    TravelConflictError,
    TravelNotFoundError,
    TravelValidationError,
    deterministic_category_id,
    find_event_insert_index,
    format_event,
)


def _now():
    return datetime.datetime.now(datetime.UTC).isoformat()


class FootprintStore:
    def __init__(self, repository):
        self.repository = repository
        self.driver = getattr(repository, "driver", None)
        self.database = getattr(repository, "database", "neo4j")
        if self.driver is None:
            self.lock = repository.lock
            with self.lock:
                if not hasattr(repository, "_footprint_drafts"):
                    repository._footprint_drafts = {}
                self.records = repository._footprint_drafts

    def initialize(self):
        if self.driver is not None:
            with self.driver.session(database=self.database) as session:
                session.run("CREATE CONSTRAINT footprint_draft_id IF NOT EXISTS FOR (d:FootprintDraft) REQUIRE d.id IS UNIQUE").consume()
                session.run("CREATE INDEX footprint_draft_status IF NOT EXISTS FOR (d:FootprintDraft) ON (d.status)").consume()

    @staticmethod
    def _decode(node):
        return json.loads(node["record_json"])

    @staticmethod
    def _write(tx, record):
        tx.run("""
            MATCH (d:FootprintDraft {id:$id,owner_id:$owner,trip_id:$trip})
            SET d.record_json=$record,d.version=$version,d.status=$status,d.request_id=$request_id,d.updated_at=$updated_at
            """, id=record["id"], owner=record["owner_id"], trip=record["trip_id"],
            record=json.dumps(record, ensure_ascii=False), version=record["version"],
            status=record["status"], request_id=record.get("request_id"), updated_at=record["updated_at"]).consume()

    def _owned_memory(self, owner, trip_id, draft_id):
        trip = self.repository.get_trip(owner, trip_id)
        record = self.records.get(draft_id)
        if not trip or not record or record["owner_id"] != owner or record["trip_id"] != trip_id:
            raise TravelNotFoundError("找不到足跡草稿。")
        return trip, record

    def _locked_neo(self, tx, owner, trip_id, draft_id):
        trip = tx.run("""
            MATCH (t:Trip {id:$trip,owner_id:$owner})
            SET t.__lock=coalesce(t.__lock,0)+1 RETURN properties(t) AS t
            """, trip=trip_id, owner=owner).single()
        if not trip:
            raise TravelNotFoundError("找不到手記。")
        row = tx.run("""
            MATCH (:Trip {id:$trip,owner_id:$owner})-[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {id:$id,owner_id:$owner})
            RETURN properties(d) AS d
            """, trip=trip_id, owner=owner, id=draft_id).single()
        if not row:
            raise TravelNotFoundError("找不到足跡草稿。")
        return dict(trip["t"]), self._decode(row["d"])

    @staticmethod
    def _record_date_in_trip(trip, record_date, required=False):
        if record_date is None and not required:
            return
        try:
            datetime.date.fromisoformat(record_date)
        except (ValueError, TypeError):
            raise TravelValidationError("記錄日期格式不正確。") from None
        if not trip["start_date"] <= record_date <= trip["end_date"]:
            raise TravelValidationError("記錄日期必須在手記期間內。")

    def create(self, owner, trip_id, record_date=None, text=""):
        record = {"id": str(uuid4()), "owner_id": owner, "trip_id": trip_id, "record_date": record_date,
                      "text": text, "items": [], "status": "editing", "version": 1, "request_id": None,
                      "generation_requests": {}, "error": None, "created_at": _now(), "updated_at": _now()}
        if self.driver is None:
            with self.lock:
                trip = self.repository.get_trip(owner, trip_id)
                if not trip:
                    raise TravelNotFoundError("找不到手記。")
                self._record_date_in_trip(trip, record_date)
                record["trip_version"] = trip["version"]
                self.records[record["id"]] = record
                return copy.deepcopy(record)
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip = tx.run("MATCH (t:Trip {id:$trip,owner_id:$owner}) SET t.__lock=coalesce(t.__lock,0)+1 RETURN t.version AS version,t.start_date AS start_date,t.end_date AS end_date", trip=trip_id, owner=owner).single()
            if not trip:
                raise TravelNotFoundError("找不到手記。")
            self._record_date_in_trip(trip, record_date)
            record["trip_version"] = trip["version"]
            tx.run("""
                MATCH (t:Trip {id:$trip,owner_id:$owner})
                CREATE (d:FootprintDraft {id:$id,owner_id:$owner,trip_id:$trip,version:1,status:'editing',record_json:$record,updated_at:$updated_at})
                CREATE (t)-[:HAS_FOOTPRINT_DRAFT]->(d)
                """, trip=trip_id, owner=owner, id=record["id"], record=json.dumps(record, ensure_ascii=False), updated_at=record["updated_at"]).consume()
            tx.commit()
        return copy.deepcopy(record)

    def get(self, owner, trip_id, draft_id):
        if self.driver is None:
            with self.lock:
                _, record = self._owned_memory(owner, trip_id, draft_id)
                return copy.deepcopy(record)
        with self.driver.session(database=self.database) as session:
            row = session.run("""
                MATCH (:Trip {id:$trip,owner_id:$owner})-[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {id:$id,owner_id:$owner})
                RETURN properties(d) AS d
                """, trip=trip_id, owner=owner, id=draft_id).single()
            if not row:
                raise TravelNotFoundError("找不到足跡草稿。")
            return self._decode(row["d"])

    def latest(self, owner, trip_id):
        if self.driver is None:
            with self.lock:
                if not self.repository.get_trip(owner, trip_id):
                    raise TravelNotFoundError("找不到手記。")
                records = [r for r in self.records.values() if r["owner_id"] == owner and r["trip_id"] == trip_id and r["status"] != "committed"]
                return copy.deepcopy(max(records, key=lambda r: (r["updated_at"], r["id"]))) if records else None
        with self.driver.session(database=self.database) as session:
            if not self.repository.get_trip(owner, trip_id):
                raise TravelNotFoundError("找不到手記。")
            row = session.run("""
                MATCH (:Trip {id:$trip,owner_id:$owner})-[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {owner_id:$owner})
                WHERE d.status <> 'committed' RETURN properties(d) AS d
                ORDER BY d.updated_at DESC,d.id DESC LIMIT 1
                """, trip=trip_id, owner=owner).single()
            return self._decode(row["d"]) if row else None

    def _mutate(self, owner, trip_id, draft_id, change):
        if self.driver is None:
            with self.lock:
                trip, current = self._owned_memory(owner, trip_id, draft_id)
                record = copy.deepcopy(current)
                result = change(trip, record)
                if result is not None:
                    self.records[draft_id] = record
                return copy.deepcopy(result)
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip, record = self._locked_neo(tx, owner, trip_id, draft_id)
            result = change(trip, record)
            if result is not None:
                self._write(tx, record)
                tx.commit()
            return copy.deepcopy(result)

    @staticmethod
    def _editable(record, expected_version):
        if record["version"] != expected_version or record["status"] in ("queued", "running", "committed"):
            raise TravelConflictError("草稿已更新或正在處理，請重新載入。")

    def update(self, owner, trip_id, draft_id, expected_version, changes):
        if set(changes) - {"text", "record_date", "items"}:
            raise TravelValidationError("不允許修改此草稿欄位。")
        def change(trip, record):
            self._editable(record, expected_version)
            if "record_date" in changes:
                self._record_date_in_trip(trip, changes["record_date"])
            record.update(copy.deepcopy(changes), version=record["version"] + 1, updated_at=_now())
            return record
        return self._mutate(owner, trip_id, draft_id, change)

    def queue(self, owner, trip_id, draft_id, expected_version, request_id, record_date, text):
        payload = {"text": text, "record_date": record_date}
        def change(trip, record):
            known = record["generation_requests"].get(request_id)
            if known is not None:
                if known != payload:
                    raise TravelConflictError("這個請求識別碼已用於其他內容。")
                return record
            self._editable(record, expected_version)
            self._record_date_in_trip(trip, record_date, required=True)
            record["generation_requests"][request_id] = payload
            record.update(text=text, record_date=record_date, request_id=request_id, status="queued",
                          error=None, version=record["version"] + 1, trip_version=trip["version"], updated_at=_now())
            return record
        return self._mutate(owner, trip_id, draft_id, change)

    def pending(self):
        if self.driver is None:
            with self.lock:
                records = [copy.deepcopy(r) for r in self.records.values()
                           if r["status"] == "queued" and self.repository.get_trip(r["owner_id"], r["trip_id"])]
        else:
            with self.driver.session(database=self.database) as session:
                rows = session.run("""
                    MATCH (t:Trip)-[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {status:'queued'})
                    WHERE t.owner_id=d.owner_id RETURN properties(d) AS d
                    """).data()
                records = [self._decode(r["d"]) for r in rows]
        return sorted(records, key=lambda r: (r["updated_at"], r["id"]))[:100]

    def claim(self, owner, trip_id, draft_id, version, request_id):
        def change(trip, record):
            if record["version"] != version or record["request_id"] != request_id or record["status"] != "queued":
                return None
            record.update(status="running", updated_at=_now())
            return record
        try:
            return self._mutate(owner, trip_id, draft_id, change)
        except TravelNotFoundError:
            return None

    def finish(self, owner, trip_id, draft_id, version, request_id, items, error=None):
        def change(trip, record):
            if record["version"] != version or record["request_id"] != request_id or record["status"] != "running":
                return None
            record.update(status="failed" if error else "ready", error=error,
                          version=record["version"] + 1, updated_at=_now())
            if not error:
                record["items"] = copy.deepcopy(items)
            return record
        try:
            return self._mutate(owner, trip_id, draft_id, change)
        except TravelNotFoundError:
            return None

    def recover(self):
        if self.driver is None:
            with self.lock:
                for record in self.records.values():
                    if record["status"] == "running":
                        record.update(status="queued", updated_at=_now())
        else:
            with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
                rows = tx.run("MATCH (t:Trip)-[:HAS_FOOTPRINT_DRAFT]->(d:FootprintDraft {status:'running'}) WHERE t.owner_id=d.owner_id RETURN properties(d) AS d").data()
                for row in rows:
                    record = self._decode(row["d"])
                    record.update(status="queued", updated_at=_now())
                    self._write(tx, record)
                tx.commit()

    def discard(self, owner, trip_id, draft_id, version):
        if self.driver is None:
            with self.lock:
                _, record = self._owned_memory(owner, trip_id, draft_id)
                if record["version"] != version or record["status"] == "committed":
                    raise TravelConflictError("草稿已更新或已加入手記。")
                del self.records[draft_id]
                return
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            _, record = self._locked_neo(tx, owner, trip_id, draft_id)
            if record["version"] != version or record["status"] == "committed":
                raise TravelConflictError("草稿已更新或已加入手記。")
            tx.run("MATCH (d:FootprintDraft {id:$id,owner_id:$owner}) DETACH DELETE d", id=draft_id, owner=owner).consume()
            tx.commit()

    @staticmethod
    def _validate_commit(record, trip, version, trip_version, items):
        if record["status"] == "committed":
            return copy.deepcopy(record["commit_result"])
        if record["version"] != version or record["status"] in ("queued", "running") or trip["version"] != trip_version:
            raise TravelConflictError("手記或草稿已更新，請核對後再加入。")
        if not 1 <= len(items) <= 20:
            raise TravelValidationError("請選擇一至二十筆足跡。")
        for item in items:
            if not item.get("place_name", "").strip() or not item.get("category", "").strip() or not item.get("date"):
                raise TravelValidationError("請補齊地點、日期與分類。")
            if not trip["start_date"] <= item["date"] <= trip["end_date"]:
                raise TravelValidationError("足跡日期必須在手記期間內。")
        return None

    @staticmethod
    def _mark_committed(record, events, trip_version, request_id):
        record.update(status="committed", version=record["version"] + 1, updated_at=_now(),
                      commit_request_id=request_id)
        # The snapshot is independent of subsequent edits/deletions to created events.
        record["commit_result"] = {"events": copy.deepcopy(events), "trip_version": trip_version}
        return copy.deepcopy(record["commit_result"]) | {"draft": copy.deepcopy(record)}

    def commit(self, owner, trip_id, draft_id, expected_version, expected_trip_version, items, request_id):
        if self.driver is None:
            with self.lock:
                trip, record = self._owned_memory(owner, trip_id, draft_id)
                previous = self._validate_commit(record, trip, expected_version, expected_trip_version, items)
                if previous is not None:
                    return previous | {"draft": copy.deepcopy(record)}
                names = ("trips", "events", "places", "categories")
                snapshots = {name: copy.deepcopy(getattr(self.repository, name)) for name in names}
                try:
                    created = []
                    for item in items:
                        created.append(self.repository.create_event(owner, trip_id, dict(item, place_id=None)))
                    self.repository.trips[trip_id]["version"] = expected_trip_version + 1
                    # A later earlier-date addition can shift a previously created event's position.
                    created = [format_event(self.repository.events[e["id"]]) for e in created]
                    return self._mark_committed(record, created, expected_trip_version + 1, request_id)
                except Exception:
                    for name, snapshot in snapshots.items():
                        setattr(self.repository, name, snapshot)
                    raise
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            trip, record = self._locked_neo(tx, owner, trip_id, draft_id)
            previous = self._validate_commit(record, trip, expected_version, expected_trip_version, items)
            if previous is not None:
                return previous | {"draft": copy.deepcopy(record)}
            existing = [dict(r) for r in tx.run("""
                MATCH (:Trip {id:$trip,owner_id:$owner})-[:HAS_EVENT]->(e:Event)
                RETURN e.id AS id,e.date AS date,e.position AS position ORDER BY e.position,e.id
                """, trip=trip_id, owner=owner)]
            created = []
            for item in items:
                event_id, place_id = str(uuid4()), str(uuid4())
                category = item["category"]
                norm = category.strip()
                cat_id = deterministic_category_id(owner, norm)
                position = find_event_insert_index(existing, item["date"])
                existing.insert(position, {"id": event_id, "date": item["date"]})
                event = {"id": event_id, "owner_id": owner, "trip_id": trip_id, "place_id": place_id,
                             "timezone": trip.get("timezone", "Asia/Taipei"), "record_scope": "trip",
                             "place_name": item["place_name"], "city": item.get("city", ""), **stored_location(item),
                             "category": category, "date": item["date"], "time": item.get("time"), "notes": item.get("notes", ""),
                             "version": 1, "position": position, "embedding_status": "pending", "embedded_version": 0}
                tx.run("""
                    MATCH (t:Trip {id:$trip,owner_id:$owner})
                    MERGE (u:User {id:$owner})
                    CREATE (p:Place {id:$place,owner_id:$owner,name:$name,city:$city,address:$address,map_url:$map_url})
                    CREATE (u)-[:OWNS_PLACE]->(p)
                    MERGE (c:Category {id:$category_id})
                    ON CREATE SET c.owner_id=$owner,c.name=$category,c.normalized_name=$norm
                    MERGE (u)-[:OWNS_CATEGORY]->(c)
                    CREATE (e:Event) SET e=$event
                    CREATE (t)-[:HAS_EVENT]->(e)
                    CREATE (u)-[:OWNS_EVENT]->(e)
                    CREATE (e)-[:AT]->(p)
                    CREATE (e)-[:HAS_CATEGORY]->(c)
                    """, trip=trip_id, owner=owner, place=place_id, name=event["place_name"], city=event["city"],
                    address=event["address"], map_url=event["map_url"], category_id=cat_id, category=category, norm=norm, event=event).consume()
                created.append(event)
            positions = {event["id"]: i for i, event in enumerate(existing)}
            tx.run("""
                UNWIND $positions AS item MATCH (e:Event {id:item.id,owner_id:$owner,trip_id:$trip})
                SET e.position=item.position
                """, owner=owner, trip=trip_id, positions=[{"id": key, "position": value} for key, value in positions.items()]).consume()
            tx.run("""
                MATCH (:Trip {id:$trip,owner_id:$owner})-[:HAS_EVENT]->(e:Event)-[r:NEXT]->()
                DELETE r
                """, trip=trip_id, owner=owner).consume()
            pairs = [{"a": existing[i]["id"], "b": existing[i + 1]["id"]} for i in range(len(existing) - 1)]
            tx.run("""
                UNWIND $pairs AS pair
                MATCH (a:Event {id:pair.a,owner_id:$owner,trip_id:$trip})
                MATCH (b:Event {id:pair.b,owner_id:$owner,trip_id:$trip}) CREATE (a)-[:NEXT]->(b)
                """, pairs=pairs, owner=owner, trip=trip_id).consume()
            tx.run("MATCH (t:Trip {id:$trip,owner_id:$owner}) SET t.version=t.version+1", trip=trip_id, owner=owner).consume()
            for event in created:
                event["position"] = positions[event["id"]]
            result = self._mark_committed(record, [format_event(e) for e in created], expected_trip_version + 1, request_id)
            self._write(tx, record)
            tx.commit()
            return result
