"""Photo search service orchestrating BM25, E5 embeddings, Neo4j prefiltering, and RRF."""

from __future__ import annotations

import inspect
import logging
from functools import cache
from typing import Any

from backend.photo_analysis import build_photo_search_text
from backend.retrieval import compute_rrf
from backend.search_store import BM25Index, cosine_similarity
from backend.travel_store import format_event

logger = logging.getLogger(__name__)


def _safe_format_event(ev: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ev or not isinstance(ev, dict):
        return None
    try:
        return format_event(ev)
    except Exception:  # noqa: BLE001
        return dict(ev)


def _to_photo_dto(
    photo: dict[str, Any],
    photo_service: Any = None,
    owner_id: str = "",
) -> dict[str, Any]:
    """Converts internal photo dictionary to public Photo DTO format honoring A contract."""
    photo_id = str(photo.get("id", ""))
    owner = owner_id or photo.get("owner_id", "")
    if photo_service is not None and hasattr(photo_service, "get"):
        try:
            dto = photo_service.get(owner, photo_id)
            if dto and isinstance(dto, dict):
                analysis_part = dto.get("analysis")
                if isinstance(analysis_part, dict):
                    vt = analysis_part.get("visible_text")
                    if isinstance(vt, str):
                        analysis_part["visible_text"] = [vt] if vt.strip() else []
                return dto
        except Exception:  # noqa: BLE001, S110
            pass

    analysis = photo.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {
            "summary": "",
            "visible_text": [],
            "tags": [],
            "place_candidates": [],
            "date_candidate": None,
            "uncertainties": [],
        }

    raw_vt = analysis.get("visible_text") or []
    if isinstance(raw_vt, list):
        visible_text_list = [str(x) for x in raw_vt if str(x).strip()]
    elif isinstance(raw_vt, str) and raw_vt.strip():
        visible_text_list = [raw_vt.strip()]
    else:
        visible_text_list = []

    return {
        "id": photo_id,
        "caption": photo.get("caption", ""),
        "version": photo.get("version", 1),
        "analysis_version": photo.get("analysis_version", 1),
        "status": photo.get("status", "ready"),
        "analysis": {
            "summary": analysis.get("summary", ""),
            "visible_text": visible_text_list,
            "tags": analysis.get("tags") or [],
            "place_candidates": analysis.get("place_candidates") or [],
            "date_candidate": analysis.get("date_candidate"),
            "uncertainties": analysis.get("uncertainties") or [],
        },
        "width": photo.get("width", 0),
        "height": photo.get("height", 0),
        "size_bytes": photo.get("size_bytes", 0),
        "thumbnail_size_bytes": photo.get("thumbnail_size_bytes", 0),
        "created_at": photo.get("created_at"),
        "updated_at": photo.get("updated_at"),
        "bindings": photo.get("bindings") or [],
        "url": f"/api/v1/photos/{photo_id}/content",
        "thumbnail_url": f"/api/v1/photos/{photo_id}/thumbnail",
    }


class PhotoSearchService:
    """Owner-filtered photo search engine using BM25 and multilingual E5 embeddings with RRF."""

    def __init__(self, settings: Any, photo_service: Any, embedder: Any = None):
        self.settings = settings
        self.photo_service = photo_service
        self.embedder = embedder
        self.top_k = getattr(settings, "retrieval_top_k", 50)
        self.rrf_k = getattr(settings, "rrf_k", 60)

    def initialize(self) -> None:
        """Initializes Neo4j Photo vector index with p.id, owner, and searchable prefilters."""
        store = getattr(self.photo_service, "store", None)
        driver = getattr(store, "driver", None)
        database = getattr(store, "database", "neo4j")

        if driver is not None:
            try:
                with driver.session(database=database) as session:
                    try:
                        indexes = session.run(
                            "SHOW INDEXES YIELD name, properties WHERE name = 'photo_embeddings' RETURN properties"
                        ).data()
                        if indexes:
                            existing_props = set(indexes[0].get("properties") or [])
                            if existing_props and not {"id", "owner_id", "searchable"}.issubset(existing_props):
                                session.run("DROP INDEX photo_embeddings").consume()
                    except Exception as e_idx:  # noqa: BLE001
                        logger.warning("Could not inspect existing photo index schema: %s", type(e_idx).__name__)

                    session.run("""
                    CYPHER 25
                    CREATE VECTOR INDEX photo_embeddings IF NOT EXISTS
                    FOR (p:Photo) ON (p.embedding)
                    WITH [p.id, p.owner_id, p.searchable, p.trip_id]
                    OPTIONS {indexConfig: {
                      `vector.dimensions`: 384,
                      `vector.similarity_function`: 'cosine'
                    }}
                    """).consume()
                    session.run("CALL db.awaitIndex('photo_embeddings', 30)").consume()
                    logger.info("Initialized Neo4j vector index 'photo_embeddings'")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j photo vector index initialization warning: %s", type(exc).__name__)

    def rebuild(self, owner_id: str | None = None) -> None:
        """Reindexes ready stored analyses without paying vision again.

        Regenerates search_text and dense passage embeddings for ready photos.
        Preserves all existing visual analysis facts.
        """
        store = getattr(self.photo_service, "store", None)
        if store is None:
            return

        driver = getattr(store, "driver", None)
        database = getattr(store, "database", "neo4j")

        if driver is not None:
            with driver.session(database=database) as session:
                query = """
                MATCH (p:Photo {status: 'ready'})
                WHERE ($owner IS NULL OR p.owner_id = $owner)
                RETURN p
                """
                records = session.run(query, owner=owner_id).data()
                for row in records:
                    # Neo4j saves analysis/bindings as JSON properties, unlike memory records.
                    p = store._record_from_node(row["p"])
                    pid = p["id"]
                    analysis = p.get("analysis")
                    if isinstance(analysis, str):
                        try:
                            import json
                            analysis = json.loads(analysis)
                        except Exception:  # noqa: BLE001
                            analysis = {}
                    caption = p.get("caption") or ""
                    search_text = build_photo_search_text(caption, analysis)

                    embedding = None
                    embedding_status = "disabled"
                    if self.embedder is not None and search_text:
                        try:
                            res = self.embedder.encode_passages([search_text])
                            vectors = res[0] if isinstance(res, tuple) else res
                            if vectors and len(vectors) > 0 and len(vectors[0]) > 0:
                                embedding = list(vectors[0])
                                embedding_status = "completed"
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Rebuild embedding generation error: %s", type(exc).__name__)
                            embedding_status = "failed"

                    bindings = p.get("bindings") or []
                    if isinstance(bindings, str):
                        try:
                            import json
                            bindings = json.loads(bindings)
                        except Exception:  # noqa: BLE001
                            bindings = []
                    is_attached = any(b.get("kind") in ("trip", "event") for b in bindings)

                    session.run(
                        """
                        MATCH (p:Photo {id: $id, owner_id: $owner, version: $version, status: 'ready'})
                        SET p.embedding = $embedding,
                            p.embedding_version = p.version,
                            p.embedding_status = $embedding_status,
                            p.search_text = $search_text,
                            p.searchable = $searchable
                        """,
                        id=pid,
                        owner=p["owner_id"],
                        version=p["version"],
                        embedding=embedding,
                        embedding_status=embedding_status,
                        search_text=search_text,
                        searchable=is_attached,
                    ).consume()
            logger.info("PhotoSearchService rebuilt Neo4j photo embeddings for owner=%s", owner_id)
            return

        # Rebuild in Memory
        candidates = self._fetch_owner_candidates(owner_id) if owner_id else []
        if not candidates and hasattr(store, "photos") and isinstance(store.photos, dict):
            candidates = list(store.photos.values())

        for p in candidates:
            if p.get("status") != "ready":
                continue
            if owner_id and p.get("owner_id") != owner_id:
                continue

            pid = p.get("id")
            caption = p.get("caption") or ""
            analysis = p.get("analysis") or {}
            search_text = build_photo_search_text(caption, analysis)

            embedding = None
            embedding_status = "disabled"
            if self.embedder is not None and search_text:
                try:
                    res = self.embedder.encode_passages([search_text])
                    vectors = res[0] if isinstance(res, tuple) else res
                    if vectors and len(vectors) > 0 and len(vectors[0]) > 0:
                        embedding = list(vectors[0])
                        embedding_status = "completed"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Memory rebuild embedding error: %s", type(exc).__name__)
                    embedding_status = "failed"

            bindings = p.get("bindings") or []
            is_attached = any(b.get("kind") in ("trip", "event") for b in bindings)

            p["embedding"] = embedding
            p["embedding_version"] = p.get("version", 1)
            p["embedding_status"] = embedding_status
            p["search_text"] = search_text
            p["searchable"] = is_attached

            if hasattr(store, "photos") and isinstance(store.photos, dict) and pid in store.photos:
                store.photos[pid]["embedding"] = embedding
                store.photos[pid]["embedding_version"] = store.photos[pid].get("version", 1)
                store.photos[pid]["embedding_status"] = embedding_status
                store.photos[pid]["search_text"] = search_text
                store.photos[pid]["searchable"] = is_attached
            elif hasattr(store, "update"):
                store.update(p.get("owner_id"), pid, p.get("version", 1), {
                    "embedding": embedding,
                    "embedding_version": p.get("version", 1),
                    "embedding_status": embedding_status,
                    "search_text": search_text,
                    "searchable": is_attached,
                })

        logger.info("PhotoSearchService rebuilt in-memory photo embeddings for owner=%s", owner_id)

    def get_query_text(self, owner_id: str, photo_ids: list[str]) -> str:
        """Extracts bounded search query clues from ready photo analysis for multi-modal recall."""
        if not photo_ids:
            return ""

        photos: list[dict[str, Any]] = []
        if hasattr(self.photo_service, "ready_evidence"):
            try:
                photos = self.photo_service.ready_evidence(owner_id, photo_ids)
            except Exception:  # noqa: BLE001
                photos = []

        if not photos:
            store = getattr(self.photo_service, "store", None)
            for pid in photo_ids:
                rec = None
                if hasattr(self.photo_service, "get"):
                    try:
                        rec = self.photo_service.get(owner_id, pid)
                    except Exception:  # noqa: BLE001, S110
                        pass
                if rec is None and store is not None and hasattr(store, "get"):
                    rec = store.get(owner_id, pid)
                if rec and rec.get("status") == "ready":
                    photos.append(rec)

        clues: list[str] = []
        for p in photos:
            p_parts: list[str] = []
            caption = p.get("caption") or ""
            if caption and caption.strip():
                p_parts.append(caption.strip())
            analysis = p.get("analysis") or {}
            summary = analysis.get("summary") or ""
            if summary and summary.strip():
                p_parts.append(summary.strip())
            # Evidence DTOs intentionally exclude retrieval-only fields.
            private = None
            store = getattr(self.photo_service, "store", None)
            if store is not None and hasattr(store, "get"):
                private = store.get(owner_id, p["id"])
            internal = (private.get("analysis") or {}) if private and private.get("status") == "ready" else analysis
            english = internal.get("summary_en") or ""
            if english and english.strip() and english.strip() != summary.strip():
                p_parts.append(english.strip())
            vis = analysis.get("visible_text") or []
            if isinstance(vis, list):
                vis_text = " ".join(str(v).strip() for v in vis if v and str(v).strip())
            else:
                vis_text = str(vis).strip()
            if vis_text:
                p_parts.append(vis_text)
            tags = analysis.get("tags") or []
            if isinstance(tags, list):
                tags_text = " ".join(str(t).strip() for t in tags if t and str(t).strip())
            else:
                tags_text = str(tags).strip()
            if tags_text:
                p_parts.append(tags_text)
            places = analysis.get("place_candidates") or []
            if isinstance(places, list):
                places_text = " ".join(str(pl).strip() for pl in places if pl and str(pl).strip())
            else:
                places_text = str(places).strip()
            if places_text:
                p_parts.append(places_text)

            if p_parts:
                clues.append(" ".join(p_parts))

        return "\n".join(clues).strip()[:1500]

    def _fetch_owner_candidates(self, owner_id: str) -> list[dict[str, Any]]:
        """Retrieves raw photos belonging to owner_id from store."""
        store = getattr(self.photo_service, "store", None)
        if store is None:
            return []

        if hasattr(store, "list"):
            sig = inspect.signature(store.list)
            try:
                if "owner" in sig.parameters:
                    res = store.list(owner=owner_id)
                elif len(sig.parameters) > 0:
                    res = store.list(owner_id)
                else:
                    res = store.list()
                if isinstance(res, list):
                    return [p for p in res if p.get("owner_id") == owner_id]
            except Exception as exc:  # noqa: BLE001
                logger.warning("store.list error: %s", type(exc).__name__)

        if hasattr(store, "photos") and isinstance(store.photos, dict):
            return [p for p in store.photos.values() if p.get("owner_id") == owner_id]

        return []

    def search(
        self,
        owner_id: str,
        query: str = "",
        limit: int = 10,
        trip_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        city: str | None = None,
        category: str | None = None,
        record_scope: str | None = "all",
    ) -> list[dict[str, Any]]:
        """Searches owned trip/event-attached ready photos using BM25 and E5 RRF.

        Excludes chat-only, unbound, and dead/deleted targets. Honors all supplied filters.
        Album photos with no event facts are excluded when event filters are applied.
        Pushes p.id IN $eligible_ids inside CYPHER 25 native SEARCH before LIMIT.
        Restricts vector candidates to completed embedding_version == version.
        Guarantees BM25 fallback if Neo4j vector search fails.
        """
        limit = max(1, min(limit, 50))
        trimmed_query = (query or "").strip()
        has_event_filters = bool(date_from or date_to or city or category)
        repository = getattr(self.photo_service, "travel_repository", None)
        if repository is None:
            return []

        @cache
        def get_event(event_id: str) -> dict[str, Any] | None:
            return repository.get_event(owner_id, event_id)

        @cache
        def trip_exists(album_id: str) -> bool:
            return repository.get_trip(owner_id, album_id) is not None

        raw_candidates = self._fetch_owner_candidates(owner_id)
        matched_photos: list[dict[str, Any]] = []
        matched_sources: dict[str, tuple[dict[str, Any] | None, str | None]] = {}

        for photo in raw_candidates:
            if photo.get("owner_id") != owner_id or photo.get("status") != "ready":
                continue

            matched_event = None
            source_trip = None
            for binding in photo.get("bindings") or []:
                target = binding.get("target_id", "")
                if binding.get("kind") == "trip":
                    if (
                        source_trip is None
                        and record_scope != "standalone"
                        and not has_event_filters
                        and (trip_id is None or target == trip_id)
                        and trip_exists(target)
                    ):
                        source_trip = target
                    continue
                if binding.get("kind") != "event":
                    continue

                event = get_event(target)
                if event is None:
                    continue
                event_trip = event.get("trip_id")
                if trip_id is not None and event_trip != trip_id:
                    continue
                if record_scope == "standalone" and event_trip is not None:
                    continue
                if record_scope == "trip" and event_trip is None:
                    continue
                if date_from and str(event.get("date", "")) < date_from:
                    continue
                if date_to and str(event.get("date", "")) > date_to:
                    continue
                if city and str(event.get("city", "")).casefold() != city.casefold():
                    continue
                if category and str(event.get("category", "")).casefold() != category.casefold():
                    continue
                matched_event, source_trip = event, event_trip
                break

            if matched_event is None and source_trip is None:
                continue
            matched_photos.append(photo)
            matched_sources[photo["id"]] = matched_event, source_trip

        if not matched_photos:
            return []

        # Ranking: BM25 and Vector Search
        if trimmed_query:
            # 1. BM25 Search (Always computed for ranking and fallback on all ready matched photos)
            texts = [
                p.get("search_text")
                or build_photo_search_text(p.get("caption", ""), p.get("analysis"))
                for p in matched_photos
            ]
            bm25 = BM25Index()
            bm25.fit(matched_photos, texts)
            bm25_items = bm25.score(trimmed_query)

            # 2. Vector Search (E5) restricted to completed embedding_version == version
            vector_items: list[tuple[dict[str, Any], float]] = []
            eligible_vector_photos = [
                p for p in matched_photos
                if p.get("embedding_status") == "completed"
                and p.get("embedding_version") is not None
                and p.get("embedding_version") == p.get("version", 1)
            ]
            eligible_vector_ids = [p["id"] for p in eligible_vector_photos]

            if self.embedder is not None and eligible_vector_ids:
                try:
                    query_vector = self.embedder.encode_query(trimmed_query)

                    store = getattr(self.photo_service, "store", None)
                    driver = getattr(store, "driver", None)
                    database = getattr(store, "database", "neo4j")
                    used_neo4j = False

                    if driver is not None:
                        try:
                            # Pre-filter candidate IDs inside SEARCH before LIMIT
                            cypher = """
                            CYPHER 25
                            MATCH (p:Photo)
                            SEARCH p IN (
                              VECTOR INDEX photo_embeddings FOR $qvec
                              WHERE p.owner_id = $owner_id AND p.searchable = true AND p.id IN $eligible_ids
                              LIMIT $limit
                            )
                            SCORE AS score
                            RETURN p, score
                            ORDER BY score DESC, p.id ASC
                            """
                            params = {
                                "owner_id": owner_id,
                                "qvec": query_vector,
                                "limit": self.top_k,
                                "eligible_ids": eligible_vector_ids,
                            }
                            with driver.session(database=database) as session:
                                records = session.run(cypher, parameters=params).data()
                                id_to_photo = {p["id"]: p for p in eligible_vector_photos}
                                for r in records:
                                    p_rec = dict(r["p"])
                                    pid = p_rec.get("id")
                                    if pid in id_to_photo:
                                        vector_items.append((id_to_photo[pid], float(r["score"])))
                            used_neo4j = True
                        except Exception as n_exc:  # noqa: BLE001
                            logger.warning(
                                "Neo4j vector search index query error: %s; falling back to BM25/memory.",
                                type(n_exc).__name__,
                            )

                    if not used_neo4j:
                        for p in eligible_vector_photos:
                            emb = p.get("embedding")
                            if emb:
                                sim = cosine_similarity(query_vector, emb)
                                if sim > 0:
                                    vector_items.append((p, float(sim)))
                        vector_items.sort(key=lambda item: (-item[1], str(item[0].get("id", ""))))
                except Exception as v_exc:  # noqa: BLE001
                    logger.warning("Dense vector query failed: %s; serving via BM25.", type(v_exc).__name__)

            # 3. Hybrid RRF Fusion (BM25 always included)
            fused = compute_rrf(bm25_items, vector_items, k=self.rrf_k)
            results: list[dict[str, Any]] = []
            for p, sc, rsn in fused[:limit]:
                dto = _to_photo_dto(p, self.photo_service, owner_id)
                event, source_trip = matched_sources[p["id"]]
                results.append({
                    "photo": dto,
                    "score": round(float(sc), 4),
                    "reasons": rsn,
                    "event": _safe_format_event(event),
                    "trip_id": source_trip,
                })
            return results

        # If query is empty, sort by created_at descending (pure filter matching)
        matched_photos.sort(
            key=lambda p: (str(p.get("created_at") or ""), str(p.get("id", ""))),
            reverse=True,
        )
        results = []
        for p in matched_photos[:limit]:
            dto = _to_photo_dto(p, self.photo_service, owner_id)
            event, source_trip = matched_sources[p["id"]]
            results.append({
                "photo": dto,
                "score": 1.0,
                "reasons": ["條件篩選匹配"],
                "event": _safe_format_event(event),
                "trip_id": source_trip,
            })
        return results
