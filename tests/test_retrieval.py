import math

import pytest

from backend.embedding import (
    E5_DIMENSION,
    E5_MODEL_NAME,
    E5_REVISION,
    EmbeddingModel,
    event_to_passage_text,
    l2_normalize,
)
from backend.retrieval import SearchService
from backend.travel_store import MemoryTravelRepository


class MockEmbedder:
    def __init__(self, vector_map=None):
        self.revision = E5_REVISION
        self.dimension = E5_DIMENSION
        self.vector_map = vector_map or {}
        self.default_vector = [1.0 / math.sqrt(E5_DIMENSION)] * E5_DIMENSION

    def encode_query(self, text: str) -> list[float]:
        for k, v in self.vector_map.items():
            if k in text:
                return v
        return self.default_vector

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        results = []
        for t in texts:
            matched = False
            for k, v in self.vector_map.items():
                if k in t:
                    results.append(v)
                    matched = True
                    break
            if not matched:
                results.append(self.default_vector)
        return results


def test_embedding_model_specification():
    # 1. Pinned constants
    assert E5_MODEL_NAME == "intfloat/multilingual-e5-small"
    assert E5_REVISION == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert E5_DIMENSION == 384

    # 2. Lazy loading: must NOT load model on instantiation
    model = EmbeddingModel()
    assert not model.is_loaded

    # 3. L2 normalization helper
    raw = [3.0, 4.0]
    norm = l2_normalize(raw)
    assert math.isclose(math.sqrt(sum(x * x for x in norm)), 1.0)
    assert math.isclose(norm[0], 0.6)
    assert math.isclose(norm[1], 0.8)

    # 4. Passage text serialization uses only own fields
    event = {
        "date": "2026-05-01",
        "time": "12:30",
        "category": "美食",
        "place_name": "一蘭拉麵",
        "city": "東京",
        "address": "新宿區",
        "notes": "濃郁豚骨湯頭",
    }
    passage = event_to_passage_text(event)
    assert "日期: 2026-05-01" in passage
    assert "時間: 12:30" in passage
    assert "類別: 美食" in passage
    assert "地點: 一蘭拉麵" in passage
    assert "城市: 東京" in passage
    assert "心得: 濃郁豚骨湯頭" in passage


def test_embedding_graceful_degradation():
    class FailingEmbedder(EmbeddingModel):
        def encode_query(self, text: str) -> list[float]:
            raise RuntimeError("Model download failed or environment lacks torch.")

    repo = MemoryTravelRepository()
    service = SearchService(None, repo, embedder=FailingEmbedder())

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "清水寺",
        "category": "景點",
        "date": "2026-05-01",
        "time": None,
        "notes": "古色古香",
    })

    # Search should still succeed via BM25 and report vector_status = 'degraded'
    result = service.search("user-1", "清水寺")
    assert result["vector_status"] == "degraded"
    assert len(result["items"]) == 1
    assert result["items"][0]["event"]["place_name"] == "清水寺"


