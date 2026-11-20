from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import AuthService
from backend.retrieval import SearchService, compute_rrf, parse_directional_query
from backend.search import create_search_router
from backend.search_store import BM25Index, tokenize_bm25
from backend.store import MemoryStore
from backend.travel_store import MemoryTravelRepository


def test_bm25_multilingual_tokenizer():
    # Test English
    tokens_en = tokenize_bm25("Ramen in Tokyo")
    assert "ramen" in tokens_en
    assert "in" in tokens_en
    assert "tokyo" in tokens_en

    # Test Japanese / CJK n-grams and full segment
    tokens_cjk = tokenize_bm25("淺草寺清水寺")
    # Full segment
    assert "淺草寺清水寺" in tokens_cjk
    # Bigrams
    assert "淺草" in tokens_cjk
    assert "草寺" in tokens_cjk
    assert "清水" in tokens_cjk
    # 3-grams
    assert "淺草寺" in tokens_cjk
    assert "清水寺" in tokens_cjk


def test_bm25_index_and_tie_breaking():
    index = BM25Index()
    docs = [
        {"id": "ev-b", "text": "東京拉麵 好吃拉麵"},
        {"id": "ev-a", "text": "東京拉麵 好吃拉麵"},
        {"id": "ev-c", "text": "京都拉麵"},
    ]
    texts = [d["text"] for d in docs]
    index.fit(docs, texts)

    results = index.score("東京拉麵")
    assert len(results) >= 2
    # ev-a and ev-b have identical scores; tie-break must be stable by id ascending: ev-a before ev-b
    assert results[0][0]["id"] == "ev-a"
    assert results[1][0]["id"] == "ev-b"


def test_rrf_computation_and_stability():
    bm25_items = [
        ({"id": "event-2"}, 10.0),
        ({"id": "event-1"}, 8.0),
    ]
    vector_items = [
        ({"id": "event-1"}, 0.95),
        ({"id": "event-3"}, 0.90),
    ]

    fused = compute_rrf(bm25_items, vector_items, k=60)
    # event-1 rank in bm25: 2 (1/62), rank in vector: 1 (1/61) -> ~0.0325
    # event-2 rank in bm25: 1 (1/61) -> ~0.01639
    # event-3 rank in vector: 2 (1/62) -> ~0.01612
    assert fused[0][0]["id"] == "event-1"
    assert fused[1][0]["id"] == "event-2"
    assert fused[2][0]["id"] == "event-3"

    # Test tie break by ID when scores are identical
    tie_bm25 = [({"id": "b"}, 1.0)]
    tie_vec = [({"id": "a"}, 1.0)]
    fused_tie = compute_rrf(tie_bm25, tie_vec, k=60)
    # Both 'a' and 'b' have rank 1 -> identical score 1/61. Tie break sorts 'a' before 'b'
    assert fused_tie[0][0]["id"] == "a"
    assert fused_tie[1][0]["id"] == "b"


def test_parse_directional_query():
    # Ambiguous forward query with "之後"
    res1 = parse_directional_query("在淺草寺之後的美食")
    assert res1 is not None
    assert res1["anchor_query"] == "淺草寺"
    assert res1["direction"] == "next"
    assert res1["target_query"] == "美食"
    assert res1["is_ambiguous_after"] is True

    # Explicit forward query with "下一站"
    res2 = parse_directional_query("淺草寺下一站")
    assert res2 is not None
    assert res2["anchor_query"] == "淺草寺"
    assert res2["direction"] == "next"
    assert res2["is_ambiguous_after"] is False

    # Backward query with "之前"
    res3 = parse_directional_query("東京鐵塔之前的咖啡廳")
    assert res3 is not None
    assert res3["anchor_query"] == "東京鐵塔"
    assert res3["direction"] == "prev"
    assert res3["target_query"] == "咖啡廳"
    assert res3["is_ambiguous_after"] is False

    # English: WHICH pattern with target category and broad "after"
    res4 = parse_directional_query("Which Ramen Restaurant did I visit after Matsuya?")
    assert res4 is not None
    assert res4["anchor_query"] == "Matsuya"
    assert res4["direction"] == "next"
    assert res4["target_query"] == "Ramen Restaurant"
    assert res4["is_ambiguous_after"] is True

    # English: immediately after (not ambiguous)
    res5 = parse_directional_query("What did I visit immediately after Sensoji?")
    assert res5 is not None
    assert res5["anchor_query"] == "Sensoji"
    assert res5["direction"] == "next"
    assert res5["is_ambiguous_after"] is False

    # English: next stop after
    res6 = parse_directional_query("What was the next stop after Tokyo Station?")
    assert res6 is not None
    assert res6["anchor_query"] == "Tokyo Station"
    assert res6["direction"] == "next"
    assert res6["is_ambiguous_after"] is False

    # English: previous stop before
    res7 = parse_directional_query("Previous stop before Akihabara")
    assert res7 is not None
    assert res7["anchor_query"] == "Akihabara"
    assert res7["direction"] == "prev"
    assert res7["is_ambiguous_after"] is False

    # English: broad before
    res8 = parse_directional_query("Where did I visit before Ueno Park?")
    assert res8 is not None
    assert res8["anchor_query"] == "Ueno Park"
    assert res8["direction"] == "prev"
    assert res8["is_ambiguous_after"] is True

    # Non-directional query
    assert parse_directional_query("好吃的抹茶冰淇淋") is None
    assert parse_directional_query("delicious matcha ice cream in Tokyo") is None


class DummyEmbedder:
    revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 384

    def encode_query(self, text: str) -> list[float]:
        return [0.1] * 384

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]


