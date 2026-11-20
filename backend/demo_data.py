"""Explicit, owner-scoped demo data import for the command-line entry point."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from backend.travel import EventCreate, TripCreate
from backend.travel_store import deterministic_category_id

DEFAULT_PACKAGE = Path(__file__).resolve().parent.parent / "examples/demo/scenarios.json"


class DemoImportError(ValueError):
    """Invalid demo input or an import that cannot safely proceed."""


def resource_id(owner: str, pack: str, kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"travelmemo:demo:{owner}:{pack}:{kind}:{key}"))


def normalize_owner(email: str, allowed: set[str]) -> str:
    normalized = email.strip().casefold()
    if not normalized or normalized not in allowed:
        raise DemoImportError("目標信箱必須在允許名單內。")
    return normalized


def load_package(path: Path = DEFAULT_PACKAGE) -> dict:
    package = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parent
    for photo in package.get("photos", []):
        source = (root / photo["file"]).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise DemoImportError("示範圖片不存在或超出資料包範圍。")
    return package


def build_plan(package: dict, owner_id: str, anchor_date: str, package_root: Path) -> dict:
    """Validate the portable fixture and resolve dates and owner-specific resource IDs."""
    try:
        anchor = dt.date.fromisoformat(anchor_date)
    except (TypeError, ValueError) as exc:
        raise DemoImportError("基準日期必須為 YYYY-MM-DD。") from exc
    pack = package.get("pack_id")
    if not isinstance(pack, str) or not pack.strip():
        raise DemoImportError("資料包缺少識別名稱。")
    plan = {
        "owner_id": owner_id, "pack_id": pack, "anchor_date": anchor.isoformat(),
        "package_root": str(package_root.resolve()), "trips": [], "photos": [],
        "places": [], "categories": [], "next_edges": [],
    }
    keys: set[str] = set()
    trip_by_key, event_by_key, places, categories = {}, {}, {}, {}

    def take_key(record: dict) -> str:
        key = record.get("key")
        if not isinstance(key, str) or not key.strip() or key in keys:
            raise DemoImportError("示範項目識別名稱不得空白或重複。")
        keys.add(key)
        return key

    def offset(value) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise DemoImportError("日期偏移必須為整數天。")
        return value

    for source in package.get("trips", []):
        key = take_key(source)
        start = anchor + dt.timedelta(days=offset(source["start_offset"]))
        end = anchor + dt.timedelta(days=offset(source["end_offset"]))
        trip = TripCreate(
            name=source["name"], description=source.get("description", ""),
            start_date=start.isoformat(), end_date=end.isoformat(),
            timezone=source.get("timezone", "Asia/Taipei"),
        ).model_dump()
        trip.update(key=key, id=resource_id(owner_id, pack, "trip", key),
                    owner_id=owner_id, events=[])
        previous_date = None
        for position, item in enumerate(source.get("events", [])):
            event_key = take_key(item)
            date = (start + dt.timedelta(days=offset(item["day_offset"]))).isoformat()
            if not start.isoformat() <= date <= end.isoformat():
                raise DemoImportError("足跡日期超出手記範圍。")
            if previous_date and date < previous_date:
                raise DemoImportError("資料包足跡必須依日期及當日確認順序排列。")
            previous_date = date
            event = EventCreate(
                place_name=item["place_name"], city=item.get("city", ""),
                address=item.get("address", ""), category=item["category"],
                date=date, time=item.get("time"), notes=item.get("notes", ""),
            ).model_dump(exclude={"place_id"})
            place_key = item.get("place_key")
            if not isinstance(place_key, str) or not place_key.strip():
                raise DemoImportError("足跡缺少地點識別名稱。")
            place = {"id": resource_id(owner_id, pack, "place", place_key),
                     "owner_id": owner_id, "name": event["place_name"],
                     "city": event["city"], "address": event["address"]}
            if place_key in places and places[place_key] != place:
                raise DemoImportError("同一地點識別名稱的內容不一致。")
            places[place_key] = place
            category = event["category"].strip()
            if not category:
                raise DemoImportError("足跡分類不得空白。")
            event["category"] = category
            category_id = deterministic_category_id(owner_id, category)
            categories[category_id] = {"id": category_id, "owner_id": owner_id,
                                       "name": category, "normalized_name": category}
            event.update(key=event_key, id=resource_id(owner_id, pack, "event", event_key),
                         owner_id=owner_id, trip_id=trip["id"], place_id=place["id"],
                         category_id=category_id, position=position,
                         timezone=trip["timezone"], record_scope="trip")
            trip["events"].append(event)
            event_by_key[event_key] = event
        trip["version"] = 1 + len(trip["events"])
        for left, right in zip(trip["events"], trip["events"][1:]):
            plan["next_edges"].append({"from_id": left["id"], "to_id": right["id"]})
        trip_by_key[key] = trip
        plan["trips"].append(trip)
    if not plan["trips"]:
        raise DemoImportError("資料包至少需要一本手記。")

    covers = set()
    photo_keys = set()
    for source in package.get("photos", []):
        key = source.get("key")
        if not isinstance(key, str) or not key.strip() or key in photo_keys:
            raise DemoImportError("圖片識別名稱不得空白或重複。")
        photo_keys.add(key)
        trip = trip_by_key.get(source.get("trip_key"))
        event = event_by_key.get(source.get("event_key")) if source.get("event_key") else None
        if not trip or (source.get("event_key") and not event):
            raise DemoImportError("照片引用了不存在的手記或足跡。")
        if event and event["trip_id"] != trip["id"]:
            raise DemoImportError("照片足跡不屬於指定手記。")
        source_path = (package_root / source["file"]).resolve()
        if not source_path.is_relative_to(package_root.resolve()) or not source_path.is_file():
            raise DemoImportError("示範圖片不存在或超出資料包範圍。")
        if source.get("cover"):
            if trip["id"] in covers:
                raise DemoImportError("每本手記只能指定一張初始封面。")
            covers.add(trip["id"])
        plan["photos"].append({**copy.deepcopy(source), "key": key,
                               "trip_id": trip["id"], "event_id": event["id"] if event else None})
    case_ids = set()
    for case in package.get("cases", []):
        if not case.get("id") or case["id"] in case_ids:
            raise DemoImportError("測試題目識別名稱不得空白或重複。")
        case_ids.add(case["id"])
        if any(key not in trip_by_key and key not in event_by_key
               for key in case.get("source_keys", [])):
            raise DemoImportError("測試題目引用了不存在的來源。")
        if case.get("image_key") and not any(p["key"] == case["image_key"] for p in plan["photos"]):
            raise DemoImportError("測試題目引用了不存在的圖片。")
    plan["places"] = list(places.values())
    plan["categories"] = list(categories.values())
    plan["counts"] = {"trips": len(plan["trips"]), "events": len(event_by_key),
                      "photos": len(plan["photos"])}
    return plan


class Neo4jDemoRepository:
    def __init__(self, store):
        self.driver, self.database = store.driver, store.database

    def context(self, email: str, pack: str) -> dict:
        with self.driver.session(database=self.database) as session:
            users = list(session.run(
                "MATCH (u:User) WHERE toLower(u.email)=$email RETURN u.id AS id", email=email
            ))
            if len(users) > 1:
                raise DemoImportError("目標信箱對應多個帳號，請先處理帳號資料。")
            owner = users[0]["id"] if users else str(uuid5(NAMESPACE_URL, "travelmemo:" + email))
            record = session.run(
                "MATCH (d:DemoImport {id:$id, owner_id:$owner}) RETURN d.anchor_date AS anchor_date",
                id=resource_id(owner, pack, "import", pack), owner=owner,
            ).single()
            return {"owner_id": owner, "anchor_date": record["anchor_date"] if record else None}

    def apply(self, plan: dict, email: str) -> bool:
        with self.driver.session(database=self.database) as session:
            return session.execute_write(self._apply, plan, email)

    def _apply(self, tx, plan: dict, email: str) -> bool:
        owner, pack = plan["owner_id"], plan["pack_id"]
        user = tx.run(
            "MERGE (u:User {id:$owner}) ON CREATE SET u.email=$email, u.created_at=datetime() "
            "SET u.__demo_lock=coalesce(u.__demo_lock,0)+1 RETURN u.email AS email",
            owner=owner, email=email,
        ).single()
        if not user or str(user["email"] or "").casefold() != email:
            raise DemoImportError("目標帳號識別衝突，匯入已中止。")
        import_id = resource_id(owner, pack, "import", pack)
        record = tx.run(
            "MATCH (d:DemoImport {id:$id}) RETURN d.owner_id AS owner_id, "
            "d.anchor_date AS anchor_date, d.status AS status", id=import_id,
        ).single()
        if record:
            if (record["owner_id"] != owner or record["anchor_date"] != plan["anchor_date"]
                    or record["status"] != "graph_ready"):
                raise DemoImportError("既有示範匯入紀錄不相容，未覆寫任何資料。")
            tx.run("MATCH (u:User {id:$owner}) REMOVE u.__demo_lock", owner=owner).consume()
            return False
        ids = [t["id"] for t in plan["trips"]] + [p["id"] for p in plan["places"]]
        ids += [e["id"] for t in plan["trips"] for e in t["events"]]
        collision = tx.run("MATCH (n) WHERE n.id IN $ids RETURN count(n) AS count", ids=ids).single()
        if collision["count"]:
            raise DemoImportError("示範識別名稱已被其他資料使用，未覆寫任何資料。")
        for category in plan["categories"]:
            existing = tx.run(
                "MATCH (n {id:$id}) RETURN labels(n) AS labels, n.owner_id AS owner_id, "
                "n.normalized_name AS name", id=category["id"],
            ).single()
            if existing and ("Category" not in existing["labels"]
                             or existing["owner_id"] != owner
                             or existing["name"] != category["normalized_name"]):
                raise DemoImportError("既有分類識別衝突，未覆寫任何資料。")
        self._create_graph(tx, plan)
        tx.run(
            "CREATE (:DemoImport {id:$id, owner_id:$owner, pack_id:$pack, "
            "anchor_date:$anchor, status:'graph_ready', created_at:datetime()})",
            id=import_id, owner=owner, pack=pack, anchor=plan["anchor_date"],
        ).consume()
        tx.run("MATCH (u:User {id:$owner}) REMOVE u.__demo_lock", owner=owner).consume()
        return True

    def _create_graph(self, tx, plan):
        owner, pack = plan["owner_id"], plan["pack_id"]
        trips = [{k: v for k, v in t.items() if k not in {"events", "key"}}
                 | {"demo_pack": pack, "demo_key": t["key"]} for t in plan["trips"]]
        events = [{k: v for k, v in e.items() if k not in {"key", "category_id"}}
                  | {"demo_pack": pack, "demo_key": e["key"], "version": 1,
                     "embedding_status": "pending", "embedded_version": 0}
                  for t in plan["trips"] for e in t["events"]]
        tx.run(
            "MATCH (u:User {id:$owner}) UNWIND $rows AS row "
            "CREATE (t:Trip) SET t=row CREATE (u)-[:OWNS]->(t)", owner=owner, rows=trips,
        ).consume()
        tx.run(
            "MATCH (u:User {id:$owner}) UNWIND $rows AS row "
            "CREATE (p:Place) SET p=row CREATE (u)-[:OWNS_PLACE]->(p)",
            owner=owner, rows=plan["places"],
        ).consume()
        tx.run(
            "MATCH (u:User {id:$owner}) UNWIND $rows AS row "
            "MERGE (c:Category {id:row.id}) ON CREATE SET c=row "
            "MERGE (u)-[:OWNS_CATEGORY]->(c)", owner=owner, rows=plan["categories"],
        ).consume()
        category_by_name = {c["normalized_name"]: c["id"] for c in plan["categories"]}
        rows = [{"props": e, "category_id": category_by_name[e["category"]]} for e in events]
        tx.run(
            "MATCH (u:User {id:$owner}) UNWIND $rows AS row MATCH (t:Trip {id:row.props.trip_id, owner_id:$owner}) "
            "MATCH (p:Place {id:row.props.place_id, owner_id:$owner}) "
            "MATCH (c:Category {id:row.category_id, owner_id:$owner}) "
            "CREATE (e:Event) SET e=row.props CREATE (t)-[:HAS_EVENT]->(e) "
            "CREATE (u)-[:OWNS_EVENT]->(e) "
            "CREATE (e)-[:AT]->(p) CREATE (e)-[:HAS_CATEGORY]->(c)", owner=owner, rows=rows,
        ).consume()
        tx.run(
            "UNWIND $pairs AS pair MATCH (a:Event {id:pair.from_id, owner_id:$owner}) "
            "MATCH (b:Event {id:pair.to_id, owner_id:$owner}) "
            "WHERE a.trip_id=b.trip_id CREATE (a)-[:NEXT]->(b)",
            owner=owner, pairs=plan["next_edges"],
        ).consume()


def prepare_import(settings, repository, package, email: str, anchor_date: str | None,
                   package_root: Path) -> tuple[str, dict]:
    email = normalize_owner(email, settings.emails)
    context = repository.context(email, package["pack_id"])
    fixed_anchor = context.get("anchor_date")
    if fixed_anchor and anchor_date and fixed_anchor != anchor_date:
        raise DemoImportError("這批示範資料已有固定基準日，請省略 --anchor-date 或使用原日期。")
    anchor = fixed_anchor or anchor_date or dt.datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    return email, build_plan(package, context["owner_id"], anchor, package_root)


def seed_demo(settings, email: str, anchor_date: str | None = None, apply: bool = False,
              *, package_path: Path = DEFAULT_PACKAGE) -> dict:
    """Preview by default. Applying never creates a login session or sends an email."""
    from backend.store import Neo4jStore

    email = normalize_owner(email, settings.emails)
    package = load_package(package_path)
    store = Neo4jStore(settings)
    try:
        repository = Neo4jDemoRepository(store)
        email, plan = prepare_import(settings, repository, package, email, anchor_date,
                                     package_path.resolve().parent)
        result = {"mode": "applied" if apply else "preview", **plan["counts"]}
        if apply:
            result["graph_created"] = repository.apply(plan, email)
            from backend.demo_photos import seed_photos

            result["photo_import"] = seed_photos(settings, store, plan)
        return result
    finally:
        store.close()
