"""Atomic auth storage. Memory implementation is injected by tests only."""

import copy
import json
from contextlib import contextmanager
from threading import RLock

from neo4j import GraphDatabase


class MemoryStore:
    def __init__(self):
        self.records = {}
        self.lock = RLock()

    @contextmanager
    def atomic(self):
        with self.lock:
            before = copy.deepcopy(self.records)
            try:
                yield self
            except Exception:
                self.records = before
                raise

    def get(self, key):
        return copy.deepcopy(self.records.get(key))

    def put(self, key, value):
        self.records[key] = copy.deepcopy(value)

    def delete(self, key):
        self.records.pop(key, None)

    def user(self, user_id, email):
        self.put("user:" + user_id, {"id": user_id, "email": email})

    def ping(self):
        return True

    def close(self):
        pass


class Neo4jTransaction:
    def __init__(self, tx):
        self.tx = tx

    def get(self, key):
        record = self.tx.run(
            "MATCH (r:AuthRecord {key:$key}) RETURN r.payload AS payload", key=key
        ).single()
        return json.loads(record["payload"]) if record else None

    def put(self, key, value):
        self.tx.run(
            "MERGE (r:AuthRecord {key:$key}) SET r.payload=$payload, r.expires_at=$expires_at",
            key=key,
            payload=json.dumps(value),
            expires_at=value.get("expires_at"),
        ).consume()

    def delete(self, key):
        self.tx.run("MATCH (r:AuthRecord {key:$key}) DELETE r", key=key).consume()

    def user(self, user_id, email):
        self.tx.run(
            "MERGE (u:User {id:$id}) ON CREATE SET u.email=$email, u.created_at=datetime()",
            id=user_id,
            email=email,
        ).consume()


class Neo4jStore:
    def __init__(self, settings):
        self.database = settings.neo4j_database
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=5,
            notifications_min_severity="OFF",
        )

    def initialize(self):
        with self.driver.session(database=self.database) as session:
            for label, prop in [
                ("User", "id"),
                ("User", "email"),
                ("AuthRecord", "key"),
                ("AuthLock", "name"),
            ]:
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                ).consume()

    @contextmanager
    def atomic(self):
        with (
            self.driver.session(database=self.database) as session,
            session.begin_transaction() as tx,
        ):
            # A small shared lock serializes login state across processes/restarts.
            tx.run(
                "MERGE (l:AuthLock {name:'auth'}) SET l.version=coalesce(l.version,0)+1"
            ).consume()
            yield Neo4jTransaction(tx)
            tx.commit()

    def cleanup(self, now):
        with self.driver.session(database=self.database) as session:
            session.run(
                "MATCH (r:AuthRecord) WHERE r.expires_at < $now DELETE r", now=now
            ).consume()

    def ping(self):
        with self.driver.session(database=self.database) as session:
            session.run("RETURN 1").consume()
        return True

    def close(self):
        self.driver.close()
