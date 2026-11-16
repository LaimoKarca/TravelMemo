"""Download fixed public benchmark inputs; never import into the application database."""

import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

COMMIT = "cadb2eca2a1e09475a1851545e12de99779b8a53"
REPOSITORY = "https://github.com/LaimoKarca/fuzzy-travel-recall-benchmark"
FILES = {
    "events": "data/prepared/stage_04_retrieval/common/tokyo_event_documents.csv",
    "queries": "data/prepared/stage_03_queries/tokyo_recall_queries_main.csv",
}


def explicit_adjacency_queries(queries: list[dict]) -> list[dict]:
    """Separate diagnostic variant; original benchmark queries remain untouched."""
    result = []
    for query in queries:
        if query["query_type"] != "relational_after":
            continue
        text, count = re.subn(
            r"\bafter\b", "immediately after", query["query_text"], count=1, flags=re.IGNORECASE
        )
        if count != 1:
            raise ValueError("Adjacency diagnostic expects an explicit English after cue")
        result.append({**query, "query_text": text})
    return result


def prepare(root: str | Path) -> tuple[list[dict], list[dict], dict]:
    root = Path(root) / "upstream"
    root.mkdir(parents=True, exist_ok=True)
    inputs = {}
    rows = {}
    for name, relative in FILES.items():
        path = root / Path(relative).name
        # Re-fetch pinned public input to validate the cached file; no branch aliases.
        url = f"https://raw.githubusercontent.com/LaimoKarca/fuzzy-travel-recall-benchmark/{COMMIT}/{relative}"
        with urlopen(url, timeout=60) as response:
            expected = response.read()
        if not path.exists() or path.read_bytes() != expected:
            path.write_bytes(expected)
        inputs[name] = {"source": relative, "sha256": hashlib.sha256(expected).hexdigest()}
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows[name] = list(csv.DictReader(stream))
    manifest = {"benchmark_repository": REPOSITORY, "benchmark_commit": COMMIT, "inputs": inputs}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return rows["events"], rows["queries"], manifest


def event_records(rows: list[dict]) -> list[dict]:
    """Represent only the event's own fields; do not embed neighbor/target metadata."""
    groups = {}
    result = []
    for row in rows:
        group = (row["user_id"], row["trail_id"])
        groups.setdefault(group, []).append(row)
    for (owner, trip), events in groups.items():
        for position, row in enumerate(
            sorted(events, key=lambda r: (r["timestamp"], r["event_id"]))
        ):
            timestamp = row["timestamp"].replace("T", " ")
            result.append(
                {
                    "id": row["event_id"],
                    "owner_id": owner,
                    "trip_id": f"{owner}:{trip}",
                    "place_id": f"{owner}:{row['venue_id']}",
                    "place_name": row["name"],
                    "city": row["venue_city"],
                    "address": row["address"],
                    "category": row["venue_category"],
                    "date": timestamp[:10],
                    "time": timestamp[11:16] or None,
                    "notes": "",
                    "position": position,
                    "version": 1,
                }
            )
    return result
