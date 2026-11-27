"""SearchService orchestrating BM25, Vector Search, RRF Fusion, and Graph Reranking."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from backend.embedding import EmbeddingModel, event_to_passage_text
from backend.search_store import (
    MemorySearchStore,
    Neo4jSearchStore,
    passes_filters,
)
from backend.travel_store import format_event

logger = logging.getLogger(__name__)

# Direction parsing regexes for Chinese and English
_CHINESE_DIRECTIONAL_RE = re.compile(
    r"(?:在|去完|參觀完|抵達|離開)?\s*(?P<anchor>[^\s,，。?]+?)\s*"
    r"(?P<dir>之後|後來|接著|緊接著|然後|下一站|下一個|之前|先前|前面|上一站|上一個)"
    r"(?:\s*(?:去|吃|玩|看|住|買|的)?\s*(?P<target>[^\s,，。?]+))?"
)

_CHINESE_SEPARATED_DIRECTION_RE = re.compile(
    r"(?P<anchor>[^。！？!?]{2,240}?)\s*[,，。…]+\s*(?:那|我|所以我)?\s*"
    r"(?P<dir>下一站|上一站|下一個|上一個|前一站|前一個|緊接著|接著)"
    r"\s*(?P<target>[^,，。!?！？]*)"
)
_CHINESE_OPEN_TARGET_RE = re.compile(
    r"^(?:(?:我|的|是|去|在|到|哪|裡|裏|兒|邊|何處|什麼|地方|地點|啊|呀|呢|嗎)\s*)*$"
)

_ENGLISH_WHICH_RE = re.compile(
    r"^(?:Which|What)\s+(?P<target>.+?)\s+did\s+I\s+(?:visit|go\s+to)\s+"
    r"(?P<dir>immediately\s+after|immediately\s+before|after|before)\s+"
    r"(?P<anchor>[^?]+)\??$",
    re.IGNORECASE,
)

_ENGLISH_WHAT_WHERE_RE = re.compile(
    r"^(?:What|Where)(?:\s+place|\s+spot)?\s+(?:did\s+I\s+(?:visit|go)(?:\s+to)?\s+)?"
    r"(?P<dir>immediately\s+after|immediately\s+before|after|before)\s+"
    r"(?P<anchor>[^?]+)\??$",
    re.IGNORECASE,
)

_ENGLISH_STOP_RE = re.compile(
    r"^(?:what\s+(?:is|was)\s+the\s+)?(?P<dir>next\s+stop|previous\s+stop|next\s+place|previous\s+place)\s+"
    r"(?:after|before|from)?\s*(?P<anchor>[^?]+)\??$",
    re.IGNORECASE,
)

_ENGLISH_AFTER_BEFORE_PREFIX_RE = re.compile(
    r"^(?P<dir>immediately\s+after|immediately\s+before|after|before)\s+"
    r"(?P<anchor>[^,，?]+)(?:,\s*(?:which|what)?\s*(?P<target>[^?]+))?\??$",
    re.IGNORECASE,
)

_FORWARD_KEYWORDS = {
    "之後",
    "後來",
    "接著",
    "緊接著",
    "然後",
    "下一站",
    "下一個",
    "after",
    "immediately after",
    "next",
    "next stop",
    "next place",
}
_AMBIGUOUS_KEYWORDS = {"之後", "後來", "after", "before"}


def parse_directional_query(query: str) -> dict[str, Any] | None:
    q = query.strip()
    anchor = None
    dir_word = None
    target = ""

    # 1. Try English WHICH pattern
    m = _ENGLISH_WHICH_RE.match(q)
    if m:
        anchor = m.group("anchor").strip().rstrip("?")
        dir_word = m.group("dir").strip().lower()
        target = m.group("target").strip()
        if target.lower() in ("place", "spot", "attraction", "site"):
            target = ""
    elif (m := _ENGLISH_WHAT_WHERE_RE.match(q)) is not None or (
        m := _ENGLISH_STOP_RE.match(q)
    ) is not None:
        anchor = m.group("anchor").strip().rstrip("?")
        dir_word = m.group("dir").strip().lower()
        target = ""
    elif (m := _ENGLISH_AFTER_BEFORE_PREFIX_RE.match(q)) is not None:
        anchor = m.group("anchor").strip().rstrip("?")
        dir_word = m.group("dir").strip().lower()
        raw_target = (m.group("target") or "").strip().rstrip("?")
        # Clean target: "which Cafe did I visit" -> "Cafe"
        raw_target = re.sub(
            r"^(?:which|what)\s+(?:place\s+|spot\s+)?", "", raw_target, flags=re.IGNORECASE
        )
        target = re.sub(
            r"\s+did\s+I\s+(?:visit|go).*$", "", raw_target, flags=re.IGNORECASE
        ).strip()
        if target.lower() in ("place", "spot", "attraction", "site"):
            target = ""
    elif (m := _CHINESE_SEPARATED_DIRECTION_RE.search(q)) is not None:
        anchor = m.group("anchor").strip()
        dir_word = m.group("dir").strip()
        target = m.group("target").strip()
        if _CHINESE_OPEN_TARGET_RE.fullmatch(target):
            target = ""
    elif (m := _CHINESE_DIRECTIONAL_RE.search(q)) is not None:
        anchor = m.group("anchor").strip().rstrip("?")
        dir_word = m.group("dir").strip()
        target = (m.group("target") or "").strip().rstrip("?")
        if target in ("行程", "地點", "地方", "景點"):
            target = ""

    if not anchor or not dir_word:
        return None

    direction = "next" if dir_word in _FORWARD_KEYWORDS else "prev"
    is_ambiguous = dir_word in _AMBIGUOUS_KEYWORDS

    return {
        "anchor_query": anchor,
        "direction": direction,
        "direction_word": dir_word,
        "target_query": target,
        "is_ambiguous_after": is_ambiguous,
    }


def compute_rrf(
    bm25_items: list[tuple[dict[str, Any], float]],
    vector_items: list[tuple[dict[str, Any], float]],
    k: int = 60,
) -> list[tuple[dict[str, Any], float, list[str]]]:
    """Combines BM25 and Vector search results using Reciprocal Rank Fusion (k=60).

    Tie-breaking is strictly stable by event ID ascending.
    """
    scores: dict[str, float] = {}
    events: dict[str, dict[str, Any]] = {}
    reasons_map: dict[str, list[str]] = {}

    for rank, (ev, _raw_score) in enumerate(bm25_items, start=1):
        ev_id = ev["id"]
        events[ev_id] = ev
        scores[ev_id] = scores.get(ev_id, 0.0) + (1.0 / (k + rank))
        reasons_map.setdefault(ev_id, []).append(f"BM25 關鍵字匹配 (名次 {rank})")

    for rank, (ev, _raw_score) in enumerate(vector_items, start=1):
        ev_id = ev["id"]
        events[ev_id] = ev
        scores[ev_id] = scores.get(ev_id, 0.0) + (1.0 / (k + rank))
        reasons_map.setdefault(ev_id, []).append(f"語意相似向量匹配 (名次 {rank})")

    ranked = [(events[ev_id], scores[ev_id], reasons_map[ev_id]) for ev_id in scores]
    # Sort descending by score, tie-break by event ID ascending
    ranked.sort(key=lambda item: (-item[1], item[0]["id"]))
    return ranked


class SearchService:
    """Core search service coordinating BM25, E5 embeddings, and 1-hop relationship reranking."""

    def __init__(self, settings: Any, travel_repository: Any, embedder: Any = None):
        self.settings = settings
        self.repository = travel_repository
        self.embedder = embedder or EmbeddingModel(settings)
        self.model = self.embedder  # CLI and evaluator compatibility attribute
        self.top_k = getattr(settings, "retrieval_top_k", 50)
        self.rrf_k = getattr(settings, "rrf_k", 60)
        self.relation_weight = getattr(settings, "relation_weight", 0.5)

        # Select appropriate search store
        if hasattr(travel_repository, "driver") and hasattr(travel_repository, "database"):
            self.store = Neo4jSearchStore(
                travel_repository.driver,
                database=travel_repository.database,
                embedder=self.embedder,
            )
        else:
            self.store = MemorySearchStore(travel_repository, embedder=self.embedder)

        self._running = False

    def initialize(self):
        self.store.initialize()

    def process_pending(self, batch_size: int = 8) -> int:
        """Synchronously processes pending events and indexes them.

        Returns the number of events attempted.
        """
        retry_seconds = float(getattr(self.settings, "embedding_retry_seconds", 60.0))
        pending = self.store.get_pending_events(limit=batch_size, retry_seconds=retry_seconds)
        if not pending:
            return 0

        texts = [event_to_passage_text(ev) for ev in pending]
        try:
            if hasattr(self.embedder, "encode_passages_with_metadata"):
                embeddings, metadata_list = self.embedder.encode_passages_with_metadata(texts)
            else:
                embeddings = self.embedder.encode_passages(texts)
                metadata_list = [{"token_count": len(t), "truncated": False} for t in texts]

            updates = []
            for ev, emb, meta in zip(pending, embeddings, metadata_list):
                updates.append(
                    {
                        "id": ev["id"],
                        "owner_id": ev["owner_id"],
                        "version": ev["version"],
                        "embedding": emb,
                        "revision": getattr(self.embedder, "revision", "default"),
                        "token_count": meta.get("token_count", 0),
                        "truncated": meta.get("truncated", False),
                    }
                )
            self.store.update_embeddings(updates)
            logger.info("Indexed %d pending events into vector store.", len(updates))
            return len(pending)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed processing pending embeddings: %s", exc)
            failed = [
                {
                    "id": ev["id"],
                    "owner_id": ev["owner_id"],
                    "version": ev["version"],
                    "error": str(exc),
                }
                for ev in pending
            ]
            self.store.mark_embeddings_failed(failed)
            return len(pending)

    def index_status(self, owner_id: str | None = None) -> dict[str, int]:
        """Returns counts of pending, ready, and failed indexed events."""
        return self.store.index_status(owner_id)

    def rebuild(self, owner_id: str | None = None) -> None:
        """Resets all events to pending state and clears stale embeddings."""
        self.store.rebuild(owner_id)

    async def run_worker(self):
        """Background asynchronous worker ensuring pending and updated events get embedded."""
        self._running = True
        logger.info("SearchService background worker started.")
        poll_interval = getattr(self.settings, "embedding_poll_seconds", 3.0)
        try:
            while self._running:
                try:
                    count = await asyncio.to_thread(self.process_pending)
                    if count == 0:
                        await asyncio.sleep(poll_interval)
                    else:
                        await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error in embedding worker loop: %s", exc)
                    await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            self._running = False
            logger.info("SearchService background worker cancelled.")
            raise

    def search(
        self,
        owner_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        method: str = "next",
        anchor_id: str | None = None,
    ) -> dict[str, Any]:
        """Searches events for owner_id.

        Supported methods:
        - "bm25": BM25 retrieval only (MUST NOT invoke embedder).
        - "e5": Dense vector retrieval only.
        - "rrf": BM25 + Vector fused via Reciprocal Rank Fusion without graph reranking.
        - "next": Full hybrid retrieval with 1-hop relation reranking and clarification.
        """
        filters = filters or {}
        limit = max(1, min(limit, 50))
        method = method.lower()

        # 1. BM25 baseline: Must not invoke embedder
        if method == "bm25":
            bm25_items = self.store.query_bm25(owner_id, query, filters=filters, limit=limit)
            final_items = [
                {
                    "event": format_event(ev),
                    "score": round(float(sc), 4),
                    "reasons": [f"BM25 關鍵字匹配 (分數 {round(float(sc), 4)})"],
                    "relation": None,
                }
                for ev, sc in bm25_items
            ]
            return {
                "items": final_items,
                "clarification": None,
                "vector_status": "disabled",
            }

        # 2. Dense vector baseline (e5 only)
        if method == "e5":
            query_vector = self.embedder.encode_query(query)
            vector_items = self.store.query_vector(
                owner_id, query_vector, filters=filters, limit=limit
            )
            final_items = [
                {
                    "event": format_event(ev),
                    "score": round(float(sc), 4),
                    "reasons": [f"語意相似向量匹配 (分數 {round(float(sc), 4)})"],
                    "relation": None,
                }
                for ev, sc in vector_items
            ]
            return {
                "items": final_items,
                "clarification": None,
                "vector_status": "ready",
            }

        # 3. Hybrid RRF baseline (bm25 + e5 fused via RRF, no graph)
        if method == "rrf":
            bm25_items = self.store.query_bm25(owner_id, query, filters=filters, limit=self.top_k)
            vector_items: list[tuple[dict[str, Any], float]] = []
            vector_status = "degraded"
            try:
                query_vector = self.embedder.encode_query(query)
                vector_items = self.store.query_vector(
                    owner_id, query_vector, filters=filters, limit=self.top_k
                )
                vector_status = "ready"
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Vector search unavailable in RRF mode (%s); falling back to BM25.", exc
                )
                vector_status = "degraded"

            hybrid_ranked = compute_rrf(bm25_items, vector_items, k=self.rrf_k)
            final_items = [
                {
                    "event": format_event(ev),
                    "score": round(float(sc), 4),
                    "reasons": rsn,
                    "relation": None,
                }
                for ev, sc, rsn in hybrid_ranked[:limit]
            ]
            return {
                "items": final_items,
                "clarification": None,
                "vector_status": vector_status,
            }

        # 4. Default "next" method: BM25 + Vector + Graph Reranking
        bm25_items = self.store.query_bm25(owner_id, query, filters=filters, limit=self.top_k)
        vector_items = []
        vector_status = "degraded"

        try:
            query_vector = self.embedder.encode_query(query)
            vector_items = self.store.query_vector(
                owner_id, query_vector, filters=filters, limit=self.top_k
            )
            vector_status = "ready"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector search unavailable (%s); falling back to BM25.", exc)
            vector_status = "degraded"

        # RRF Fusion
        hybrid_ranked = compute_rrf(bm25_items, vector_items, k=self.rrf_k)

        # Directional Query Resolution & Relationship Reranking
        dir_info = parse_directional_query(query)
        if not dir_info and anchor_id:
            q_lower = query.casefold().strip()
            next_word = re.search(r"下一站|下一個|緊接著|接著|然後|\b(?:next|after)\b", q_lower)
            previous_word = re.search(r"上一站|上一個|之前|先前|\b(?:prev(?:ious)?|before)\b", q_lower)
            if next_word:
                dir_info = {
                    "anchor_query": "",
                    "direction": "next",
                    "direction_word": next_word[0],
                    "is_ambiguous_after": False,
                    "target_query": "",
                }
            elif previous_word:
                dir_info = {
                    "anchor_query": "",
                    "direction": "prev",
                    "direction_word": previous_word[0],
                    "is_ambiguous_after": False,
                    "target_query": "",
                }

        clarification: str | None = None
        final_items: list[dict[str, Any]] = []

        if dir_info:
            anchor_query = dir_info["anchor_query"]
            direction = dir_info["direction"]
            target_query = dir_info["target_query"]
            is_eng_query = any(
                w in dir_info.get("direction_word", "") for w in ("after", "before", "next", "prev")
            )
            independent_visit = {
                "items": [],
                "clarification": (
                    "Independent visits do not have previous or next stops."
                    if is_eng_query
                    else "日常足跡各自獨立，沒有上一站或下一站。"
                ),
                "vector_status": vector_status,
            }
            if filters.get("record_scope") == "standalone":
                return independent_visit
            if dir_info["is_ambiguous_after"]:
                clarification = (
                    "Do you mean the immediately adjacent stop, or later events after this place?"
                    if is_eng_query
                    else "您是指該地點緊接著的下一個行程，還是之後的其他行程？"
                )
                return {
                    "items": [
                        {
                            "event": format_event(ev),
                            "score": round(score, 8),
                            "reasons": reasons,
                            "relation": None,
                        }
                        for ev, score, reasons in hybrid_ranked[:limit]
                    ],
                    "clarification": clarification,
                    "vector_status": vector_status,
                }

            # Match target category from actual owned category labels
            owned_categories = self.store.get_owned_categories(owner_id)
            target_category: str | None = None
            if target_query:
                t_lower = target_query.casefold().strip()
                for cat in sorted(owned_categories, key=len, reverse=True):
                    c_lower = cat.casefold().strip()
                    if c_lower and (c_lower in t_lower or t_lower in c_lower):
                        target_category = cat
                        break

            # If a specific target query/category was specified, also run hybrid retrieval on it
            if target_query:
                target_bm25 = self.store.query_bm25(
                    owner_id, target_query, filters=filters, limit=self.top_k
                )
                target_vec: list[tuple[dict[str, Any], float]] = []
                if vector_status == "ready":
                    try:
                        t_vec = self.embedder.encode_query(target_query)
                        target_vec = self.store.query_vector(
                            owner_id, t_vec, filters=filters, limit=self.top_k
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Target vector query fallback: %s", exc)
                target_fused = compute_rrf(target_bm25, target_vec, k=self.rrf_k)
                target_dict = {ev["id"]: (ev, sc, rsn) for ev, sc, rsn in target_fused}
                for ev, sc, rsn in hybrid_ranked:
                    if ev["id"] not in target_dict:
                        target_dict[ev["id"]] = (ev, sc * 0.5, rsn)
                hybrid_ranked = sorted(target_dict.values(), key=lambda x: (-x[1], x[0]["id"]))

            # Retrieve anchor events:
            # If explicit internal anchor_id provided, resolve that exact owned event without re-searching same-name places
            anchors: list[dict[str, Any]] = []
            if anchor_id:
                ev = self.get_event(owner_id, anchor_id)
                if ev:
                    if not ev.get("trip_id"):
                        return independent_visit
                    selected_trip = filters.get("trip_id") if filters else None
                    if not selected_trip or ev.get("trip_id") == selected_trip:
                        anchors = [ev]

            # When anchor_id is absent, execute standard query-only anchor search
            if not anchors and not anchor_id:
                # Location, category and date filters constrain the target, not the anchor.
                anchor_filters = {key: filters[key] for key in ("trip_id", "record_scope") if filters.get(key)}
                anchor_bm25 = self.store.query_bm25(
                    owner_id, anchor_query, filters=anchor_filters, limit=5
                )
                anchor_vector: list[tuple[dict[str, Any], float]] = []
                if vector_status == "ready":
                    try:
                        anchor_vec = self.embedder.encode_query(anchor_query)
                        anchor_vector = self.store.query_vector(
                            owner_id, anchor_vec, filters=anchor_filters, limit=5
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Anchor vector query fallback: %s", exc)
                anchors_fused = compute_rrf(anchor_bm25, anchor_vector, k=self.rrf_k)[:5]
                anchors = [item[0] for item in anchors_fused]
                exact_anchors = [
                    ev for ev in anchors
                    if str(ev.get("place_name", "")).casefold() == anchor_query.casefold()
                ]
                if exact_anchors and all(not ev.get("trip_id") for ev in exact_anchors):
                    return independent_visit

            # Find 1-hop adjacent candidates from anchors (enforcing target_category if recognized)
            relation_candidates: dict[str, dict[str, Any]] = {}
            for rank_idx, anchor_ev in enumerate(anchors, start=1):
                if not anchor_ev.get("trip_id"):
                    continue
                adj_list = self.store.get_adjacent_events(
                    owner_id, anchor_ev["id"], direction=direction
                )
                for cand in adj_list:
                    if (
                        target_category
                        and cand.get("category", "").casefold() != target_category.casefold()
                    ):
                        continue
                    cand_id = cand["id"]
                    if cand_id not in relation_candidates:
                        relation_candidates[cand_id] = {
                            "event": cand,
                            "anchor": anchor_ev,
                            "r_score": 1.0 / rank_idx,
                            "direction": direction,
                        }

            # If relation candidates found, apply (1-w) H + w R reranking
            if relation_candidates:
                w = self.relation_weight
                h_weight = 1.0 - w

                h_scores = {ev["id"]: score for ev, score, _ in hybrid_ranked}
                max_h = max(h_scores.values()) if h_scores else 1.0
                min_h = min(h_scores.values()) if h_scores else 0.0

                max_r = max(c["r_score"] for c in relation_candidates.values())
                min_r = min(c["r_score"] for c in relation_candidates.values())

                scored_pool: dict[str, dict[str, Any]] = {}

                for ev, score, reasons in hybrid_ranked:
                    ev_id = ev["id"]
                    h_norm = (score - min_h) / (max_h - min_h) if max_h > min_h else 1.0
                    scored_pool[ev_id] = {
                        "event": ev,
                        "h_norm": h_norm,
                        "r_norm": 0.0,
                        "reasons": list(reasons),
                        "relation": None,
                    }

                for cand_id, rel_data in relation_candidates.items():
                    cand_ev = rel_data["event"]
                    anchor_ev = rel_data["anchor"]
                    r_norm = (
                        (rel_data["r_score"] - min_r) / (max_r - min_r) if max_r > min_r else 1.0
                    )

                    if cand_id in scored_pool:
                        scored_pool[cand_id]["r_norm"] = r_norm
                    else:
                        scored_pool[cand_id] = {
                            "event": cand_ev,
                            "h_norm": 0.0,
                            "r_norm": r_norm,
                            "reasons": [],
                            "relation": None,
                        }

                    scored_pool[cand_id]["relation"] = {
                        "anchor_id": anchor_ev["id"],
                        "direction": rel_data["direction"],
                        "anchor_date": anchor_ev.get("date", ""),
                        "target_date": cand_ev.get("date", ""),
                    }
                    if is_eng_query:
                        dir_text = "after" if rel_data["direction"] == "next" else "before"
                        reason_text = (
                            f"Relation candidate: 1-hop stop {dir_text} "
                            f"[{anchor_ev.get('place_name', '')}] ({anchor_ev.get('date', '')})"
                        )
                    else:
                        dir_text = "之後" if rel_data["direction"] == "next" else "之前"
                        reason_text = (
                            f"關係候選：在 [{anchor_ev.get('place_name', '')}] "
                            f"({anchor_ev.get('date', '')}) {dir_text}的一跳行程"
                        )
                    scored_pool[cand_id]["reasons"].append(reason_text)

                reranked_list = []
                for item_info in scored_pool.values():
                    ev = item_info["event"]
                    if not passes_filters(ev, filters):
                        continue
                    if item_info["relation"] is not None:
                        combined_score = h_weight * item_info["h_norm"] + w * item_info["r_norm"]
                    else:
                        combined_score = h_weight * item_info["h_norm"]

                    reranked_list.append(
                        (ev, combined_score, item_info["reasons"], item_info["relation"])
                    )

                reranked_list.sort(key=lambda x: (-x[1], 0 if x[3] is not None else 1, x[0]["id"]))
                final_items = [
                    {
                        "event": format_event(ev),
                        "score": round(float(sc), 4),
                        "reasons": rsn,
                        "relation": rel,
                    }
                    for ev, sc, rsn, rel in reranked_list[:limit]
                ]
            else:
                final_items = [
                    {
                        "event": format_event(ev),
                        "score": round(float(sc), 4),
                        "reasons": rsn,
                        "relation": None,
                    }
                    for ev, sc, rsn in hybrid_ranked[:limit]
                ]
        else:
            final_items = [
                {
                    "event": format_event(ev),
                    "score": round(float(sc), 4),
                    "reasons": rsn,
                    "relation": None,
                }
                for ev, sc, rsn in hybrid_ranked[:limit]
            ]

        return {
            "items": final_items,
            "clarification": clarification,
            "vector_status": vector_status,
        }

    def get_event(self, owner_id: str, event_id: str) -> dict[str, Any] | None:
        """Reads current event with owner verification and attaches trip_name if available."""
        if hasattr(self.repository, "get_event"):
            return self.repository.get_event(owner_id, event_id)

        # Fallback via get_trip_detail or store
        if hasattr(self.repository, "events"):
            with self.repository.lock:
                ev = self.repository.events.get(event_id)
                if not ev or ev.get("owner_id") != owner_id:
                    return None
                formatted = format_event(ev)
                trip = self.repository.trips.get(ev.get("trip_id"))
                if trip:
                    formatted["trip_name"] = trip.get("name", "")
                return formatted

        return None

    def verify_relation(
        self,
        owner_id: str,
        anchor_id: str,
        target_id: str,
        direction: str = "next",
    ) -> bool:
        """Verifies whether target_id is currently 1-hop adjacent to anchor_id in the graph.

        Uses current actual owned NEXT/previous adjacency within the same trip.
        Returns False if graph has been reordered or does not match.
        """
        adj_events = self.store.get_adjacent_events(owner_id, anchor_id, direction=direction)
        return any(ev.get("id") == target_id for ev in adj_events)
