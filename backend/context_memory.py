"""Pure bounded context and memory helper utilities for TravelMemo.

Provides stateful memory preparation (with incremental batching, bounds checking,
and failure cooldown) and prompt packaging (with JSON escaping budgeting,
evidence allowlist tracking, and safe field reduction).
"""

import json
from collections.abc import Callable
from typing import Any, TypedDict


class MemoryState(TypedDict, total=False):
    summary: str
    covered_count: int
    attempted_at_count: int


def extract_header_and_notes(text: str) -> tuple[str, str]:
    """Separate header lines (e.g. event ID, date, place) from notes in an evidence block."""
    for marker in ("\n筆記:", "\n筆記：", "\nNotes:", "\nnotes:"):
        idx = text.find(marker)
        if idx != -1:
            return text[: idx + len(marker)], text[idx + len(marker) :]
    lines = text.splitlines(keepends=True)
    if len(lines) > 2:
        return "".join(lines[:2]), "".join(lines[2:])
    return text, ""


def prepare_memory(
    messages: list[dict[str, Any]],
    state: dict[str, Any] | None,
    summarize: Callable[[str, list[dict[str, Any]]], str | None],
    recent_limit: int = 12,
    trigger_messages: int = 12,
    trigger_chars: int = 12000,
    summary_chars: int = 1600,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Prepare context memory and update bounded summary state.

    Args:
        messages: Full previous history excluding current question in append-only order.
        state: State dictionary with keys summary, covered_count, attempted_at_count.
        summarize: Callback receiving (previous_summary, batch_to_summarize).
        recent_limit: Number of latest messages to retain in recent context.
        trigger_messages: Message count threshold for pending older history.
        trigger_chars: Character length threshold for pending older history.
        summary_chars: Maximum character limit for summary.

    Returns:
        tuple of (summary, recent_messages, new_state)
    """
    st = state if isinstance(state, dict) else {}
    raw_summary = st.get("summary", "")
    summary = str(raw_summary)[:summary_chars] if isinstance(raw_summary, str) else ""

    raw_attempted = st.get("attempted_at_count", 0)
    attempted_at_count = (
        raw_attempted if isinstance(raw_attempted, int) and raw_attempted >= 0 else 0
    )

    # Split into older prefix and recent tail
    total_count = len(messages)
    if total_count <= recent_limit:
        older: list[dict[str, Any]] = []
        recent: list[dict[str, Any]] = list(messages)
    else:
        older = list(messages[:-recent_limit])
        recent = list(messages[-recent_limit:])

    # Clamp invalid covered_count to 0 and clear summary
    raw_covered = st.get("covered_count", 0)
    if not isinstance(raw_covered, int) or raw_covered < 0 or raw_covered > len(older):
        covered_count = 0
        summary = ""
    else:
        covered_count = raw_covered

    pending = older[covered_count:]
    pending_chars = sum(len(str(m.get("content", ""))) for m in pending)

    # Check trigger condition
    # Summarize only if:
    # 1. pending >= trigger_messages OR (pending >= 4 and sum lengths >= trigger_chars)
    # 2. total message count minus attempted_at_count >= 4
    # 3. pending is not empty
    should_trigger = (
        (len(pending) >= trigger_messages or (len(pending) >= 4 and pending_chars >= trigger_chars))
        and (total_count - attempted_at_count >= 4)
        and len(pending) > 0
    )

    if should_trigger:
        # Batch up to 12 pending, per content 1000
        candidate_pending = pending[:12]
        batch: list[dict[str, Any]] = []
        for m in candidate_pending:
            raw_content = str(m.get("content", ""))
            is_truncated = len(raw_content) > 1000
            capped_content = raw_content[:1000]
            item = {
                "role": "assistant" if m.get("role") == "assistant" else "user",
                "content": capped_content,
                "truncated": is_truncated,
            }
            # Bounded total serialized request <= 12000 including previous summary
            test_batch = batch + [item]
            serialized_req = json.dumps(
                {"untrusted_previous_summary": summary, "untrusted_messages": test_batch}, ensure_ascii=False
            )
            if len(serialized_req) <= 12000:
                batch.append(item)
            elif not batch:
                # Escaped controls can expand sixfold; fit the first message too.
                low, high = 0, len(capped_content)
                item["truncated"] = True
                while low < high:
                    mid = (low + high + 1) // 2
                    item["content"] = capped_content[:mid]
                    size = len(json.dumps(
                        {"untrusted_previous_summary": summary, "untrusted_messages": [item]},
                        ensure_ascii=False,
                    ))
                    if size <= 12000:
                        low = mid
                    else:
                        high = mid - 1
                item["content"] = capped_content[:low]
                batch.append(item)
                break
            else:
                break

        if batch:
            # Persist attempted_at_count on attempt even failure
            attempted_at_count = total_count
            try:
                cb_res = summarize(summary, batch)
            except Exception:  # noqa: BLE001
                cb_res = None

            if isinstance(cb_res, str) and cb_res.strip():
                summary = cb_res.strip()[:summary_chars]
                # Advance covered_count only by included batch count
                covered_count += len(batch)
            # On failure (None, empty string, or exception), retain old summary and cursor

    new_state: dict[str, Any] = {
        "summary": summary,
        "covered_count": covered_count,
        "attempted_at_count": attempted_at_count,
    }
    return summary, recent, new_state


def pack_prompt(
    question: str,
    summary: str,
    recent: list[dict[str, Any]],
    evidence: list[tuple[str, str]],
    max_chars: int = 24000,
) -> tuple[str, set[str]]:
    """Pack context, evidence, and question into a valid bounded JSON envelope.

    Args:
        question: User query string (preserved full).
        summary: Conversation summary string (capped to 1600).
        recent: Recent messages list (total history <= 6000, content <= 1000).
        evidence: List of (event_id, event_text) pairs.
        max_chars: Upper bound for serialized JSON envelope.

    Returns:
        tuple of (serialized_json_envelope, allowed_citation_event_ids)

    Raises:
        ValueError: If max_chars is too small to fit the full question and minimal structure.
    """
    min_env = {
        "untrusted_summary": "",
        "untrusted_history": "",
        "untrusted_evidence": "",
        "question": question,
    }
    min_len = len(json.dumps(min_env, ensure_ascii=False))
    if max_chars < min_len:
        raise ValueError(
            f"max_chars ({max_chars}) is too small to fit question (min JSON len: {min_len})"
        )

    summary_str = (summary or "")[:1600]

    # Process history: newest first accounting for JSON escaping, each content <= 1000
    recent_lines: list[str] = []
    for msg in reversed(recent or []):
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", ""))[:1000]
        line = f"{role}: {content}"
        candidate = [line] + recent_lines
        candidate_str = "\n".join(candidate)
        escaped_len = len(json.dumps(candidate_str, ensure_ascii=False)) - 2
        if escaped_len <= 6000:
            recent_lines.insert(0, line)
        else:
            break

    # Process evidence: per-event <= 1400 initially
    cur_evidence: list[tuple[str, str]] = [
        (str(ev_id), str(ev_text)[:1400]) for ev_id, ev_text in (evidence or [])
    ]

    def build_envelope(s: str, h_lines: list[str], ev_list: list[tuple[str, str]]) -> str:
        ev_str = "\n---\n".join(t for _, t in ev_list)
        env = {
            "untrusted_summary": s,
            "untrusted_history": "\n".join(h_lines),
            "untrusted_evidence": ev_str,
            "question": question,
        }
        return json.dumps(env, ensure_ascii=False)

    serialized = build_envelope(summary_str, recent_lines, cur_evidence)

    # 1. Drop trailing evidence if len > 1 and over budget
    while len(cur_evidence) > 1 and len(serialized) > max_chars:
        cur_evidence.pop()
        serialized = build_envelope(summary_str, recent_lines, cur_evidence)

    # 2. Drop old history if over budget
    while recent_lines and len(serialized) > max_chars:
        recent_lines.pop(0)
        serialized = build_envelope(summary_str, recent_lines, cur_evidence)

    # 3. Trim single evidence notes if still over budget while retaining essential header
    if cur_evidence and len(serialized) > max_chars:
        ev_id, ev_text = cur_evidence[0]
        header, notes = extract_header_and_notes(ev_text)
        excess = len(serialized) - max_chars
        if notes:
            trimmed_notes = notes[: max(0, len(notes) - excess - 20)]
            cur_evidence = [(ev_id, header + trimmed_notes)]
            serialized = build_envelope(summary_str, recent_lines, cur_evidence)

    # 4. Trim summary if still over budget
    if summary_str and len(serialized) > max_chars:
        excess = len(serialized) - max_chars
        summary_str = summary_str[: max(0, len(summary_str) - excess - 20)]
        serialized = build_envelope(summary_str, recent_lines, cur_evidence)

    if len(serialized) > max_chars:
        raise ValueError(
            f"max_chars ({max_chars}) is too small to fit question and essential context"
        )

    allowed_ids = {ev_id for ev_id, _ in cur_evidence}
    return serialized, allowed_ids
