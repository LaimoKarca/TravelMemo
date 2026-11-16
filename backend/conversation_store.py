"""Conversation and usage storage implementations (Memory and Neo4j)."""

import copy
import json
from threading import RLock
from typing import Any
from uuid import uuid4


class MemoryConversationStore:
    """In-memory thread-safe store for conversation history and usage tracking."""

    def __init__(self):
        self.conversations: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.usage: dict[tuple[str, str], dict[str, int]] = {}
        self.user_active: dict[str, int] = {}
        self.global_active: int = 0
        self.lock = RLock()

    def initialize(self) -> None:
        """No-op for in-memory store."""

    def create_conversation(
        self, owner_id: str, title: str | None = None, created_at: str | None = None
    ) -> dict[str, Any]:
        cid = str(uuid4())
        record = {
            "id": cid,
            "owner_id": owner_id,
            "title": title if title and title.strip() else "新對話",
            "created_at": created_at or "",
        }
        with self.lock:
            self.conversations[cid] = copy.deepcopy(record)
            self.messages[cid] = []
        return {
            "id": record["id"],
            "title": record["title"],
            "created_at": record["created_at"],
        }

    def list_conversations(self, owner_id: str) -> list[dict[str, Any]]:
        with self.lock:
            user_convs = [
                copy.deepcopy(c)
                for c in self.conversations.values()
                if c["owner_id"] == owner_id
            ]
        user_convs.sort(key=lambda c: c["created_at"], reverse=True)
        return [
            {"id": c["id"], "title": c["title"], "created_at": c["created_at"]}
            for c in user_convs
        ]

    def get_conversation(self, owner_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self.lock:
            conv = self.conversations.get(conversation_id)
            if not conv or conv["owner_id"] != owner_id:
                return None
            return {
                "id": conv["id"],
                "title": conv["title"],
                "created_at": conv["created_at"],
            }

    def delete_conversation(self, owner_id: str, conversation_id: str) -> bool:
        with self.lock:
            conv = self.conversations.get(conversation_id)
            if not conv or conv["owner_id"] != owner_id:
                return False
            del self.conversations[conversation_id]
            self.messages.pop(conversation_id, None)
            return True

    def add_message(
        self,
        owner_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "answered",
        citations: list[dict[str, Any]] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self.lock:
            conv = self.conversations.get(conversation_id)
            if not conv or conv["owner_id"] != owner_id:
                return None
            msg_id = str(uuid4())
            msg = {
                "id": msg_id,
                "conversation_id": conversation_id,
                "owner_id": owner_id,
                "role": role,
                "content": content,
                "status": status,
                "citations": copy.deepcopy(citations or []),
                "created_at": created_at or "",
            }
            self.messages.setdefault(conversation_id, []).append(msg)
            return {
                "id": msg["id"],
                "role": msg["role"],
                "content": msg["content"],
                "status": msg["status"],
                "citations": copy.deepcopy(msg["citations"]),
                "created_at": msg["created_at"],
            }

    def get_messages(
        self, owner_id: str, conversation_id: str
    ) -> list[dict[str, Any]] | None:
        with self.lock:
            conv = self.conversations.get(conversation_id)
            if not conv or conv["owner_id"] != owner_id:
                return None
            msgs = [
                copy.deepcopy(m)
                for m in self.messages.get(conversation_id, [])
            ]
        msgs.sort(key=lambda m: m["created_at"])
        return [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "status": m["status"],
                "citations": m["citations"],
                "created_at": m["created_at"],
            }
            for m in msgs
        ]

    def reserve_slot(
        self,
        owner_id: str,
        date_str: str,
        max_daily: int = 50,
        max_user_concurrent: int = 1,
        max_global_concurrent: int = 2,
    ) -> tuple[bool, str | None]:
        with self.lock:
            key = (owner_id, date_str)
            usage = self.usage.setdefault(
                key, {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            )
            if usage["requests"] >= max_daily:
                return False, f"今日對話請求次數已達上限 ({max_daily} 次)。"

            active_user = self.user_active.get(owner_id, 0)
            if active_user >= max_user_concurrent:
                return False, "已有進行中的對話請求，請稍候。"

            if self.global_active >= max_global_concurrent:
                return False, "全站對話請求繁忙，請稍後再試。"

            usage["requests"] += 1
            self.user_active[owner_id] = active_user + 1
            self.global_active += 1
            return True, None

    def release_slot(self, owner_id: str) -> None:
        with self.lock:
            if self.user_active.get(owner_id, 0) > 0:
                self.user_active[owner_id] -= 1
            if self.global_active > 0:
                self.global_active -= 1

    def record_tokens(
        self, owner_id: str, date_str: str, input_tokens: int, output_tokens: int
    ) -> None:
        with self.lock:
            key = (owner_id, date_str)
            usage = self.usage.setdefault(
                key, {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            )
            usage["input_tokens"] += input_tokens
            usage["output_tokens"] += output_tokens

    def get_usage(self, owner_id: str, date_str: str) -> dict[str, int]:
        with self.lock:
            key = (owner_id, date_str)
            usage = self.usage.get(
                key, {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            )
            return copy.deepcopy(usage)


class Neo4jConversationStore:
    """Neo4j persistent store for conversation history and usage tracking."""

    def __init__(self, driver: Any, database: str = "neo4j"):
        self.driver = driver
        self.database = database
        self.user_active: dict[str, int] = {}
        self.global_active: int = 0
        self.lock = RLock()

    def initialize(self) -> None:
        with self.driver.session(database=self.database) as session:
            session.run(
                "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (c:Conversation) REQUIRE c.id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT conv_usage_key IF NOT EXISTS FOR (u:ConversationUsage) REQUIRE u.key IS UNIQUE"
            ).consume()
            session.run(
                "CREATE INDEX conversation_owner IF NOT EXISTS FOR (c:Conversation) ON (c.owner_id)"
            ).consume()
            session.run(
                "CREATE INDEX message_conversation IF NOT EXISTS FOR (m:Message) ON (m.conversation_id)"
            ).consume()

    def create_conversation(
        self, owner_id: str, title: str | None = None, created_at: str | None = None
    ) -> dict[str, Any]:
        cid = str(uuid4())
        norm_title = title if title and title.strip() else "新對話"
        created_at_val = created_at or ""
        with self.driver.session(database=self.database) as session:
            session.run(
                """
                CREATE (c:Conversation {
                    id: $id,
                    owner_id: $owner_id,
                    title: $title,
                    created_at: $created_at
                })
                """,
                id=cid,
                owner_id=owner_id,
                title=norm_title,
                created_at=created_at_val,
            ).consume()
        return {
            "id": cid,
            "title": norm_title,
            "created_at": created_at_val,
        }

    def list_conversations(self, owner_id: str) -> list[dict[str, Any]]:
        with self.driver.session(database=self.database) as session:
            result = session.run(
                """
                MATCH (c:Conversation {owner_id: $owner_id})
                RETURN c.id AS id, c.title AS title, c.created_at AS created_at
                ORDER BY c.created_at DESC
                """,
                owner_id=owner_id,
            )
            return [
                {"id": r["id"], "title": r["title"], "created_at": r["created_at"]}
                for r in result
            ]

    def get_conversation(self, owner_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self.driver.session(database=self.database) as session:
            record = session.run(
                """
                MATCH (c:Conversation {id: $id, owner_id: $owner_id})
                RETURN c.id AS id, c.title AS title, c.created_at AS created_at
                """,
                id=conversation_id,
                owner_id=owner_id,
            ).single()
            if not record:
                return None
            return {
                "id": record["id"],
                "title": record["title"],
                "created_at": record["created_at"],
            }

    def delete_conversation(self, owner_id: str, conversation_id: str) -> bool:
        with self.driver.session(database=self.database) as session:
            record = session.run(
                """
                MATCH (c:Conversation {id: $id, owner_id: $owner_id})
                OPTIONAL MATCH (c)-[:HAS_MESSAGE]->(m:Message)
                DETACH DELETE c, m
                RETURN count(c) AS deleted
                """,
                id=conversation_id,
                owner_id=owner_id,
            ).single()
            return bool(record and record["deleted"] > 0)

    def add_message(
        self,
        owner_id: str,
        conversation_id: str,
        role: str,
        content: str,
        status: str = "answered",
        citations: list[dict[str, Any]] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any] | None:
        msg_id = str(uuid4())
        created_at_val = created_at or ""
        citations_json = json.dumps(citations or [])
        with self.driver.session(database=self.database) as session:
            record = session.run(
                """
                MATCH (c:Conversation {id: $conversation_id, owner_id: $owner_id})
                CREATE (m:Message {
                    id: $id,
                    conversation_id: $conversation_id,
                    owner_id: $owner_id,
                    role: $role,
                    content: $content,
                    status: $status,
                    citations: $citations,
                    created_at: $created_at
                })
                CREATE (c)-[:HAS_MESSAGE]->(m)
                RETURN m.id AS id
                """,
                id=msg_id,
                conversation_id=conversation_id,
                owner_id=owner_id,
                role=role,
                content=content,
                status=status,
                citations=citations_json,
                created_at=created_at_val,
            ).single()
            if not record:
                return None
            return {
                "id": msg_id,
                "role": role,
                "content": content,
                "status": status,
                "citations": copy.deepcopy(citations or []),
                "created_at": created_at_val,
            }

    def get_messages(
        self, owner_id: str, conversation_id: str
    ) -> list[dict[str, Any]] | None:
        with self.driver.session(database=self.database) as session:
            conv = session.run(
                """
                MATCH (c:Conversation {id: $conversation_id, owner_id: $owner_id})
                RETURN c.id AS id
                """,
                conversation_id=conversation_id,
                owner_id=owner_id,
            ).single()
            if not conv:
                return None

            result = session.run(
                """
                MATCH (c:Conversation {id: $conversation_id, owner_id: $owner_id})-[:HAS_MESSAGE]->(m:Message)
                RETURN m.id AS id, m.role AS role, m.content AS content, m.status AS status,
                       m.citations AS citations, m.created_at AS created_at
                ORDER BY m.created_at ASC
                """,
                conversation_id=conversation_id,
                owner_id=owner_id,
            )
            messages = []
            for r in result:
                citations_raw = r["citations"]
                parsed_citations = json.loads(citations_raw) if citations_raw else []
                messages.append(
                    {
                        "id": r["id"],
                        "role": r["role"],
                        "content": r["content"],
                        "status": r["status"],
                        "citations": parsed_citations,
                        "created_at": r["created_at"],
                    }
                )
            return messages

    def reserve_slot(
        self,
        owner_id: str,
        date_str: str,
        max_daily: int = 50,
        max_user_concurrent: int = 1,
        max_global_concurrent: int = 2,
    ) -> tuple[bool, str | None]:
        with self.lock:
            active_user = self.user_active.get(owner_id, 0)
            if active_user >= max_user_concurrent:
                return False, "已有進行中的對話請求，請稍候。"

            if self.global_active >= max_global_concurrent:
                return False, "全站對話請求繁忙，請稍後再試。"

            key = f"{owner_id}:{date_str}"

            def _increment_tx(tx):
                record = tx.run(
                    """
                    MERGE (u:ConversationUsage {key: $key})
                    ON CREATE SET u.owner_id = $owner_id, u.date = $date,
                                  u.requests = 0, u.input_tokens = 0, u.output_tokens = 0
                    WITH u
                    WHERE u.requests < $max_daily
                    SET u.requests = u.requests + 1
                    RETURN u.requests AS requests
                    """,
                    key=key,
                    owner_id=owner_id,
                    date=date_str,
                    max_daily=max_daily,
                ).single()
                return bool(record)

            with self.driver.session(database=self.database) as session:
                ok = session.execute_write(_increment_tx)
                if not ok:
                    return False, f"今日對話請求次數已達上限 ({max_daily} 次)。"

            self.user_active[owner_id] = active_user + 1
            self.global_active += 1
            return True, None

    def release_slot(self, owner_id: str) -> None:
        with self.lock:
            if self.user_active.get(owner_id, 0) > 0:
                self.user_active[owner_id] -= 1
            if self.global_active > 0:
                self.global_active -= 1

    def record_tokens(
        self, owner_id: str, date_str: str, input_tokens: int, output_tokens: int
    ) -> None:
        key = f"{owner_id}:{date_str}"

        def _record_tx(tx):
            tx.run(
                """
                MERGE (u:ConversationUsage {key: $key})
                ON CREATE SET u.owner_id = $owner_id, u.date = $date,
                              u.requests = 0, u.input_tokens = $in_tok, u.output_tokens = $out_tok
                ON MATCH SET u.input_tokens = coalesce(u.input_tokens, 0) + $in_tok,
                             u.output_tokens = coalesce(u.output_tokens, 0) + $out_tok
                """,
                key=key,
                owner_id=owner_id,
                date=date_str,
                in_tok=input_tokens,
                out_tok=output_tokens,
            ).consume()

        with self.driver.session(database=self.database) as session:
            session.execute_write(_record_tx)

    def get_usage(self, owner_id: str, date_str: str) -> dict[str, int]:
        key = f"{owner_id}:{date_str}"
        with self.driver.session(database=self.database) as session:
            record = session.run(
                """
                MATCH (u:ConversationUsage {key: $key})
                RETURN u.requests AS requests, u.input_tokens AS input_tokens, u.output_tokens AS output_tokens
                """,
                key=key,
            ).single()
            if not record:
                return {"requests": 0, "input_tokens": 0, "output_tokens": 0}
            return {
                "requests": record["requests"] or 0,
                "input_tokens": record["input_tokens"] or 0,
                "output_tokens": record["output_tokens"] or 0,
            }