def test_search_isolation_multi_tenant():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    # Alice's trip & events
    trip_a = repo.create_trip("alice", {
        "name": "Alice in Tokyo",
        "start_date": "2026-05-01",
        "end_date": "2026-05-03",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev_a = repo.create_event("alice", trip_a["id"], {
        "place_name": "東京鐵塔",
        "category": "景點",
        "date": "2026-05-01",
        "time": "10:00",
        "notes": "紅色鐵塔",
    })

    # Bob's trip & events
    trip_b = repo.create_trip("bob", {
        "name": "Bob in Tokyo",
        "start_date": "2026-05-01",
        "end_date": "2026-05-03",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev_b = repo.create_event("bob", trip_b["id"], {
        "place_name": "東京晴空塔",
        "category": "景點",
        "date": "2026-05-01",
        "time": "14:00",
        "notes": "晴空塔",
    })

    # Alice searches "東京" -> only ev_a, never ev_b
    res_a = service.search("alice", "東京")
    returned_ids_a = [item["event"]["id"] for item in res_a["items"]]
    assert ev_a["id"] in returned_ids_a
    assert ev_b["id"] not in returned_ids_a

    # Bob searches "東京" -> only ev_b, never ev_a
    res_b = service.search("bob", "東京")
    returned_ids_b = [item["event"]["id"] for item in res_b["items"]]
    assert ev_b["id"] in returned_ids_b
    assert ev_a["id"] not in returned_ids_b


def test_search_filters():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "日本雙城",
        "start_date": "2026-05-01",
        "end_date": "2026-05-10",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "築地市場",
        "city": "東京",
        "category": "美食",
        "date": "2026-05-01",
        "notes": "生魚片",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "錦市場",
        "city": "京都",
        "category": "美食",
        "date": "2026-05-06",
        "notes": "小吃",
    })

    # Filter by city Tokyo
    res_city = service.search("user-1", "市場", filters={"city": "東京"})
    assert len(res_city["items"]) == 1
    assert res_city["items"][0]["event"]["place_name"] == "築地市場"

    # Filter by date range (May 5 to May 10)
    res_date = service.search("user-1", "市場", filters={"date_from": "2026-05-05"})
    assert len(res_date["items"]) == 1
    assert res_date["items"][0]["event"]["place_name"] == "錦市場"


def test_directional_reranking_and_clarification():
    repo = MemoryTravelRepository()

    # Orthogonal vectors for distinct semantic concepts
    v_tsukiji = [1.0] + [0.0] * 383
    v_ramen = [0.0, 1.0] + [0.0] * 382
    v_tower = [0.0, 0.0, 1.0] + [0.0] * 381

    embedder = MockEmbedder(vector_map={
        "築地": v_tsukiji,
        "拉麵": v_ramen,
        "鐵塔": v_tower,
    })
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "東京漫遊",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })

    # Sequential events: Tsukiji -> Ginza Ramen -> Tokyo Tower
    e1 = repo.create_event("user-1", trip["id"], {
        "place_name": "築地市場",
        "category": "美食",
        "date": "2026-05-01",
        "time": "09:00",
        "notes": "海鮮早餐",
    })
    e2 = repo.create_event("user-1", trip["id"], {
        "place_name": "銀座拉麵",
        "category": "美食",
        "date": "2026-05-01",
        "time": "12:00",
        "notes": "濃郁醬油拉麵",
    })
    e3 = repo.create_event("user-1", trip["id"], {
        "place_name": "東京鐵塔",
        "category": "景點",
        "date": "2026-05-01",
        "time": "15:00",
        "notes": "看市景",
    })

    # 1. Forward directional query with ambiguous "之後":
    # "在築地市場之後的拉麵" -> 1-hop NEXT is e2 ("銀座拉麵")
    res_after = service.search("user-1", "在築地市場之後的拉麵")
    assert res_after["clarification"] == "您是指該地點緊接著的下一個行程，還是之後的其他行程？"
    assert len(res_after["items"]) > 0
    top_item = res_after["items"][0]
    assert top_item["event"]["id"] == e2["id"]
    assert top_item["relation"] is not None
    assert top_item["relation"]["anchor_id"] == e1["id"]
    assert top_item["relation"]["direction"] == "next"
    assert top_item["relation"]["anchor_date"] == "2026-05-01"
    assert top_item["relation"]["target_date"] == "2026-05-01"
    assert any("關係候選" in r for r in top_item["reasons"])

    # 2. Explicit adjacent query with "下一站" -> NO clarification
    res_next = service.search("user-1", "築地市場下一站")
    assert res_next["clarification"] is None
    assert res_next["items"][0]["event"]["id"] == e2["id"]

    # 3. Backward directional query with "之前":
    # "在東京鐵塔之前的拉麵" -> reverse 1-hop is e2 ("銀座拉麵")
    res_before = service.search("user-1", "在東京鐵塔之前的拉麵")
    assert res_before["clarification"] is None
    top_before = res_before["items"][0]
    assert top_before["event"]["id"] == e2["id"]
    assert top_before["relation"]["anchor_id"] == e3["id"]
    assert top_before["relation"]["direction"] == "prev"


