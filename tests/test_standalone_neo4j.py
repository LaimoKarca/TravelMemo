"""Opt-in checks for an isolated Neo4j database, never a private database."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from neo4j import GraphDatabase

from backend.photo_store import Neo4jPhotoStore, sync_event_photo_trip
from backend.travel_store import Neo4jTravelRepository, TravelConflictError, TravelValidationError


@pytest.fixture
def graph():
    uri = os.getenv("TRAVELMEMO_STANDALONE_TEST_URI")
    if not uri:
        pytest.skip("Disposable database opt-in")
    driver = GraphDatabase.driver(uri, auth=None)
    owner = "standalone-test-" + uuid4().hex
    repo = Neo4jTravelRepository(driver)
    repo.initialize()
    try:
        yield repo, driver, owner
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.owner_id STARTS WITH $owner OR n.id STARTS WITH $owner DETACH DELETE n",
                        owner=owner).consume()
        driver.close()


def event_data(**changes):
    return {"place_name": "海邊", "city": "臺南", "category": "散步", "date": "2026-11-20",
            "timezone": "Asia/Taipei", **changes}


def trip_data(**changes):
    return {"name": "小旅行", "start_date": "2026-11-19", "end_date": "2026-11-22",
            "timezone": "Asia/Taipei", **changes}


def test_migration_only_backfills_verified_legacy_ownership_and_is_idempotent(graph):
    repo, driver, owner = graph
    trip = repo.create_trip(owner, trip_data())
    legacy = {**event_data(), "id": owner + "legacy", "owner_id": owner, "trip_id": trip["id"],
              "place_id": owner + "place", "address": "", "version": 1, "position": 0}
    legacy.pop("timezone")
    invalid = {**legacy, "id": owner + "invalid", "owner_id": owner + "other"}
    with driver.session() as session:
        session.run("""MATCH (t:Trip {id:$trip}) CREATE (e:Event) SET e=$event CREATE (t)-[:HAS_EVENT]->(e)
                      CREATE (bad:Event) SET bad=$invalid CREATE (t)-[:HAS_EVENT]->(bad)""",
                    trip=trip["id"], event=legacy, invalid=invalid).consume()
    repo.initialize()
    repo.initialize()
    assert repo.get_event(owner, legacy["id"])["timezone"] == "Asia/Taipei"
    assert repo.get_event(owner, invalid["id"]) is None
    assert repo.get_event(owner + "other", invalid["id"]) is None
    with driver.session() as session:
        row = session.run("MATCH (:User {id:$owner})-[r:OWNS_EVENT]->() RETURN count(r) AS n", owner=owner).single()
        assert row["n"] == 1


def test_real_standalone_crud_attach_order_and_rollback(graph):
    repo, _, owner = graph
    single = repo.create_standalone_event(owner, event_data())
    assert repo.get_event(owner + "other", single["id"]) is None
    assert single["trip_id"] is None and single["position"] is None
    assert repo.list_standalone_events(owner, q="海邊")["items"] == [single]
    updated = repo.update_event(owner, single["id"], event_data(version=1, notes="晚霞"))
    assert updated["version"] == 2
    trip = repo.create_trip(owner, trip_data())
    first = repo.create_event(owner, trip["id"], event_data(place_name="早晨"))
    data = {"trip_id": trip["id"], "version": 2, "trip_version": 2, "before_event_id": first["id"]}
    with pytest.raises(TravelValidationError):
        repo.attach_event_to_trip(owner, single["id"], {**data, "before_event_id": "missing"})
    assert repo.get_event(owner, single["id"])["trip_id"] is None
    attached = repo.attach_event_to_trip(owner, single["id"], data)
    assert attached["id"] == single["id"] and attached["version"] == 3
    assert [e["id"] for e in repo.get_trip_detail(owner, trip["id"])["events"]] == [single["id"], first["id"]]
    assert repo.get_trip_detail(owner, trip["id"])["next_edges"] == [{"from_id": single["id"], "to_id": first["id"]}]
    assert repo.list_standalone_events(owner)["items"] == []
    with pytest.raises(TravelConflictError):
        repo.delete_event(owner, single["id"], 2)
    repo.delete_event(owner, single["id"], 3)
    standalone = repo.create_standalone_event(owner, event_data())
    repo.delete_event(owner, standalone["id"], 1)
    assert repo.get_event(owner, standalone["id"]) is None


def test_real_standalone_same_time_uses_creation_order_and_pages(graph):
    repo, driver, owner = graph
    legacy = repo.create_standalone_event(owner, event_data())
    older = repo.create_standalone_event(owner, event_data())
    newest = repo.create_standalone_event(owner, event_data())
    with driver.session() as session:
        session.run("MATCH (e:Event {id:$id}) REMOVE e.created_at", id=legacy["id"]).consume()
        session.run("MATCH (e:Event {id:$id}) SET e.created_at=$at", id=older["id"], at="2026-11-20T01:00:00+00:00").consume()
        session.run("MATCH (e:Event {id:$id}) SET e.created_at=$at", id=newest["id"], at="2026-11-20T02:00:00+00:00").consume()
    page = repo.list_standalone_events(owner, limit=2)
    assert [e["id"] for e in page["items"]] == [newest["id"], older["id"]]
    assert page["next_offset"] == 2
    assert repo.list_standalone_events(owner, offset=2)["items"][0]["id"] == legacy["id"]


def test_real_attach_races_update_with_one_optimistic_winner(graph):
    repo, _, owner = graph
    trip = repo.create_trip(owner, trip_data())
    single = repo.create_standalone_event(owner, event_data())
    barrier = Barrier(2)

    def run(attach):
        barrier.wait()
        try:
            if attach:
                return repo.attach_event_to_trip(owner, single["id"],
                    {"trip_id": trip["id"], "version": 1, "trip_version": 1})
            return repo.update_event(owner, single["id"], event_data(version=1, notes="changed"))
        except TravelConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [True, False]))
    assert sum(result is not None for result in results) == 1
    assert repo.get_event(owner, single["id"])["version"] == 2


def wait_for_blocked_photo_write(driver, photo_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = driver.execute_query(
            "SHOW TRANSACTIONS YIELD status, parameters "
            "WHERE status STARTS WITH 'Blocked' AND parameters.id = $id "
            "RETURN count(*) AS blocked",
            id=photo_id,
        )
        if result.records[0]["blocked"]:
            return
        time.sleep(0.05)
    pytest.fail("Concurrent photo writer did not reach the locked record")


def test_real_stale_photo_delete_cannot_cross_binding_update(graph):
    repo, driver, owner = graph
    repo.create_trip(owner, trip_data())
    photo_id = owner + "-photo"
    driver.execute_query(
        "MATCH (u:User {id:$owner}) "
        "CREATE (u)-[:OWNS]->(:Photo {id:$id, owner_id:$owner, version:1, bindings_json:'[]'})",
        owner=owner,
        id=photo_id,
    )
    store = Neo4jPhotoStore(driver)
    with ThreadPoolExecutor(max_workers=1) as pool, driver.session() as session:
        with session.begin_transaction(timeout=15) as tx:
            tx.run("MATCH (p:Photo {id:$id}) SET p.version=2", id=photo_id).consume()
            stale_delete = pool.submit(store.remove, owner, photo_id, expected_version=1)
            wait_for_blocked_photo_write(driver, photo_id)
            tx.commit()
        assert not stale_delete.result(timeout=10)
    assert store.get(owner, photo_id)["version"] == 2


@pytest.mark.parametrize("unbind", [False, True])
def test_real_photo_binding_change_preserves_concurrent_trip_membership(graph, unbind):
    repo, driver, owner = graph
    other_trip = repo.create_trip(owner, trip_data())
    original = repo.create_standalone_event(owner, event_data())
    destination = repo.create_trip(owner, trip_data())
    photo_id = owner + "-photo"
    driver.execute_query(
        "MATCH (u:User {id:$owner}) "
        "CREATE (u)-[:OWNS]->(:Photo {id:$id, owner_id:$owner, version:1, status:'ready', bindings_json:'[]'})",
        owner=owner,
        id=photo_id,
    )
    store = Neo4jPhotoStore(driver)
    store.bind(owner, photo_id, "event", original["id"])
    before = store.bind(owner, photo_id, "trip", other_trip["id"], other_trip["id"])
    with ThreadPoolExecutor(max_workers=1) as pool, driver.session() as session:
        with session.begin_transaction(timeout=15) as tx:
            sync_event_photo_trip(tx, owner, original["id"], destination["id"])
            write = (
                pool.submit(store.unbind, owner, photo_id, "trip", other_trip["id"], False)
                if unbind else
                pool.submit(store.bind, owner, photo_id, "trip", other_trip["id"], other_trip["id"])
            )
            wait_for_blocked_photo_write(driver, photo_id)
            tx.commit()
        assert write.result(timeout=10)
    after = store.get(owner, photo_id)
    assert {"kind": "event", "target_id": original["id"], "trip_id": destination["id"]} in after["bindings"]
    assert any(binding["target_id"] == other_trip["id"] for binding in after["bindings"]) is not unbind
    assert after["version"] == before["version"] + 2
