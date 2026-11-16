"""Opt-in real Neo4j + SMTP checks against the local development containers."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import AuthError, AuthService
from backend.config import Settings
from backend.mail import smtp_sender
from backend.store import Neo4jStore


@pytest.mark.skipif(os.getenv("TRAVELMEMO_INTEGRATION") != "1", reason="Local containers opt-in")
def test_real_database_smtp_restart_and_atomic_use():
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.smtp_host == "localhost" and settings.smtp_port == 1025
    email = f"test-{uuid4().hex}@example.com"
    settings.allowed_emails = email
    store = Neo4jStore(settings)
    store.initialize()
    auth = AuthService(settings, store, smtp_sender(settings))
    try:
        auth.request_code(email, "integration")
        messages = httpx.get("http://localhost:8025/api/v1/messages").json()["messages"]
        message = next(m for m in messages if any(t["Address"] == email for t in m["To"]))
        content = httpx.get(f"http://localhost:8025/api/v1/message/{message['ID']}").json()
        code = re.search(r"\b\d{6}\b", content["Text"]).group()

        def consume():
            try:
                return auth.verify(email, code, "integration")
            except AuthError as exc:
                return exc.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        successes = [r for r in results if isinstance(r, tuple)]
        assert len(successes) == 1
        assert results.count(401) == 1
        token, user, csrf = successes[0]
    finally:
        store.close()

    # New driver and app instance must retain the session after a process restart.
    replacement = Neo4jStore(settings)
    try:
        with TestClient(create_app(settings, replacement)) as client:
            client.cookies.set("travelmemo_session", token)
            assert client.get("/api/v1/auth/me").json()["user"] == user
            assert (
                client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code
                == 204
            )
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        replacement.close()
