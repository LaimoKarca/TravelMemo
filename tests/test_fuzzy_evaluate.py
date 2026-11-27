import json

from backend.embedding import E5_REVISION
from backend.retrieval import SearchService
from backend.travel_store import MemoryTravelRepository
from experiments.fuzzy_evaluate import TraversalTrace, _measure_quality, _restore, summarize


class MockEmbedder:
    revision = E5_REVISION

    def encode_query(self, text):
        return [1.0, 0.0]


def test_directional_reranking_and_no_edges_share_production_queries():
    repository = MemoryTravelRepository()
    for position, (name, category) in enumerate(
        [("Pine Temple", "Temple"), ("Quiet Lunch", "Cafe"), ("Cafe Extra", "Cafe")]
    ):
        event_id = f"event-{position}"
        repository.events[event_id] = {
            "id": event_id,
            "owner_id": "owner",
            "trip_id": "trip",
            "place_id": event_id,
            "place_name": name,
            "category": category,
            "date": "2026-01-30",
            "position": position,
            "version": 1,
            "embedded_version": 1,
            "embedding_status": "completed",
            "embedding_model_revision": E5_REVISION,
            "embedding": [1.0, 0.0],
        }
    service = SearchService(None, repository, embedder=MockEmbedder())
    service.store = TraversalTrace(service.store)
    query = {
        "query_id": "q",
        "user_id": "owner",
        "query_text": "Which Cafe did I visit immediately after Pine Temple?",
        "expected": "unique",
        "query_type": "relational",
        "variant": "no_name",
        "family_id": "f",
        "target_event_id": "event-1",
        "anchor_event_id": "event-0",
        "hard_negative_id": "event-2",
        "direction": "next",
    }
    methods = {
        name: _measure_quality(service, query, name)
        for name in ("bm25", "e5", "rrf", "next", "next_no_edges")
    }
    assert methods["next"]["trace"]["target_relation"]["anchor_id"] == "event-0"
    assert methods["next_no_edges"]["ranking"]
    summary = summarize([{**query, "methods": methods}])
    assert summary["direction"]["overall"]["gold_edge_passed_category"] == 1
    assert summary["paired_comparisons"]["next_minus_next_no_edges"]["rr"]["pairs"] == 1


def test_restore_truncates_only_interrupted_tail(tmp_path):
    path = tmp_path / "test-ranking.jsonl"
    good = {"query_id": "q", "methods": {"bm25": {"ranking": ["target"]}}}
    committed = (json.dumps(good) + "\n").encode()
    path.write_bytes(committed + b'{"query_id":')
    assert _restore(path) == {"q": good}
    assert path.read_bytes() == committed
