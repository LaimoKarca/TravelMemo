"""Focused tests for pure bounded context memory and prompt packaging helpers."""

import json

import pytest

from backend.context_memory import (
    extract_header_and_notes,
    pack_prompt,
    prepare_memory,
)


class TestPrepareMemory:
    def test_recent_messages_returned_unchanged(self):
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        state = {"summary": "existing", "covered_count": 0, "attempted_at_count": 0}
        summary, recent, new_state = prepare_memory(messages, state, lambda s, b: "new")

        assert len(recent) == 10
        assert recent == messages
        assert summary == "existing"
        assert new_state["summary"] == "existing"

    def test_clamp_invalid_covered_count_and_clear_summary(self):
        # 15 messages total -> 3 older, 12 recent
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
        # covered_count=10 > len(older)=3 -> invalid
        invalid_state = {"summary": "old summary", "covered_count": 10, "attempted_at_count": 0}
        summary, _recent, new_state = prepare_memory(messages, invalid_state, lambda s, b: None)

        assert new_state["covered_count"] == 0
        assert new_state["summary"] == ""
        assert summary == ""

        # Negative covered_count -> invalid
        neg_state = {"summary": "old summary", "covered_count": -5, "attempted_at_count": 0}
        summary, _recent, new_state = prepare_memory(messages, neg_state, lambda s, b: None)
        assert new_state["covered_count"] == 0
        assert new_state["summary"] == ""

    def test_threshold_pending_count_triggers_summary(self):
        # 24 messages total -> 12 older, 12 recent
        messages = [{"role": "user", "content": f"m-{i}"} for i in range(24)]
        state = {"summary": "", "covered_count": 0, "attempted_at_count": 0}

        called = []

        def summarize(prev_sum: str, batch: list[dict]) -> str:
            called.append((prev_sum, batch))
            return "Summary of 12 messages"

        summary, _recent, new_state = prepare_memory(messages, state, summarize)

        assert len(called) == 1
        assert len(called[0][1]) == 12
        assert summary == "Summary of 12 messages"
        assert new_state["covered_count"] == 12
        assert new_state["attempted_at_count"] == 24

    def test_threshold_pending_chars_triggers_summary(self):
        # 16 messages total -> 4 older, 12 recent
        # older has 4 messages with 3500 chars each = 14000 chars >= 12000
        older_msgs = [{"role": "user", "content": "x" * 3500} for _ in range(4)]
        recent_msgs = [{"role": "user", "content": f"r-{i}"} for i in range(12)]
        messages = older_msgs + recent_msgs

        state = {"summary": "prev", "covered_count": 0, "attempted_at_count": 0}

        def summarize(prev_sum: str, batch: list[dict]) -> str:
            assert len(batch) == 4
            # Content capped at 1000 per message
            assert all(len(m["content"]) == 1000 for m in batch)
            assert all(m["truncated"] is True for m in batch)
            return "Summarized large messages"

        summary, _recent, new_state = prepare_memory(messages, state, summarize)
        assert summary == "Summarized large messages"
        assert new_state["covered_count"] == 4
        assert new_state["attempted_at_count"] == 16

    def test_no_trigger_below_thresholds(self):
        # 15 messages -> 3 older (< 4 and < 12)
        messages = [{"role": "user", "content": "short"} for _ in range(15)]
        state = {"summary": "existing", "covered_count": 0, "attempted_at_count": 0}

        called = []
        summary, _recent, new_state = prepare_memory(messages, state, lambda s, b: called.append(b))
        assert len(called) == 0
        assert summary == "existing"
        assert new_state["covered_count"] == 0

    def test_incremental_batching(self):
        # 30 messages -> 18 older, 12 recent
        messages = [{"role": "user", "content": f"m-{i}"} for i in range(30)]
        state = {"summary": "", "covered_count": 0, "attempted_at_count": 0}

        # First turn: batches up to 12
        summary, _, state = prepare_memory(messages, state, lambda s, b: "Batch 1")
        assert summary == "Batch 1"
        assert state["covered_count"] == 12
        assert state["summary"] == "Batch 1"
        assert state["attempted_at_count"] == 30

        # Next turn with 34 messages (4 new messages -> cooldown 34 - 30 >= 4 satisfied)
        messages_next = messages + [{"role": "user", "content": f"m-{i}"} for i in range(30, 34)]
        # Total 34 -> 22 older, 12 recent; covered_count=12 -> pending = 10 messages (< 12 and < 12000 chars)
        _summary, _, state = prepare_memory(messages_next, state, lambda s, b: "Batch 2")
        # Pending is 10 messages -> not yet >= 12, so no second batch yet
        assert state["covered_count"] == 12
        assert state["summary"] == "Batch 1"

        # Now add 2 more messages -> total 36 -> 24 older, covered=12 -> pending=12
        messages_next2 = messages_next + [
            {"role": "user", "content": f"m-{i}"} for i in range(34, 36)
        ]
        _summary, _, state = prepare_memory(messages_next2, state, lambda s, b: "Batch 2")
        assert state["covered_count"] == 24
        assert state["summary"] == "Batch 2"

    def test_failure_cooldown_and_retention(self):
        # 24 messages -> 12 older
        messages = [{"role": "user", "content": f"m-{i}"} for i in range(24)]
        state = {"summary": "original summary", "covered_count": 0, "attempted_at_count": 0}

        # Callback fails by returning None
        summary, _, state = prepare_memory(messages, state, lambda s, b: None)
        assert summary == "original summary"
        assert state["covered_count"] == 0
        assert state["attempted_at_count"] == 24

        # Next 3 messages (25, 26, 27) -> difference 27 - 24 = 3 < 4 (cooldown active)
        messages_27 = messages + [{"role": "user", "content": "x"} for _ in range(3)]
        called = []
        summary, _, state = prepare_memory(messages_27, state, lambda s, b: called.append(1))
        assert len(called) == 0
        assert state["attempted_at_count"] == 24

        # 4th message (28) -> difference 28 - 24 = 4 >= 4 (cooldown expired)
        messages_28 = messages_27 + [{"role": "user", "content": "x"}]

        # Callback raises exception
        def failing_cb(s, b):
            raise RuntimeError("API timeout")

        summary, _, state = prepare_memory(messages_28, state, failing_cb)
        assert summary == "original summary"
        assert state["covered_count"] == 0
        assert state["attempted_at_count"] == 28

    def test_summary_cap_at_1600(self):
        messages = [{"role": "user", "content": f"m-{i}"} for i in range(24)]
        state = {"summary": "", "covered_count": 0, "attempted_at_count": 0}

        long_summary = "S" * 3000
        summary, _, state = prepare_memory(messages, state, lambda s, b: long_summary)
        assert len(summary) == 1600
        assert len(state["summary"]) == 1600

    def test_request_size_bound_under_12000(self):
        # 12 messages with 1000 chars and large previous summary
        large_prev_summary = "P" * 1500
        messages = [{"role": "user", "content": "C" * 1000} for _ in range(24)]
        state = {"summary": large_prev_summary, "covered_count": 0, "attempted_at_count": 0}

        recorded_batches = []

        def summarize(prev, batch):
            recorded_batches.append(batch)
            req = json.dumps({"untrusted_previous_summary": prev, "untrusted_messages": batch}, ensure_ascii=False)
            assert len(req) <= 12000
            return "OK"

        _summary, _, state = prepare_memory(messages, state, summarize)
        assert len(recorded_batches) == 1
        # Batch was bounded so request <= 12000
        assert state["covered_count"] == len(recorded_batches[0])

    def test_escaped_first_message_and_previous_summary_still_fit_budget(self):
        messages = [{"role": "user", "content": "\x01" * 1000} for _ in range(24)]
        captured = []

        def summarize(previous, batch):
            payload = {"untrusted_previous_summary": previous, "untrusted_messages": batch}
            captured.append(payload)
            return "摘要"

        _, _, state = prepare_memory(messages, {"summary": "\x01" * 1600}, summarize)
        assert len(json.dumps(captured[0], ensure_ascii=False)) <= 12000
        assert captured[0]["untrusted_messages"][0]["truncated"] is True
        assert state["covered_count"] == 1