def test_outdated_embedding_version_exclusion():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev = repo.create_event("user-1", trip["id"], {
        "place_name": "淺草寺",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "求籤",
    })

    # Simulate completed embedding at version 1
    service.store.update_embeddings([{
        "id": ev["id"],
        "owner_id": "user-1",
        "version": 1,
        "embedding": [0.5] * 384,
    }])

    # Vector query finds it at version 1
    found = service.store.query_vector("user-1", [0.5] * 384)
    assert len(found) == 1
    assert found[0][0]["id"] == ev["id"]

    # Update event -> version bumps to 2, embedding_status resets to pending
    repo.update_event("user-1", ev["id"], {
        "place_name": "淺草寺 本堂",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "求籤與大繪馬",
        "version": 1,
    })

    # Vector query MUST NOT return the outdated embedding (embedded_version 1 != version 2)
    found_after_update = service.store.query_vector("user-1", [0.5] * 384)
    assert len(found_after_update) == 0

    # Search continues to work via BM25
    res = service.search("user-1", "淺草寺")
    assert len(res["items"]) == 1
    assert res["items"][0]["event"]["id"] == ev["id"]


@pytest.mark.anyio
async def test_background_worker_and_rebuild():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev = repo.create_event("user-1", trip["id"], {
        "place_name": "清水舞台",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "俯瞰京都市景",
    })

    # Event starts pending
    status_before = service.index_status("user-1")
    assert status_before["pending"] == 1
    assert status_before["ready"] == 0

    # Process pending embeddings synchronously
    attempted = service.process_pending()
    assert attempted == 1

    # Now no pending events remain, ready count is 1
    status_after = service.index_status("user-1")
    assert status_after["pending"] == 0
    assert status_after["ready"] == 1

    # Vector search now succeeds with version check passing
    vec_results = service.store.query_vector("user-1", embedder.default_vector)
    assert len(vec_results) == 1
    assert vec_results[0][0]["id"] == ev["id"]

    # Rebuild resets state
    service.rebuild()
    status_rebuilt = service.index_status("user-1")
    assert status_rebuilt["pending"] == 1
    assert status_rebuilt["ready"] == 0


def test_search_method_ablations():
    class CountingEmbedder(MockEmbedder):
        def __init__(self):
            super().__init__()
            self.query_count = 0

        def encode_query(self, text: str) -> list[float]:
            self.query_count += 1
            return super().encode_query(text)

    repo = MemoryTravelRepository()
    embedder = CountingEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Tokyo Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "銀座拉麵",
        "category": "美食",
        "date": "2026-05-01",
        "notes": "醬油拉麵",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "淺草寺",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "雷門",
    })

    # Index events
    service.process_pending()

    # 1. method="bm25": MUST NOT invoke embedder
    embedder.query_count = 0
    res_bm25 = service.search("user-1", "拉麵", method="bm25")
    assert embedder.query_count == 0
    assert res_bm25["vector_status"] == "disabled"
    assert len(res_bm25["items"]) == 1
    assert res_bm25["items"][0]["event"]["place_name"] == "銀座拉麵"

    # 2. method="e5": vector only
    embedder.query_count = 0
    res_e5 = service.search("user-1", "拉麵", method="e5")
    assert embedder.query_count == 1
    assert res_e5["vector_status"] == "ready"
    assert len(res_e5["items"]) > 0

    # 3. method="rrf": hybrid without graph
    res_rrf = service.search("user-1", "在銀座拉麵之後的景點", method="rrf")
    assert res_rrf["vector_status"] == "ready"
    assert res_rrf["clarification"] is None

    # 4. method="next": default full graph + clarification
    res_next = service.search("user-1", "在銀座拉麵之後的景點", method="next")
    assert res_next["clarification"] is not None
    assert any(item.get("relation") is not None for item in res_next["items"])


