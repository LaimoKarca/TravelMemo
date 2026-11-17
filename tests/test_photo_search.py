"""Focused tests for Photo Search Service (BM25, E5, Neo4j prefiltering, RRF)."""

from unittest.mock import MagicMock

from backend.photo_search import PhotoSearchService, _to_photo_dto


class DummySettings:
    retrieval_top_k = 10
    rrf_k = 60


class MockTravelRepository:
    def __init__(self, events=None, trips=None):
        self.events = events or {}
        self.trips = trips or {}

    def get_event(self, owner_id, event_id):
        ev = self.events.get(event_id)
        if ev and ev.get("owner_id") == owner_id:
            return dict(ev)
        return None

    def get_trip(self, owner_id, trip_id):
        t = self.trips.get(trip_id)
        if t and t.get("owner_id") == owner_id:
            return dict(t)
        return None


class MockPhotoStore:
    def __init__(self, photos=None, driver=None, database="neo4j"):
        self.photos = photos or {}
        self.driver = driver
        self.database = database

    def list(self, owner=None, status=None):
        items = list(self.photos.values())
        if owner is not None:
            items = [p for p in items if p.get("owner_id") == owner]
        if status is not None:
            items = [p for p in items if p.get("status") == status]
        return items

    def get(self, owner, photo_id):
        p = self.photos.get(photo_id)
        if p and (owner is None or p.get("owner_id") == owner):
            return dict(p)
        return None


class MockPhotoService:
    def __init__(self, store, travel_repository=None, settings=None):
        self.store = store
        self.travel_repository = travel_repository or MockTravelRepository()
        self.settings = settings or DummySettings()

    def get(self, owner, photo_id):
        rec = self.store.get(owner, photo_id)
        if not rec:
            return None
        return _to_photo_dto(rec, owner_id=owner)

    def ready_evidence(self, owner, photo_ids):
        res = []
        for pid in photo_ids:
            rec = self.store.get(owner, pid)
            if rec and rec.get("status") == "ready":
                res.append(dict(rec))
        return res


def test_photo_search_initialization_neo4j_includes_id():
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    store = MockPhotoStore(driver=mock_driver)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    search_svc.initialize()

    # Index creation must include p.id in filter properties
    calls = [str(c[0][0]) for c in mock_session.run.call_args_list]
    assert any("CREATE VECTOR INDEX photo_embeddings" in c for c in calls)
    assert any("p.id, p.owner_id, p.searchable, p.trip_id" in c for c in calls)
    assert any("CALL db.awaitIndex('photo_embeddings'" in c for c in calls)


def test_photo_search_neo4j_native_search_passes_eligible_ids():
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Photo 1 is ready with completed embedding matching version
    # Photo 2 is ready but embedding is outdated (version mismatch)
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "version": 1,
            "status": "ready",
            "caption": "拉麵",
            "search_text": "拉麵",
            "embedding": [0.1] * 384,
            "embedding_version": 1,
            "embedding_status": "completed",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-2": {
            "id": "p-2",
            "owner_id": "user-1",
            "version": 2,
            "status": "ready",
            "caption": "拉麵",
            "search_text": "拉麵",
            "embedding": [0.2] * 384,
            "embedding_version": 1,  # Outdated version!
            "embedding_status": "completed",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
    }
    store = MockPhotoStore(photos, driver=mock_driver)
    service = MockPhotoService(store)

    mock_embedder = MagicMock()
    mock_embedder.encode_query.return_value = [0.1] * 384

    # Neo4j query returns p-1
    mock_session.run.return_value.data.return_value = [
        {"p": photos["p-1"], "score": 0.95}
    ]

    search_svc = PhotoSearchService(DummySettings(), service, embedder=mock_embedder)
    results = search_svc.search("user-1", query="拉麵")

    # Check cypher call parameters
    assert mock_session.run.called
    cypher_call = mock_session.run.call_args
    cypher_text = cypher_call[0][0]
    params = cypher_call[1]["parameters"]

    assert "p.id IN $eligible_ids" in cypher_text
    # Only p-1 has embedding_version == version; p-2 is excluded from vector eligible
    assert params["eligible_ids"] == ["p-1"]
    assert len(results) >= 1


