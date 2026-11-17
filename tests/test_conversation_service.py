from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.conversation import ConversationService
from backend.conversation_store import MemoryConversationStore
from backend.llm import LLMResult, MockLLM


class FakeSearchService:
    def __init__(self, search_results=None, events=None, edges=None):
        self.search_results = search_results or {"items": [], "clarification": None}
        self.events = events or {}
        self.edges = set(edges) if edges is not None else None
        self.last_anchor_id = None

    def search(
        self,
        owner_id: str,
        query: str,
        limit: int = 10,
        anchor_id: str | None = None,
    ):
        self.last_anchor_id = anchor_id
        return self.search_results

    def get_event(self, owner_id: str, event_id: str):
        ev = self.events.get(event_id)
        if ev and ev.get("owner_id") == owner_id:
            return ev
        return None

    def verify_relation(self, owner_id: str, anchor_id: str, target_id: str, direction: str) -> bool:
        if self.edges is None:
            return True
        if direction == "next":
            return (anchor_id, target_id) in self.edges
        elif direction == "prev":
            return (target_id, anchor_id) in self.edges
        return False


def test_conversation_crud_and_cross_account():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    search_service = FakeSearchService()
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=MockLLM())

    c1 = service.create_conversation("user-1", title="首爾五日")
    assert c1["title"] == "首爾五日"

    # User 1 lists
    u1_items = service.list_conversations("user-1")
    assert len(u1_items) == 1
    assert u1_items[0]["id"] == c1["id"]

    # User 2 lists
    assert service.list_conversations("user-2") == []

    # Cross account get messages
    assert service.get_messages("user-2", c1["id"]) is None

    # Cross account post message raises 404
    with pytest.raises(HTTPException) as exc_info:
        service.post_message("user-2", c1["id"], "Hello")
    assert exc_info.value.status_code == 404

    # Delete conversation
    assert service.delete_conversation("user-1", c1["id"])
    assert service.list_conversations("user-1") == []


