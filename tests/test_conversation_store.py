from unittest.mock import MagicMock

from backend.conversation_store import MemoryConversationStore, Neo4jConversationStore


def test_memory_store_conversation_crud_and_isolation():
    store = MemoryConversationStore()
    store.initialize()

    # User 1 creates conversation
    c1 = store.create_conversation("user-1", title="東京行", created_at="2026-11-16T10:00:00Z")
    assert c1["title"] == "東京行"
    assert c1["created_at"] == "2026-11-16T10:00:00Z"

    # User 2 creates conversation
    c2 = store.create_conversation("user-2", title="京都行", created_at="2026-11-16T11:00:00Z")

    # List conversations isolation
    u1_list = store.list_conversations("user-1")
    assert len(u1_list) == 1
    assert u1_list[0]["id"] == c1["id"]

    u2_list = store.list_conversations("user-2")
    assert len(u2_list) == 1
    assert u2_list[0]["id"] == c2["id"]

    # Cross-account get returns None
    assert store.get_conversation("user-1", c2["id"]) is None
    assert store.get_conversation("user-2", c1["id"]) is None
    assert store.get_conversation("user-1", c1["id"]) is not None

    # Cross-account delete returns False
    assert not store.delete_conversation("user-1", c2["id"])
    assert store.get_conversation("user-2", c2["id"]) is not None

    # Proper delete
    assert store.delete_conversation("user-1", c1["id"])
    assert store.get_conversation("user-1", c1["id"]) is None
    assert len(store.list_conversations("user-1")) == 0


def test_memory_store_messages():
    store = MemoryConversationStore()
    c = store.create_conversation("user-1", title="東京行", created_at="2026-11-16T10:00:00Z")
    cid = c["id"]

    # Add user message
    m1 = store.add_message(
        "user-1",
        cid,
        role="user",
        content="有去晴空塔嗎？",
        status="answered",
        citations=[],
        created_at="2026-11-16T10:01:00Z",
    )
    assert m1 is not None
    assert m1["role"] == "user"

    # Add assistant message with citations
    citations = [
        {
            "event_id": "evt-1",
            "trip_id": "trip-1",
            "date": "2026-11-01",
            "place_name": "晴空塔",
            "version": 1,
            "state": "current",
        }
    ]
    m2 = store.add_message(
        "user-1",
        cid,
        role="assistant",
        content="有的，11月1日造訪了晴空塔。",
        status="answered",
        citations=citations,
        created_at="2026-11-16T10:01:05Z",
    )
    assert m2 is not None
    assert m2["role"] == "assistant"
    assert len(m2["citations"]) == 1

    # Cross-account cannot add message
    assert (
        store.add_message(
            "user-2",
            cid,
            role="user",
            content="cross account",
            created_at="2026-11-16T10:02:00Z",
        )
        is None
    )

    # Cross-account cannot read messages
    assert store.get_messages("user-2", cid) is None

    # Owner reads messages in order
    msgs = store.get_messages("user-1", cid)
    assert len(msgs) == 2
    assert msgs[0]["id"] == m1["id"]
    assert msgs[1]["id"] == m2["id"]


def test_memory_store_concurrency_and_usage():
    store = MemoryConversationStore()

    # Reserve slot user 1
    ok, err = store.reserve_slot("user-1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert ok
    assert err is None

    # User 1 concurrent limit reached (max 1)
    ok, err = store.reserve_slot("user-1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert not ok
    assert "進行中" in err

    # User 2 reserves slot (global count = 2)
    ok, err = store.reserve_slot("user-2", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert ok

    # User 3 attempts slot -> global limit (2) saturated
    ok, err = store.reserve_slot("user-3", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert not ok
    assert "全站" in err

    # Release user 1 slot
    store.release_slot("user-1")

    # Now user 3 can reserve
    ok, err = store.reserve_slot("user-3", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert ok
    store.release_slot("user-2")
    store.release_slot("user-3")

    # Daily limit test
    for i in range(48):  # Already did 1 request for user-1
        ok, _ = store.reserve_slot("user-1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
        assert ok
        store.release_slot("user-1")

    # 50th request ok
    ok, _ = store.reserve_slot("user-1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert ok
    store.release_slot("user-1")

    # 51st request rejected (max_daily=50)
    ok, err = store.reserve_slot("user-1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert not ok
    assert "上限" in err

    # Record tokens and verify get_usage
    store.record_tokens("user-1", "2026-11-16", input_tokens=100, output_tokens=200)
    store.record_tokens("user-1", "2026-11-16", input_tokens=50, output_tokens=30)
    usage = store.get_usage("user-1", "2026-11-16")
    assert usage["requests"] == 50
    assert usage["input_tokens"] == 150
    assert usage["output_tokens"] == 230


def test_neo4j_conversation_store_mocked_driver():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    store = Neo4jConversationStore(mock_driver, database="neo4j")
    store.initialize()
    assert mock_session.run.call_count >= 5

    # Mock create conversation
    c = store.create_conversation("user-1", title="東京之旅", created_at="2026-11-16T12:00:00Z")
    assert c["title"] == "東京之旅"
    assert c["created_at"] == "2026-11-16T12:00:00Z"



def test_neo4j_conversation_store_reserve_slot_execute_write():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    store = Neo4jConversationStore(mock_driver, database="neo4j")

    # Mock execute_write behavior returning True (success within daily limit)
    mock_session.execute_write.return_value = True

    ok, err = store.reserve_slot("u1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert ok
    assert err is None
    assert mock_session.execute_write.called

    # If execute_write returns False (daily limit saturated in write transaction)
    mock_session.execute_write.return_value = False
    store.release_slot("u1")
    ok, err = store.reserve_slot("u1", "2026-11-16", max_daily=50, max_user_concurrent=1, max_global_concurrent=2)
    assert not ok
    assert "上限" in err


def test_conversation_store_citation_relation_proof_persisted():
    """Verify additive Citation.relation proof {anchor_id, direction, anchor_date, target_date}
    is persisted and restored by conversation stores.
    """
    store = MemoryConversationStore()
    c = store.create_conversation("user-rel-proof", title="行程關係測試")
    cid = c["id"]

    citation_with_relation = {
        "event_id": "ev-target",
        "trip_id": "trip-1",
        "date": "2026-11-02",
        "place_name": "清水寺",
        "version": 1,
        "state": "current",
        "relation": {
            "anchor_id": "ev-anchor",
            "direction": "next",
            "anchor_date": "2026-11-01",
            "target_date": "2026-11-02",
        },
    }

    msg = store.add_message(
        owner_id="user-rel-proof",
        conversation_id=cid,
        role="assistant",
        content="在清水寺之後前往金閣寺。",
        status="answered",
        citations=[citation_with_relation],
    )
    assert msg is not None
    assert len(msg["citations"]) == 1
    rel = msg["citations"][0]["relation"]
    assert rel["anchor_id"] == "ev-anchor"
    assert rel["direction"] == "next"
    assert rel["anchor_date"] == "2026-11-01"
    assert rel["target_date"] == "2026-11-02"

    # Fetch messages from store
    messages = store.get_messages("user-rel-proof", cid)
    assert messages is not None
    assert len(messages) == 1
    saved_rel = messages[0]["citations"][0]["relation"]
    assert saved_rel["anchor_id"] == "ev-anchor"
    assert saved_rel["direction"] == "next"
    assert saved_rel["anchor_date"] == "2026-11-01"
    assert saved_rel["target_date"] == "2026-11-02"