def test_photo_search_live_bound_target_refresh_excludes_deleted_targets():
    """Even without filters, photos with dead bindings to deleted trips/events are excluded."""
    # Only event ev-live exists in repository; ev-dead does NOT exist
    events = {"ev-live": {"id": "ev-live", "owner_id": "user-1", "trip_id": "trip-1", "name": "活著的景點"}}
    trips = {"trip-live": {"id": "trip-live", "owner_id": "user-1", "name": "活著的旅程"}}
    travel_repo = MockTravelRepository(events=events, trips=trips)

    photos = {
        "p-live-event": {
            "id": "p-live-event",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "event", "target_id": "ev-live"}],
        },
        "p-live-trip": {
            "id": "p-live-trip",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-live"}],
        },
        "p-dead-event": {
            "id": "p-dead-event",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "event", "target_id": "ev-dead"}],  # Deleted event
        },
        "p-dead-trip": {
            "id": "p-dead-trip",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-dead"}],  # Deleted trip
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store, travel_repository=travel_repo)
    search_svc = PhotoSearchService(DummySettings(), service)

    # Search with query and no filters: dead bindings MUST be excluded!
    results = search_svc.search("user-1", query="拉麵")
    result_ids = {r["photo"]["id"] for r in results}
    assert result_ids == {"p-live-event", "p-live-trip"}
    assert "p-dead-event" not in result_ids
    assert "p-dead-trip" not in result_ids


def test_photo_search_rebuild_preserves_analysis():
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "version": 2,
            "status": "ready",
            "caption": "更新過的標題",
            "analysis": {
                "summary": "東京鐵塔夕陽",
                "visible_text": ["TOKYO TOWER"],
                "tags": ["tower"],
            },
            "embedding": None,
            "embedding_version": 1,
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        }
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)

    mock_embedder = MagicMock()
    mock_embedder.encode_passages.return_value = [[0.9] * 384]

    search_svc = PhotoSearchService(DummySettings(), service, embedder=mock_embedder)
    search_svc.rebuild(owner_id="user-1")

    mock_embedder.encode_passages.assert_called_once()
    called_text = mock_embedder.encode_passages.call_args[0][0][0]
    assert "更新過的標題" in called_text
    assert "東京鐵塔夕陽" in called_text

    p1 = store.photos["p-1"]
    assert p1["embedding"] == [0.9] * 384
    assert p1["embedding_status"] == "completed"
    assert p1["searchable"] is True
    assert p1["analysis"]["summary"] == "東京鐵塔夕陽"


def test_photo_search_neo4j_error_graceful_bm25_fallback():
    mock_session = MagicMock()
    mock_session.run.side_effect = RuntimeError("Neo4j vector index failure")
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "version": 1,
            "status": "ready",
            "caption": "一蘭拉麵",
            "search_text": "一蘭拉麵 豚骨湯頭",
            "embedding": [0.1] * 384,
            "embedding_version": 1,
            "embedding_status": "completed",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        }
    }
    store = MockPhotoStore(photos, driver=mock_driver)
    service = MockPhotoService(store)

    mock_embedder = MagicMock()
    mock_embedder.encode_query.return_value = [0.1] * 384

    search_svc = PhotoSearchService(DummySettings(), service, embedder=mock_embedder)
    # Even if Neo4j vector search fails, BM25 fallback MUST return the matching photo!
    results = search_svc.search("user-1", query="拉麵")
    assert len(results) == 1
    assert results[0]["photo"]["id"] == "p-1"
    assert any("BM25" in r for r in results[0]["reasons"])


