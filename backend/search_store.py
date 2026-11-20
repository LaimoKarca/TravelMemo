"""Search storage and retrieval engines: BM25, Vector Search, and Graph Traversal."""

from __future__ import annotations

import logging
import math
import time
import unicodedata
from typing import Any

from backend.embedding import E5_REVISION, event_to_passage_text

logger = logging.getLogger(__name__)


# Based on mixed_language_tokenize from upstream benchmark (MIT License)
# Copyright (c) 2026 TravelMemo Benchmark Authors
def _is_japanese_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or character in {"々", "〆", "ヶ"}
    )


def mixed_language_tokenize(value: object) -> list[str]:
    """Tokenize Latin words/numbers and Japanese character n-grams."""
    if value is None:
        return []
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    normalized = " ".join(normalized.split())

    tokens: list[str] = []
    segment: list[str] = []
    segment_kind: str | None = None

    def flush() -> None:
        nonlocal segment, segment_kind
        if not segment:
            return
        text = "".join(segment)
        if segment_kind == "japanese":
            tokens.append(text)
            for width in (2, 3):
                if len(text) > width:
                    tokens.extend(
                        text[index : index + width]
                        for index in range(len(text) - width + 1)
                    )
        else:
            tokens.append(text)
        segment = []
        segment_kind = None

    for character in normalized:
        if _is_japanese_character(character):
            kind = "japanese"
        else:
            category = unicodedata.category(character)
            kind = "word" if category[0] in {"L", "M", "N"} else None

        if kind is None:
            flush()
            continue
        if segment_kind is not None and kind != segment_kind:
            flush()
        segment_kind = kind
        segment.append(character)

    flush()
    return tokens


tokenize_bm25 = mixed_language_tokenize


