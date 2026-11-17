"""HTTP-level photo lifecycle with synthetic images and offline AI dependencies."""

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.config import Settings
from backend.llm import MockLLM
from backend.store import MemoryStore


class Embedder:
    revision = "synthetic"

    def encode_query(self, text):
        return [1.0] + [0.0] * 383

    def encode_passages(self, texts):
        return [self.encode_query(text) for text in texts]


class Analyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, path, question=""):
        self.calls += 1
        return {"summary": "A synthetic green tea cafe sign", "visible_text": ["GREEN TEA"],
                "tags": ["cafe", "tea"], "place_candidates": [], "date_candidate": None,
                "uncertainties": [], "safety": {"decision": "allow", "reason": "safe"}}


def test_http_image_to_album_search_chat_and_shared_attachment_deletion(tmp_path):
    settings = Settings(_env_file=None, session_secret="x" * 48,
                        allowed_emails="owner@example.com,friend@example.com",
                        smtp_host="localhost", media_root=str(tmp_path / "media"))
    codes = []
    llm = MockLLM()
    analyzer = Analyzer()
    app = create_app(settings, MemoryStore(), sender=lambda email, code: codes.append(code),
                     llm=llm, embedder=Embedder(), photo_analyzer=analyzer)
    image = BytesIO()
    Image.new("RGB", (600, 400), "green").save(image, "PNG")
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/request-code", json={"email": "owner@example.com"}).status_code == 202
        auth = client.post("/api/v1/auth/verify-code", json={"email": "owner@example.com", "code": codes[-1]}).json()
        headers = {"X-CSRF-Token": auth["csrf_token"]}
        trip = client.post("/api/v1/trips", json={"name": "Synthetic trip", "start_date": "2026-01-01",
                            "end_date": "2026-01-02", "timezone": "Asia/Taipei"}, headers=headers).json()
        response = client.post("/api/v1/photos", content=image.getvalue(), headers={**headers, "Content-Type": "image/png"})
        assert response.status_code == 201, response.text
        photo = response.json()
        assert "stored_path" not in photo and "owner_id" not in photo
        assert photo["status"] == "pending"
        assert client.get(photo["url"]).headers["content-type"].startswith("image/webp")
        assert app.state.photo_worker.process_pending() == 1
        before = client.post("/api/v1/search", json={"query": "green tea"}, headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["photo_items"] == []  # Unbound photos are not travel records.
        response = client.post(f"/api/v1/photos/{photo['id']}/bindings", json={"kind": "trip", "target_id": trip["id"]}, headers=headers)
        assert response.status_code == 200, response.text
        record = app.state.photos.store.get(auth["user"]["id"], photo["id"])
        assert record["embedding_version"] == record["version"]
        updated = client.patch(f"/api/v1/photos/{photo['id']}", json={"version": record["version"], "caption": "Green tea by the river"}, headers=headers)
        assert updated.status_code == 200, updated.text
        app.state.photo_worker.process_pending()
        assert analyzer.calls == 1  # Caption edits reuse visual analysis.
        response = client.post("/api/v1/search", json={"photo_ids": [photo["id"]]}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["photo_items"][0]["photo"]["id"] == photo["id"]
        assert response.json()["photo_items"][0]["event"] is None
        conversation = client.post("/api/v1/conversations", json={}, headers=headers).json()
        llm.default_answer_scope = "image"
        llm.default_cited_photo_ids = [photo["id"]]
        llm.default_content = "The image shows a green tea sign."
        response = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                               json={"photo_ids": [photo["id"]]}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["photo_citations"][0]["photo_id"] == photo["id"]
        history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()["items"]
        assert history[0]["photos"][0]["id"] == photo["id"]
        with TestClient(app) as other:
            other.post("/api/v1/auth/request-code", json={"email": "friend@example.com"})
            other_auth = other.post("/api/v1/auth/verify-code", json={"email": "friend@example.com", "code": codes[-1]}).json()
            other_headers = {"X-CSRF-Token": other_auth["csrf_token"]}
            assert other.get(photo["url"]).status_code == 404
            assert other.get(f"/api/v1/photos/{photo['id']}").status_code == 404
            assert other.post("/api/v1/search", json={"photo_ids": [photo["id"]]}, headers=other_headers).status_code == 404
            assert other.get(f"/api/v1/conversations/{conversation['id']}/messages").status_code == 404
        assert client.delete(f"/api/v1/conversations/{conversation['id']}", headers=headers).status_code == 204
        assert client.get(photo["url"]).status_code == 200  # Album still owns a reference.
        assert client.delete(f"/api/v1/trips/{trip['id']}?version={trip['version']}", headers=headers).status_code == 204
        assert client.get(photo["url"]).status_code == 404
    assert not list((tmp_path / "media").rglob("*.webp"))