def test_get_query_text_ready_analysis():
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "伏見稻荷大社鳥居",
            "analysis": {
                "summary": "朱紅色的千本鳥居在山道上延伸",
                "visible_text": ["伏見稻荷大社", "奉納"],
                "tags": ["torii", "shrine", "kyoto"],
                "place_candidates": ["Fushimi Inari Taisha"],
            },
        }
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    clues = search_svc.get_query_text("user-1", ["p-1"])
    assert "伏見稻荷大社鳥居" in clues
    assert "千本鳥居" in clues
    assert "奉納" in clues
    assert "torii" in clues
    assert "Fushimi Inari" in clues
    assert len(clues) <= 1500


def test_photo_search_bm25_only_when_e5_missing():
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "一蘭拉麵 豚骨濃郁",
            "search_text": "一蘭拉麵 豚骨濃郁 好吃",
            "bindings": [{"kind": "trip", "target_id": "trip-tokyo"}],
        },
        "p-2": {
            "id": "p-2",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "淺草寺 雷門",
            "search_text": "淺草寺 雷門 觀光",
            "bindings": [{"kind": "trip", "target_id": "trip-tokyo"}],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service, embedder=None)

    results = search_svc.search("user-1", query="拉麵")
    assert len(results) == 1
    hit = results[0]
    assert hit["photo"]["id"] == "p-1"
    assert hit["score"] > 0
    assert any("BM25" in r for r in hit["reasons"])


def test_photo_search_hybrid_rrf():
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "version": 1,
            "status": "ready",
            "caption": "東京鐵塔",
            "search_text": "東京鐵塔 紅色建築",
            "embedding": [1.0, 0.0, 0.0],
            "embedding_version": 1,
            "embedding_status": "completed",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-2": {
            "id": "p-2",
            "owner_id": "user-1",
            "version": 1,
            "status": "ready",
            "caption": "晴空塔展望台",
            "search_text": "晴空塔展望台 夜景",
            "embedding": [0.0, 1.0, 0.0],
            "embedding_version": 1,
            "embedding_status": "completed",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)

    mock_embedder = MagicMock()
    mock_embedder.encode_query.return_value = [0.0, 1.0, 0.0]

    search_svc = PhotoSearchService(DummySettings(), service, embedder=mock_embedder)
    results = search_svc.search("user-1", query="東京鐵塔", limit=10)

    assert len(results) >= 1
    all_reasons = [r for hit in results for r in hit["reasons"]]
    assert any("BM25" in r for r in all_reasons)
    assert any("向量" in r for r in all_reasons)


