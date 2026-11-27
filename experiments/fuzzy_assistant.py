"""Run the TravelMemo assistant against frozen, fictional travel records."""

import argparse
import hashlib
import json
import logging
import os
import random
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import HTTPException

from backend.conversation import ConversationService
from backend.llm import OpenAILLM

ANSWERABLE_TYPES = ("semantic", "time_place", "relational")
VARIANTS = ("exact", "colloquial", "no_name", "weak")
BOUNDARIES = ("multi", "clarify", "missing")
SEED = 20261127
EVENT_HEADER = re.compile(r"^\[Event ID: ([^\]\r\n]+)\]", re.MULTILINE)


def select_rounds(queries: list[dict], split: str = "test", limit: int | None = None):
    """Return fixed, interleaved strata. Repeated cases keep their original ID."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for query in queries:
        if query["split"] == split:
            groups[query["query_type"], query["variant"]].append(query)
    randomizer = random.Random(SEED)
    primary_groups = []
    for kind, variant, count in [
        *((kind, variant, 30) for kind in ANSWERABLE_TYPES for variant in VARIANTS),
        *((kind, "boundary", 80) for kind in BOUNDARIES),
    ]:
        candidates = sorted(groups[kind, variant], key=lambda q: q["query_id"])
        randomizer.shuffle(candidates)
        if split == "test" and len(candidates) < count:
            raise ValueError(f"Not enough held-out cases for {kind}/{variant}")
        primary_groups.append(candidates[:count])
    primary = [
        group[index] for index in range(80) for group in primary_groups if index < len(group)
    ]
    if limit is not None:
        return [(query, 1) for query in primary[:limit]]
    if split != "test":
        return [(query, 1) for query in primary]
    no_name = [
        query
        for group in primary_groups[:12]
        for query in group[:10]
        if query["variant"] in ("no_name", "weak")
    ]
    boundary = [query for group in primary_groups[12:] for query in group[:20]]
    return [(query, 1) for query in primary] + [
        (query, attempt) for attempt in (2, 3) for query in no_name + boundary
    ]


class EvidenceRecorder:
    """Observe exactly the evidence delivered to the production answer model."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.evidence_ids: list[str] = []
        self.model_called = False
        self.model_tokens = {"input": 0, "output": 0}

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def generate(self, instructions, input_text):
        envelope = json.loads(input_text)
        self.evidence_ids = EVENT_HEADER.findall(envelope.get("untrusted_evidence", ""))
        self.model_called = True
        result = self.adapter.generate(instructions, input_text)
        self.model_tokens = {"input": result.input_tokens, "output": result.output_tokens}
        return result


