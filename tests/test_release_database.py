"""Opt-in persistence checks using unique synthetic owners, never existing user records."""

import os
from uuid import uuid4

import pytest
from neo4j import GraphDatabase

from backend.config import Settings
from backend.conversation_store import Neo4jConversationStore


@pytest.mark.skipif(os.getenv("TRAVELMEMO_INTEGRATION") != "1", reason="Local Neo4j opt-in")
def test_conversation_persistence_usage_and_owner_isolation():
    settings = Settings()
    owner = "release-test-" + uuid4().hex
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        store = Neo4jConversationStore(driver, settings.neo4j_database)
        store.initialize()
        conversation = store.create_conversation(
            owner, "Synthetic release test", "2026-11-16T00:00:00Z"
        )
        cid = conversation["id"]
        assert store.get_conversation("other-" + owner, cid) is None
        assert store.add_message(
            owner,
            cid,
            "assistant",
            "Synthetic evidence",
            "answered",
            [
                {
                    "event_id": "test-event",
                    "trip_id": "test-trip",
                    "date": "2026-11-01",
                    "place_name": "Test cafe",
                    "version": 1,
                    "state": "current",
                    "relation": {
                        "anchor_id": "test-anchor",
                        "direction": "next",
                        "anchor_date": "2026-10-31",
                        "target_date": "2026-11-01",
                    },
                }
            ],
            "2026-11-16T00:00:01Z",
        )
        assert store.reserve_slot(owner, "2026-11-16", max_daily=1)[0]
        store.record_tokens(owner, "2026-11-16", 10, 20)
        store.release_slot(owner)
        reopened = Neo4jConversationStore(driver, settings.neo4j_database)
        messages = reopened.get_messages(owner, cid)
        assert len(messages) == 1
        assert messages[0]["citations"][0]["event_id"] == "test-event"
        assert messages[0]["citations"][0]["relation"]["anchor_id"] == "test-anchor"
        usage = reopened.get_usage(owner, "2026-11-16")
        assert usage == {"requests": 1, "input_tokens": 10, "output_tokens": 20}
        assert not reopened.reserve_slot(owner, "2026-11-16", max_daily=1)[0]
        assert not reopened.delete_conversation("other-" + owner, cid)
        assert reopened.delete_conversation(owner, cid)
        assert reopened.get_messages(owner, cid) is None
    finally:
        driver.execute_query(
            "MATCH (n) WHERE n.owner_id=$owner OR (n:User AND n.id=$owner) DETACH DELETE n",
            owner=owner,
            database_=settings.neo4j_database,
        )
        driver.close()