def test_photo_search_ownership_and_ready_filter():
    photos = {
        "p-user1-ready": {
            "id": "p-user1-ready",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-user1-pending": {
            "id": "p-user1-pending",
            "owner_id": "user-1",
            "status": "pending",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-user1-blocked": {
            "id": "p-user1-blocked",
            "owner_id": "user-1",
            "status": "blocked",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-user2-ready": {
            "id": "p-user2-ready",
            "owner_id": "user-2",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    results = search_svc.search("user-1", query="拉麵")
    assert len(results) == 1
    assert results[0]["photo"]["id"] == "p-user1-ready"


def test_photo_search_chatonly_and_unbound_excluded():
    photos = {
        "p-trip": {
            "id": "p-trip",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-event": {
            "id": "p-event",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "event", "target_id": "ev-1", "trip_id": "trip-1"}],
        },
        "p-chat-conv": {
            "id": "p-chat-conv",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "conversation", "target_id": "conv-1"}],
        },
        "p-chat-msg": {
            "id": "p-chat-msg",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "message", "target_id": "msg-1"}],
        },
        "p-unbound": {
            "id": "p-unbound",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    results = search_svc.search("user-1", query="拉麵")
    returned_ids = {r["photo"]["id"] for r in results}
    assert returned_ids == {"p-trip", "p-event"}
    assert "p-chat-conv" not in returned_ids
    assert "p-chat-msg" not in returned_ids
    assert "p-unbound" not in returned_ids


def test_photo_search_trip_filter():
    photos = {
        "p-t1": {
            "id": "p-t1",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-t2": {
            "id": "p-t2",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵",
            "bindings": [{"kind": "trip", "target_id": "trip-2"}],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    results = search_svc.search("user-1", query="拉麵", trip_id="trip-1")
    assert len(results) == 1
    assert results[0]["photo"]["id"] == "p-t1"


def test_photo_search_event_facts_filters():
    events = {
        "ev-ramen": {
            "id": "ev-ramen",
            "owner_id": "user-1",
            "trip_id": "trip-1",
            "name": "一蘭拉麵",
            "date": "2026-05-02",
            "city": "Tokyo",
            "category": "food",
        },
        "ev-temple": {
            "id": "ev-temple",
            "owner_id": "user-1",
            "trip_id": "trip-1",
            "name": "清水寺",
            "date": "2026-05-05",
            "city": "Kyoto",
            "category": "sightseeing",
        },
    }
    photos = {
        "p-album": {
            "id": "p-album",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "美麗景色",
            "search_text": "美麗景色",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-ramen": {
            "id": "p-ramen",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "拉麵照片",
            "search_text": "拉麵照片 一蘭",
            "bindings": [{"kind": "event", "target_id": "ev-ramen", "trip_id": "trip-1"}],
        },
        "p-temple": {
            "id": "p-temple",
            "owner_id": "user-1",
            "status": "ready",
            "caption": "寺廟照片",
            "search_text": "寺廟照片 清水寺",
            "bindings": [{"kind": "event", "target_id": "ev-temple", "trip_id": "trip-1"}],
        },
    }
    repo = MockTravelRepository(events)
    store = MockPhotoStore(photos)
    service = MockPhotoService(store, travel_repository=repo)
    search_svc = PhotoSearchService(DummySettings(), service)

    # 1. Filter by city="Tokyo"
    res_city = search_svc.search("user-1", query="", city="Tokyo")
    assert len(res_city) == 1
    assert res_city[0]["photo"]["id"] == "p-ramen"
    assert res_city[0]["event"]["id"] == "ev-ramen"

    # 2. Filter by category="sightseeing"
    res_cat = search_svc.search("user-1", query="", category="sightseeing")
    assert len(res_cat) == 1
    assert res_cat[0]["photo"]["id"] == "p-temple"
    assert res_cat[0]["event"]["id"] == "ev-temple"

    # 3. Filter by date range (2026-05-01 to 2026-05-03)
    res_date = search_svc.search("user-1", query="", date_from="2026-05-01", date_to="2026-05-03")
    assert len(res_date) == 1
    assert res_date[0]["photo"]["id"] == "p-ramen"

    # 4. Search with NO event filters: album photo IS included with event=None!
    res_no_event_filter = search_svc.search("user-1", query="", trip_id="trip-1")
    ids = {r["photo"]["id"] for r in res_no_event_filter}
    assert ids == {"p-album", "p-ramen", "p-temple"}
    album_hit = next(r for r in res_no_event_filter if r["photo"]["id"] == "p-album")
    assert album_hit["event"] is None


def test_photo_search_empty_query_filter_only():
    photos = {
        "p-1": {
            "id": "p-1",
            "owner_id": "user-1",
            "status": "ready",
            "created_at": "2026-05-01T12:00:00",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
        "p-2": {
            "id": "p-2",
            "owner_id": "user-1",
            "status": "ready",
            "created_at": "2026-05-02T12:00:00",
            "bindings": [{"kind": "trip", "target_id": "trip-1"}],
        },
    }
    store = MockPhotoStore(photos)
    service = MockPhotoService(store)
    search_svc = PhotoSearchService(DummySettings(), service)

    results = search_svc.search("user-1", query="", trip_id="trip-1")
    assert len(results) == 2
    assert results[0]["score"] == 1.0
    assert results[0]["reasons"] == ["條件篩選匹配"]
    assert results[0]["photo"]["id"] == "p-2"
    assert results[1]["photo"]["id"] == "p-1"


def test_photo_service_and_worker_real_store_integration():
    import io
    import shutil
    import tempfile

    from PIL import Image

    from backend.photo_analysis import PhotoAnalysisWorker
    from backend.photo_store import MemoryPhotoStore
    from backend.photos import PhotoService
    from backend.travel_store import MemoryTravelRepository

    storage_dir = tempfile.mkdtemp()
    class Settings:
        photo_storage_dir = storage_dir
        media_upload_max_bytes = 20 * 1024 * 1024
        media_max_pixels = 50_000_000
        media_max_dimension = 2048
        media_image_max_bytes = 512 * 1024
        media_thumbnail_max_bytes = 64 * 1024
        media_user_quota_bytes = 250 * 1024 * 1024
        media_global_quota_bytes = 5 * 1024 * 1024 * 1024
        retrieval_top_k = 10
        rrf_k = 60
        vision_model = "gpt-6-luna"
        openai_model = "gpt-6-luna"
        openai_api_key = "test"
        openai_timeout = 25.0

    settings = Settings()
    store = MemoryPhotoStore()
    travel_repo = MemoryTravelRepository()
    t = travel_repo.create_trip("user-1", {"id": "trip-kyoto", "name": "京都賞楓", "start_date": "2026-05-01", "end_date": "2026-05-10"})
    trip_id = t["id"]
    service = PhotoService(settings, store, travel_repository=travel_repo)

    # 1. Upload valid JPEG
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
    dto = service.upload("user-1", buf.getvalue(), "image/jpeg")
    photo_id = dto["id"]
    assert dto["status"] == "pending"

    # 2. Bind photo to trip
    service.bind("user-1", photo_id, "trip", trip_id)

    # 3. Worker analysis
    def mock_analyze(path, q=""):
        return {
            "summary": "金閣寺金碧輝煌",
            "visible_text": ["金閣寺"],
            "tags": ["temple", "kyoto", "gold"],
            "place_candidates": ["Kinkaku-ji"],
            "date_candidate": None,
            "uncertainties": [],
            "safety": {"decision": "allow", "reason": "safe"},
        }

    class MockEmbedder:
        def encode_passages(self, texts):
            return [[0.2] * 384]
        def encode_query(self, text):
            return [0.2] * 384

    worker = PhotoAnalysisWorker(settings, service, analyzer=type("Analyzer", (), {"analyze": staticmethod(mock_analyze)})(), embedder=MockEmbedder())
    processed = worker.process_pending(batch_size=1)
    assert processed == 1

    ready_dto = service.get("user-1", photo_id)
    assert ready_dto["status"] == "ready"
    assert ready_dto["analysis"]["summary"] == "金閣寺金碧輝煌"

    # 4. Search
    search_svc = PhotoSearchService(settings, service, embedder=MockEmbedder())
    results = search_svc.search("user-1", query="金閣寺")
    assert len(results) == 1
    assert results[0]["photo"]["id"] == photo_id
    assert results[0]["score"] > 0
    assert any("BM25" in r or "向量" in r for r in results[0]["reasons"])

    # 5. Rebuild preserves analysis without vision
    mock_worker_embedder = MagicMock()
    mock_worker_embedder.encode_passages.return_value = [[0.7] * 384]
    search_svc_rebuild = PhotoSearchService(settings, service, embedder=mock_worker_embedder)
    search_svc_rebuild.rebuild(owner_id="user-1")
    rebuilt_photo = store.photos[photo_id]
    assert rebuilt_photo["embedding"] == [0.7] * 384
    assert rebuilt_photo["analysis"]["summary"] == "金閣寺金碧輝煌"

    shutil.rmtree(storage_dir, ignore_errors=True)
