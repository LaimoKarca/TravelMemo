"""Score frozen synthetic travel questions with the application's real retrieval service."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.config import Settings
from backend.embedding import E5_MODEL_NAME, E5_REVISION, EmbeddingModel, event_to_passage_text
from backend.retrieval import SearchService, parse_directional_query
from backend.search_store import BM25Index, MemorySearchStore, passes_filters
from backend.travel_store import MemoryTravelRepository
from experiments.cache import PassageCache

METHODS = ("bm25", "e5", "rrf", "next", "next_no_edges")
MODEL_DIR = Path("data/models/multilingual-e5-small")
RANK_CUTOFF = 50


class QualityEmbedder(PassageCache):
    """Share deterministic query encodings in the ranking pass, not in the timing pass."""

    def __init__(self, model, path):
        super().__init__(model, path)
        self.cached_query = lru_cache(maxsize=8192)(model.encode_query)

    def encode_query(self, text):
        return self.cached_query(text)


class QualityStore(MemorySearchStore):
    """Reuse fitted BM25 and cosine ranks only while the benchmark corpus is immutable."""

    def __init__(self, repository, embedder):
        super().__init__(repository, embedder)
        self.fitted_bm25 = lru_cache(maxsize=256)(self._fit_bm25)
        self.vector_ranks = lru_cache(maxsize=256)(self._score_vector)

    def _fit_bm25(self, owner_id, filter_items):
        filters = dict(filter_items)
        events = [
            e
            for e in self.repository.events.values()
            if e["owner_id"] == owner_id and passes_filters(e, filters)
        ]
        index = BM25Index()
        index.fit(events, [event_to_passage_text(e) for e in events])
        return index

    def query_bm25(self, owner_id, query, filters=None, limit=50, include_zero_scores=False):
        index = self.fitted_bm25(owner_id, tuple(sorted((filters or {}).items())))
        return index.score(query, include_zero_scores=include_zero_scores)[:limit]

    def _score_vector(self, owner_id, vector, filter_items):
        return super().query_vector(owner_id, list(vector), dict(filter_items), limit=RANK_CUTOFF)

    def query_vector(self, owner_id, query_vector, filters=None, limit=50):
        return self.vector_ranks(
            owner_id, tuple(query_vector), tuple(sorted((filters or {}).items()))
        )[:limit]


class TraversalTrace:
    """Observe production adjacency calls and optionally suppress edges for one run."""

    def __init__(self, store):
        self.store = store
        self.edges = []
        self.suppress_edges = False

    def __getattr__(self, name):
        return getattr(self.store, name)

    def get_adjacent_events(self, owner_id, anchor_id, direction="next"):
        candidates = (
            []
            if self.suppress_edges
            else self.store.get_adjacent_events(owner_id, anchor_id, direction=direction)
        )
        self.edges.append((anchor_id, direction, candidates))
        return candidates


def build_search(corpus, *, model_dir=MODEL_DIR, cache_path=None, owners=None):
    """Build a local SearchService using only the provided corpus and pinned local weights."""
    defaults = Settings.model_construct()
    defaults.embedding_model = E5_MODEL_NAME
    defaults.embedding_revision = E5_REVISION
    defaults.embedding_model_dir = str(model_dir)
    defaults.session_secret = "offline-evaluation-only-" * 3
    model = EmbeddingModel(defaults)
    embedder = QualityEmbedder(model, Path(cache_path)) if cache_path else model
    repository = MemoryTravelRepository()
    repository.trips.update(
        {
            trip["id"]: trip.copy()
            for trip in corpus["trips"]
            if owners is None or trip["owner_id"] in owners
        }
    )
    for row in corpus["events"]:
        if owners is not None and row["owner_id"] not in owners:
            continue
        event = {
            "version": 1,
            "place_id": row["id"],
            **row,
        }
        repository.events[event["id"]] = event

    service = SearchService(defaults, repository, embedder=embedder)
    service.store = QualityStore(repository, embedder=embedder)
    service.initialize()
    service.rebuild()
    indexed = 0
    while size := service.process_pending(batch_size=128):
        indexed += size
        if cache_path and indexed % 512 == 0:
            embedder.save()
    status = service.index_status()
    if (
        status.get("pending")
        or status.get("failed")
        or status.get("ready") != len(repository.events)
    ):
        raise RuntimeError(f"Pinned E5 corpus must be fully indexed: {status}")
    if cache_path:
        embedder.save()
    return service


def _ranked_lookup(results, event_id):
    return results.index(event_id) + 1 if event_id and event_id in results else None


def _traversal_trace(store, query, result):
    parsed = parse_directional_query(query["query_text"])
    categories = store.get_owned_categories(query["user_id"]) if store.edges else ()
    target_query = (parsed or {}).get("target_query", "").casefold().strip()
    # Mirror the category guard in SearchService solely to expose its pre-ranking effect.
    category = next(
        (
            value.casefold().strip()
            for value in sorted(categories, key=len, reverse=True)
            if target_query
            and value.strip()
            and (
                value.casefold().strip() in target_query or target_query in value.casefold().strip()
            )
        ),
        None,
    )
    candidate = next(
        (item for item in result["items"] if item["event"]["id"] == query.get("target_event_id")),
        None,
    )
    return {
        "parsed": parsed,
        "attempted_anchors": [anchor for anchor, _, _ in store.edges],
        "adjacency": [
            {
                "anchor_id": anchor,
                "direction": direction,
                "candidate_ids": [item["id"] for item in items],
                "valid_candidate_ids": [
                    item["id"]
                    for item in items
                    if category is None or item.get("category", "").casefold() == category
                ],
            }
            for anchor, direction, items in store.edges
        ],
        "target_relation": candidate.get("relation") if candidate else None,
    }


def _measure_quality(service, query, method):
    store = service.store
    store.edges.clear()
    store.suppress_edges = method == "next_no_edges"
    result = service.search(
        query["user_id"],
        query["query_text"],
        limit=RANK_CUTOFF,
        method="next" if store.suppress_edges else method,
    )
    if method != "bm25" and result["vector_status"] != "ready":
        raise RuntimeError(f"Unexpected E5 fallback on {query['query_id']} / {method}")
    ids = [item["event"]["id"] for item in result["items"]]
    row = {
        "ranking": ids,
        "rank": _ranked_lookup(ids, query.get("target_event_id"))
        if not result["clarification"]
        else None,
        "negative_rank": _ranked_lookup(ids, query.get("hard_negative_id")),
        "has_negative": bool(query.get("hard_negative_id")),
        "clarified": bool(result["clarification"]),
    }
    if method == "next":
        row["trace"] = _traversal_trace(store, query, result)
    return row


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _rr(rank):
    return 1 / rank if rank else 0.0


def _hit_at(rank, k):
    return bool(rank and rank <= k)


def _method_summary(rows, method):
    records = [entry["methods"][method] for entry in rows if method in entry["methods"]]
    return {
        "queries": len(records),
        "mrr_at_50": _mean(_rr(row["rank"]) for row in records),
        "success_at_1": _mean(_hit_at(row["rank"], 1) for row in records),
        "success_at_5": _mean(_hit_at(row["rank"], 5) for row in records),
        "hard_negative_win_rate": _mean(
            bool(
                row["rank"] and (row["negative_rank"] is None or row["rank"] < row["negative_rank"])
            )
            for row in records
            if row["has_negative"]
        ),
    }


def _paired_difference(pairs):
    """Cluster bootstrap over travelers, preserving paired queries within each cluster."""
    clusters = defaultdict(list)
    differences = []
    for owner, comparison, reference in pairs:
        delta = comparison - reference
        clusters[owner].append(delta)
        differences.append(delta)
    if not differences:
        return {"pairs": 0, "travelers": 0, "delta": None, "ci95": None}
    count = len(clusters)
    interval = None
    if count > 1:
        sums = np.array([sum(cluster) for cluster in clusters.values()])
        sizes = np.array([len(cluster) for cluster in clusters.values()])
        sample = np.random.default_rng(20261127).integers(count, size=(2000, count))
        means = sums[sample].sum(axis=1) / sizes[sample].sum(axis=1)
        interval = [float(number) for number in np.quantile(means, [0.025, 0.975])]
    return {
        "pairs": len(differences),
        "travelers": count,
        "delta": _mean(differences),
        "ci95": interval,
        "wins": sum(delta > 0 for delta in differences),
        "ties": sum(delta == 0 for delta in differences),
        "losses": sum(delta < 0 for delta in differences),
    }


def _direction_summary(rows):
    """Evaluate stages from runtime trace; gold IDs appear only in scoring."""
    breakdown = defaultdict(list)
    for row in rows:
        trace = row["methods"]["next"]["trace"]
        parsed = trace["parsed"] or {}
        anchor, target, direction = row["anchor_event_id"], row["target_event_id"], row["direction"]
        raw_target_edge = any(
            step["anchor_id"] == anchor
            and step["direction"] == direction
            and target in step["candidate_ids"]
            for step in trace["adjacency"]
        )
        valid_target_edge = any(
            step["anchor_id"] == anchor
            and step["direction"] == direction
            and target in step["valid_candidate_ids"]
            for step in trace["adjacency"]
        )
        candidate_relation = trace["target_relation"] or {}
        outcome = {
            "parsed": bool(parsed),
            "correct_direction": parsed.get("direction") == direction,
            "gold_anchor_attempted": anchor in trace["attempted_anchors"],
            "gold_edge_reached_before_filters": raw_target_edge,
            "gold_edge_passed_category": valid_target_edge,
            "target_ranked_with_gold_edge": candidate_relation.get("anchor_id") == anchor
            and candidate_relation.get("direction") == direction,
        }
        breakdown["overall"].append(outcome)
        breakdown[row["variant"]].append(outcome)
    return {
        name: {
            "queries": len(entries),
            **{key: sum(entry[key] for entry in entries) for key in entries[0]},
        }
        for name, entries in breakdown.items()
    }


def summarize(rows):
    unique = [row for row in rows if row["expected"] == "unique"]
    relational = [row for row in unique if row["query_type"] == "relational"]
    unique_by_family = defaultdict(dict)
    for row in unique:
        unique_by_family[(row["user_id"], row["family_id"])][row["variant"]] = row
    multi = [row for row in rows if row["expected"] == "multi"]
    clarify = [row for row in rows if row["expected"] == "clarify"]
    no_evidence = [row for row in rows if row["expected"] == "no_evidence"]
    methods = {}
    paired = {}
    for method in METHODS:
        selected = relational if method == "next_no_edges" else unique
        methods[method] = {
            "overall": _method_summary(selected, method),
            "by_variant": {
                kind: _method_summary([r for r in selected if r["variant"] == kind], method)
                for kind in sorted({r["variant"] for r in selected})
            },
            "by_query_type": {
                kind: _method_summary([r for r in selected if r["query_type"] == kind], method)
                for kind in sorted({r["query_type"] for r in selected})
            },
            "by_query_type_and_variant": {
                kind: {
                    variant: _method_summary(
                        [
                            r
                            for r in selected
                            if r["query_type"] == kind and r["variant"] == variant
                        ],
                        method,
                    )
                    for variant in sorted({r["variant"] for r in selected})
                }
                for kind in sorted({r["query_type"] for r in selected})
            },
            "weak_minus_exact_rr": _paired_difference(
                (
                    owner,
                    _rr(group["weak"]["methods"][method]["rank"]),
                    _rr(group["exact"]["methods"][method]["rank"]),
                )
                for (owner, _), group in sorted(unique_by_family.items())
                if "weak" in group and "exact" in group and method in group["weak"]["methods"]
            ),
        }
        if method == "next_no_edges":
            continue
        methods[method]["boundary"] = {
            "multi_queries": len(multi),
            "multi_recall_at_5": _mean(
                len(set(row["relevant_event_ids"]) & set(row["methods"][method]["ranking"][:5]))
                / len(row["relevant_event_ids"])
                for row in multi
            ),
            "expected_clarification_queries": len(clarify),
            "expected_clarification_rate": _mean(
                row["methods"][method]["clarified"] for row in clarify
            ),
            "no_evidence_queries": len(no_evidence),
            "no_evidence_returned_candidates_rate": _mean(
                bool(row["methods"][method]["ranking"]) for row in no_evidence
            ),
        }
    for method, baseline, selected in (
        ("e5", "bm25", unique),
        ("rrf", "bm25", unique),
        ("rrf", "e5", unique),
        ("next", "rrf", relational),
        ("next", "next_no_edges", relational),
    ):
        paired[f"{method}_minus_{baseline}"] = {
            name: _paired_difference(
                (
                    row["user_id"],
                    score(row["methods"][method]["rank"]),
                    score(row["methods"][baseline]["rank"]),
                )
                for row in selected
            )
            for name, score in (("rr", _rr), ("success_at_1", lambda rank: _hit_at(rank, 1)))
        }
    return {
        "methods": methods,
        "paired_comparisons": paired,
        "direction": _direction_summary(relational),
    }


def evaluation_settings():
    """Public experimental parameters, excluding paths and verification metadata."""
    return {
        "model": E5_MODEL_NAME,
        "top_k": 50,
        "rrf_k": 60,
        "relation_weight": 0.5,
        "ranking_cutoff": RANK_CUTOFF,
        "anchor_top_k": 5,
    }


def _selected_queries(corpus, split, limit):
    queries = sorted(
        (query for query in corpus["queries"] if query["split"] == split),
        key=lambda query: query["query_id"],
    )
    if limit:
        random.Random(20261127).shuffle(queries)
        queries = queries[:limit]
    if not queries:
        raise ValueError(f"No queries for {split!r}")
    return queries


def _restore(path):
    records = {}
    if path.exists():
        with path.open("r+b") as stream:
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    # A process interrupted during append can leave an incomplete tail line.
                    stream.truncate(offset)
                    break
                row = json.loads(line)
                records[row["query_id"]] = row
    return records


def _timing_sample(service, queries, records, per_stratum):
    groups = defaultdict(list)
    for query in queries:
        groups[(query["query_type"], query["variant"])].append(query)
    randomizer = random.Random(20261127)
    chosen = [
        query
        for name in sorted(groups)
        for query in randomizer.sample(groups[name], min(per_stratum, len(groups[name])))
    ]
    randomizer.shuffle(chosen)
    raw_model = getattr(service.embedder, "model", service.embedder)
    service.embedder = raw_model
    service.store = MemorySearchStore(service.repository, embedder=raw_model)
    for method in METHODS[:4]:
        service.search(chosen[0]["user_id"], chosen[0]["query_text"], method=method)
    elapsed = defaultdict(list)
    for query in chosen:
        order = list(METHODS[:4])
        randomizer.shuffle(order)
        for method in order:
            started = time.perf_counter()
            result = service.search(
                query["user_id"], query["query_text"], limit=RANK_CUTOFF, method=method
            )
            elapsed[method].append((time.perf_counter() - started) * 1000)
            ranked_ids = [item["event"]["id"] for item in result["items"]]
            if ranked_ids != records[query["query_id"]]["methods"][method]["ranking"]:
                raise RuntimeError(f"Cached/uncached rank mismatch: {query['query_id']} / {method}")
    return {
        method: {
            "queries": len(times),
            "p50_ms": float(np.median(times)),
            "p95_ms": sorted(times)[math.ceil(len(times) * 0.95) - 1],
        }
        for method, times in elapsed.items()
    }


def evaluate(
    input_path,
    output,
    split="test",
    limit=0,
    latency_per_stratum=0,
    model_dir=MODEL_DIR,
    cache_path=None,
):
    input_path, output = Path(input_path), Path(output)
    raw = input_path.read_bytes()
    corpus = json.loads(raw)
    queries = _selected_queries(corpus, split, limit)
    owners = {query["user_id"] for query in queries}
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / f"{split}-checkpoint.json"
    source_root = Path(__file__).resolve().parent.parent
    algorithms = (
        "experiments/fuzzy_evaluate.py",
        "experiments/cache.py",
        "backend/retrieval.py",
        "backend/search_store.py",
        "backend/embedding.py",
    )
    signature = {
        "input": hashlib.sha256(raw).hexdigest(),
        "implementation": hashlib.sha256(
            b"\0".join((source_root / rel).read_bytes() for rel in algorithms)
        ).hexdigest(),
        "model_revision": E5_REVISION,
        "settings": evaluation_settings(),
    }
    row_path = output / f"{split}-ranking.jsonl"
    if checkpoint.exists():
        if json.loads(checkpoint.read_text(encoding="utf-8")) != signature:
            raise ValueError("Checkpoint corpus or evaluator changed; use a new output directory")
    elif row_path.exists():
        raise ValueError("Cannot resume rankings without their evaluator checkpoint")
    else:
        temporary = checkpoint.with_suffix(".tmp")
        temporary.write_text(json.dumps(signature, indent=2), encoding="utf-8")
        temporary.replace(checkpoint)
    rows = _restore(row_path)
    pending = [query for query in queries if query["query_id"] not in rows]
    service = None
    if pending or latency_per_stratum:
        service = build_search(
            corpus,
            model_dir=model_dir,
            cache_path=cache_path or output / "passages.npz",
            owners=owners,
        )
        service.store = TraversalTrace(service.store)
    if pending:
        assert service is not None
        with row_path.open("a", encoding="utf-8", newline="\n") as stream:
            for index, query in enumerate(pending, start=1):
                methods = METHODS if query["query_type"] == "relational" else METHODS[:4]
                row = {
                    **query,
                    "methods": {m: _measure_quality(service, query, m) for m in methods},
                }
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                rows[query["query_id"]] = row
                if index % 100 == 0:
                    print(f"Completed {index}/{len(pending)} remaining queries", flush=True)
    selected = [rows[query["query_id"]] for query in queries]
    result = {
        "dataset": {
            "split": split,
            "queries": len(queries),
            "travelers": len(owners),
            "events_in_split": sum(e["owner_id"] in owners for e in corpus["events"]),
            "unique_target_families": len(
                {(q["user_id"], q["family_id"]) for q in queries if q["expected"] == "unique"}
            ),
            "distinct_anchors": len(
                {q["anchor_event_id"] for q in queries if q.get("anchor_event_id")}
            ),
        },
        "settings": evaluation_settings(),
        **summarize(selected),
    }
    if latency_per_stratum:
        assert service is not None
        result["uncached_latency"] = _timing_sample(service, queries, rows, latency_per_stratum)
    (output / f"{split}-summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Scored {len(queries)} queries from {len(owners)} travelers", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=Path("data/fuzzy-evaluation"), type=Path)
    parser.add_argument("--split", default="test", choices=("pilot", "dev", "test"))
    parser.add_argument(
        "--limit", default=0, type=int, help="fixed-seed sample limit for smoke runs"
    )
    parser.add_argument("--latency-per-stratum", default=0, type=int)
    parser.add_argument("--model-dir", default=MODEL_DIR, type=Path)
    parser.add_argument(
        "--cache", type=Path, help="shared pinned-E5 passage cache in ignored data/"
    )
    args = parser.parse_args()
    if min(args.limit, args.latency_per_stratum) < 0:
        parser.error("sample counts must be non-negative")
    evaluate(
        args.input,
        args.output,
        args.split,
        args.limit,
        args.latency_per_stratum,
        args.model_dir,
        args.cache,
    )


if __name__ == "__main__":
    main()