def test_stale_failure_isolation():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev = repo.create_event("user-1", trip["id"], {
        "place_name": "東京晴空塔",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "展望台",
    })
    assert ev["version"] == 1

    # User edits the event, advancing version to 2
    ev_v2 = repo.update_event("user-1", ev["id"], {
        "place_name": "東京晴空塔 (頂層)",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "最高層展望台",
        "version": 1,
    })
    assert ev_v2["version"] == 2
    stored_ev = repo.events[ev["id"]]
    assert stored_ev["version"] == 2
    assert stored_ev["embedding_status"] == "pending"

    # A delayed worker job for old version 1 tries to write back failure
    service.store.mark_embeddings_failed([
        {"id": ev["id"], "owner_id": "user-1", "version": 1, "error": "timeout"}
    ])

    # Old failure must NOT mark the newer edit (v2) as failed
    assert stored_ev["embedding_status"] == "pending"
    assert stored_ev.get("embedding_error") is None

    # Processing pending now handles current version 2 successfully
    attempted = service.process_pending()
    assert attempted == 1
    assert stored_ev["embedding_status"] == "completed"
    assert stored_ev["embedded_version"] == 2


def test_revision_mismatch_and_missing_fails(tmp_path):
    class FakeSettings:
        embedding_model = E5_MODEL_NAME
        embedding_revision = E5_REVISION
        embedding_model_dir = str(tmp_path)

    # 1. config.json exists, but revision.txt is missing
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    model_missing = EmbeddingModel(FakeSettings())
    with pytest.raises(RuntimeError, match="revision marker missing"):
        model_missing._ensure_loaded()

    # 2. revision.txt exists, but hash is wrong
    (tmp_path / "revision.txt").write_text("0000000000000000000000000000000000000000", encoding="utf-8")
    model_mismatch = EmbeddingModel(FakeSettings())
    with pytest.raises(RuntimeError, match="revision mismatch"):
        model_mismatch._ensure_loaded()


def test_retry_cooldown_and_recovery():
    class TemporarilyFailingEmbedder(MockEmbedder):
        def __init__(self):
            super().__init__()
            self.should_fail = True

        def encode_passages(self, texts: list[str]) -> list[list[float]]:
            if self.should_fail:
                raise RuntimeError("Temporary model loading timeout")
            return super().encode_passages(texts)

    class FastRetrySettings:
        embedding_retry_seconds = 0.05
        retrieval_top_k = 50
        rrf_k = 60
        relation_weight = 0.5

    repo = MemoryTravelRepository()
    embedder = TemporarilyFailingEmbedder()
    service = SearchService(FastRetrySettings(), repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "嵐山竹林",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "幽靜小徑",
    })

    # First attempt fails
    attempted = service.process_pending()
    assert attempted == 1
    status = service.index_status("user-1")
    assert status["failed"] == 1
    assert status["ready"] == 0

    # Immediate second attempt within cooldown period does NOT retry (no tight retry spin)
    attempted_immediate = service.process_pending()
    assert attempted_immediate == 0

    # After cooldown period expires and model recovers
    import time
    time.sleep(0.06)
    embedder.should_fail = False

    # Next attempt retries and succeeds
    attempted_recovered = service.process_pending()
    assert attempted_recovered == 1
    status_recovered = service.index_status("user-1")
    assert status_recovered["ready"] == 1
    assert status_recovered["failed"] == 0


