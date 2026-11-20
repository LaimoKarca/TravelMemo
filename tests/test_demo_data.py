"""Owner and fixture boundaries for the explicitly invoked demo importer."""

import copy
import json
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.demo_data import (
    DemoImportError,
    Neo4jDemoRepository,
    build_plan,
    load_package,
    normalize_owner,
    prepare_import,
    resource_id,
    seed_demo,
)


@pytest.fixture
def package(tmp_path):
    (tmp_path / "sample.png").write_bytes(b"synthetic-image-placeholder")
    return {
        "pack_id": "example-demo",
        "trips": [
            {"key": "walk", "name": "測試散步", "description": "原創假資料",
             "start_offset": -1, "end_offset": 1, "timezone": "Asia/Tokyo",
             "events": [
                 {"key": "coffee-morning", "place_key": "coffee", "place_name": "河畔咖啡",
                  "city": "東京", "category": "咖啡", "day_offset": 0, "time": "09:00",
                  "notes": "靠窗看河"},
                 {"key": "coffee-again", "place_key": "coffee", "place_name": "河畔咖啡",
                  "city": "東京", "category": "咖啡", "day_offset": 0, "time": None,
                  "notes": "再次造訪，沒有記下時間"},
                 {"key": "museum", "place_key": "museum", "place_name": "光影美術館",
                  "city": "東京", "category": "文化", "day_offset": 1, "time": "10:00",
                  "notes": "雨天展覽"},
             ]},
            {"key": "empty", "name": "空白手記", "start_offset": 10, "end_offset": 11,
             "timezone": "UTC+05:30", "events": []},
        ],
        "photos": [{"key": "photo", "file": "sample.png", "caption": "示意圖",
                    "trip_key": "walk", "event_key": "coffee-morning", "cover": True}],
        "cases": [{"id": "C01", "source_keys": ["walk", "coffee-again"],
                   "image_key": "photo", "question": "那間靠窗的店？"}],
    }


def test_plan_preserves_order_repeated_visits_and_cross_day_links(package, tmp_path):
    plan = build_plan(package, "owner", "2026-11-20", tmp_path)
    assert plan["counts"] == {"trips": 2, "events": 3, "photos": 1}
    trip = plan["trips"][0]
    assert (trip["start_date"], trip["end_date"]) == ("2026-11-19", "2026-11-21")
    assert [e["position"] for e in trip["events"]] == [0, 1, 2]
    assert [e["date"] for e in trip["events"]] == ["2026-11-19", "2026-11-19", "2026-11-20"]
    first, second, last = trip["events"]
    assert first["id"] != second["id"]
    assert first["place_id"] == second["place_id"]
    assert second["time"] is None
    assert plan["next_edges"] == [{"from_id": first["id"], "to_id": second["id"]},
                                  {"from_id": second["id"], "to_id": last["id"]}]
    assert plan["photos"][0]["event_id"] == first["id"]
    assert plan["trips"][1]["events"] == []


def test_ids_are_owner_scoped_and_deterministic_without_mutating_fixture(package, tmp_path):
    before = copy.deepcopy(package)
    first = build_plan(package, "owner-one", "2026-11-20", tmp_path)
    repeated = build_plan(package, "owner-one", "2026-11-20", tmp_path)
    other = build_plan(package, "owner-two", "2026-11-20", tmp_path)
    assert first == repeated
    assert first["trips"][0]["id"] != other["trips"][0]["id"]
    assert first["places"][0]["id"] != other["places"][0]["id"]
    assert package == before


@pytest.mark.parametrize("corruption", ["duplicate", "order", "out-of-bounds", "place", "source", "photo-event", "image", "path", "missing"])
def test_plan_rejects_unsafe_or_inconsistent_inputs(package, tmp_path, corruption):
    events = package["trips"][0]["events"]
    if corruption == "duplicate":
        events[1]["key"] = events[0]["key"]
    elif corruption == "order":
        events[0]["day_offset"] = 1
    elif corruption == "out-of-bounds":
        events[2]["day_offset"] = 9
    elif corruption == "place":
        events[1]["place_name"] = "不同地點"
    elif corruption == "source":
        package["cases"][0]["source_keys"] = ["unknown"]
    elif corruption == "photo-event":
        package["photos"][0]["trip_key"] = "empty"
    elif corruption == "image":
        package["cases"][0]["image_key"] = "unknown"
    elif corruption == "path":
        package["photos"][0]["file"] = "../sample.png"
    elif corruption == "missing":
        package["photos"][0]["file"] = "missing.png"
    with pytest.raises(DemoImportError):
        build_plan(package, "owner", "2026-11-20", tmp_path)