class BM25Index:
    """Okapi BM25 implementation for rank-ordering event documents.

    Uses rank_bm25.BM25Okapi with k1=1.5, b=0.75, epsilon=0.25 and mixed_language_tokenize.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        self.docs: list[dict[str, Any]] = []
        self._bm25 = None

    def fit(self, docs: list[dict[str, Any]], texts: list[str]):
        self.docs = docs
        if not docs or not texts:
            self._bm25 = None
            return

        from rank_bm25 import BM25Okapi

        tokenized_corpus = [mixed_language_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(
            tokenized_corpus,
            k1=self.k1,
            b=self.b,
            epsilon=self.epsilon,
        )
        # Handle small corpus edge-case where average_idf <= 0 in rank_bm25
        if self._bm25.average_idf <= 0:
            for word in self._bm25.idf:
                if self._bm25.idf[word] <= 0:
                    self._bm25.idf[word] = 0.25
            self._bm25.average_idf = 0.25

    def score(self, query: str, include_zero_scores: bool = False) -> list[tuple[dict[str, Any], float]]:
        if self._bm25 is None or not self.docs:
            return []
        query_tokens = mixed_language_tokenize(query)
        if not query_tokens:
            return []

        import numpy as np

        raw_scores = self._bm25.get_scores(query_tokens)
        scores = np.asarray(raw_scores, dtype=float)

        results: list[tuple[dict[str, Any], float]] = []
        for idx, doc in enumerate(self.docs):
            sc = float(scores[idx])
            if include_zero_scores or sc > 0:
                results.append((doc, sc))

        # Sort descending by score, tie-break by event ID ascending
        results.sort(key=lambda item: (-item[1], str(item[0].get("id", ""))))
        return results


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def passes_filters(event: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    if filters.get("trip_id") and event.get("trip_id") != filters["trip_id"]:
        return False
    scope = filters.get("record_scope")
    event_scope = event.get("record_scope") or ("trip" if event.get("trip_id") else "standalone")
    if scope and scope != "all" and scope != event_scope:
        return False
    if filters.get("date_from") and event.get("date", "") < filters["date_from"]:
        return False
    if filters.get("date_to") and event.get("date", "") > filters["date_to"]:
        return False
    if filters.get("city") and event.get("city") != filters["city"]:
        return False
    return not (filters.get("category") and event.get("category") != filters["category"])


class MemorySearchStore:
    """Thread-safe In-Memory Search Store for testing and offline execution."""

    def __init__(self, repository: Any, embedder: Any = None):
        self.repository = repository
        self.embedder = embedder

    def initialize(self):
        pass

    def query_bm25(
        self,
        owner_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        include_zero_scores: bool = False,
    ) -> list[tuple[dict[str, Any], float]]:
        with self.repository.lock:
            all_events = [
                e
                for e in self.repository.events.values()
                if e.get("owner_id") == owner_id and passes_filters(e, filters)
            ]
        if not all_events:
            return []

        texts = [event_to_passage_text(e) for e in all_events]
        bm25 = BM25Index()
        bm25.fit(all_events, texts)
        ranked = bm25.score(query, include_zero_scores=include_zero_scores)
        return ranked[:limit]

    def query_vector(
        self,
        owner_id: str,
        query_vector: list[float],
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[tuple[dict[str, Any], float]]:
        active_revision = getattr(self.embedder, "revision", E5_REVISION)
        with self.repository.lock:
            candidates = [
                e
                for e in self.repository.events.values()
                if e.get("owner_id") == owner_id
                and e.get("embedding_status") == "completed"
                and e.get("embedding_model_revision") == active_revision
                and e.get("embedded_version") == e.get("version")
                and e.get("embedding") is not None
                and passes_filters(e, filters)
            ]

        results = []
        for e in candidates:
            score = cosine_similarity(query_vector, e["embedding"])
            results.append((e, score))

        results.sort(key=lambda item: (-item[1], str(item[0].get("id", ""))))
        return results[:limit]

    def get_adjacent_events(
        self,
        owner_id: str,
        anchor_id: str,
        direction: str = "next",
    ) -> list[dict[str, Any]]:
        with self.repository.lock:
            anchor = self.repository.events.get(anchor_id)
            if not anchor or anchor.get("owner_id") != owner_id or not anchor.get("trip_id"):
                return []

            trip_events = [
                e
                for e in self.repository.events.values()
                if e.get("trip_id") == anchor["trip_id"] and e.get("owner_id") == owner_id
            ]
            trip_events.sort(key=lambda e: (e.get("position", 0), e["id"]))

            for idx, ev in enumerate(trip_events):
                if ev["id"] == anchor_id:
                    if direction == "next" and idx + 1 < len(trip_events):
                        return [trip_events[idx + 1]]
                    if direction == "prev" and idx - 1 >= 0:
                        return [trip_events[idx - 1]]
                    break
        return []

    def get_owned_categories(self, owner_id: str) -> set[str]:
        with self.repository.lock:
            return {
                e["category"]
                for e in self.repository.events.values()
                if e.get("owner_id") == owner_id and e.get("category")
            }

    def get_pending_events(
        self, limit: int = 50, retry_seconds: float = 60.0
    ) -> list[dict[str, Any]]:
        active_revision = getattr(self.embedder, "revision", E5_REVISION)
        now = time.time()
        with self.repository.lock:
            normal_pending = []
            retryable_failed = []
            for e in self.repository.events.values():
                status = e.get("embedding_status", "pending")
                emb_ver = e.get("embedded_version", 0)
                cur_ver = e.get("version", 1)
                emb = e.get("embedding")
                rev = e.get("embedding_model_revision")
                last_failed = e.get("last_failed_at")

                if status == "failed":
                    if last_failed is None or (now - last_failed) >= retry_seconds:
                        retryable_failed.append(dict(e))
                else:
                    is_pending = (
                        status == "pending"
                        or emb is None
                        or emb_ver != cur_ver
                        or (status == "completed" and rev != active_revision)
                    )
                    if is_pending:
                        normal_pending.append(dict(e))

            # Prioritize fresh pending jobs before failed retries to prevent starvation
            pending = (normal_pending + retryable_failed)[:limit]
            return pending

    def update_embeddings(self, updates: list[dict[str, Any]]) -> None:
        now = time.time()
        with self.repository.lock:
            for upd in updates:
                ev = self.repository.events.get(upd["id"])
                if (
                    ev
                    and ev.get("owner_id") == upd.get("owner_id")
                    and ev.get("version") == upd.get("version")
                ):
                    ev["embedding"] = upd["embedding"]
                    ev["embedded_version"] = upd["version"]
                    ev["embedding_status"] = "completed"
                    ev["embedding_model_revision"] = upd.get("revision", E5_REVISION)
                    ev["token_count"] = upd.get("token_count", 0)
                    ev["truncated"] = upd.get("truncated", False)
                    ev["embedding_error"] = None
                    ev["embedding_retries"] = 0
                    ev["last_embedded_at"] = now

    def mark_embedding_failed(
        self,
        event_id: str,
        error: str,
        owner_id: str | None = None,
        version: int | None = None,
    ) -> None:
        self.mark_embeddings_failed(
            [{"id": event_id, "error": error, "owner_id": owner_id, "version": version}]
        )

    def mark_embeddings_failed(self, failed: list[dict[str, Any]]) -> None:
        now = time.time()
        with self.repository.lock:
            for f in failed:
                ev = self.repository.events.get(f["id"])
                if ev:
                    # Require matching owner_id and version if provided
                    if f.get("owner_id") and ev.get("owner_id") != f["owner_id"]:
                        continue
                    if f.get("version") is not None and ev.get("version") != f["version"]:
                        continue
                    ev["embedding_status"] = "failed"
                    ev["embedding_error"] = f["error"]
                    ev["embedding_retries"] = ev.get("embedding_retries", 0) + 1
                    ev["last_failed_at"] = now

    def index_status(self, owner_id: str | None = None) -> dict[str, int]:
        active_revision = getattr(self.embedder, "revision", E5_REVISION)
        with self.repository.lock:
            pending = 0
            ready = 0
            failed = 0
            for e in self.repository.events.values():
                if owner_id and e.get("owner_id") != owner_id:
                    continue
                status = e.get("embedding_status", "pending")
                emb = e.get("embedding")
                emb_ver = e.get("embedded_version", 0)
                cur_ver = e.get("version", 1)
                rev = e.get("embedding_model_revision")
                if status == "failed":
                    failed += 1
                elif (
                    status == "completed"
                    and emb is not None
                    and emb_ver == cur_ver
                    and rev == active_revision
                ):
                    ready += 1
                else:
                    pending += 1
            return {"pending": pending, "ready": ready, "failed": failed}

    def rebuild(self, owner_id: str | None = None) -> None:
        with self.repository.lock:
            for ev in self.repository.events.values():
                if owner_id and ev.get("owner_id") != owner_id:
                    continue
                ev["embedding"] = None
                ev["embedded_version"] = 0
                ev["embedding_status"] = "pending"
                ev["embedding_retries"] = 0
                ev["embedding_error"] = None
                ev["last_failed_at"] = None


class Neo4jSearchStore:
    """Production Search Store backed by Neo4j 2026.10.2 vector indexes and CYPHER 25 SEARCH."""

    def __init__(self, driver: Any, database: str = "neo4j", embedder: Any = None):
        self.driver = driver
        self.database = database
        self.embedder = embedder

    def initialize(self):
        with self.driver.session(database=self.database) as session:
            required_props = {
                "embedding",
                "owner_id",
                "trip_id",
                "record_scope",
                "date",
                "city",
                "category",
                "embedding_status",
                "embedding_model_revision",
            }
            try:
                indexes = session.run(
                    "SHOW INDEXES YIELD name, properties WHERE name = 'event_embeddings' RETURN properties"
                ).data()
                if indexes:
                    existing_props = set(indexes[0].get("properties") or [])
                    if existing_props != required_props:
                        logger.info(
                            "Migrating vector index 'event_embeddings': updating indexed properties from %s to %s",
                            existing_props,
                            required_props,
                        )
                        session.run("DROP INDEX event_embeddings").consume()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not inspect existing index schema: %s", exc)

            try:
                session.run("""
                CYPHER 25
                CREATE VECTOR INDEX event_embeddings IF NOT EXISTS
                FOR (e:Event) ON (e.embedding)
                WITH [e.owner_id, e.trip_id, e.record_scope, e.date, e.city, e.category, e.embedding_status, e.embedding_model_revision]
                OPTIONS {indexConfig: {
                  `vector.dimensions`: 384,
                  `vector.similarity_function`: 'cosine'
                }}
                """).consume()
            except Exception as exc:
                raise RuntimeError(
                    f"Vector index 'event_embeddings' initialization failed: {exc}. "
                    "If the existing index has an incompatible definition, drop it manually via "
                    "'DROP INDEX event_embeddings' in Neo4j before restarting."
                ) from exc

            try:
                session.run("CALL db.awaitIndex('event_embeddings', 30)").consume()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Awaiting vector index readiness timed out or failed: %s", exc)

    def query_vector(
        self,
        owner_id: str,
        query_vector: list[float],
        filters: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> list[tuple[dict[str, Any], float]]:
        filters = filters or {}
        active_revision = getattr(self.embedder, "revision", E5_REVISION)

        predicates = [
            "e.owner_id = $owner_id",
            "e.embedding_status = 'completed'",
            "e.embedding_model_revision = $active_revision",
        ]
        params: dict[str, Any] = {
            "owner_id": owner_id,
            "qvec": query_vector,
            "limit": limit,
            "active_revision": active_revision,
        }

        # Push supported active filters inside SEARCH WHERE using allowlisted properties
        if filters.get("trip_id"):
            predicates.append("e.trip_id = $trip_id")
            params["trip_id"] = filters["trip_id"]
        if filters.get("record_scope") in ("trip", "standalone"):
            predicates.append("e.record_scope = $record_scope")
            params["record_scope"] = filters["record_scope"]
        if filters.get("city"):
            predicates.append("e.city = $city")
            params["city"] = filters["city"]
        if filters.get("category"):
            predicates.append("e.category = $category")
            params["category"] = filters["category"]
        if filters.get("date_from"):
            predicates.append("e.date >= $date_from")
            params["date_from"] = filters["date_from"]
        if filters.get("date_to"):
            predicates.append("e.date <= $date_to")
            params["date_to"] = filters["date_to"]

        where_clause = " AND ".join(predicates)

        cypher = f"""
        CYPHER 25
        MATCH (e:Event)
        SEARCH e IN (
          VECTOR INDEX event_embeddings FOR $qvec
          WHERE {where_clause}
          LIMIT $limit
        )
        SCORE AS score
        WHERE e.embedded_version = e.version
          AND EXISTS {{
            MATCH (:User {{id: $owner_id}})-[:OWNS_EVENT]->(e)
          }}
        RETURN e, score
        ORDER BY score DESC, e.id ASC
        """
        with self.driver.session(database=self.database) as session:
            records = session.run(cypher, parameters=params).data()
            return [(dict(r["e"]), float(r["score"])) for r in records]

    def query_bm25(
        self,
        owner_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        include_zero_scores: bool = False,
    ) -> list[tuple[dict[str, Any], float]]:
        filters = filters or {}
        cypher = """
        MATCH (:User {id: $owner_id})-[:OWNS_EVENT]->(e:Event {owner_id: $owner_id})
        WHERE ($trip_id IS NULL OR e.trip_id = $trip_id)
          AND ($record_scope IS NULL OR e.record_scope = $record_scope)
          AND ($date_from IS NULL OR e.date >= $date_from)
          AND ($date_to IS NULL OR e.date <= $date_to)
          AND ($city IS NULL OR e.city = $city)
          AND ($category IS NULL OR e.category = $category)
        RETURN e
        ORDER BY e.id ASC
        """
        params = {
            "owner_id": owner_id,
            "trip_id": filters.get("trip_id"),
            "record_scope": filters.get("record_scope") if filters.get("record_scope") in ("trip", "standalone") else None,
            "date_from": filters.get("date_from"),
            "date_to": filters.get("date_to"),
            "city": filters.get("city"),
            "category": filters.get("category"),
        }
        with self.driver.session(database=self.database) as session:
            records = session.run(cypher, parameters=params).data()
            all_events = [dict(r["e"]) for r in records]

        if not all_events:
            return []

        texts = [event_to_passage_text(e) for e in all_events]
        bm25 = BM25Index()
        bm25.fit(all_events, texts)
        ranked = bm25.score(query, include_zero_scores=include_zero_scores)
        return ranked[:limit]

    def get_adjacent_events(
        self,
        owner_id: str,
        anchor_id: str,
        direction: str = "next",
    ) -> list[dict[str, Any]]:
        edge = "-[:NEXT]->" if direction == "next" else "<-[:NEXT]-"
        cypher = f"""
        MATCH (u:User {{id: $owner_id}})-[:OWNS_EVENT]->(a:Event {{id: $anchor_id, owner_id: $owner_id}})
        MATCH (a){edge}(t:Event {{owner_id: $owner_id}})<-[:OWNS_EVENT]-(u)
        WHERE a.trip_id IS NOT NULL AND t.trip_id = a.trip_id
        RETURN DISTINCT t
        """
        with self.driver.session(database=self.database) as session:
            res = session.run(cypher, parameters={"anchor_id": anchor_id, "owner_id": owner_id}).data()
            return [dict(r["t"]) for r in res]

    def get_owned_categories(self, owner_id: str) -> set[str]:
        cypher = """
        MATCH (:User {id: $owner_id})-[:OWNS_EVENT]->(e:Event {owner_id: $owner_id})
        WHERE e.category IS NOT NULL AND e.category <> ''
        RETURN DISTINCT e.category AS category
        """
        with self.driver.session(database=self.database) as session:
            records = session.run(cypher, parameters={"owner_id": owner_id}).data()
            return {r["category"] for r in records}

    def get_pending_events(
        self, limit: int = 50, retry_seconds: float = 60.0
    ) -> list[dict[str, Any]]:
        retry_ms = int(retry_seconds * 1000)
        active_revision = getattr(self.embedder, "revision", E5_REVISION)
        cypher = """
        MATCH (e:Event)
        WHERE (
            coalesce(e.embedding_status, 'pending') = 'pending'
            OR (
                e.embedding_status = 'completed'
                AND (
                    coalesce(e.embedded_version, 0) <> e.version
                    OR e.embedding IS NULL
                    OR coalesce(e.embedding_model_revision, '') <> $active_revision
                )
            )
        ) OR (
            e.embedding_status = 'failed'
            AND (e.last_failed_at IS NOT NULL AND e.last_failed_at <= timestamp() - $retry_ms)
        )
        RETURN e.id AS id, e.owner_id AS owner_id, e.version AS version,
               e.date AS date, e.time AS time, e.place_name AS place_name,
               e.city AS city, e.address AS address, e.category AS category, e.notes AS notes
        ORDER BY CASE WHEN e.embedding_status = 'failed' THEN 1 ELSE 0 END ASC, e.id ASC
        LIMIT $limit
        """
        with self.driver.session(database=self.database) as session:
            res = session.run(
                cypher,
                parameters={"limit": limit, "retry_ms": retry_ms, "active_revision": active_revision},
            ).data()
            return res

    def update_embeddings(self, updates: list[dict[str, Any]]) -> None:
        if not updates:
            return
        cypher = """
        UNWIND $updates AS upd
        MATCH (e:Event {id: upd.id, owner_id: upd.owner_id, version: upd.version})
        SET e.embedding = upd.embedding,
            e.embedded_version = upd.version,
            e.embedding_status = 'completed',
            e.embedding_model_revision = upd.revision,
            e.token_count = upd.token_count,
            e.truncated = upd.truncated,
            e.embedding_error = NULL,
            e.embedding_retries = 0,
            e.last_embedded_at = timestamp()
        """
        with self.driver.session(database=self.database) as session:
            session.run(cypher, parameters={"updates": updates}).consume()

    def mark_embedding_failed(
        self,
        event_id: str,
        error: str,
        owner_id: str | None = None,
        version: int | None = None,
    ) -> None:
        self.mark_embeddings_failed(
            [{"id": event_id, "error": error, "owner_id": owner_id, "version": version}]
        )

    def mark_embeddings_failed(self, failed: list[dict[str, Any]]) -> None:
        if not failed:
            return
        cypher = """
        UNWIND $failed AS f
        MATCH (e:Event {id: f.id})
        WHERE (f.owner_id IS NULL OR e.owner_id = f.owner_id)
          AND (f.version IS NULL OR e.version = f.version)
        SET e.embedding_status = 'failed',
            e.embedding_error = f.error,
            e.embedding_retries = coalesce(e.embedding_retries, 0) + 1,
            e.last_failed_at = timestamp()
        """
        with self.driver.session(database=self.database) as session:
            session.run(cypher, parameters={"failed": failed}).consume()

    def index_status(self, owner_id: str | None = None) -> dict[str, int]:
        active_revision = getattr(self.embedder, "revision", E5_REVISION)
        cypher = """
        MATCH (e:Event)
        WHERE ($owner_id IS NULL OR e.owner_id = $owner_id)
        RETURN
          count(CASE WHEN (
              coalesce(e.embedding_status, 'pending') = 'pending'
              OR (
                  e.embedding_status = 'completed'
                  AND (
                      coalesce(e.embedded_version, 0) <> e.version
                      OR e.embedding IS NULL
                      OR coalesce(e.embedding_model_revision, '') <> $active_revision
                  )
              )
          ) AND e.embedding_status <> 'failed' THEN 1 END) AS pending,
          count(CASE WHEN e.embedding_status = 'completed' AND e.embedding IS NOT NULL AND coalesce(e.embedded_version, 0) = e.version AND coalesce(e.embedding_model_revision, '') = $active_revision THEN 1 END) AS ready,
          count(CASE WHEN e.embedding_status = 'failed' THEN 1 END) AS failed
        """
        with self.driver.session(database=self.database) as session:
            row = session.run(
                cypher, parameters={"owner_id": owner_id, "active_revision": active_revision}
            ).single()
            if row:
                return {
                    "pending": int(row["pending"] or 0),
                    "ready": int(row["ready"] or 0),
                    "failed": int(row["failed"] or 0),
                }
            return {"pending": 0, "ready": 0, "failed": 0}

    def rebuild(self, owner_id: str | None = None) -> None:
        cypher = """
        MATCH (e:Event)
        WHERE ($owner_id IS NULL OR e.owner_id = $owner_id)
        SET e.embedding = NULL,
            e.embedded_version = 0,
            e.embedding_status = 'pending',
            e.embedding_retries = 0,
            e.embedding_error = NULL,
            e.last_failed_at = NULL
        """
        with self.driver.session(database=self.database) as session:
            session.run(cypher, parameters={"owner_id": owner_id}).consume()