class TestPackPrompt:
    def test_valid_json_keys_and_structure(self):
        question = "請問清水寺的開放時間？"
        summary = "使用者去過京都。"
        recent = [
            {"role": "user", "content": "我上次去哪裡？"},
            {"role": "assistant", "content": "您上次去了京都。"},
        ]
        evidence = [("ev-1", "[Event ID: ev-1]\n地點: 清水寺 | 日期: 2026-05-01\n筆記: 06:00 開放")]

        envelope_str, allowed_ids = pack_prompt(question, summary, recent, evidence)

        data = json.loads(envelope_str)
        assert set(data.keys()) == {
            "untrusted_summary",
            "untrusted_history",
            "untrusted_evidence",
            "question",
        }
        assert data["question"] == question
        assert data["untrusted_summary"] == summary
        assert "user: 我上次去哪裡？" in data["untrusted_history"]
        assert "ev-1" in data["untrusted_evidence"]
        assert allowed_ids == {"ev-1"}

    def test_budget_preserves_question_and_drops_trailing_evidence(self):
        question = "測試問題"
        evidence = [
            ("ev-1", "[Event ID: ev-1]\n地點: 清水寺\n筆記: " + "A" * 500),
            ("ev-2", "[Event ID: ev-2]\n地點: 金閣寺\n筆記: " + "B" * 500),
            ("ev-3", "[Event ID: ev-3]\n地點: 銀閣寺\n筆記: " + "C" * 500),
        ]

        # max_chars tight enough that ev-3 and ev-2 must be dropped
        envelope_str, allowed_ids = pack_prompt(question, "", [], evidence, max_chars=800)

        assert len(envelope_str) <= 800
        data = json.loads(envelope_str)
        assert data["question"] == question
        # Trailing evidence dropped
        assert "ev-3" not in data["untrusted_evidence"]
        assert "ev-2" not in data["untrusted_evidence"]
        assert "ev-1" in data["untrusted_evidence"]
        assert allowed_ids == {"ev-1"}

    def test_budget_drops_old_history_first(self):
        question = "京都行程推薦？"
        recent = [
            {"role": "user", "content": "old message " + "1" * 800},
            {"role": "assistant", "content": "old reply " + "2" * 800},
            {"role": "user", "content": "newest message"},
        ]
        evidence = [("ev-1", "[Event ID: ev-1]\n地點: 嵐山\n筆記: 竹林")]

        # Budget allows newest message + evidence but not old history
        envelope_str, allowed_ids = pack_prompt(question, "", recent, evidence, max_chars=1400)

        assert len(envelope_str) <= 1400
        data = json.loads(envelope_str)
        assert "newest message" in data["untrusted_history"]
        assert "old message" not in data["untrusted_history"]
        assert allowed_ids == {"ev-1"}

    def test_json_escaping_budget_accounting(self):
        # Characters that expand heavily in JSON: quotes, backslashes, newlines
        expanded_chars = '"\\\n\t' * 200  # raw len 800, serialized > 1600
        question = "包含特殊字元與引號的問題"
        recent = [{"role": "user", "content": expanded_chars}]
        evidence = [("ev-1", '[Event ID: ev-1]\n地點: 特殊符號"\\\n筆記: 測試' + expanded_chars)]

        max_budget = 2000
        envelope_str, allowed_ids = pack_prompt(
            question, "", recent, evidence, max_chars=max_budget
        )

        assert len(envelope_str) <= max_budget
        assert allowed_ids == {"ev-1"}
        # Must be completely valid parseable JSON
        data = json.loads(envelope_str)
        assert data["question"] == question

    def test_extract_header_and_notes_preservation(self):
        text = "[Event ID: ev-99]\n地點: 伏見稻荷大社 | 日期: 2026-06-01\n筆記: 千本鳥居人很多"
        header, notes = extract_header_and_notes(text)
        assert "[Event ID: ev-99]" in header
        assert "地點: 伏見稻荷大社" in header
        assert notes == " 千本鳥居人很多"

    def test_too_small_max_chars_raises_value_error(self):
        question = "這是長問題" * 50
        with pytest.raises(ValueError, match="too small"):
            pack_prompt(question, "", [], [], max_chars=100)

    def test_single_evidence_notes_trimmed_header_retained(self):
        question = "重點問題"
        long_notes = "筆記細節" * 500
        evidence = [("[Event ID: ev-abc]\n地點: 嵐山公園\n筆記:" + long_notes)]
        ev_tuple = ("ev-abc", evidence[0])

        envelope_str, allowed_ids = pack_prompt(question, "", [], [ev_tuple], max_chars=800)

        assert len(envelope_str) <= 800
        data = json.loads(envelope_str)
        assert "[Event ID: ev-abc]" in data["untrusted_evidence"]
        assert "地點: 嵐山公園" in data["untrusted_evidence"]
        assert allowed_ids == {"ev-abc"}