def test_load_package_checks_files_before_writing(package, tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    assert load_package(path) == package
    (tmp_path / "sample.png").unlink()
    with pytest.raises(DemoImportError):
        load_package(path)


def test_preparation_reuses_existing_owner_and_fixed_anchor(package, tmp_path):
    class Repository:
        def context(self, email, pack):
            assert email == "traveler@example.com"
            return {"owner_id": "existing-owner", "anchor_date": "2025-07-01"}

    settings = SimpleNamespace(emails={"traveler@example.com"})
    email, plan = prepare_import(settings, Repository(), package, " Traveler@Example.com ", None, tmp_path)
    assert email == "traveler@example.com"
    assert plan["owner_id"] == "existing-owner"
    assert plan["anchor_date"] == "2025-07-01"
    with pytest.raises(DemoImportError, match="固定基準日"):
        prepare_import(settings, Repository(), package, email, "2026-11-20", tmp_path)


def test_context_for_new_owner_uses_the_login_id_without_creating_a_user():
    calls = []

    class Result:
        def __iter__(self):
            return iter([])

        def single(self):
            return None

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def run(self, query, **params):
            calls.append(query)
            return Result()

    repo = Neo4jDemoRepository(SimpleNamespace(driver=SimpleNamespace(session=lambda **kwargs: Session()), database="neo4j"))
    context = repo.context("traveler@example.com", "example-demo")
    assert context["owner_id"] == str(uuid5(NAMESPACE_URL, "travelmemo:traveler@example.com"))
    assert context["anchor_date"] is None
    assert all(query.startswith("MATCH") for query in calls)


def test_preview_does_not_initialize_write_or_start_photo_services(package, tmp_path, monkeypatch):
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    settings = SimpleNamespace(emails={"traveler@example.com"})
    closed = []
    store = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr("backend.store.Neo4jStore", lambda settings: store)

    class Repository:
        def __init__(self, store):
            pass

        def context(self, email, pack):
            return {"owner_id": "existing-owner", "anchor_date": None}

        def apply(self, *args):
            pytest.fail("preview must not write")

    monkeypatch.setattr("backend.demo_data.Neo4jDemoRepository", Repository)
    result = seed_demo(settings, "traveler@example.com", "2026-11-20", package_path=path)
    assert result == {"mode": "preview", "trips": 2, "events": 3, "photos": 1}
    assert closed == [True]


def test_denylist_is_checked_before_opening_database(monkeypatch):
    monkeypatch.setattr("backend.store.Neo4jStore", lambda *args: pytest.fail("database opened"))
    with pytest.raises(DemoImportError, match="允許名單"):
        seed_demo(SimpleNamespace(emails={"allowed@example.com"}), "other@example.com")
    assert normalize_owner(" ALLOWED@EXAMPLE.COM ", {"allowed@example.com"}) == "allowed@example.com"


def test_existing_import_is_a_noop_even_if_demo_resources_were_edited_or_deleted(package, tmp_path):
    plan = build_plan(package, "owner", "2026-11-20", tmp_path)
    calls = []

    class Result:
        def __init__(self, value=None):
            self.value = value

        def single(self):
            return self.value

        def consume(self):
            pass

    class Tx:
        def run(self, query, **params):
            calls.append(query)
            if query.startswith("MERGE (u:User"):
                return Result({"email": "traveler@example.com"})
            if query.startswith("MATCH (d:DemoImport"):
                return Result({"owner_id": "owner", "anchor_date": "2026-11-20", "status": "graph_ready"})
            if "REMOVE u.__demo_lock" in query:
                return Result()
            pytest.fail("completed import must not read or rewrite fixture resources")

    repo = Neo4jDemoRepository(SimpleNamespace(driver=None, database="neo4j"))
    assert repo._apply(Tx(), plan, "traveler@example.com") is False
    assert not any("CREATE (t:Trip)" in query for query in calls)


def test_resource_ids_do_not_contain_plain_email():
    assert resource_id("owner", "pack", "trip", "walk") == resource_id("owner", "pack", "trip", "walk")
    assert resource_id("owner", "pack", "trip", "walk") != resource_id("other", "pack", "trip", "walk")


def test_public_demo_pack_counts_and_references():
    from backend.demo_data import DEFAULT_PACKAGE

    package = load_package()
    plan = build_plan(package, "example-owner", "2026-11-20", DEFAULT_PACKAGE.parent)
    assert plan["counts"] == {"trips": 12, "events": 150, "photos": 6}
    assert len(package["cases"]) == 50
    assert len(plan["next_edges"]) == 139
    assert sum(not trip["events"] for trip in plan["trips"]) == 1
