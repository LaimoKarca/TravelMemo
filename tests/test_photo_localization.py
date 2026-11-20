"""Bilingual photo summaries and resumable text-only localization."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.photo_analysis import (
    OpenAIVisionAnalyzer,
    PhotoAnalysisWorker,
    build_photo_search_text,
)
from backend.photo_localization import PhotoSummaryLocalizer, TextPhotoTranslator
from backend.photo_search import PhotoSearchService, _to_photo_dto
from backend.photo_store import MemoryPhotoStore, Neo4jPhotoStore
from backend.photos import PhotoService


def legacy(store, key="old", owner="owner"):
    return store.create(
        owner,
        {
            "id": key,
            "status": "ready",
            "caption": "我的圖說",
            "analysis": {
                "summary": "A train from Hualien to Taitung.",
                "tags": ["train"],
                "uncertainties": ["Date unknown"],
                "visible_text": ["花蓮 → 臺東"],
                "date_candidate": None,
            },
            "embedding": [1.0],
            "embedding_status": "completed",
            "embedding_version": 1,
            "bindings": [{"kind": "trip", "target_id": "trip"}],
        },
    )


class Translator:
    def __init__(self, hook=None):
        self.calls = []
        self.hook = hook

    def translate(self, analysis):
        self.calls.append(analysis)
        if self.hook:
            self.hook()
        return {
            "summary": "從花蓮開往臺東的列車。",
            "summary_en": "Translated train.",
            "tags": ["列車"],
            "uncertainties": ["日期不明"],
        }


def test_preview_does_not_translate_or_write_and_apply_is_idempotent():
    store = MemoryPhotoStore()
    original = legacy(store)
    translator = Translator()
    service = PhotoSummaryLocalizer(store, translator)
    assert service.run(apply=False)["candidates"] == 1
    assert not translator.calls
    assert store.get("owner", "old") == original
    assert service.run(apply=True)["updated"] == 1
    rec = store.get("owner", "old")
    assert rec["analysis"]["summary"] == "從花蓮開往臺東的列車。"
    assert rec["analysis"]["summary_en"] == original["analysis"]["summary"]
    assert rec["analysis"]["visible_text"] == ["花蓮 → 臺東"]
    assert rec["caption"] == "我的圖說"
    assert rec["embedding_status"] == "pending" and rec["embedding"] is None
    assert service.run(apply=True)["candidates"] == 0
    assert len(translator.calls) == 1


def test_batches_owner_filter_conflict_and_failure_are_retryable():
    store = MemoryPhotoStore()
    legacy(store, "a")
    legacy(store, "b")
    legacy(store, "c", "other")
    translate = Translator(lambda: store.update("owner", "a", 1, {"caption": "new"}))
    service = PhotoSummaryLocalizer(store, translate)
    result = service.run(owner="owner", batch_size=1, apply=True)
    assert result["conflicts"] == 1 and result["has_more"]
    assert store.get("owner", "a")["caption"] == "new"
    assert store.get("owner", "a")["analysis"]["summary"].startswith("A train")
    failing = MagicMock()
    failing.translate.side_effect = TimeoutError("private detail must not escape")
    result = PhotoSummaryLocalizer(store, failing).run(owner="owner", apply=True)
    assert result["failed"] == 2
    assert "private detail" not in json.dumps(result)
    assert store.get("other", "c")["version"] == 1
    assert PhotoSummaryLocalizer(store, Translator()).run(owner="owner", apply=True)["updated"] == 2


def test_english_search_copy_is_private_and_survives_rebuild():
    store = MemoryPhotoStore()
    legacy(store)
    PhotoSummaryLocalizer(store, Translator()).run(apply=True)
    rec = store.get("owner", "old")
    text = build_photo_search_text(rec["caption"], rec["analysis"])
    assert "從花蓮" in text and "A train from Hualien" in text
    dto = _to_photo_dto(rec)
    assert "summary_en" not in dto["analysis"]
    service = SimpleNamespace(store=store)
    search = PhotoSearchService(SimpleNamespace(), service)
    search.rebuild("owner")
    assert "A train from Hualien" in store.get("owner", "old")["search_text"]
    assert "A train from Hualien" in search.get_query_text("owner", ["old"])


def test_translator_uses_bounded_text_only_structured_request():
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = SimpleNamespace(
        summary="列車", summary_en="Train", tags=["列車"], uncertainties=[]
    )
    translator = TextPhotoTranslator(
        SimpleNamespace(openai_model="test-model", openai_timeout=10), client
    )
    assert (
        translator.translate({"summary": "a" * 10000, "tags": ["train"], "uncertainties": []})[
            "summary"
        ]
        == "列車"
    )
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["store"] is False
    assert len(kwargs["input"]) < 6500
    assert "input_image" not in kwargs["input"]
    assert "繁體中文" in kwargs["instructions"]


def test_new_analysis_and_caption_reindex_preserve_bilingual_summary(tmp_path):
    path = tmp_path / "photo.webp"
    path.write_bytes(b"synthetic image bytes")
    settings = SimpleNamespace(media_root=str(tmp_path), media_poll_seconds=1)
    store = MemoryPhotoStore()
    store.create(
        "owner",
        {
            "id": "p",
            "stored_path": str(path),
            "status": "pending",
            "bindings": [{"kind": "trip", "target_id": "trip"}],
        },
    )
    vision = MagicMock()
    vision.analyze.return_value = {
        "summary": "河邊的咖啡店。",
        "summary_en": "A riverside cafe.",
        "summary_language": "zh-Hant",
        "tags": ["咖啡店"],
        "safety": {"decision": "allow", "reason": "safe"},
    }
    embedder = MagicMock()
    embedder.encode_passages.return_value = [[0.1, 0.2]]
    photos = PhotoService(settings, store)
    worker = PhotoAnalysisWorker(settings, photos, vision, embedder)
    assert worker.process_pending() == 1
    record = store.get("owner", "p")
    assert record["analysis_language"] == "zh-Hant"
    assert "A riverside cafe." in record["search_text"]
    dto = photos.update("owner", "p", record["version"], "我的咖啡時光")
    assert "summary_en" not in dto["analysis"]
    assert worker.process_pending() == 1
    assert vision.analyze.call_count == 1
    assert store.get("owner", "p")["analysis"]["summary_en"] == "A riverside cafe."
    search = PhotoSearchService(settings, photos)
    assert "A riverside cafe." in search.get_query_text("owner", ["p"])


def test_vision_response_declares_traditional_chinese_and_internal_english(tmp_path):
    from backend.photo_analysis import VisionAnalysisResult, VisionSafety

    path = tmp_path / "photo.webp"
    path.write_bytes(b"RIFF0000WEBP")
    client = MagicMock()
    client.responses.parse.return_value.output_parsed = VisionAnalysisResult(
        summary="海岸步道",
        summary_en="A coastal path",
        tags=["海岸"],
        safety=VisionSafety(decision="allow", reason="safe"),
    )
    result = OpenAIVisionAnalyzer(SimpleNamespace(openai_timeout=10), client).analyze(path)
    assert result["summary_en"] == "A coastal path"
    assert result["summary_language"] == "zh-Hant"
    assert "Traditional Chinese" in client.responses.parse.call_args.kwargs["instructions"]


def test_neo4j_rebuild_decodes_private_json_and_writes_with_owner_version_guard():
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.data.return_value = [
        {
            "p": {
                "id": "p",
                "owner_id": "owner",
                "version": 7,
                "status": "ready",
                "caption": "圖說",
                "analysis_json": json.dumps(
                    {"summary": "河畔咖啡店", "summary_en": "Riverside cafe"}
                ),
                "bindings_json": json.dumps([{"kind": "trip", "target_id": "trip"}]),
            }
        }
    ]
    store = Neo4jPhotoStore(driver, "neo4j")
    search = PhotoSearchService(SimpleNamespace(), SimpleNamespace(store=store))
    search.rebuild("owner")
    (query,) = session.run.call_args.args
    args = session.run.call_args.kwargs
    assert "owner_id: $owner" in query and "version: $version" in query
    assert args["owner"] == "owner" and args["version"] == 7
    assert "河畔咖啡店" in args["search_text"] and "Riverside cafe" in args["search_text"]
    assert args["searchable"] is True
