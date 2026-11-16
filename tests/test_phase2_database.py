import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.store import Neo4jStore


@pytest.mark.skipif(os.getenv("TRAVELMEMO_INTEGRATION") != "1", reason="Local Neo4j opt-in")
def test_real_graph_edges_isolation_and_restart():
    settings = Settings()
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.app_env == "development"
    email = f"graph-{uuid4().hex}@example.com"
    settings.allowed_emails = email
    sent = []
    with TestClient(create_app(settings, sender=lambda email, code: sent.append(code))) as client:
        client.post("/api/v1/auth/request-code", json={"email": email})
        login = client.post(
            "/api/v1/auth/verify-code", json={"email": email, "code": sent[-1]}
        ).json()
        client.headers["X-CSRF-Token"] = login["csrf_token"]
        trip = client.post(
            "/api/v1/trips",
            json={
                "name": "Graph test",
                "start_date": "2026-10-01",
                "end_date": "2026-10-03",
                "timezone": "Asia/Tokyo",
                "description": "",
            },
        ).json()
        url = "/api/v1/trips/" + trip["id"]
        data = {
            "place_name": "Station",
            "city": "Tokyo",
            "address": "",
            "category": "Station",
            "date": "2026-10-01",
            "time": None,
            "notes": "",
        }
        first = client.post(url + "/events", json=data).json()
        second = client.post(
            url + "/events", json={**data, "place_id": first["place_id"], "date": "2026-10-02"}
        ).json()
        assert client.get(url).json()["next_edges"] == [
            {"from_id": first["id"], "to_id": second["id"]}
        ]
        cookie = client.cookies.get("travelmemo_session")

    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.set("travelmemo_session", cookie)
        restarted.headers["X-CSRF-Token"] = login["csrf_token"]
        detail = restarted.get(url).json()
        assert [e["id"] for e in detail["events"]] == [first["id"], second["id"]]
        store = Neo4jStore(settings)
        try:
            with store.driver.session(database=store.database) as session:
                count = session.run(
                    "MATCH (a:Event)-[:NEXT]->(b:Event) "
                    "WHERE a.id=$a AND b.id=$b RETURN count(*) AS n",
                    a=first["id"],
                    b=second["id"],
                ).single()["n"]
                assert count == 1
                places = session.run(
                    "MATCH (e:Event)-[:AT]->(p:Place) "
                    "WHERE e.id IN $ids RETURN count(DISTINCT p) AS n",
                    ids=[first["id"], second["id"]],
                ).single()["n"]
                assert places == 1
        finally:
            store.close()
        assert (
            restarted.delete(url, params={"version": detail["trip"]["version"]}).status_code == 204
        )
        assert restarted.get(url).status_code == 404
