"""Explicit opt-in integration test against an empty, disposable Neo4j instance."""

import os
from uuid import uuid4

import pytest

from backend.config import Settings
from backend.demo_data import (
    DEFAULT_PACKAGE,
    Neo4jDemoRepository,
    build_plan,
    load_package,
    prepare_import,
)
from backend.demo_photos import seed_photos
from backend.store import Neo4jStore
from backend.travel_store import Neo4jTravelRepository


@pytest.mark.skipif(not os.getenv("TRAVELMEMO_DEMO_TEST_URI"), reason="Disposable database opt-in")
def test_real_demo_transaction_resume_and_ownership(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, neo4j_uri=os.environ["TRAVELMEMO_DEMO_TEST_URI"],
        neo4j_user="neo4j", neo4j_password="unused", session_secret="demo-test-" * 6,
        allowed_emails="tester@example.com", media_root=str(tmp_path / "media"),
    )
    store = Neo4jStore(settings)
    owners = []
    try:
        with store.driver.session(database=store.database) as session:
            assert session.run("MATCH (n) RETURN count(n) AS n").single()["n"] == 0, (
                "Use an empty disposable database, never a development or production database"
            )
        store.initialize()
        repository = Neo4jTravelRepository(store.driver, store.database)
        repository.initialize()
        demo = Neo4jDemoRepository(store)
        package = load_package()
        email, plan = prepare_import(settings, demo, package, "tester@example.com", "2026-11-20",
                                     DEFAULT_PACKAGE.parent)
        owners.extend([plan["owner_id"], "unrelated-" + uuid4().hex])
        original = demo._create_graph

        def fail_after_writes(tx, value):
            original(tx, value)
            raise RuntimeError("simulated interruption")

        monkeypatch.setattr(demo, "_create_graph", fail_after_writes)
        with pytest.raises(RuntimeError, match="interruption"):
            demo.apply(plan, email)
        with store.driver.session(database=store.database) as session:
            assert session.run("MATCH (n) RETURN count(n) AS n").single()["n"] == 0
        monkeypatch.setattr(demo, "_create_graph", original)
        foreign = repository.create_trip(owners[1], {
            "name": "Unrelated", "start_date": "2026-01-01", "end_date": "2026-01-02",
        })
        assert demo.apply(plan, email) is True
        assert seed_photos(settings, store, plan) == {"imported": 6, "skipped": 0}
        assert len(repository.get_trips(owners[0])) == 12
        assert len(repository.get_trips(owners[1])) == 1
        with store.driver.session(database=store.database) as session:
            assert session.run("MATCH (e:Event {owner_id:$owner}) RETURN count(e) AS n",
                               owner=owners[0]).single()["n"] == 150
            assert session.run("MATCH (a:Event {owner_id:$owner})-[r:NEXT]->(b) RETURN count(r) AS n",
                               owner=owners[0]).single()["n"] == 139
            assert session.run("MATCH (p:Photo {owner_id:$owner}) RETURN count(p) AS n",
                               owner=owners[0]).single()["n"] == 6
        first = plan["trips"][0]
        repository.update_trip(owners[0], first["id"], {
            **{key: first[key] for key in ("start_date", "end_date", "timezone", "description", "version")},
            "name": "Manually edited",
        })
        repository.delete_event(owners[0], first["events"][0]["id"], 1)
        assert demo.apply(plan, email) is False
        assert seed_photos(settings, store, plan) == {"imported": 0, "skipped": 6}
        assert repository.get_trip(owners[0], first["id"])["name"] == "Manually edited"
        assert repository.get_event(owners[0], first["events"][0]["id"]) is None
        assert repository.get_trip(owners[1], foreign["id"])["name"] == "Unrelated"
        context = demo.context(email, package["pack_id"])
        assert context["anchor_date"] == "2026-11-20"
        assert build_plan(package, owners[1], "2026-11-20", DEFAULT_PACKAGE.parent)["trips"][0]["id"] != first["id"]
    finally:
        if owners:
            with store.driver.session(database=store.database) as session:
                session.run("MATCH (n) WHERE n.owner_id IN $owners OR n.id IN $owners DETACH DELETE n",
                            owners=owners).consume()
        store.close()
