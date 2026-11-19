"""Durable, owner-scoped chat requests for a single API process."""

import asyncio
import copy
import datetime
import json
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.auth import AuthError
from backend.conversation import Message, MessageCreate
from backend.conversation_store import CURRENT_CHAT_REQUEST
from backend.dependencies import authenticate

logger = logging.getLogger(__name__)


class RequestCreate(MessageCreate):
    request_id: UUID


class RequestStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    conversation_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: str
    updated_at: str
    message: Message | None = None
    error: str | None = None


class RequestList(BaseModel):
    items: list[RequestStatus]


class ChatRequestStore:
    def __init__(self, conversations):
        self.conversations = conversations
        self.driver = getattr(conversations, "driver", None)
        self.database = getattr(conversations, "database", "neo4j")
        if self.driver is None:
            if not hasattr(conversations, "chat_jobs"):
                conversations.chat_jobs = {}
            self.jobs = conversations.chat_jobs
            self.lock = conversations.lock

    def initialize(self):
        if self.driver is None:
            with self.lock:
                for record in self.jobs.values():
                    if record["status"] == "running":
                        record["status"] = "queued"
            return
        with self.driver.session(database=self.database) as session:
            session.run("CREATE CONSTRAINT chat_request_key IF NOT EXISTS FOR (j:ChatRequest) REQUIRE j.key IS UNIQUE").consume()
            session.run("CREATE INDEX chat_request_status IF NOT EXISTS FOR (j:ChatRequest) ON (j.status)").consume()
            session.run("MATCH (j:ChatRequest {status:'running'}) SET j.status='queued'").consume()

    def get(self, owner, cid, rid):
        if self.driver is None:
            with self.lock:
                return copy.deepcopy(self.jobs.get((owner, cid, rid)))
        with self.driver.session(database=self.database) as session:
            row = session.run(
                "MATCH (:Conversation {id:$cid,owner_id:$owner})-[:HAS_REQUEST]->(j:ChatRequest {id:$rid,owner_id:$owner}) RETURN properties(j) AS j",
                cid=cid, owner=owner, rid=rid,
            ).single()
            return dict(row["j"]) if row else None

    def create(self, record):
        owner, cid, rid = record["owner_id"], record["conversation_id"], record["id"]
        if self.driver is None:
            with self.lock:
                conversation = self.conversations.conversations.get(cid)
                if not conversation or conversation["owner_id"] != owner:
                    raise HTTPException(404, "找不到指定的對話。")
                key = (owner, cid, rid)
                if key in self.jobs:
                    return copy.deepcopy(self.jobs[key])
                pending = sum(j["owner_id"] == owner and j["status"] in ("queued", "running") for j in self.jobs.values())
                if pending >= 8:
                    raise HTTPException(429, "仍有多筆問題等待處理，請稍候。")
                self.jobs[key] = copy.deepcopy(record)
                return copy.deepcopy(record)
        with self.driver.session(database=self.database) as session, session.begin_transaction() as tx:
            # A conversation lock serializes duplicate submissions from multiple tabs.
            conv = tx.run("MATCH (c:Conversation {id:$cid,owner_id:$owner}) MERGE (u:User {id:$owner}) SET u.chat_request_lock=coalesce(u.chat_request_lock,0)+1 RETURN c.id AS id", cid=cid, owner=owner).single()
            if not conv:
                raise HTTPException(404, "找不到指定的對話。")
            row = tx.run("MATCH (j:ChatRequest {key:$key}) RETURN properties(j) AS j", key=record["key"]).single()
            if row:
                return dict(row["j"])
            count = tx.run("MATCH (j:ChatRequest {owner_id:$owner}) WHERE j.status IN ['queued','running'] RETURN count(j) AS n", owner=owner).single()["n"]
            if count >= 8:
                raise HTTPException(429, "仍有多筆問題等待處理，請稍候。")
            tx.run("MATCH (c:Conversation {id:$cid,owner_id:$owner}) CREATE (j:ChatRequest) SET j=$record CREATE (c)-[:HAS_REQUEST]->(j)", cid=cid, owner=owner, record=record).consume()
            tx.commit()
            return copy.deepcopy(record)

    def list(self, owner=None, cid=None, pending=False):
        if self.driver is None:
            with self.lock:
                records = [copy.deepcopy(j) for j in self.jobs.values()
                           if (owner is None or j["owner_id"] == owner)
                           and (cid is None or j["conversation_id"] == cid)
                           and (not pending or j["status"] == "queued")]
            records.sort(key=lambda j: (j["created_at"], j["id"]), reverse=not pending)
            if not pending:
                records.sort(key=lambda j: j["status"] not in ("queued", "running"))
            return records[:100]
        with self.driver.session(database=self.database) as session:
            ordering = "j.created_at ASC,j.id ASC" if pending else "CASE WHEN j.status IN ['queued','running'] THEN 0 ELSE 1 END ASC,j.created_at DESC,j.id DESC"
            result = session.run("""
                MATCH (c:Conversation)-[:HAS_REQUEST]->(j:ChatRequest)
                WHERE c.owner_id=j.owner_id AND ($owner IS NULL OR j.owner_id=$owner)
                  AND ($cid IS NULL OR c.id=$cid) AND (NOT $pending OR j.status='queued')
                RETURN properties(j) AS j ORDER BY """ + ordering + " LIMIT 100", owner=owner, cid=cid, pending=pending)
            return [dict(r["j"]) for r in result]

    def update(self, record, status, **extra):
        if self.driver is None:
            with self.lock:
                current = self.jobs.get((record["owner_id"], record["conversation_id"], record["id"]))
                if not current or (status == "running" and current["status"] != "queued"):
                    return False
                current.update(status=status, updated_at=_now(), **extra)
                return True
        with self.driver.session(database=self.database) as session:
            row = session.run("""
                MATCH (:Conversation {id:$cid,owner_id:$owner})-[:HAS_REQUEST]->(j:ChatRequest {key:$key})
                WHERE $status <> 'running' OR j.status='queued'
                SET j.status=$status,j.updated_at=$now,j += $extra RETURN j.id AS id
                """, cid=record["conversation_id"], owner=record["owner_id"], key=record["key"],
                status=status, now=_now(), extra=extra).single()
            return row is not None