def test_citations_snapshot_and_reverification():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "evt-1": {
            "id": "evt-1",
            "owner_id": "user-1",
            "trip_id": "trip-1",
            "place_name": "東京鐵塔",
            "date": "2026-11-01",
            "version": 1,
            "category": "景點",
            "notes": "展望台夜景",
        }
    }
    search_res = {
        "items": [{"event": events["evt-1"], "score": 0.9, "reasons": ["命中地點"]}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)
    llm = MockLLM(
        default_status="answered",
        default_content="您在11月1日造訪了東京鐵塔。",
        default_cited_event_ids=["evt-1"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-1", "東京行")
    msg = service.post_message("user-1", c["id"], "我哪天去東京鐵塔？")
    assert msg["status"] == "answered"
    assert len(msg["citations"]) == 1
    assert msg["citations"][0]["state"] == "current"
    assert msg["citations"][0]["place_name"] == "東京鐵塔"

    # Verify history reads current state
    history = service.get_messages("user-1", c["id"])
    assert len(history) == 2  # user + assistant
    assert history[1]["citations"][0]["state"] == "current"

    # 1. When event version is updated -> state becomes "changed"
    events["evt-1"]["version"] = 2
    history_changed = service.get_messages("user-1", c["id"])
    assert history_changed[1]["citations"][0]["state"] == "changed"

    # 2. When event is deleted -> state becomes "deleted", keeping snapshot place_name
    del events["evt-1"]
    history_deleted = service.get_messages("user-1", c["id"])
    assert history_deleted[1]["citations"][0]["state"] == "deleted"
    assert history_deleted[1]["citations"][0]["place_name"] == "東京鐵塔"


def test_hallucination_defense_and_insufficient_evidence():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "evt-real": {
            "id": "evt-real",
            "owner_id": "user-1",
            "trip_id": "trip-1",
            "place_name": "淺草寺",
            "date": "2026-11-02",
            "version": 1,
        }
    }
    search_res = {
        "items": [{"event": events["evt-real"], "score": 0.8, "reasons": ["命中"]}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)

    # LLM returns hallucinated event ID not in search items
    llm = MockLLM(
        default_status="answered",
        default_content="答案在此",
        default_cited_event_ids=["evt-fake-hallucinated"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-1")
    msg = service.post_message("user-1", c["id"], "問一個問題")

    # Hallucinated ID stripped out; without valid citations, downgraded to insufficient_evidence
    assert msg["status"] == "insufficient_evidence"
    assert msg["citations"] == []


def test_search_clarification_and_multiturn_clarification():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    store = MemoryConversationStore()

    # Case 1: Search service directly returns clarification
    search_service = FakeSearchService(
        search_results={"items": [], "clarification": "請指定要查詢哪一個行程之後？"}
    )
    service = ConversationService(settings, search_service, store=store, llm=MockLLM())
    c = service.create_conversation("user-1")
    msg = service.post_message("user-1", c["id"], "之後去了哪裡？")
    assert msg["status"] == "needs_clarification"
    assert "哪一個行程之後" in msg["content"]

    # Case 2: Multi-turn ambiguity with multiple candidate citations from previous turn
    events = {
        "e1": {"id": "e1", "owner_id": "user-1", "place_name": "景點A", "date": "2026-11-01", "version": 1},
        "e2": {"id": "e2", "owner_id": "user-1", "place_name": "景點B", "date": "2026-11-01", "version": 1},
    }
    search_res = {
        "items": [{"event": events["e1"]}, {"event": events["e2"]}],
        "clarification": None,
    }
    search_service2 = FakeSearchService(search_results=search_res, events=events)
    llm = MockLLM(
        default_status="answered",
        default_content="您去了景點A與景點B。",
        default_cited_event_ids=["e1", "e2"],
    )
    store2 = MemoryConversationStore()
    service2 = ConversationService(settings, search_service2, store=store2, llm=llm)

    c2 = service2.create_conversation("user-1")
    # First turn: returns 2 citations
    service2.post_message("user-1", c2["id"], "我第一天去了哪？")

    # Second turn: ambiguous followup "那裡有什麼好吃的？" with 2 previous candidates
    msg2 = service2.post_message("user-1", c2["id"], "那裡有什麼好吃的？")
    assert msg2["status"] == "needs_clarification"
    assert "哪一個地點" in msg2["content"]


def test_no_daily_quota():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    search_service = FakeSearchService()
    store = MemoryConversationStore()
    llm = MockLLM(default_status="insufficient_evidence", default_content="無資料")
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-1")

    # More than the old daily limit is accepted.
    for _ in range(51):
        service.post_message("user-1", c["id"], "hi")

    # Internal diagnostics remain available, but do not enforce a quota.
    usage = service.get_usage("user-1")
    assert usage["requests"] == 51
    assert usage["daily_limit"] == 0
    assert usage["model"] == "gpt-6-luna"


def test_failed_llm_releases_concurrency_and_records_request():
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    search_res = {
        "items": [{"event": {"id": "ev1", "place_name": "P", "date": "2026-11-01", "version": 1}}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res)

    def failing_handler(instructions, text):
        raise RuntimeError("LLM internal error")

    llm = MockLLM(handler=failing_handler)
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-1")
    with pytest.raises(RuntimeError):
        service.post_message("user-1", c["id"], "query")

    # Concurrency must be released even after exception!
    assert store.user_active.get("user-1", 0) == 0
    assert store.global_active == 0

    # Request count must be preserved (原子用量預留持久化，失敗也記錄請求)
    usage = service.get_usage("user-1")
    assert usage["requests"] == 1


import threading


def test_async_concurrent_user_concurrency_and_slot_release():
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-6-luna",
        ai_daily_limit=50,
        ai_user_concurrency=1,
        ai_global_concurrency=2,
    )
    events = {
        "ev1": {
            "id": "ev1",
            "owner_id": "user-concurrent",
            "place_name": "A",
            "date": "2026-11-01",
            "version": 1,
        }
    }
    search_service = FakeSearchService(
        search_results={"items": [{"event": events["ev1"]}]},
        events=events,
    )

    in_llm_event = threading.Event()
    release_llm_event = threading.Event()

    def slow_llm_handler(instructions, text):
        in_llm_event.set()
        # Wait until test signals to continue
        release_llm_event.wait(timeout=3)
        return LLMResult(
            status="answered",
            content="Slow answer",
            cited_event_ids=["ev1"],
            input_tokens=10,
            output_tokens=20,
        )

    llm = MockLLM(handler=slow_llm_handler)
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-concurrent")
    results = {}

    def thread_1_task():
        try:
            results["t1"] = service.post_message("user-concurrent", c["id"], "q1")
        except Exception as e:  # noqa: BLE001
            results["t1_err"] = e

    def thread_2_task():
        # Wait until thread 1 is actively inside post_message holding the user concurrency slot
        in_llm_event.wait(timeout=2)
        try:
            results["t2"] = service.post_message("user-concurrent", c["id"], "q2")
        except Exception as e:  # noqa: BLE001
            results["t2_err"] = e

    t1 = threading.Thread(target=thread_1_task)
    t2 = threading.Thread(target=thread_2_task)

    t1.start()
    t2.start()

    # Wait for t2 to attempt and get rejected
    t2.join(timeout=3)
    # Now allow t1 to complete
    release_llm_event.set()
    t1.join(timeout=3)

    # Thread 2 must fail with 429 due to ai_user_concurrency=1
    assert "t2_err" in results
    assert isinstance(results["t2_err"], HTTPException)
    assert results["t2_err"].status_code == 429
    assert "進行中" in results["t2_err"].detail

    # Thread 1 must have succeeded
    assert "t1" in results
    assert results["t1"]["status"] == "answered"

    # Both concurrency slots must be free
    assert store.user_active.get("user-concurrent", 0) == 0
    assert store.global_active == 0

    # User can now make another call without being blocked
    msg3 = service.post_message("user-concurrent", c["id"], "q3")
    assert msg3["status"] == "answered"

    # Usage reflects 2 successful reservations (q1 and q3); q2 was rejected before reserving
    usage = service.get_usage("user-concurrent")
    assert usage["requests"] == 2
    assert usage["input_tokens"] == 20
    assert usage["output_tokens"] == 40


def test_config_fields_respected():
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-6-luna",
        openai_timeout=45.0,
        openai_max_output_tokens=2000,
        ai_daily_limit=5,
        ai_user_concurrency=1,
        ai_global_concurrency=2,
        conversation_history_limit=2,
        conversation_evidence_limit=1,
    )
    events = {
        f"ev-{i}": {
            "id": f"ev-{i}",
            "owner_id": "user-cfg",
            "place_name": f"Place {i}",
            "date": "2026-11-01",
            "version": 1,
        }
        for i in range(5)
    }
    search_res = {
        "items": [{"event": events[f"ev-{i}"]} for i in range(5)],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)
    llm = MockLLM(default_status="answered", default_content="ok", default_cited_event_ids=["ev-0"])
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    assert service.daily_limit == 0
    assert service.user_concurrency == 1
    assert service.global_concurrency == 2
    assert service.history_limit == 2
    assert service.evidence_limit == 1

    c = service.create_conversation("user-cfg")
    service.post_message("user-cfg", c["id"], "q1")

    # Only 1 candidate evidence passed to prompt due to conversation_evidence_limit=1
    assert len(llm.calls) == 1
    assert "Place 0" in llm.calls[0]["input_text"]
    assert "Place 1" not in llm.calls[0]["input_text"]



def test_fail_closed_mixed_valid_invalid_citations():
    """If ANY cited ID is not in evidence, fail closed instead of dropping invalid ID."""
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-valid": {
            "id": "ev-valid",
            "owner_id": "user-failclosed",
            "place_name": "東京鐵塔",
            "date": "2026-11-01",
            "version": 1,
        }
    }
    search_res = {
        "items": [{"event": events["ev-valid"]}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)
    # LLM returns both a valid ID and an invalid/hallucinated ID
    llm = MockLLM(
        default_status="answered",
        default_content="答案",
        default_cited_event_ids=["ev-valid", "ev-invalid-hallucinated"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-failclosed")
    msg = service.post_message("user-failclosed", c["id"], "問題")

    # MUST fail closed: status=insufficient_evidence and citations empty!
    assert msg["status"] == "insufficient_evidence"
    assert msg["citations"] == []
    assert "不在本次檢索證據中" in msg["content"]


def test_fail_closed_concurrent_delete_and_update():
    """If an event is deleted or modified concurrently while LLM is generating, fail closed."""
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-mod": {
            "id": "ev-mod",
            "owner_id": "user-concurrent-mod",
            "place_name": "晴空塔",
            "date": "2026-11-01",
            "version": 1,
        }
    }
    search_res = {
        "items": [{"event": dict(events["ev-mod"])}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)

    def mutating_llm_handler(instructions, text):
        # Simulate concurrent update in DB before LLM completes
        events["ev-mod"]["version"] = 2
        return LLMResult(
            status="answered",
            content="回答",
            cited_event_ids=["ev-mod"],
        )

    llm = MockLLM(handler=mutating_llm_handler)
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-concurrent-mod")
    msg = service.post_message("user-concurrent-mod", c["id"], "晴空塔門票")

    # Version changed concurrently -> fail closed!
    assert msg["status"] == "insufficient_evidence"
    assert msg["citations"] == []
    assert "已被修改" in msg["content"]

    # Now simulate concurrent deletion in DB
    events["ev-del"] = {
        "id": "ev-del",
        "owner_id": "user-concurrent-mod",
        "place_name": "雷門",
        "date": "2026-11-01",
        "version": 1,
    }
    search_service.search_results = {"items": [{"event": dict(events["ev-del"])}], "clarification": None}

    def deleting_llm_handler(instructions, text):
        # Simulate concurrent deletion in DB before LLM completes
        del events["ev-del"]
        return LLMResult(
            status="answered",
            content="回答",
            cited_event_ids=["ev-del"],
        )

    service.llm = MockLLM(handler=deleting_llm_handler)
    msg2 = service.post_message("user-concurrent-mod", c["id"], "雷門")
    assert msg2["status"] == "insufficient_evidence"
    assert msg2["citations"] == []
    assert "已不存在" in msg2["content"]


def test_429_does_not_pollute_history():
    """Verify that when a request gets rejected with 429, no user message is added to history."""
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-6-luna",
        ai_daily_limit=1,  # limit to 1 request
        ai_user_concurrency=1,
        ai_global_concurrency=2,
    )
    search_service = FakeSearchService()
    llm = MockLLM(default_status="insufficient_evidence", default_content="無資料")
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-clean")

    # Request 1: succeeds
    service.post_message("user-clean", c["id"], "First message")
    msgs = service.get_messages("user-clean", c["id"])
    assert len(msgs) == 2  # user + assistant

    # Request 2: another request is already in progress (429).
    store.user_active["user-clean"] = 1
    with pytest.raises(HTTPException) as exc_info:
        service.post_message("user-clean", c["id"], "Second message (should be rejected)")
    assert exc_info.value.status_code == 429

    # Verify history still has exactly 2 messages: the rejected message must NOT appear in history!
    msgs_after = service.get_messages("user-clean", c["id"])
    assert len(msgs_after) == 2
    assert all("Second message" not in m["content"] for m in msgs_after)


def test_multiturn_anaphora_zh_en_ambiguity():
    """Test English and Chinese anaphora (incl 那家店, 那天, there, it) with ambiguity handling."""
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-cafe": {
            "id": "ev-cafe",
            "owner_id": "user-anaphora",
            "place_name": "藍瓶咖啡",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-ramen": {
            "id": "ev-ramen",
            "owner_id": "user-anaphora",
            "place_name": "一蘭拉麵",
            "date": "2026-11-01",
            "version": 1,
        },
    }
    search_res = {
        "items": [{"event": events["ev-cafe"]}, {"event": events["ev-ramen"]}],
        "clarification": None,
    }
    search_service = FakeSearchService(search_results=search_res, events=events)
    llm = MockLLM(
        default_status="answered",
        default_content="您去了藍瓶咖啡與一蘭拉麵。",
        default_cited_event_ids=["ev-cafe", "ev-ramen"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-anaphora")
    service.post_message("user-anaphora", c["id"], "第一天美食？")

    # 1. Chinese ambiguous follow-up: "那家店" refers to multiple candidates
    msg_zh = service.post_message("user-anaphora", c["id"], "那家店幾點開門？")
    assert msg_zh["status"] == "needs_clarification"
    assert "哪一個地點" in msg_zh["content"]

    # 2. Chinese ambiguous follow-up: "那天"
    msg_zh2 = service.post_message("user-anaphora", c["id"], "那天附近還有什麼？")
    assert msg_zh2["status"] == "needs_clarification"

    # 3. English ambiguous follow-up: "how to get there"
    msg_en = service.post_message("user-anaphora", c["id"], "how to get there?")
    assert msg_en["status"] == "needs_clarification"
    assert "哪一個地點" in msg_en["content"]



def test_explicit_new_entity_after_multicitation_answer_no_false_positive():
    """Regression test: after Cafe A and Cafe B citations, asking about Tokyo Tower (with 'When')

    must NOT trigger needs_clarification. Standalone time words are not demonstratives.
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-cafe-a": {
            "id": "ev-cafe-a",
            "owner_id": "user-regression",
            "place_name": "藍瓶咖啡",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-cafe-b": {
            "id": "ev-cafe-b",
            "owner_id": "user-regression",
            "place_name": "星巴克旗艦店",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-tokyo": {
            "id": "ev-tokyo",
            "owner_id": "user-regression",
            "place_name": "東京鐵塔",
            "date": "2026-11-03",
            "version": 1,
        },
    }

    # Turn 1: search returns both cafes
    search_service = FakeSearchService(
        search_results={"items": [{"event": events["ev-cafe-a"]}, {"event": events["ev-cafe-b"]}], "clarification": None},
        events=events,
    )
    llm = MockLLM(
        default_status="answered",
        default_content="您造訪了藍瓶咖啡與星巴克旗艦店。",
        default_cited_event_ids=["ev-cafe-a", "ev-cafe-b"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-regression")
    turn1_msg = service.post_message("user-regression", c["id"], "我去過哪些咖啡店？")
    assert turn1_msg["status"] == "answered"
    assert len(turn1_msg["citations"]) == 2

    # Turn 2: user asks "When did I visit Tokyo Tower?" (or "我什麼時候去了東京鐵塔？")
    # Search service now returns the Tokyo Tower event
    search_service.search_results = {
        "items": [{"event": events["ev-tokyo"]}],
        "clarification": None,
    }
    llm.default_content = "您在11月3日去了東京鐵塔。"
    llm.default_cited_event_ids = ["ev-tokyo"]

    turn2_msg = service.post_message("user-regression", c["id"], "When did I visit Tokyo Tower?")
    # MUST NOT be needs_clarification! Must be answered directly!
    assert turn2_msg["status"] == "answered"
    assert turn2_msg["citations"][0]["event_id"] == "ev-tokyo"
    assert turn2_msg["citations"][0]["place_name"] == "東京鐵塔"

    # Also test Chinese time question without demonstratives: "我什麼時候去了東京鐵塔？"
    turn3_msg = service.post_message("user-regression", c["id"], "我什麼時候去了東京鐵塔？")
    assert turn3_msg["status"] == "answered"
    assert turn3_msg["citations"][0]["event_id"] == "ev-tokyo"


def test_search_relation_anchor_evidence_in_llm():
    """Verify that search relation anchor date/place/direction is included in LLM evidence for grounding cross-day claims."""
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-sensoji": {
            "id": "ev-sensoji",
            "owner_id": "user-rel",
            "place_name": "淺草寺",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-skytree": {
            "id": "ev-skytree",
            "owner_id": "user-rel",
            "place_name": "晴空塔",
            "date": "2026-11-02",
            "version": 1,
        },
    }
    # Search returns ev-skytree with a relation linking it as "next" from anchor ev-sensoji
    search_service = FakeSearchService(
        search_results={
            "items": [
                {
                    "event": events["ev-skytree"],
                    "relation": {
                        "anchor_id": "ev-sensoji",
                        "direction": "next",
                        "anchor_date": "2026-11-01",
                        "target_date": "2026-11-02",
                    },
                }
            ],
            "clarification": None,
        },
        events=events,
    )
    llm = MockLLM(
        default_status="answered",
        default_content="晴空塔是在造訪淺草寺之後的隔天（11月2日）去的。",
        default_cited_event_ids=["ev-skytree"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-rel")
    msg = service.post_message("user-rel", c["id"], "晴空塔是在淺草寺之後去的嗎？")

    assert msg["status"] == "answered"
    assert len(llm.calls) == 1
    evidence_sent_to_llm = llm.calls[0]["input_text"]

    # Verify relation anchor place, anchor date, direction, target date are in evidence!
    assert "行程關聯" in evidence_sent_to_llm
    assert "淺草寺" in evidence_sent_to_llm
    assert "2026-11-01" in evidence_sent_to_llm
    assert "之後" in evidence_sent_to_llm
    assert "2026-11-02" in evidence_sent_to_llm



def test_sameday_reorder_during_generate_fails_closed():
    """Regression test: if same-day events are reordered from A->B->C to A->C->B while LLM is generating

    (where Event.version remains unchanged), verify_relation revalidates relationship evidence and
    fails closed to insufficient_evidence.
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-A": {
            "id": "ev-A",
            "owner_id": "user-reorder",
            "place_name": "築地早餐",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-B": {
            "id": "ev-B",
            "owner_id": "user-reorder",
            "place_name": "晴空塔",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-C": {
            "id": "ev-C",
            "owner_id": "user-reorder",
            "place_name": "淺草雷門",
            "date": "2026-11-01",
            "version": 1,
        },
    }

    # Initial order on same day: A -> B -> C
    initial_edges = {("ev-A", "ev-B"), ("ev-B", "ev-C")}
    search_service = FakeSearchService(
        search_results={
            "items": [
                {
                    "event": events["ev-B"],
                    "relation": {
                        "anchor_id": "ev-A",
                        "direction": "next",
                        "anchor_date": "2026-11-01",
                        "target_date": "2026-11-01",
                    },
                }
            ],
            "clarification": None,
        },
        events=events,
        edges=initial_edges,
    )

    reorder_happened = False

    def reordering_llm_handler(instructions, text):
        nonlocal reorder_happened
        # Ensure relation context was properly embedded in LLM evidence prompt
        assert "行程關聯" in text
        assert "築地早餐" in text
        assert "ev-A" in text
        assert "之後" in text

        # Simulate same-day reorder in graph while LLM generates: A -> C -> B
        # Notice: events["ev-A"]["version"] and events["ev-B"]["version"] DO NOT CHANGE!
        search_service.edges = {("ev-A", "ev-C"), ("ev-C", "ev-B")}
        reorder_happened = True

        return LLMResult(
            status="answered",
            content="早餐之後前往晴空塔。",
            cited_event_ids=["ev-B"],
        )

    llm = MockLLM(handler=reordering_llm_handler)
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-reorder")
    msg = service.post_message("user-reorder", c["id"], "早餐之後去哪裡？")

    assert reorder_happened
    # Event versions remained 1, but relation is broken -> MUST fail closed!
    assert msg["status"] == "insufficient_evidence"
    assert msg["citations"] == []
    assert "行程先後順序在此期間已被修改" in msg["content"]

    # Now verify control run: when edges remain valid (A -> C -> B) and query cites C (next of A)
    search_service.search_results = {
        "items": [
            {
                "event": events["ev-C"],
                "relation": {
                    "anchor_id": "ev-A",
                    "direction": "next",
                    "anchor_date": "2026-11-01",
                    "target_date": "2026-11-01",
                },
            }
        ],
        "clarification": None,
    }
    service.llm = MockLLM(
        default_status="answered",
        default_content="早餐之後前往淺草雷門。",
        default_cited_event_ids=["ev-C"],
    )
    msg_valid = service.post_message("user-reorder", c["id"], "現在早餐之後去哪？")
    assert msg_valid["status"] == "answered"
    assert len(msg_valid["citations"]) == 1
    assert msg_valid["citations"][0]["event_id"] == "ev-C"



def test_repeated_visit_anaphora_uses_exact_anchor_id():
    """Verify that when user visits a place with the same name multiple times (Day 1 and Day 3),

    multi-turn followup passes exact anchor_event.id into search so next/previous are not mixed up.
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-sb-1": {
            "id": "ev-sb-1",
            "owner_id": "user-repeated",
            "place_name": "星巴克",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-skytree": {
            "id": "ev-skytree",
            "owner_id": "user-repeated",
            "place_name": "晴空塔",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-sb-2": {
            "id": "ev-sb-2",
            "owner_id": "user-repeated",
            "place_name": "星巴克",
            "date": "2026-11-03",
            "version": 1,
        },
        "ev-airport": {
            "id": "ev-airport",
            "owner_id": "user-repeated",
            "place_name": "羽田機場",
            "date": "2026-11-03",
            "version": 1,
        },
    }

    class RepeatedVisitSearchService(FakeSearchService):
        def search(self, owner_id: str, query: str, limit: int = 10, anchor_id: str | None = None):
            self.last_anchor_id = anchor_id
            if anchor_id == "ev-sb-1":
                return {
                    "items": [
                        {
                            "event": events["ev-skytree"],
                            "relation": {
                                "anchor_id": "ev-sb-1",
                                "direction": "next",
                                "anchor_date": "2026-11-01",
                                "target_date": "2026-11-01",
                            },
                        }
                    ],
                    "clarification": None,
                }
            elif anchor_id == "ev-sb-2":
                return {
                    "items": [
                        {
                            "event": events["ev-airport"],
                            "relation": {
                                "anchor_id": "ev-sb-2",
                                "direction": "next",
                                "anchor_date": "2026-11-03",
                                "target_date": "2026-11-03",
                            },
                        }
                    ],
                    "clarification": None,
                }
            # Fallback (Turn 1 query about day 1 Starbucks)
            return {
                "items": [{"event": events["ev-sb-1"]}],
                "clarification": None,
            }

    edges = {("ev-sb-1", "ev-skytree"), ("ev-sb-2", "ev-airport")}
    search_service = RepeatedVisitSearchService(events=events, edges=edges)
    llm = MockLLM(
        default_status="answered",
        default_content="您在11月1日造訪了星巴克。",
        default_cited_event_ids=["ev-sb-1"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-repeated")
    # Turn 1: cites ev-sb-1 (Day 1)
    t1 = service.post_message("user-repeated", c["id"], "我第一天去了哪間咖啡店？")
    assert t1["status"] == "answered"
    assert t1["citations"][0]["event_id"] == "ev-sb-1"

    # Turn 2: user asks "之後去了哪裡？"
    llm.default_content = "第一天星巴克之後去了晴空塔。"
    llm.default_cited_event_ids = ["ev-skytree"]

    t2 = service.post_message("user-repeated", c["id"], "之後去了哪裡？")
    # Verify exact anchor_id="ev-sb-1" was passed to search!
    assert search_service.last_anchor_id == "ev-sb-1"
    assert t2["status"] == "answered"
    assert t2["citations"][0]["event_id"] == "ev-skytree"
    assert t2["citations"][0]["place_name"] == "晴空塔"


def test_demonstrative_followup_to_deleted_anchor_asks_clarification():
    """Verify that if a demonstrative followup points to a deleted event, it asks clarification

    that the prior record was deleted instead of silently searching unrelated records.
    Also verify that explicit new named questions still succeed.
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-cafe": {
            "id": "ev-cafe",
            "owner_id": "user-del-anchor",
            "place_name": "藍瓶咖啡",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-tokyo": {
            "id": "ev-tokyo",
            "owner_id": "user-del-anchor",
            "place_name": "東京鐵塔",
            "date": "2026-11-03",
            "version": 1,
        },
    }

    search_service = FakeSearchService(
        search_results={"items": [{"event": events["ev-cafe"]}], "clarification": None},
        events=events,
    )
    llm = MockLLM(
        default_status="answered",
        default_content="您造訪了藍瓶咖啡。",
        default_cited_event_ids=["ev-cafe"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-del-anchor")
    t1 = service.post_message("user-del-anchor", c["id"], "我去過哪間咖啡店？")
    assert t1["status"] == "answered"

    # Now simulate user deleting ev-cafe from travel records
    del events["ev-cafe"]

    # Turn 2: user asks with demonstrative "那家店" (that shop)
    t2 = service.post_message("user-del-anchor", c["id"], "那家店幾點開門？")
    # MUST ask clarification that the prior record was deleted!
    assert t2["status"] == "needs_clarification"
    assert "已被刪除" in t2["content"]
    assert "藍瓶咖啡" in t2["content"]

    # Turn 3: user asks explicit new named question "When did I visit Tokyo Tower?"
    search_service.search_results = {"items": [{"event": events["ev-tokyo"]}], "clarification": None}
    llm.default_content = "您在11月3日造訪了東京鐵塔。"
    llm.default_cited_event_ids = ["ev-tokyo"]

    t3 = service.post_message("user-del-anchor", c["id"], "When did I visit Tokyo Tower?")
    # Explicit new named question must succeed!
    assert t3["status"] == "answered"
    assert t3["citations"][0]["event_id"] == "ev-tokyo"


def test_history_marks_relation_changed_after_reorder():
    """Regression test: answer next(A)=B, then reorder A->C->B with unchanged Event.version;
    GET history must show changed for B.
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-A": {
            "id": "ev-A",
            "owner_id": "user-reorder-hist",
            "trip_id": "trip-1",
            "place_name": "築地早餐",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-B": {
            "id": "ev-B",
            "owner_id": "user-reorder-hist",
            "trip_id": "trip-1",
            "place_name": "晴空塔",
            "date": "2026-11-01",
            "version": 1,
        },
        "ev-C": {
            "id": "ev-C",
            "owner_id": "user-reorder-hist",
            "trip_id": "trip-1",
            "place_name": "淺草雷門",
            "date": "2026-11-01",
            "version": 1,
        },
    }

    # Initial order: A -> B -> C
    edges = {("ev-A", "ev-B"), ("ev-B", "ev-C")}
    search_service = FakeSearchService(
        search_results={
            "items": [
                {
                    "event": events["ev-B"],
                    "relation": {
                        "anchor_id": "ev-A",
                        "direction": "next",
                        "anchor_date": "2026-11-01",
                        "target_date": "2026-11-01",
                    },
                }
            ],
            "clarification": None,
        },
        events=events,
        edges=edges,
    )

    llm = MockLLM(
        default_status="answered",
        default_content="早餐之後前往晴空塔。",
        default_cited_event_ids=["ev-B"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-reorder-hist")
    t1 = service.post_message("user-reorder-hist", c["id"], "早餐之後去哪裡？")
    assert t1["status"] == "answered"
    assert len(t1["citations"]) == 1
    assert t1["citations"][0]["event_id"] == "ev-B"
    assert t1["citations"][0]["state"] == "current"
    assert t1["citations"][0]["relation"]["anchor_id"] == "ev-A"
    assert t1["citations"][0]["relation"]["direction"] == "next"

    # Immediately check history: must be current
    h1 = service.get_messages("user-reorder-hist", c["id"])
    assert len(h1) == 2
    assert h1[1]["citations"][0]["state"] == "current"
    assert h1[1]["citations"][0]["relation"]["anchor_id"] == "ev-A"

    # Now reorder trip: A -> C -> B
    # CRITICAL: Event versions of ev-A, ev-B, ev-C remain unchanged (1)!
    assert events["ev-A"]["version"] == 1
    assert events["ev-B"]["version"] == 1
    search_service.edges = {("ev-A", "ev-C"), ("ev-C", "ev-B")}

    # GET history must now mark relation-source changed for B!
    h2 = service.get_messages("user-reorder-hist", c["id"])
    assert len(h2) == 2
    b_cite = h2[1]["citations"][0]
    assert b_cite["event_id"] == "ev-B"
    assert b_cite["state"] == "changed"
    assert b_cite["version"] == 1
    assert b_cite["relation"]["anchor_id"] == "ev-A"


def test_transient_db_exception_propagates_not_labeled_deleted():
    """Ensure transient DB exceptions are not falsely labeled deleted
    (only get_event None means deleted; propagate Neo4j dependency errors).
    """
    settings = SimpleNamespace(openai_api_key="test-key", openai_model="gpt-6-luna")
    events = {
        "ev-1": {
            "id": "ev-1",
            "owner_id": "user-db-err",
            "trip_id": "trip-1",
            "place_name": "東京鐵塔",
            "date": "2026-11-01",
            "version": 1,
        }
    }
    search_service = FakeSearchService(
        search_results={"items": [{"event": events["ev-1"]}], "clarification": None},
        events=events,
    )
    llm = MockLLM(
        default_status="answered",
        default_content="您去了東京鐵塔。",
        default_cited_event_ids=["ev-1"],
    )
    store = MemoryConversationStore()
    service = ConversationService(settings, search_service, store=store, llm=llm)

    c = service.create_conversation("user-db-err")
    t1 = service.post_message("user-db-err", c["id"], "我去過哪裡？")
    assert t1["status"] == "answered"
    assert t1["citations"][0]["state"] == "current"

    # Simulate transient Neo4j / DB connection error on get_event
    class TransientNeo4jError(Exception):
        pass

    def flaky_get_event(owner_id, event_id):
        raise TransientNeo4jError("Neo4j database connection pool timeout.")

    search_service.get_event = flaky_get_event

    # GET messages must NOT falsely swallow the error and mark citation as "deleted"!
    # The transient DB exception must propagate!
    with pytest.raises(TransientNeo4jError):
        service.get_messages("user-db-err", c["id"])
