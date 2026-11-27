"""Compare exact and Neo4j ANN ranks for a fixed synthetic query sample."""

import argparse
import json
import os
import random
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from backend.config import Settings
from backend.embedding import EmbeddingModel
from experiments.cache import PassageCache
from experiments.evaluate import evaluate_ann

EVENT_PROPERTIES = (
    "id", "owner_id", "trip_id", "place_id", "place_name", "city", "address", "map_url",
    "category", "date", "time", "notes", "position", "version",
)


def select_queries(queries, per_stratum=5):
    buckets = defaultdict(list)
    for query in queries:
        if query["split"] == "test" and query["expected"] == "unique":
            buckets[query["query_type"], query["variant"]].append(query)
    rng = random.Random(6128)
    return [
        query
        for key, bucket in sorted(buckets.items())
        for query in rng.sample(sorted(bucket, key=lambda item: item["query_id"]), per_stratum)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ranking", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    uri = urlsplit(os.environ.get("EVAL_NEO4J_URI", ""))
    if uri.scheme != "bolt" or uri.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use an isolated loopback Bolt URI in EVAL_NEO4J_URI.")
    corpus = json.loads(args.input.read_text(encoding="utf-8"))
    queries = select_queries(corpus["queries"])
    owners = {query["user_id"] for query in queries}
    events = [
        {key: event[key] for key in EVENT_PROPERTIES if key in event}
        for event in corpus["events"]
        if event["owner_id"] in owners
    ]
    query_ids = {query["query_id"] for query in queries}
    exact = {}
    with args.ranking.open(encoding="utf-8") as rankings:
        for line in rankings:
            row = json.loads(line)
            query_id = row["query_id"]
            if query_id in query_ids:
                for method in ("e5", "rrf", "next"):
                    exact[(query_id, method)] = row["methods"][method]["ranking"]
    if len(exact) != 3 * len(queries):
        raise ValueError("Complete the exact ranking before running the Neo4j comparison.")
    settings = Settings(
        _env_file=None,
        app_env="development",
        session_secret="synthetic-evaluation-only-" * 2,
        embedding_model="intfloat/multilingual-e5-small",
        embedding_model_dir="data/models/multilingual-e5-small",
        retrieval_top_k=50,
        rrf_k=60,
        relation_weight=0.5,
    )
    model = PassageCache(EmbeddingModel(settings), args.cache)
    results = evaluate_ann(settings, events, queries, exact, model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "query_count": len(queries),
                "owner_count": len(owners),
                "event_count": len(events),
                "methods": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Exact / ANN comparison finished for {len(queries)} queries.", flush=True)


if __name__ == "__main__":
    main()
