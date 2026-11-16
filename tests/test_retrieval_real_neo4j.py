import os
import uuid

import pytest
from neo4j import GraphDatabase

from backend.config import Settings
from backend.embedding import E5_DIMENSION, E5_REVISION
from backend.retrieval import SearchService
from backend.search_store import Neo4jSearchStore
from backend.travel_store import Neo4jTravelRepository


class RealTestEmbedder:
    revision = E5_REVISION
    dimension = E5_DIMENSION

    def encode_query(self, text: str) -> list[float]:
        # Simple deterministic vector based on text
        vec = [0.0] * E5_DIMENSION
        if "拉麵" in text or "美食" in text:
            vec[0] = 1.0
        elif "鐵塔" in text or "景點" in text:
            vec[1] = 1.0
        else:
            vec[2] = 1.0
        return vec

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [self.encode_query(t) for t in texts]


@pytest.mark.skipif(os.getenv("TRAVELMEMO_INTEGRATION") != "1", reason="Local Neo4j opt-in")
def test_real_neo4j_vector_ann_isolation_and_graph():
    settings = Settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=5,
    )

    db = settings.neo4j_database
    travel_repo = Neo4jTravelRepository(driver, db)
    travel_repo.initialize()

    embedder = RealTestEmbedder()
    search_store = Neo4jSearchStore(driver, db, embedder=embedder)
    search_store.initialize()

    service = SearchService(settings, travel_repo, embedder=embedder)

    user1 = f"user1-{uuid.uuid4().hex[:8]}"
    user2 = f"user2-{uuid.uuid4().hex[:8]}"

    # Setup User 1 trip and sequential events
    trip1 = travel_repo.create_trip(user1, {
        "name": "User 1 Tokyo Trip",
        "start_date": "2026-10-01",
        "end_date": "2026-10-05",
        "timezone": "Asia/Tokyo",
        "description": "Integration test trip",
    })
    e1_u1 = travel_repo.create_event(user1, trip1["id"], {
        "place_name": "築地市場",
        "category": "美食",
        "date": "2026-10-01",
        "time": "09:00",
        "notes": "生魚片",
    })
    e2_u1 = travel_repo.create_event(user1, trip1["id"], {
        "place_name": "銀座拉麵",
        "category": "美食",
        "date": "2026-10-01",
        "time": "12:00",
        "notes": "特濃醬油拉麵",
    })

    # Setup User 2 trip and event with identical name/category
    trip2 = travel_repo.create_trip(user2, {
        "name": "User 2 Tokyo Trip",
        "start_date": "2026-10-01",
        "end_date": "2026-10-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    e1_u2 = travel_repo.create_event(user2, trip2["id"], {
        "place_name": "銀座拉麵",
        "category": "美食",
        "date": "2026-10-01",
        "time": "13:00",
        "notes": "User 2 的拉麵紀錄",
    })

    # Update embeddings in Neo4j
    u1_ramen_vec = embedder.encode_query("銀座拉麵")
    search_store.update_embeddings([
        {
            "id": e1_u1["id"],
            "owner_id": user1,
            "version": 1,
            "embedding": embedder.encode_query("築地市場"),
            "revision": E5_REVISION,
        },
        {
            "id": e2_u1["id"],
            "owner_id": user1,
            "version": 1,
            "embedding": u1_ramen_vec,
            "revision": E5_REVISION,
        },
        {
            "id": e1_u2["id"],
            "owner_id": user2,
            "version": 1,
            "embedding": u1_ramen_vec,
            "revision": E5_REVISION,
        },
    ])

    # 1. Official CYPHER 25 SEARCH query directly in Neo4j
    # User 1 vector query MUST NOT return User 2's event!
    vec_results_u1 = search_store.query_vector(user1, u1_ramen_vec, limit=10)
    returned_ids_u1 = [item[0]["id"] for item in vec_results_u1]
    assert e2_u1["id"] in returned_ids_u1
    assert e1_u2["id"] not in returned_ids_u1

    # User 2 vector query MUST NOT return User 1's event!
    vec_results_u2 = search_store.query_vector(user2, u1_ramen_vec, limit=10)
    returned_ids_u2 = [item[0]["id"] for item in vec_results_u2]
    assert e1_u2["id"] in returned_ids_u2
    assert e2_u1["id"] not in returned_ids_u2

    # 2. Graph 1-hop NEXT navigation in Neo4j
    next_events = search_store.get_adjacent_events(user1, e1_u1["id"], direction="next")
    assert len(next_events) == 1
    assert next_events[0]["id"] == e2_u1["id"]

    # 3. Directional Query Resolution via SearchService on real Neo4j
    res = service.search(user1, "在築地市場之後的拉麵")
    assert res["vector_status"] == "ready"
    assert res["clarification"] == "您是指該地點緊接著的下一個行程，還是之後的其他行程？"
    assert len(res["items"]) > 0
    top = res["items"][0]
    assert top["event"]["id"] == e2_u1["id"]
    assert top["relation"]["anchor_id"] == e1_u1["id"]
    assert top["relation"]["direction"] == "next"

    # 4. get_event with owner check and trip_name in Neo4j
    ev_detail = service.get_event(user1, e1_u1["id"])
    assert ev_detail is not None
    assert ev_detail["id"] == e1_u1["id"]
    assert ev_detail["trip_name"] == "User 1 Tokyo Trip"

    # Cross-tenant get_event returns None
    assert service.get_event(user1, e1_u2["id"]) is None

    # 5. Method ablations on real Neo4j
    bm25_only = service.search(user1, "拉麵", method="bm25")
    assert bm25_only["vector_status"] == "disabled"
    assert len(bm25_only["items"]) > 0

    e5_only = service.search(user1, "拉麵", method="e5")
    assert e5_only["vector_status"] == "ready"
    assert len(e5_only["items"]) > 0

    rrf_only = service.search(user1, "拉麵", method="rrf")
    assert rrf_only["vector_status"] == "ready"
    assert rrf_only["clarification"] is None

    # 6. Rebuild and process_pending on real Neo4j
    service.rebuild(user1)
    status_rebuilt = service.index_status(user1)
    assert status_rebuilt["pending"] >= 2
    assert status_rebuilt["ready"] == 0

    attempted = service.process_pending()
    assert attempted >= 2
    status_done = service.index_status(user1)
    assert status_done["ready"] >= 2

    # 7. Stale failure isolation on real Neo4j
    # User edits e1_u1 to version 2
    travel_repo.update_event(user1, e1_u1["id"], {
        "place_name": "築地市場 (更新)",
        "category": "美食",
        "date": "2026-10-01",
        "time": "09:30",
        "notes": "生魚片丼飯",
        "version": 1,
    })
    # Delayed failure writeback for old version 1
    search_store.mark_embeddings_failed([
        {"id": e1_u1["id"], "owner_id": user1, "version": 1, "error": "stale network timeout"}
    ])
    with driver.session(database=db) as session:
        e1_rec = session.run("MATCH (e:Event {id: $id}) RETURN e.embedding_status AS status, e.version AS version", id=e1_u1["id"]).single()
        assert e1_rec["version"] == 2
        # Must still be pending, NOT marked failed by old v1 job!
        assert e1_rec["status"] == "pending"

    # 8. Retry cooldown on real Neo4j
    search_store.mark_embeddings_failed([
        {"id": e1_u1["id"], "owner_id": user1, "version": 2, "error": "temporary error"}
    ])
    # With 60s cooldown: must NOT return e1_u1
    pending_cooldown = search_store.get_pending_events(limit=10, retry_seconds=60.0)
    assert not any(p["id"] == e1_u1["id"] for p in pending_cooldown)

    # With 0s cooldown: must return e1_u1 for retry
    pending_retryable = search_store.get_pending_events(limit=10, retry_seconds=0.0)
    assert any(p["id"] == e1_u1["id"] for p in pending_retryable)

    # 9. Truncation metadata persistence in Neo4j
    search_store.update_embeddings([{
        "id": e1_u1["id"],
        "owner_id": user1,
        "version": 2,
        "embedding": embedder.encode_query("築地市場 (更新)"),
        "revision": E5_REVISION,
        "token_count": 620,
        "truncated": True,
    }])
    with driver.session(database=db) as session:
        meta_rec = session.run("MATCH (e:Event {id: $id}) RETURN e.token_count AS tc, e.truncated AS tr", id=e1_u1["id"]).single()
        assert meta_rec["tc"] == 620
        assert meta_rec["tr"] is True

    # 10. verify_relation on real Neo4j
    assert service.verify_relation(user1, e1_u1["id"], e2_u1["id"], "next") is True
    assert service.verify_relation(user1, e2_u1["id"], e1_u1["id"], "prev") is True
    assert service.verify_relation(user1, e1_u1["id"], e1_u2["id"], "next") is False

    # 11. Filter recall with >50 distractor events pushed inside SEARCH WHERE
    # Create 55 distractor events in Osaka and 5 target events in Tokyo
    ramen_vec = embedder.encode_query("特濃拉麵")
    distractor_updates = []
    for i in range(55):
        dev = travel_repo.create_event(user1, trip1["id"], {
            "place_name": f"大阪拉麵 {i}",
            "city": "Osaka",
            "category": "美食",
            "date": "2026-10-02",
            "time": "18:00",
            "notes": "大阪拉麵",
        })
        distractor_updates.append({
            "id": dev["id"],
            "owner_id": user1,
            "version": 1,
            "embedding": ramen_vec,
            "revision": E5_REVISION,
        })
    tokyo_ids = set()
    for i in range(5):
        tev = travel_repo.create_event(user1, trip1["id"], {
            "place_name": f"東京拉麵 {i}",
            "city": "Tokyo",
            "category": "美食",
            "date": "2026-10-03",
            "time": "19:00",
            "notes": "東京拉麵",
        })
        tokyo_ids.add(tev["id"])
        distractor_updates.append({
            "id": tev["id"],
            "owner_id": user1,
            "version": 1,
            "embedding": ramen_vec,
            "revision": E5_REVISION,
        })
    search_store.update_embeddings(distractor_updates)

    # Search with city="Tokyo" filter and limit=5
    # If city filter was outside SEARCH, the top 50 candidates from Osaka would exhaust before filter
    tokyo_res = service.search(user1, "拉麵", filters={"city": "Tokyo"}, limit=5)
    assert len(tokyo_res["items"]) == 5
    for item in tokyo_res["items"]:
        assert item["event"]["city"] == "Tokyo"
        assert item["event"]["id"] in tokyo_ids

    driver.close()