def normalize(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def score_response(query: dict, row: dict, events: dict[str, dict]) -> dict[str, bool | None]:
    expected = query["expected"]
    relevant = set(query["relevant_event_ids"])
    delivered_evidence = set(row["evidence_event_ids"])
    citations = set(row["citation_event_ids"])
    status = row["status"]
    answered = status == "answered"
    score = {
        "has_all_answer_evidence": None,
        "has_all_expected_citations": None,
        "has_expected_place_names": None,
        "grounding_precheck_pass": None,
        "correct_clarification": None,
        "correct_abstention": None,
        "unsupported_answer": None,
    }
    if expected in ("unique", "multi"):
        if not relevant:
            raise ValueError("An answerable query requires relevant event IDs")
        acceptable_citations = relevant | set(query.get("support_event_ids", []))
        if query.get("anchor_event_id"):
            acceptable_citations.add(query["anchor_event_id"])
        answer = normalize(row["content"])
        names_ok = all(
            any(
                normalized_name and normalized_name in answer
                for name in [events[event_id]["place_name"], *events[event_id].get("aliases", [])]
                if (normalized_name := normalize(name))
            )
            for event_id in relevant
        )
        citations_ok = answered and relevant <= citations <= acceptable_citations
        score.update(
            has_all_answer_evidence=relevant <= delivered_evidence,
            has_all_expected_citations=citations_ok,
            has_expected_place_names=answered and names_ok,
            grounding_precheck_pass=answered and names_ok and citations_ok,
        )
    elif expected == "clarify":
        score["correct_clarification"] = status == "needs_clarification" and not citations
        score["unsupported_answer"] = answered
    elif expected == "no_evidence":
        score["correct_abstention"] = status == "insufficient_evidence" and not citations
        score["unsupported_answer"] = answered
    else:
        raise ValueError(f"Unknown assistant benchmark outcome {expected!r}")
    return score


def run_turn(query, attempt, search, llm_options, events, *, adapter_factory=OpenAILLM):
    started = time.perf_counter()
    recorder = EvidenceRecorder(adapter_factory(**llm_options))
    service = ConversationService(search.settings, search, llm=recorder)
    # Benchmark the answer pipeline with fresh histories, independent of title generation.
    owner = query["user_id"]
    conversation = service.create_conversation(owner, title="Synthetic evaluation")
    http_status = None
    try:
        response = service.post_message(owner, conversation["id"], query["query_text"])
    except HTTPException as exc:
        http_status = exc.status_code
        response = {"status": "blocked" if http_status == 400 else "unavailable", "content": ""}
    finally:
        service.delete_conversation(owner, conversation["id"])
    citations = response.get("citations", [])
    row = {
        "query_id": query["query_id"],
        "query_type": query["query_type"],
        "variant": query["variant"],
        "expected": query["expected"],
        "attempt": attempt,
        "status": response["status"],
        "http_status": http_status,
        "content": response["content"],
        "evidence_event_ids": recorder.evidence_ids,
        "citation_event_ids": [citation["event_id"] for citation in citations],
        "citation_relations": [
            {"event_id": citation["event_id"], **citation["relation"]}
            for citation in citations
            if citation.get("relation")
        ],
        "model_called": recorder.model_called,
        "model_answer_tokens": recorder.model_tokens,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    row["scores"] = score_response(query, row, events)
    return row


def summarize(rows: list[dict]) -> dict[str, Any]:
    primary = [row for row in rows if row["attempt"] == 1]

    def scores(subset):
        result = {}
        for field in sorted({field for row in subset for field in row["scores"]}):
            values = [row["scores"][field] for row in subset if row["scores"][field] is not None]
            if values:
                result[field] = {
                    "numerator": sum(values),
                    "denominator": len(values),
                    "rate": sum(values) / len(values),
                }
        return result

    groups: dict[str, list[dict]] = defaultdict(list)
    repeats: dict[str, list[dict]] = defaultdict(list)
    status_counts: dict[str, int] = defaultdict(int)
    for row in primary:
        status_counts[row["status"]] += 1
        groups[f"{row['query_type']}/{row['variant']}"].append(row)
    for row in rows:
        repeats[row["query_id"]].append(row)
    complete = [group for group in repeats.values() if len(group) == 3]
    return {
        "primary_cases": len(primary),
        "total_attempts": len(rows),
        "primary_status_counts": dict(status_counts),
        "primary_scores": scores(primary),
        "by_stratum": {key: scores(group) for key, group in sorted(groups.items())},
        "repeat_stability": {
            "cases_with_three_attempts": len(complete),
            "same_status": sum(len({r["status"] for r in group}) == 1 for group in complete),
            "same_status_and_citations": sum(
                len({(r["status"], frozenset(r["citation_event_ids"])) for r in group}) == 1
                for group in complete
            ),
        },
        "notes": [
            "Rates include unavailable and blocked attempts in their eligible denominators.",
            "Grounding precheck verifies expected place names and IDs, not all natural-language claims.",
            "Only delivered event IDs count as model evidence; direct route decisions may omit a model call.",
            "Latency is end-to-end per assistant turn under the configured concurrency.",
            "Assistant token counts are answer-model calls only, excluding safety and tool-selection calls.",
        ],
    }


def load_llm_options(env_file: Path) -> dict:
    configured = dotenv_values(env_file) if env_file.is_file() else {}

    def value(name, default):
        return os.environ.get(name) or configured.get(name) or default

    key = value("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Configure OPENAI_API_KEY locally before calling the assistant benchmark")
    return {
        "api_key": key,
        "model": value("OPENAI_MODEL", "gpt-6-luna"),
        "timeout": float(value("OPENAI_TIMEOUT", "45")),
        "max_output_tokens": int(value("OPENAI_MAX_OUTPUT_TOKENS", "2000")),
    }


def write_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_grounding_review(
    path: Path, rows: list[dict], queries: list[dict], events: dict[str, dict]
):
    """Export a blind, stratified sample for independent inspection of answer text."""
    by_stratum: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in sorted(rows, key=lambda row: row["query_id"]):
        if row["attempt"] == 1:
            by_stratum[row["query_type"], row["variant"]].append(row)
    query_map = {query["query_id"]: query for query in queries}
    randomizer = random.Random(SEED)
    sample = []
    for group, candidates in sorted(by_stratum.items()):
        for row in randomizer.sample(candidates, min(4, len(candidates))):
            query = query_map[row["query_id"]]
            label_ids = query["relevant_event_ids"] + query.get("alternative_event_ids", [])
            if query.get("anchor_event_id"):
                label_ids.append(query["anchor_event_id"])
            supplied_ids = list(
                dict.fromkeys(label_ids + row["evidence_event_ids"] + row["citation_event_ids"])
            )
            sample.append(
                {
                    "query_id": query["query_id"],
                    "stratum": "/".join(group),
                    "question": query["query_text"],
                    "expected_action": query["expected"],
                    "labeled_event_ids": label_ids,
                    "answer": row["content"],
                    "answer_status": row["status"],
                    "answer_citation_ids": row["citation_event_ids"],
                    "records": [
                        {
                            field: events[event_id].get(field)
                            for field in (
                                "id",
                                "trip_id",
                                "position",
                                "place_name",
                                "category",
                                "city",
                                "date",
                                "time",
                                "notes",
                            )
                        }
                        for event_id in supplied_ids
                        if event_id in events
                    ],
                    "review_decision": None,
                    "review_evidence": None,
                }
            )
    randomizer.shuffle(sample)
    write_json(
        path,
        {
            "rubric": {
                "supported": "答覆、日期與順序均由紀錄支持，引用對應正確，或按預期澄清／拒答。",
                "partial": "答覆包含受支持的內容，但缺漏了題目要求的答案或來源。",
                "unsupported": "答覆包含錯誤、無紀錄依據的聲稱，或未處理必須先澄清的情況。",
                "unavailable": "無可供覆核的助理答覆。",
            },
            "sample": sample,
        },
    )


def assert_isolated_output(output: Path):
    if not output.resolve().is_relative_to(Path("data").resolve()):
        raise ValueError("Assistant records must be written beneath the ignored data directory")


def evaluate_assistant(
    corpus,
    *,
    output,
    model_dir,
    cache_path,
    options,
    split,
    limit,
    workers,
    retry_unavailable=False,
):
    from experiments.fuzzy_corpus import validate_corpus
    from experiments.fuzzy_evaluate import build_search

    assert_isolated_output(output)
    validate_corpus(corpus)
    runs = select_rounds(corpus["queries"], split, limit)
    if not runs:
        raise ValueError("The selected split contains no assistant benchmark cases")
    output.mkdir(parents=True, exist_ok=True)
    manifest_file = output / "assistant-manifest.json"
    journal_file = output / "assistant-attempts.jsonl"
    manifest = {
        "corpus_sha256": hashlib.sha256(
            json.dumps(corpus, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "split": split,
        "model": options["model"],
        "timeout": options["timeout"],
        "max_output_tokens": options["max_output_tokens"],
        "workers": workers,
        "seed": SEED,
    }
    if manifest_file.is_file():
        if json.loads(manifest_file.read_text(encoding="utf-8")) != manifest:
            raise ValueError("The saved run uses different inputs; choose a new output directory")
    else:
        if journal_file.exists():
            raise ValueError("The attempt journal exists without its manifest")
        write_json(manifest_file, manifest)

    requested_ids = {(query["query_id"], attempt) for query, attempt in runs}
    rows = {}
    if journal_file.exists():
        for line in journal_file.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rows[row["query_id"], row["attempt"]] = row
    pending = []
    for query, attempt in runs:
        previous = rows.get((query["query_id"], attempt))
        if previous is None or (retry_unavailable and previous["status"] == "unavailable"):
            pending.append((query, attempt))
    events = {event["id"]: event for event in corpus["events"]}
    if pending:
        print(
            f"Assistant evaluation: {len(pending)} remaining calls; building local evidence index",
            flush=True,
        )
        search = build_search(corpus, model_dir=model_dir, cache_path=cache_path)

        def execute(item):
            query, attempt = item
            return run_turn(query, attempt, search, options, events)

        with (
            journal_file.open("a", encoding="utf-8") as journal,
            ThreadPoolExecutor(max_workers=workers) as pool,
        ):
            consecutive_unavailable = 0
            for start in range(0, len(pending), workers):
                batch = pending[start : start + workers]
                for row in pool.map(execute, batch):
                    rows[row["query_id"], row["attempt"]] = row
                    journal.write(json.dumps(row, ensure_ascii=False) + "\n")
                    journal.flush()
                    consecutive_unavailable = (
                        consecutive_unavailable + 1 if row["status"] == "unavailable" else 0
                    )
                done = min(start + len(batch), len(pending))
                if done % (workers * 5) == 0 or done == len(pending):
                    print(f"Assistant attempts saved: {done}/{len(pending)}", flush=True)
                if consecutive_unavailable >= max(workers, 4):
                    break
    selected_rows = [rows[key] for key in sorted(requested_ids & rows.keys())]
    summary = summarize(selected_rows)
    summary["model"] = options["model"]
    summary["requested_attempts"] = len(runs)
    summary["complete"] = summary["total_attempts"] == len(runs)
    write_json(output / "assistant-summary.json", summary)
    export_grounding_review(
        output / "grounding-review-sample.json", selected_rows, corpus["queries"], events
    )
    return summary


def fixed_followup(options, model_dir: Path, *, adapter_factory=OpenAILLM):
    """Exercise an anchor, a directional follow-up, and a corrected journal note."""
    from backend.config import Settings
    from backend.retrieval import SearchService
    from backend.travel_store import MemoryTravelRepository

    settings = Settings.model_construct()
    settings.embedding_model_dir = str(model_dir)
    repository = MemoryTravelRepository()
    owner = "synthetic-follow-up-owner"
    date = "2025-04-15"
    trip = repository.create_trip(
        owner,
        {
            "name": "虛構的春日祈願",
            "start_date": date,
            "end_date": date,
            "timezone": "Asia/Taipei",
        },
    )
    temple = repository.create_event(
        owner,
        trip["id"],
        {
            "place_name": "望杉祈願堂",
            "city": "臺中",
            "category": "廟宇",
            "date": date,
            "time": "09:00",
            "notes": "廟裡的月老神桌旁放滿紅線，我在那裡求姻緣。",
        },
    )
    restaurant = repository.create_event(
        owner,
        trip["id"],
        {
            "place_name": "禾盞鍋物",
            "city": "臺中",
            "category": "火鍋",
            "date": date,
            "time": "11:30",
            "notes": "那一餐我記的是香菇清湯，價格偏高。",
        },
    )
    repository.create_event(
        owner,
        trip["id"],
        {
            "place_name": "拂雨茶亭",
            "city": "臺中",
            "category": "飲品",
            "date": date,
            "time": "15:30",
            "notes": "喝了一壺冷泡茶，窗外開始下雨。",
        },
    )
    search = SearchService(settings, repository)
    search.initialize()
    search.rebuild()
    while search.process_pending():
        pass
    if search.index_status().get("ready") != len(repository.events):
        raise RuntimeError("The synthetic follow-up needs a complete local E5 index")
    recorder = EvidenceRecorder(adapter_factory(**options))
    service = ConversationService(settings, search, llm=recorder)
    conversation = service.create_conversation(owner, title="Synthetic evaluation")["id"]
    turns = []

    def ask(question):
        recorder.evidence_ids = []
        try:
            reply = service.post_message(owner, conversation, question)
        except HTTPException as exc:
            reply = {"status": "unavailable", "content": f"HTTP {exc.status_code}", "citations": []}
        turn = {
            "question": question,
            "status": reply["status"],
            "content": reply["content"],
            "evidence_event_ids": recorder.evidence_ids,
            "citations": reply.get("citations", []),
        }
        turns.append(turn)
        return turn

    first = ask("我好像在台中拜過月老，手記記的是哪座廟？")
    second = ask("那裡的下一站是哪間店？當時手記記的鍋底是什麼？")
    updated = repository.update_event(
        owner,
        restaurant["id"],
        {
            "date": date,
            "time": restaurant["time"],
            "category": restaurant["category"],
            "place_id": restaurant["place_id"],
            "version": restaurant["version"],
            "notes": "重新核對後我寫下：那次鍋底是番茄紅湯，價格偏高。",
        },
    )
    while search.process_pending():
        pass
    if search.index_status().get("ready") != len(repository.events):
        raise RuntimeError("The corrected synthetic note did not finish vector indexing")
    history = service.get_messages(owner, conversation) or []
    stale_citations = [
        cite
        for message in history
        for cite in message["citations"]
        if cite["event_id"] == restaurant["id"] and cite["state"] == "changed"
    ]
    third = ask("禾盞鍋物那次，我的手記現在寫的是什麼鍋底？")
    checks = {
        "initial_anchor_cited": any(
            cite["event_id"] == temple["id"] for cite in first["citations"]
        ),
        "direction_verified": any(
            cite["event_id"] == restaurant["id"]
            and (cite.get("relation") or {}).get("anchor_id") == temple["id"]
            and (cite.get("relation") or {}).get("direction") == "next"
            for cite in second["citations"]
        ),
        "original_note_reported": "香菇" in second["content"],
        "historical_citation_marked_changed": bool(stale_citations),
        "corrected_note_delivered": restaurant["id"] in third["evidence_event_ids"],
        "updated_note_reported": any(word in third["content"] for word in ("番茄", "蕃茄")),
        "updated_version_cited": any(
            cite["event_id"] == restaurant["id"] and cite["version"] == updated["version"]
            for cite in third["citations"]
        ),
    }
    return {"model": options["model"], "checks": checks, "turns": turns}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--corpus", type=Path, help="Frozen synthetic corpus JSON")
    source.add_argument(
        "--follow-up", action="store_true", help="Run the fixed three-turn note update case"
    )
    parser.add_argument("--output", type=Path, default=Path("data/fuzzy_eval/assistant"))
    parser.add_argument("--model-dir", type=Path, default=Path("data/models/multilingual-e5-small"))
    parser.add_argument("--cache", type=Path, default=Path("data/fuzzy_eval/passages.npz"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--split", choices=("pilot", "dev", "test"), default="test")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--retry-unavailable",
        action="store_true",
        help="Retry resume entries where the provider did not return an answer",
    )
    parser.add_argument(
        "--run-llm", action="store_true", help="Send fictional evidence to the configured API"
    )
    args = parser.parse_args()
    if not args.run_llm:
        parser.error("--run-llm is required to enable API calls")
    if not 1 <= args.workers <= 16 or (args.limit is not None and args.limit < 1):
        parser.error("Workers must be 1–16 and limit must be positive")
    # Configure only local diagnostics. Adapter logs exception classes, never keys or prompts.
    logging.basicConfig(level=logging.WARNING)
    try:
        assert_isolated_output(args.output)
        assert_isolated_output(args.cache)
        options = load_llm_options(args.env_file)
        if args.follow_up:
            result = fixed_followup(options, args.model_dir)
            args.output.mkdir(parents=True, exist_ok=True)
            write_json(args.output / "follow-up.json", result)
            print(json.dumps(result["checks"], ensure_ascii=False), flush=True)
            return
        corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
        summary = evaluate_assistant(
            corpus,
            output=args.output,
            model_dir=args.model_dir,
            cache_path=args.cache,
            options=options,
            split=args.split,
            limit=args.limit,
            workers=args.workers,
            retry_unavailable=args.retry_unavailable,
        )
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    if not summary["complete"]:
        parser.exit(
            2, "Assistant run paused after repeated unavailable responses; see private summary.\n"
        )


if __name__ == "__main__":
    main()
