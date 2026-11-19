from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.chat_jobs import ChatJobService
from backend.conversation import ConversationService
from backend.conversation_store import MemoryConversationStore
from backend.llm import MockLLM


def service():
    store = MemoryConversationStore()
    search = SimpleNamespace(search=lambda **kw: {'items': []}, get_event=lambda *a: None)
    conversations = ConversationService(SimpleNamespace(), search, store, llm=MockLLM())
    conv = conversations.create_conversation('owner')
    jobs = ChatJobService(conversations)
    jobs.initialize()
    return conversations, conv['id'], jobs


def test_idempotent_pollable_request_survives_recovery_without_duplicate_history():
    conversations, cid, jobs = service()
    rid = str(uuid4())
    request = jobs.enqueue('owner', cid, rid, {'content': '你好'})
    assert request['status'] == 'queued'
    assert jobs.enqueue('owner', cid, rid, {'content': '你好'})['id'] == rid
    with pytest.raises(HTTPException) as exc:
        jobs.enqueue('owner', cid, rid, {'content': 'Different'})
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        jobs.get('friend', cid, rid)
    assert exc.value.status_code == 404
    jobs.process_pending()
    done = jobs.get('owner', cid, rid)
    assert done['status'] == 'completed'
    assert done['message']['answer_scope'] == 'general'
    jobs.initialize()
    jobs.process_pending()
    assert len(conversations.get_messages('owner', cid)) == 2
    assert jobs.get('owner', cid, rid)['message']['id'] == done['message']['id']


def test_interrupted_job_recovers_existing_assistant_without_model_replay():
    conversations, cid, jobs = service()
    rid = str(uuid4())
    jobs.enqueue('owner', cid, rid, {'content': '你好'})
    jobs.process_pending()
    jobs.store.jobs[('owner', cid, rid)]['status'] = 'running'
    conversations.post_message = lambda *a, **kw: pytest.fail('Must reuse committed answer')
    jobs.initialize()
    jobs.process_pending()
    assert jobs.get('owner', cid, rid)['status'] == 'completed'


def test_recovery_list_includes_latest_requests_after_more_than_hundred_messages():
    _, cid, jobs = service()
    newest = None
    for _ in range(105):
        newest = str(uuid4())
        jobs.enqueue('owner', cid, newest, {'content': '你好'})
        jobs.process_pending()
    pending = str(uuid4())
    jobs.enqueue('owner', cid, pending, {'content': '你好'})
    items = jobs.list('owner', cid)
    assert len(items) == 30
    assert items[0]['id'] == pending
    assert newest in {r['id'] for r in items}


def test_deleting_conversation_removes_queued_requests_and_cannot_resurrect_history():
    conversations, cid, jobs = service()
    jobs.enqueue('owner', cid, str(uuid4()), {'content': '你好'})
    conversations.delete_conversation('owner', cid)
    assert jobs.process_pending() == 0
    assert conversations.store.get_messages('owner', cid) is None


def test_deleting_conversation_between_enqueue_check_and_insert_does_not_leave_private_job():
    conversations, cid, jobs = service()
    create = jobs.store.create

    def delete_before_insert(record):
        conversations.delete_conversation('owner', cid)
        return create(record)

    jobs.store.create = delete_before_insert
    with pytest.raises(HTTPException) as exc:
        jobs.enqueue('owner', cid, str(uuid4()), {'content': 'private pending question'})
    assert exc.value.status_code == 404
    assert jobs.store.jobs == {}


def test_http_queue_requires_auth_and_csrf_and_polls_without_repeating_request():
    from fastapi.testclient import TestClient

    from backend.chat_jobs import create_chat_job_router
    from tests.test_conversation_api import create_test_api, login_user

    app, auth, conversations, _ = create_test_api()
    jobs = ChatJobService(conversations)
    jobs.initialize()
    app.include_router(create_chat_job_router(auth, jobs))
    with TestClient(app) as client:
        assert client.get('/api/v1/conversations/missing/requests').status_code == 401
        csrf = login_user(client, auth, 'alice@example.com', 'alice-id')
        cid = conversations.create_conversation('alice-id')['id']
        route = f'/api/v1/conversations/{cid}/requests'
        body = {'request_id': str(uuid4()), 'content': '你好'}
        assert client.post(route, json=body).status_code == 403
        response = client.post(route, json=body, headers={'X-CSRF-Token': csrf})
        assert response.status_code == 202
        assert response.json()['status'] == 'queued'
        jobs.process_pending()
        result = client.get(f"{route}/{body['request_id']}")
        assert result.status_code == 200
        assert result.json()['status'] == 'completed'
        assert result.json()['message']['answer_scope'] == 'general'
        login_user(client, auth, 'bob@example.com', 'bob-id')
        assert client.get(f"{route}/{body['request_id']}").status_code == 404
