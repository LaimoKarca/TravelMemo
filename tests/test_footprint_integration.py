"""Application-level assistant workflow with synthetic travel facts only."""
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.store import MemoryStore


class Generator:
    def generate(self, trip, record_date, text):
        return {"decision": "allow", "too_many_events": False, "items": [
            {"place_name": "Synthetic river", "date": record_date, "time": None,
             "category": "景點", "city": "", "address": "", "notes": note}
            for note in ("First visit", "Explicit second visit")
        ]}


def test_full_app_generate_confirm_replay_and_delete_draft():
    settings = Settings(_env_file=None, session_secret="x" * 48, allowed_emails="owner@example.com",
                        smtp_host="localhost")
    codes = []
    app = create_app(settings, MemoryStore(), sender=lambda _, code: codes.append(code),
                     footprint_generator=Generator())
    with TestClient(app) as client:
        client.post('/api/v1/auth/request-code', json={'email': 'owner@example.com'})
        login = client.post('/api/v1/auth/verify-code', json={'email': 'owner@example.com', 'code': codes[-1]}).json()
        headers = {'X-CSRF-Token': login['csrf_token']}
        trip = client.post('/api/v1/trips', headers=headers, json={'name': 'Synthetic trip', 'start_date': '2026-01-01', 'end_date': '2026-01-03'}).json()
        root = f'/api/v1/trips/{trip["id"]}'
        created = client.post(root + '/footprint-drafts', headers=headers, json={'record_date': '2026-01-02', 'text': 'First and second river visits'})
        assert created.status_code == 201, created.text
        draft = created.json()
        assert 'owner_id' not in draft
        path = root + '/footprint-drafts/' + draft['id']
        queued = client.post(path + '/generate', headers=headers, json={'version': draft['version'], 'request_id': str(uuid4())})
        assert queued.status_code == 202, queued.text
        for _ in range(30):
            draft = client.get(path).json()
            if draft['status'] == 'ready':
                break
            time.sleep(.05)
        assert draft['status'] == 'ready', draft
        assert len(draft['items']) == 2
        assert client.get(root).json()['events'] == []
        body = {'version': draft['version'], 'trip_version': trip['version'], 'request_id': str(uuid4())}
        committed = client.post(path + '/commit', headers=headers, json=body)
        assert committed.status_code == 200, committed.text
        retry = client.post(path + '/commit', headers=headers, json=body)
        assert retry.status_code == 200, retry.text
        assert [e['id'] for e in retry.json()['events']] == [e['id'] for e in committed.json()['events']]
        detail = client.get(root).json()
        assert len(detail['events']) == 2
        assert detail['events'][0]['place_id'] != detail['events'][1]['place_id']
        assert len(detail['next_edges']) == 1
        assert detail['trip']['version'] == trip['version'] + 1
        assert client.delete(root + '?version=' + str(detail['trip']['version']), headers=headers).status_code == 204
        assert client.get(path).status_code == 404
        assert app.state.footprints.store.records == {}
