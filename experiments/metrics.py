"""Known-item recall metrics. Missing/abstained queries remain in denominators."""

from statistics import median


def summarize(rows: list[dict]) -> dict:
    count = len(rows)
    ranks = [None if r.get("clarified") else r.get("rank") for r in rows]
    times = sorted(r["latency_ms"] for r in rows)
    return {
        "queries": count,
        "mrr": sum(1 / rank for rank in ranks if rank) / count if count else 0,
        "success_at_1": sum(rank == 1 for rank in ranks) / count if count else 0,
        "success_at_5": sum(bool(rank and rank <= 5) for rank in ranks) / count if count else 0,
        "latency_p50_ms": median(times) if count else 0,
        "latency_p95_ms": times[min(count - 1, int(count * 0.95))] if count else 0,
    }
