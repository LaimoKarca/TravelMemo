import pytest

from experiments.benchmark import event_records, explicit_adjacency_queries
from experiments.cache import PassageCache
from experiments.metrics import summarize


def test_metrics_use_all_queries_and_stable_cutoffs():
    result = summarize(
        [
            {"rank": 1, "latency_ms": 10},
            {"rank": 5, "latency_ms": 20},
            {"rank": None, "latency_ms": 30},
        ]
    )
    assert result["queries"] == 3
    assert result["mrr"] == pytest.approx(0.4)
    assert result["success_at_1"] == pytest.approx(1 / 3)
    assert result["success_at_5"] == pytest.approx(2 / 3)
    assert result["latency_p50_ms"] == 20
    assert summarize([])["mrr"] == 0
    assert summarize([{"rank": 1, "clarified": True, "latency_ms": 1}])["mrr"] == 0


def test_benchmark_events_keep_repeat_visits_and_owner_trip_boundaries():
    base = {
        "user_id": "a",
        "trail_id": "t",
        "venue_id": "same-place",
        "name": "Cafe",
        "venue_city": "Tokyo",
        "venue_category": "Coffee",
        "address": "Test address",
    }
    events = event_records(
        [
            {**base, "event_id": "second", "timestamp": "2026-11-02 09:00:00"},
            {**base, "event_id": "first", "timestamp": "2026-11-01 09:00:00"},
            {**base, "user_id": "b", "event_id": "other", "timestamp": "2026-11-01 09:00:00"},
        ]
    )
    assert [e["id"] for e in events] == ["first", "second", "other"]
    assert events[0]["place_id"] == events[1]["place_id"]
    assert events[0]["trip_id"] != events[2]["trip_id"]
    assert events[0]["place_id"] != events[2]["place_id"]
    assert events[1]["position"] == 1
    assert all(e["notes"] == "" for e in events)


def test_passage_cache_reuses_public_vectors_but_not_queries(tmp_path):
    class Encoder:
        revision = "fixed"
        dimension = 2
        calls = 0

        def encode_passages(self, texts):
            self.calls += 1
            return [[1.0, 0.0] for _ in texts]

        def encode_query(self, text):
            self.calls += 1
            return [0.0, 1.0]

    encoder = Encoder()
    cache = PassageCache(encoder, tmp_path / "vectors.npz")
    assert cache.encode_passages(["a", "a"]) == [[1.0, 0.0], [1.0, 0.0]]
    cache.save()
    reloaded = PassageCache(encoder, cache.path)
    assert reloaded.encode_passages(["a"]) == [[1.0, 0.0]]
    reloaded.encode_query("a")
    reloaded.encode_query("a")
    assert encoder.calls == 3


def test_adjacency_diagnostic_is_explicit_and_preserves_labels():
    rows = [
        {
            "query_type": "relational_after",
            "query_text": "Which cafe did I visit after Tower?",
            "target_event_id": "b",
        },
        {"query_type": "semantic", "query_text": "matcha cafe", "target_event_id": "b"},
    ]
    result = explicit_adjacency_queries(rows)
    assert len(result) == 1
    assert result[0]["query_text"] == "Which cafe did I visit immediately after Tower?"
    assert result[0]["target_event_id"] == "b"
    assert rows[0]["query_text"] == "Which cafe did I visit after Tower?"