def test_shared_encoder_concurrency():
    import concurrent.futures

    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    def worker_task(idx: int):
        q_vec = service.embedder.encode_query(f"query {idx}")
        p_vecs = service.embedder.encode_passages([f"passage {idx}-a", f"passage {idx}-b"])
        return len(q_vec), len(p_vecs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_task, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    assert all(dim == 384 and count == 2 for dim, count in results)


def test_truncation_metadata_persisted():
    repo = MemoryTravelRepository()

    class TruncationAwareEmbedder(MockEmbedder):
        def encode_passages_with_metadata(self, texts: list[str]):
            vecs = self.encode_passages(texts)
            metas = []
            for t in texts:
                token_count = len(t.split())
                metas.append({"token_count": token_count, "truncated": token_count > 512})
            return vecs, metas

    service = SearchService(None, repo, embedder=TruncationAwareEmbedder())

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    long_notes = " ".join(["word"] * 600)
    ev = repo.create_event("user-1", trip["id"], {
        "place_name": "詳細景點",
        "category": "景點",
        "date": "2026-05-01",
        "notes": long_notes,
    })

    service.process_pending()

    with repo.lock:
        stored = repo.events[ev["id"]]
        assert stored["truncated"] is True
        assert stored["token_count"] > 512


def test_verify_relation_graph_reorder():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev_a = repo.create_event("user-1", trip["id"], {
        "place_name": "A 景點",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "",
    })
    ev_b = repo.create_event("user-1", trip["id"], {
        "place_name": "B 景點",
        "category": "景點",
        "date": "2026-05-02",
        "notes": "",
    })
    ev_c = repo.create_event("user-1", trip["id"], {
        "place_name": "C 景點",
        "category": "景點",
        "date": "2026-05-03",
        "notes": "",
    })

    # Initial order: A -> B -> C
    assert service.verify_relation("user-1", ev_a["id"], ev_b["id"], "next") is True
    assert service.verify_relation("user-1", ev_b["id"], ev_c["id"], "next") is True
    assert service.verify_relation("user-1", ev_a["id"], ev_c["id"], "next") is False

    # User reorders trip events so that C comes before B: A (05-01) -> C (05-01) -> B (05-02)
    # Update C date to 2026-05-01 (inserting after A)
    repo.update_event("user-1", ev_c["id"], {
        "place_name": "C 景點",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "",
        "version": 1,
    })

    # Now adjacent next of A is C, NOT B! Stale answer must fail closed:
    assert service.verify_relation("user-1", ev_a["id"], ev_b["id"], "next") is False
    assert service.verify_relation("user-1", ev_a["id"], ev_c["id"], "next") is True


def test_revision_change_queues_and_excludes_old_vectors():
    class DynamicRevisionEmbedder(MockEmbedder):
        def __init__(self, rev):
            super().__init__()
            self.revision = rev

    repo = MemoryTravelRepository()
    embedder = DynamicRevisionEmbedder("rev_initial")
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "京都神社",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "",
    })

    # 1. Index at rev_initial
    service.process_pending()
    status1 = service.index_status("user-1")
    assert status1["ready"] == 1
    assert status1["pending"] == 0

    results1 = service.store.query_vector("user-1", embedder.default_vector)
    assert len(results1) == 1

    # 2. Reconfigured revision changes to rev_updated
    embedder.revision = "rev_updated"

    # Querying vector MUST NOT return vector from incompatible revision
    results_mismatch = service.store.query_vector("user-1", embedder.default_vector)
    assert len(results_mismatch) == 0

    # Index status indicates old revision vector needs re-indexing (pending=1, ready=0)
    status2 = service.index_status("user-1")
    assert status2["ready"] == 0
    assert status2["pending"] == 1

    # process_pending re-indexes with rev_updated
    attempted = service.process_pending()
    assert attempted == 1
    status3 = service.index_status("user-1")
    assert status3["ready"] == 1
    assert status3["pending"] == 0

    # Vector query now finds it with rev_updated
    results_updated = service.store.query_vector("user-1", embedder.default_vector)
    assert len(results_updated) == 1


def test_failed_cooldown_and_no_starvation():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev_fail = repo.create_event("user-1", trip["id"], {
        "place_name": "失敗景點",
        "category": "景點",
        "date": "2026-05-01",
        "notes": "",
    })
    # Mark ev_fail as failed just now
    service.store.mark_embeddings_failed([
        {"id": ev_fail["id"], "owner_id": "user-1", "version": 1, "error": "test timeout"}
    ])

    # Now create a fresh second event
    ev_fresh = repo.create_event("user-1", trip["id"], {
        "place_name": "新鮮景點",
        "category": "景點",
        "date": "2026-05-02",
        "notes": "",
    })

    # When fetching pending with limit=1, fresh pending MUST proceed and NOT be starved by failed job
    pending = service.store.get_pending_events(limit=1, retry_seconds=60.0)
    assert len(pending) == 1
    assert pending[0]["id"] == ev_fresh["id"]