def _now():
    return datetime.datetime.now(datetime.UTC).isoformat()


class ChatJobService:
    def __init__(self, conversations):
        self.conversations = conversations
        self.store = ChatRequestStore(conversations.store)
        self.task = None
        self.stopping = False

    def initialize(self):
        self.store.initialize()

    def _conversation(self, owner, cid):
        if not self.conversations.store.get_conversation(owner, cid):
            raise HTTPException(404, "找不到指定的對話。")

    def _dto(self, record, message_map=None):
        message = None
        if record.get("message_id"):
            if message_map is None:
                messages = self.conversations.get_messages(record["owner_id"], record["conversation_id"]) or []
                message_map = {m["id"]: m for m in messages}
            message = message_map.get(record["message_id"])
        return {k: record.get(k) for k in ("id", "conversation_id", "status", "created_at", "updated_at", "error")} | {"message": message}

    def enqueue(self, owner, cid, rid, payload):
        self._conversation(owner, cid)
        try:
            rid = str(UUID(rid))
        except (ValueError, TypeError):
            raise HTTPException(422, "請求識別碼格式不正確。") from None
        payload = MessageCreate.model_validate(payload).model_dump()
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        previous = self.store.get(owner, cid, rid)
        if previous:
            if previous["payload"] != encoded:
                raise HTTPException(409, "此請求識別碼已用於另一則問題。")
            return self._dto(previous)
        if payload["photo_ids"]:
            if not self.conversations.photo_service:
                raise HTTPException(400, "照片服務未啟用。")
            self.conversations.photo_service.ready_evidence(owner, payload["photo_ids"])
        now = _now()
        record = self.store.create({"key": f"{owner}:{cid}:{rid}", "id": rid, "owner_id": owner,
                                        "conversation_id": cid, "payload": encoded, "status": "queued",
                                        "created_at": now, "updated_at": now})
        if record["payload"] != encoded:
            raise HTTPException(409, "此請求識別碼已用於另一則問題。")
        return self._dto(record)

    def get(self, owner, cid, rid):
        self._conversation(owner, cid)
        record = self.store.get(owner, cid, rid)
        if not record:
            raise HTTPException(404, "找不到指定的請求。")
        return self._dto(record)

    def list(self, owner, cid):
        self._conversation(owner, cid)
        # Recent requests are sufficient for recovery; terminal history lives in messages.
        records = self.store.list(owner, cid)[:30]
        messages = self.conversations.get_messages(owner, cid) if any(r.get("message_id") for r in records) else []
        message_map = {m["id"]: m for m in messages or []}
        return [self._dto(r, message_map) for r in records]

    def _process(self, record):
        if not self.store.update(record, "running"):
            return
        owner, cid, rid = record["owner_id"], record["conversation_id"], record["id"]
        context = CURRENT_CHAT_REQUEST.set(rid)
        try:
            messages = self.conversations.store.get_messages(owner, cid) or []
            committed = next((m for m in messages if m.get("request_id") == rid and m["role"] == "assistant"), None)
            if committed:
                answer = committed
            else:
                answer = self.conversations.post_message(owner, cid, **json.loads(record["payload"]))
            if answer:
                self.store.update(record, "completed", message_id=answer["id"], error=None)
            else:
                self.store.update(record, "failed", error="對話已不存在。")
        except HTTPException as exc:
            if exc.status_code == 429:
                self.store.update(record, "queued")
            else:
                self.store.update(record, "failed", error=str(exc.detail)[:200])
        except Exception as exc:  # noqa: BLE001 - job errors must not kill the queue
            logger.warning("Chat request failed: %s", type(exc).__name__)
            self.store.update(record, "failed", error="AI 回答暫時無法完成，請稍後重試。")
        finally:
            CURRENT_CHAT_REQUEST.reset(context)

    def process_pending(self):
        records = self.store.list(pending=True)
        for record in records:
            self._process(record)
        return len(records)

    async def _run(self):
        while not self.stopping:
            try:
                records = await asyncio.to_thread(self.store.list, pending=True)
                batch, owners = [], set()
                for record in records:
                    if record["owner_id"] not in owners:
                        owners.add(record["owner_id"])
                        batch.append(record)
                    if len(batch) >= self.conversations.global_concurrency:
                        break
                if batch:
                    await asyncio.gather(*(asyncio.to_thread(self._process, r) for r in batch))
                    await asyncio.sleep(0.25)
                else:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chat queue unavailable: %s", type(exc).__name__)
                await asyncio.sleep(2)

    async def start(self):
        self.stopping = False
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.stopping = True
        if self.task:
            # Finish any bounded model request; queued work stays persisted for restart.
            await self.task
            self.task = None


def create_chat_job_router(auth, jobs, prefix="/api/v1"):
    router = APIRouter(prefix=prefix)

    def owner(request, write=False):
        try:
            return authenticate(auth, request, write=write)
        except AuthError as exc:
            raise HTTPException(exc.status, exc.message) from None

    @router.post("/conversations/{id}/requests", response_model=RequestStatus, status_code=202)
    def enqueue(id: str, body: RequestCreate, request: Request):
        return jobs.enqueue(owner(request, True), id, str(body.request_id), body.model_dump(exclude={"request_id"}))

    @router.get("/conversations/{id}/requests", response_model=RequestList)
    def list_requests(id: str, request: Request):
        return {"items": jobs.list(owner(request), id)}

    @router.get("/conversations/{id}/requests/{request_id}", response_model=RequestStatus)
    def status(id: str, request_id: str, request: Request):
        return jobs.get(owner(request), id, request_id)

    return router
