"""Compare production retrievers on pinned public inputs without touching live data."""

import hashlib
import json
import os
import platform
import subprocess
import time
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import numpy as np

from experiments.benchmark import event_records, explicit_adjacency_queries, prepare
from experiments.cache import PassageCache
from experiments.metrics import summarize


def evaluate(
    root="data/benchmark", output="data/evaluation", limit=0, ann=False, explicit_adjacency=False
):
    from backend.config import Settings
    from backend.embedding import EmbeddingModel
    from backend.retrieval import SearchService
    from backend.travel_store import MemoryTravelRepository

    source_events, queries, manifest = prepare(root)
    if explicit_adjacency:
        queries = explicit_adjacency_queries(queries)
        event_map = {e["event_id"]: e for e in source_events}
        if any(
            event_map.get(q["cue_previous_event_id"], {}).get("next_event_id")
            != q["target_event_id"]
            for q in queries
        ):
            raise ValueError("Cannot use non-adjacent labels for the adjacency diagnostic")
        manifest["query_variant"] = (
            "relational_after replaced by immediately after; separate diagnostic"
        )
        manifest["diagnostic_queries_sha256"] = hashlib.sha256(
            json.dumps(queries, sort_keys=True).encode()
        ).hexdigest()
        manifest["adjacent_labels_validated"] = len(queries)
    events = event_records(source_events)
    if limit:
        queries = queries[:limit]
    if not queries:
        raise ValueError("Evaluation requires at least one query")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # This Settings instance intentionally ignores the application's private .env.
    settings = Settings(
        _env_file=None,
        session_secret="evaluation-only-" * 4,
        embedding_model_dir=str(Path(root).parent / "models/multilingual-e5-small"),
    )
    model = PassageCache(
        EmbeddingModel(settings), Path(root) / f"e5-passages-{settings.embedding_revision}.npz"
    )
    if model.download() is False:
        raise RuntimeError("Pinned model download failed")
    repository = MemoryTravelRepository()
    for event in events:
        repository.events[event["id"]] = event.copy()
        tid = event["trip_id"]
        trip = repository.trips.setdefault(
            tid,
            {
                "id": tid,
                "owner_id": event["owner_id"],
                "name": tid,
                "start_date": event["date"],
                "end_date": event["date"],
                "timezone": "Asia/Tokyo",
                "description": "",
                "version": 1,
            },
        )
        trip["start_date"] = min(trip["start_date"], event["date"])
        trip["end_date"] = max(trip["end_date"], event["date"])
    service = SearchService(settings, repository, embedder=model)
    service.initialize()
    service.rebuild()
    while service.process_pending():
        pass
    model.save()
    status = service.index_status()
    if status.get("failed") or status.get("pending") or status.get("ready") != len(events):
        raise RuntimeError(f"Evaluation requires complete embeddings: {status}")

    methods = ("bm25", "e5", "rrf", "next")
    rows = []
    rankings = {}
    for i, query in enumerate(queries):
        for method in methods:
            started = time.perf_counter()
            # Only actual query text + owner enter retrieval. Cue/target metadata are labels, never inputs.
            found = service.search(query["user_id"], query["query_text"], limit=50, method=method)
            if (
                method != "bm25"
                and not found.get("clarification")
                and found.get("vector_status") != "ready"
            ):
                raise RuntimeError(f"{method} evaluation requires working E5 retrieval")
            ids = [item["event"]["id"] for item in found["items"]]
            target = query["target_event_id"]
            rank = (
                ids.index(target) + 1 if target in ids and not found.get("clarification") else None
            )
            rows.append(
                {
                    "query_id": query["query_id"],
                    "query_type": query["query_type"],
                    "method": method,
                    "rank": rank,
                    "clarified": bool(found.get("clarification")),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            rankings[(query["query_id"], method)] = ids
        if (i + 1) % 20 == 0:
            print(f"Evaluated {i + 1}/{len(queries)} queries", flush=True)

    summaries = {}
    for method in methods:
        selected = [r for r in rows if r["method"] == method]
        summaries[method] = {"overall": summarize(selected), "by_query_type": {}}
        for kind in sorted({r["query_type"] for r in selected}):
            summaries[method]["by_query_type"][kind] = summarize(
                [r for r in selected if r["query_type"] == kind]
            )
        summaries[method]["clarifications"] = sum(r["clarified"] for r in selected)

    manifest.update(
        {
            "application_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"])),
            "model": settings.embedding_model,
            "revision": settings.embedding_revision,
            "parameters": {
                "top_k": settings.retrieval_top_k,
                "rrf_k": settings.rrf_k,
                "relation_weight": settings.relation_weight,
                "ranking_cutoff": 50,
            },
            "event_count": len(events),
            "query_count": len(queries),
            "representation": "event own place/category/city/address/date/time/notes; no neighbor text",
            "representation_sha256": hashlib.sha256(
                json.dumps(events, sort_keys=True).encode()
            ).hexdigest(),
            "runtime": {
                "python": platform.python_version(),
                **{p: version(p) for p in ("numpy", "torch", "transformers", "neo4j", "rank-bm25")},
            },
            "search_mode": "exact_in_memory",
            "notes": [
                "MRR is truncated at 50; all missing and clarification queries score zero.",
                "Broad after/before queries may require clarification under product semantics.",
                "Latency includes query encoding and on-demand ranking; not a concurrency load test.",
            ],
        }
    )
    result = {"manifest": manifest, "methods": summaries, "per_query": rows}
    if ann:
        result["ann"] = evaluate_ann(settings, events, queries, rankings, model)
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [
        "# Retrieval evaluation",
        "",
        f"Events: {len(events)}; queries: {len(queries)}.",
        "",
        "| Method | MRR@50 | Success@1 | Success@5 | p50 ms | p95 ms |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for method, summary in summaries.items():
        m = summary["overall"]
        lines.append(
            f"| {method} | {m['mrr']:.4f} | {m['success_at_1']:.4f} | "
            f"{m['success_at_5']:.4f} | {m['latency_p50_ms']:.1f} | {m['latency_p95_ms']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Relational queries",
            "",
            "| Method | MRR@50 | Success@1 | Success@5 | Clarifications (all types) |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for method, summary in summaries.items():
        m = summary["by_query_type"].get("relational_after", summarize([]))
        lines.append(
            f"| {method} | {m['mrr']:.4f} | {m['success_at_1']:.4f} | "
            f"{m['success_at_5']:.4f} | {summary['clarifications']} |"
        )
    lines.extend(["", "## Reproducibility", "", "```json", json.dumps(manifest, indent=2), "```"])
    if ann:
        lines.extend(
            [
                "",
                "## Neo4j ANN (separate isolated database)",
                "",
                "```json",
                json.dumps(result["ann"], indent=2),
                "```",
            ]
        )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Evaluation complete: {output / 'report.md'}")
    return result


def evaluate_ann(settings, events, queries, exact_rankings, model):
    """Implemented against an explicitly isolated EVAL_NEO4J_URI, never application URI."""
    from neo4j import GraphDatabase

    from backend.retrieval import SearchService
    from backend.travel_store import Neo4jTravelRepository

    uri = os.environ.get("EVAL_NEO4J_URI", "")
    password = os.environ.get("EVAL_NEO4J_PASSWORD", "")
    if not uri or not password:
        raise ValueError(
            "--ann requires EVAL_NEO4J_URI and EVAL_NEO4J_PASSWORD for an empty isolated database"
        )
    with GraphDatabase.driver(
        uri, auth=("neo4j", password), notifications_min_severity="OFF"
    ) as driver:
        count = driver.execute_query("MATCH (n) RETURN count(n) AS n").records[0]["n"]
        if count:
            raise ValueError(
                "ANN evaluation refuses nonempty databases; create a fresh isolated volume"
            )
        # Bulk load the exact same events, with labels and relationships used by production.
        driver.execute_query("UNWIND $events AS row CREATE (e:Event) SET e = row", events=events)
        driver.execute_query(
            "MATCH (e:Event) MERGE (u:User {id:e.owner_id}) "
            "MERGE (t:Trip {id:e.trip_id}) ON CREATE SET t.owner_id=e.owner_id, "
            "t.name=e.trip_id, t.start_date=e.date, t.end_date=e.date, "
            "t.version=1, t.timezone='Asia/Tokyo' "
            "MERGE (u)-[:OWNS]->(t) MERGE (t)-[:HAS_EVENT]->(e)"
        )
        driver.execute_query(
            "MATCH (a:Event), (b:Event) WHERE a.owner_id=b.owner_id "
            "AND a.trip_id=b.trip_id AND b.position=a.position+1 MERGE (a)-[:NEXT]->(b)"
        )
        service = SearchService(settings, Neo4jTravelRepository(driver, "neo4j"), embedder=model)
        service.initialize()
        service.rebuild()
        while service.process_pending():
            pass
        driver.execute_query("CALL db.awaitIndexes(180)")
        if service.index_status().get("ready") != len(events):
            raise RuntimeError("ANN evaluation embeddings failed")
        rows = []
        overlap = defaultdict(list)
        for query in queries:
            for method in ("e5", "rrf", "next"):
                started = time.perf_counter()
                found = service.search(
                    query["user_id"], query["query_text"], limit=50, method=method
                )
                if not found.get("clarification") and found.get("vector_status") != "ready":
                    raise RuntimeError("ANN evaluation requires actual indexed vector retrieval")
                ids = [item["event"]["id"] for item in found["items"]]
                target = query["target_event_id"]
                rows.append(
                    {
                        "method": method,
                        "query_type": query["query_type"],
                        "rank": ids.index(target) + 1
                        if target in ids and not found.get("clarification")
                        else None,
                        "clarified": bool(found.get("clarification")),
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                exact = exact_rankings[(query["query_id"], method)]
                overlap[method].append(len(set(ids[:5]) & set(exact[:5])) / max(1, len(exact[:5])))
        return {
            method: {
                **summarize([r for r in rows if r["method"] == method]),
                "exact_top5_overlap": float(np.mean(overlap[method])),
                "by_query_type": {
                    kind: summarize(
                        [r for r in rows if r["method"] == method and r["query_type"] == kind]
                    )
                    for kind in sorted({r["query_type"] for r in rows})
                },
            }
            for method in ("e5", "rrf", "next")
        }