def test_load_failed_unlatches_when_files_appear(tmp_path):
    class FakeSettings:
        embedding_model = E5_MODEL_NAME
        embedding_revision = E5_REVISION
        embedding_model_dir = str(tmp_path)

    model = EmbeddingModel(FakeSettings())

    # Initially missing files -> _ensure_loaded raises and marks _load_failed
    with pytest.raises(RuntimeError):
        model._ensure_loaded()
    assert model._load_failed is True

    # Now create dummy config and revision marker, but not complete weights
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "revision.txt").write_text(E5_REVISION, encoding="utf-8")
    (tmp_path / "model.safetensors").write_text("weights", encoding="utf-8")

    # When files have appeared, next _ensure_loaded unlatches _load_failed
    # (It will attempt to load transformers from tmp_path and fail on dummy weights, NOT on "unavailable" latch!)
    with pytest.raises(Exception) as excinfo:
        model._ensure_loaded()
    assert "Embedding model unavailable" not in str(excinfo.value)
    assert model._load_failed is True


def test_directional_english_and_chinese_category_enforcement():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Tokyo Trip",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })

    # Trip sequence:
    # 1. Matsuya (Fast Food Restaurant)
    # 2. Ichiran (Ramen Restaurant)
    # 3. Lawson (Convenience Store)
    ev1 = repo.create_event("user-1", trip["id"], {
        "place_name": "Matsuya",
        "category": "Fast Food Restaurant",
        "date": "2026-05-01",
        "notes": "Quick beef bowl",
    })
    ev2 = repo.create_event("user-1", trip["id"], {
        "place_name": "Ichiran",
        "category": "Ramen Restaurant",
        "date": "2026-05-01",
        "notes": "Tonkotsu ramen",
    })
    repo.create_event("user-1", trip["id"], {
        "place_name": "Lawson",
        "category": "Convenience Store",
        "date": "2026-05-01",
        "notes": "Snacks and drinks",
    })

    # 1. English query: "Which Ramen Restaurant did I visit after Matsuya?"
    # Anchor: Matsuya -> 1-hop next: Ichiran
    # Target category: Ramen Restaurant (matches Ichiran)
    res_en = service.search("user-1", "Which Ramen Restaurant did I visit after Matsuya?")
    assert len(res_en["items"]) > 0
    top_item = res_en["items"][0]
    assert top_item["event"]["id"] == ev2["id"]
    assert top_item["relation"] is not None
    assert top_item["relation"]["anchor_id"] == ev1["id"]
    assert any("Relation candidate: 1-hop stop after [Matsuya]" in r for r in top_item["reasons"])
    assert res_en["clarification"] == "Do you mean the immediately adjacent stop, or later events after this place?"

    # 2. Query asking for a category that does NOT match the 1-hop stop:
    # "Which Convenience Store did I visit after Matsuya?"
    # The 1-hop stop after Matsuya is Ichiran (Ramen Restaurant), NOT Convenience Store.
    # Therefore Ichiran must NOT be admitted as a relation candidate for this query!
    res_mismatch = service.search("user-1", "Which Convenience Store did I visit after Matsuya?")
    top_rel = [it for it in res_mismatch["items"] if it.get("relation") is not None]
    assert len(top_rel) == 0

    # 3. Chinese query with category constraint:
    # Trip with 松屋 -> 一蘭拉麵
    trip_zh = repo.create_trip("user-zh", {
        "name": "台北美食之旅",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "timezone": "Asia/Taipei",
        "description": "",
    })
    ev_zh1 = repo.create_event("user-zh", trip_zh["id"], {
        "place_name": "松屋",
        "category": "速食店",
        "date": "2026-06-01",
        "notes": "牛丼",
    })
    ev_zh2 = repo.create_event("user-zh", trip_zh["id"], {
        "place_name": "一蘭拉麵",
        "category": "拉麵店",
        "date": "2026-06-01",
        "notes": "天然豚骨湯頭",
    })
    res_zh = service.search("user-zh", "在松屋之後去吃哪間拉麵店？")
    assert len(res_zh["items"]) > 0
    top_zh = res_zh["items"][0]
    assert top_zh["event"]["id"] == ev_zh2["id"]
    assert top_zh["relation"] is not None
    assert top_zh["relation"]["anchor_id"] == ev_zh1["id"]
    assert res_zh["clarification"] == "您是指該地點緊接著的下一個行程，還是之後的其他行程？"