def setup_test_api():
    store = MemoryStore()
    settings = type("Settings", (), {
        "session_days": 7,
        "cookie_secure": False,
        "resend_seconds": 60,
        "session_secret": "secret" * 8,
        "emails": {"user1@example.com", "user2@example.com"},
    })()
    auth = AuthService(settings, store, sender=lambda e, c: None)
    store.user("user-1", "user1@example.com")
    store.user("user-2", "user2@example.com")

    # Generate session for user-1
    token = "session-token-user1"
    csrf_token = "csrf-token-user1"
    store.put(
        "session:" + auth.digest(token),
        {
            "user": {"id": "user-1", "email": "user1@example.com"},
            "csrf_token": csrf_token,
            "expires_at": auth.clock() + 3600,
        },
    )

    repo = MemoryTravelRepository()
    embedder = DummyEmbedder()
    service = SearchService(settings, repo, embedder=embedder)

    app = FastAPI()
    app.include_router(create_search_router(auth, service))
    client = TestClient(app)
    client.cookies.set("travelmemo_session", token)

    return client, csrf_token, repo, service


def test_api_search_csrf_and_validation():
    client, csrf, _repo, _service = setup_test_api()

    # Missing CSRF header on POST /api/v1/search -> 403
    resp_no_csrf = client.post("/api/v1/search", json={"query": "拉麵"})
    assert resp_no_csrf.status_code == 403

    # Invalid extra field (extra=forbid)
    resp_extra = client.post(
        "/api/v1/search",
        json={"query": "拉麵", "forbidden_field": 123},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_extra.status_code == 422

    # Whitespace-only query rejected -> 422
    resp_whitespace = client.post(
        "/api/v1/search",
        json={"query": "    "},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_whitespace.status_code == 422
    assert "空白" in resp_whitespace.text

    # Invalid calendar date (Feb 31) -> 422
    resp_invalid_date = client.post(
        "/api/v1/search",
        json={"query": "拉麵", "date_from": "2026-02-31"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_invalid_date.status_code == 422
    assert "日期格式無效" in resp_invalid_date.text

    # Reversed date range (date_from > date_to) -> 422
    resp_reversed_date = client.post(
        "/api/v1/search",
        json={"query": "拉麵", "date_from": "2026-05-10", "date_to": "2026-05-01"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_reversed_date.status_code == 422
    assert "不得晚於" in resp_reversed_date.text

    # Valid empty search
    resp_valid = client.post(
        "/api/v1/search",
        json={"query": "拉麵", "limit": 10},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert "items" in data
    assert "clarification" in data
    assert data["vector_status"] in {"ready", "degraded"}


def test_standalone_scope_is_applied_before_search_limits():
    client, csrf, repo, service = setup_test_api()
    trip = repo.create_trip("user-1", {
        "name": "週末旅程", "start_date": "2026-01-01", "end_date": "2026-01-03",
        "timezone": "Asia/Taipei",
    })
    event = {
        "place_name": "海邊堤防", "category": "散步", "date": "2026-01-02",
        "notes": "一起看夕陽",
    }
    trip_event = repo.create_event("user-1", trip["id"], event)
    standalone = repo.create_standalone_event("user-1", event)
    repo.create_standalone_event("user-2", event)
    service.process_pending()

    def search(scope):
        return client.post(
            "/api/v1/search",
            json={"query": "海邊堤防", "record_scope": scope, "limit": 1},
            headers={"X-CSRF-Token": csrf},
        )

    response = search("standalone")
    assert response.status_code == 200, response.text
    assert [hit["event"]["id"] for hit in response.json()["items"]] == [standalone["id"]]
    assert response.json()["items"][0]["event"]["trip_id"] is None
    assert [hit["event"]["id"] for hit in search("trip").json()["items"]] == [trip_event["id"]]
    for method in ("bm25", "e5"):
        results = service.search("user-1", "海邊堤防", {"record_scope": "standalone"}, 1, method)
        assert [hit["event"]["id"] for hit in results["items"]] == [standalone["id"]]
    directional = service.search("user-1", "下一站呢？", anchor_id=standalone["id"])
    assert "日常足跡" in directional["clarification"]
    assert directional["items"] == []
    assert not service.verify_relation("user-1", standalone["id"], trip_event["id"])


def test_api_get_event_isolation():
    client, _csrf, repo, _service = setup_test_api()

    # Create trip and event for user-1
    trip = repo.create_trip("user-1", {
        "name": "東京之旅",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev1 = repo.create_event("user-1", trip["id"], {
        "place_name": "雷門",
        "category": "景點",
        "date": "2026-05-01",
        "time": "10:00",
        "notes": "人很多",
    })

    # Create event for user-2
    trip2 = repo.create_trip("user-2", {
        "name": "京都之旅",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "timezone": "Asia/Tokyo",
        "description": "",
    })
    ev2 = repo.create_event("user-2", trip2["id"], {
        "place_name": "金閣寺",
        "category": "景點",
        "date": "2026-06-01",
        "time": "14:00",
        "notes": "金碧輝煌",
    })

    # user-1 accessing own event -> 200, includes trip_name
    resp_own = client.get(f"/api/v1/events/{ev1['id']}")
    assert resp_own.status_code == 200
    res_data = resp_own.json()
    assert res_data["id"] == ev1["id"]
    assert res_data["place_name"] == "雷門"
    assert res_data.get("trip_name") == "東京之旅"

    # user-1 accessing user-2's event -> 404
    resp_other = client.get(f"/api/v1/events/{ev2['id']}")
    assert resp_other.status_code == 404
