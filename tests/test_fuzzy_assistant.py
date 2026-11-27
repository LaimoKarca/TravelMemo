from collections import Counter
from types import SimpleNamespace

from backend.llm import MockLLM
from experiments.fuzzy_assistant import (
    ANSWERABLE_TYPES,
    BOUNDARIES,
    VARIANTS,
    run_turn,
    score_response,
    select_rounds,
    summarize,
)


def test_assistant_sampling_is_stratified_and_repeat_cases_are_frozen():
    groups = [(kind, variant) for kind in ANSWERABLE_TYPES for variant in VARIANTS]
    groups += [(kind, "boundary") for kind in BOUNDARIES]
    cases = [
        {
            "query_id": f"{kind}-{variant}-{i}",
            "query_type": kind,
            "variant": variant,
            "split": "test",
        }
        for kind, variant in groups
        for i in range(100)
    ]
    selected = select_rounds(cases)
    primary = Counter(
        (query["query_type"], query["variant"]) for query, repeat in selected if repeat == 1
    )
    assert primary == {key: 80 if key[1] == "boundary" else 30 for key in groups}
    repeats = {query["query_id"] for query, repeat in selected if repeat == 2}
    assert len(repeats) == 120
    assert repeats == {query["query_id"] for query, repeat in selected if repeat == 3}
    assert len(selected) == 840
    assert select_rounds(list(reversed(cases))) == selected


def test_grounding_precheck_distinguishes_supplied_cited_and_named():
    query = {
        "expected": "unique",
        "relevant_event_ids": ["answer"],
        "anchor_event_id": "anchor",
    }
    events = {"answer": {"place_name": "北河火鍋"}}
    row = {
        "status": "answered",
        "content": "你去的是北河火鍋。",
        "evidence_event_ids": ["answer", "anchor", "distractor"],
        "citation_event_ids": ["answer", "anchor"],
    }
    assert score_response(query, row, events)["grounding_precheck_pass"] is True
    row["citation_event_ids"].append("distractor")
    assert score_response(query, row, events)["grounding_precheck_pass"] is False
    assert score_response(query, row, events)["has_all_answer_evidence"] is True
    row["content"] = "我找不到店名。"
    assert score_response(query, row, events)["has_expected_place_names"] is False


def test_unanswerable_rate_is_separate_from_clarification_and_availability():
    row = {
        "status": "unavailable",
        "evidence_event_ids": [],
        "citation_event_ids": [],
        "content": "",
    }
    missing = score_response({"expected": "no_evidence", "relevant_event_ids": []}, row, {})
    ambiguous = score_response(
        {"expected": "clarify", "relevant_event_ids": []},
        row | {"status": "needs_clarification"},
        {},
    )
    rows = [
        {
            "attempt": 1,
            "query_id": "missing",
            "query_type": "missing",
            "variant": "boundary",
            "status": "unavailable",
            "scores": missing,
        },
        {
            "attempt": 1,
            "query_id": "clarify",
            "query_type": "clarify",
            "variant": "boundary",
            "status": "needs_clarification",
            "scores": ambiguous,
        },
    ]
    summary = summarize(rows)
    assert summary["primary_scores"]["correct_abstention"] == {
        "numerator": 0,
        "denominator": 1,
        "rate": 0.0,
    }
    assert summary["primary_scores"]["correct_clarification"]["rate"] == 1.0


def test_assistant_observes_prompt_evidence_and_verified_citation():
    event = {
        "id": "fixture-e1",
        "owner_id": "fixture-owner",
        "trip_id": "fixture-trip",
        "date": "2026-01-04",
        "place_name": "北河火鍋",
        "version": 1,
    }
    search = SimpleNamespace(
        settings=SimpleNamespace(),
        search=lambda **_: {"items": [{"event": event}], "clarification": None},
        get_event=lambda owner, event_id: (
            event if (owner, event_id) == ("fixture-owner", "fixture-e1") else None
        ),
    )
    row = run_turn(
        {
            "query_id": "fixture-q1",
            "user_id": "fixture-owner",
            "query_text": "那餐熱湯不夠濃，是哪一間？",
            "query_type": "semantic",
            "variant": "weak",
            "expected": "unique",
            "relevant_event_ids": [event["id"]],
        },
        1,
        search,
        {},
        {event["id"]: event},
        adapter_factory=lambda **_: MockLLM(
            default_status="answered",
            default_content="是北河火鍋。",
            default_cited_event_ids=[event["id"]],
        ),
    )
    assert row["evidence_event_ids"] == row["citation_event_ids"] == [event["id"]]
    assert row["scores"]["grounding_precheck_pass"] is True