def test_anchor_filtering_isolation_and_multi_trip_duplicates():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    # Trip 1 in Osaka -> target next event in Tokyo
    trip1 = repo.create_trip("user-1", {
        "name": "Trip 1",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    t1_ev1 = repo.create_event("user-1", trip1["id"], {
        "place_name": "Matsuya",
        "category": "Fast Food",
        "city": "Osaka",
        "date": "2026-05-01",
        "notes": "Osaka breakfast",
    })
    t1_ev2 = repo.create_event("user-1", trip1["id"], {
        "place_name": "Ichiran Shinjuku",
        "category": "Ramen Restaurant",
        "city": "Tokyo",
        "date": "2026-05-02",
        "notes": "Tokyo lunch",
    })

    # Trip 2 in Tokyo with duplicate anchor "Matsuya"
    trip2 = repo.create_trip("user-1", {
        "name": "Trip 2",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    repo.create_event("user-1", trip2["id"], {
        "place_name": "Matsuya",
        "category": "Fast Food",
        "city": "Tokyo",
        "date": "2026-06-01",
        "notes": "Tokyo breakfast",
    })
    t2_ev2 = repo.create_event("user-1", trip2["id"], {
        "place_name": "Ippudo Ginza",
        "category": "Ramen Restaurant",
        "city": "Tokyo",
        "date": "2026-06-02",
        "notes": "Tokyo ramen",
    })

    # 1. Unfiltered query: both Matsuyas are valid anchors; candidates include both Ichiran and Ippudo
    res_unfiltered = service.search("user-1", "Which Ramen Restaurant did I visit after Matsuya?")
    cand_ids = {it["event"]["id"] for it in res_unfiltered["items"] if it.get("relation")}
    assert t1_ev2["id"] in cand_ids
    assert t2_ev2["id"] in cand_ids

    # 2. Filtered by trip_id=trip1["id"]: anchor search must ONLY search within trip1
    res_trip1 = service.search(
        "user-1",
        "Which Ramen Restaurant did I visit after Matsuya?",
        filters={"trip_id": trip1["id"]},
    )
    cand_ids_t1 = {it["event"]["id"] for it in res_trip1["items"] if it.get("relation")}
    assert t1_ev2["id"] in cand_ids_t1
    assert t2_ev2["id"] not in cand_ids_t1

    # 3. Anchor filter isolation: Target search filters city="Tokyo", date_from="2026-05-02".
    # Anchor Matsuya (city="Osaka", date="2026-05-01") is NOT in Tokyo and NOT on 2026-05-02.
    # Because anchor retrieval is NOT restricted by target city/date, Matsuya is successfully found as anchor!
    res_filtered_city = service.search(
        "user-1",
        "Which Ramen Restaurant did I visit after Matsuya?",
        filters={"trip_id": trip1["id"], "city": "Tokyo", "date_from": "2026-05-02"},
    )
    assert len(res_filtered_city["items"]) > 0
    top_res = res_filtered_city["items"][0]
    assert top_res["event"]["id"] == t1_ev2["id"]
    assert top_res["relation"] is not None
    assert top_res["relation"]["anchor_id"] == t1_ev1["id"]


def test_two_visits_same_place_explicit_anchor_id():
    repo = MemoryTravelRepository()
    embedder = MockEmbedder()
    service = SearchService(None, repo, embedder=embedder)

    trip = repo.create_trip("user-1", {
        "name": "Tokyo Trip with Two Matsuya Visits",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })

    # Day 1: Matsuya -> Blue Bottle Coffee
    ev1_matsuya = repo.create_event("user-1", trip["id"], {
        "place_name": "Matsuya",
        "category": "Fast Food",
        "date": "2026-05-01",
        "notes": "Day 1 breakfast beef bowl",
    })
    ev2_coffee = repo.create_event("user-1", trip["id"], {
        "place_name": "Blue Bottle Coffee",
        "category": "Cafe",
        "date": "2026-05-01",
        "notes": "Day 1 coffee break",
    })

    # Day 2: Tokyo Skytree
    repo.create_event("user-1", trip["id"], {
        "place_name": "Tokyo Skytree",
        "category": "Attraction",
        "date": "2026-05-02",
        "notes": "Observation deck",
    })

    # Day 3: Matsuya -> Tsutaya Books
    ev4_matsuya = repo.create_event("user-1", trip["id"], {
        "place_name": "Matsuya",
        "category": "Fast Food",
        "date": "2026-05-03",
        "notes": "Day 3 dinner beef bowl",
    })
    ev5_books = repo.create_event("user-1", trip["id"], {
        "place_name": "Tsutaya Books",
        "category": "Bookstore",
        "date": "2026-05-03",
        "notes": "Late night bookstore visit",
    })

    # 1. Without anchor_id: query-only anchor search retrieves both visits
    # Graph expansion mixes NEXT context from both Matsuya visits
    res_no_anchor = service.search("user-1", "Where did I go after Matsuya?")
    rel_cand_ids = {it["event"]["id"] for it in res_no_anchor["items"] if it.get("relation")}
    assert ev2_coffee["id"] in rel_cand_ids
    assert ev5_books["id"] in rel_cand_ids

    # 2. With explicit anchor_id for Day 3 visit (ev4_matsuya):
    # Only Day 3 Matsuya is used as anchor; NEXT context is strictly ev5_books (Tsutaya Books)
    res_day3 = service.search("user-1", "Where did I go after Matsuya?", anchor_id=ev4_matsuya["id"])
    top_day3 = res_day3["items"][0]
    assert top_day3["event"]["id"] == ev5_books["id"]
    assert top_day3["relation"] is not None
    assert top_day3["relation"]["anchor_id"] == ev4_matsuya["id"]
    day3_rel_cand_ids = {it["event"]["id"] for it in res_day3["items"] if it.get("relation")}
    assert ev5_books["id"] in day3_rel_cand_ids
    assert ev2_coffee["id"] not in day3_rel_cand_ids

    # 3. With explicit anchor_id for Day 1 visit (ev1_matsuya):
    # Only Day 1 Matsuya is used as anchor; NEXT context is strictly ev2_coffee (Blue Bottle Coffee)
    res_day1 = service.search("user-1", "Where did I go after Matsuya?", anchor_id=ev1_matsuya["id"])
    top_day1 = res_day1["items"][0]
    assert top_day1["event"]["id"] == ev2_coffee["id"]
    assert top_day1["relation"] is not None
    assert top_day1["relation"]["anchor_id"] == ev1_matsuya["id"]
    day1_rel_cand_ids = {it["event"]["id"] for it in res_day1["items"] if it.get("relation")}
    assert ev2_coffee["id"] in day1_rel_cand_ids
    assert ev5_books["id"] not in day1_rel_cand_ids

    # 4. Multi-turn relative query without in-text anchor: "What was the next stop?" with anchor_id
    res_relative = service.search("user-1", "What was the next stop?", anchor_id=ev4_matsuya["id"])
    assert len(res_relative["items"]) > 0
    top_rel = res_relative["items"][0]
    assert top_rel["event"]["id"] == ev5_books["id"]
    assert top_rel["relation"] is not None
    assert top_rel["relation"]["anchor_id"] == ev4_matsuya["id"]

    # 5. Respect selected trip: If anchor_id belongs to trip1 but filters specify a different trip_id,
    # it must reject the mismatched anchor_id
    res_mismatched_trip = service.search(
        "user-1",
        "Where did I go after Matsuya?",
        filters={"trip_id": "different-trip-id"},
        anchor_id=ev4_matsuya["id"],
    )
    rel_mismatched = [it for it in res_mismatched_trip["items"] if it.get("relation")]
    assert len(rel_mismatched) == 0
