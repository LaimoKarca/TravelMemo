from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.assistant_tools import AssistantTools
from backend.conversation import Citation, ConversationService
from backend.conversation_store import MemoryConversationStore
from backend.llm import LLMResult, MockLLM, OpenAILLM
from backend.travel_store import MemoryTravelRepository


def setup():
    repo = MemoryTravelRepository()
    trip = repo.create_trip('owner', {'name': '京都慢旅行', 'start_date': '2026-01-01', 'end_date': '2026-01-02'})
    other = repo.create_trip('friend', {'name': 'Private journal', 'start_date': '2026-01-01', 'end_date': '2026-01-02'})
    search = SimpleNamespace(repository=repo, search=lambda **kw: {'items': []})
    service = ConversationService(SimpleNamespace(), search, MemoryConversationStore(), llm=MockLLM())
    cid = service.create_conversation('owner')['id']
    return service, cid, repo, trip, other


def test_journal_without_events_is_discoverable_and_citations_are_revalidated():
    service, cid, repo, trip, other = setup()
    answer = service.post_message('owner', cid, '我手記有哪些?')
    assert answer['status'] == 'answered'
    assert '京都慢旅行' in answer['content']
    assert 'Private journal' not in answer['content']
    assert answer['citations'] == []
    assert [c['trip_id'] for c in answer['trip_citations']] == [trip['id']]
    repo.trips[trip['id']]['version'] += 1
    assert service.get_messages('owner', cid)[-1]['trip_citations'][0]['state'] == 'changed'
    del repo.trips[trip['id']]
    assert service.get_messages('owner', cid)[-1]['trip_citations'][0]['state'] == 'deleted'
    assert AssistantTools(service.search_service).execute('owner', {'name': 'get_trip', 'arguments': {'trip_id': other['id']}}) == {'trip': None}


def test_tools_reject_owner_override_unknown_functions_and_unbounded_results():
    service, *_ = setup()
    tools = AssistantTools(service.search_service)
    for call in [
        {'name': 'list_trips', 'arguments': {'owner_id': 'friend'}},
        {'name': 'list_trips', 'arguments': {'limit': 99999}},
        {'name': 'run_cypher', 'arguments': {'query': 'MATCH (n) RETURN n'}},
    ]:
        with pytest.raises(ValidationError):
            tools.execute('owner', call)


def test_trip_answer_rejects_fabricated_trip_citations():
    service, cid, *_ = setup()
    service.llm.generate = lambda *a: LLMResult(status='answered', content='Invented', cited_trip_ids=['foreign'])
    answer = service.post_message('owner', cid, '這個手記內容是什麼')
    assert answer['status'] == 'insufficient_evidence'
    assert answer.get('trip_citations', []) == []


def test_recent_standalone_footprints_are_cited_and_follow_the_live_trip_assignment():
    service, cid, repo, trip, _other = setup()
    event = {
        "id": "sunset", "trip_id": None, "date": "2026-01-01", "time": None,
        "place_name": "海邊堤防", "version": 1, "record_scope": "standalone",
    }
    repo.list_standalone_events = MagicMock(return_value={"items": [dict(event)], "next_offset": None})
    service.search_service.get_event = MagicMock(side_effect=lambda owner, _id: event if owner == "owner" else None)
    answer = service.post_message("owner", cid, "最近記了哪些日常足跡？")
    repo.list_standalone_events.assert_called_once_with("owner", limit=8)
    assert answer["status"] == "answered"
    assert "海邊堤防" in answer["content"]
    assert Citation.model_validate(answer["citations"][0]).trip_id is None
    event.update(trip_id=trip["id"], version=2, record_scope="trip")
    citation = service.get_messages("owner", cid)[-1]["citations"][0]
    assert citation["state"] == "changed"
    assert citation["trip_id"] == trip["id"]


@pytest.mark.parametrize('question', [
    '我的旅行去過哪些餐廳？',
    '列出我的旅程中造訪的景點',
    '我的手記裡有哪些咖啡店？',
    'Which restaurants did I visit on my trips?',
])
def test_event_questions_keep_using_event_retrieval_instead_of_journal_inventory(question):
    service, cid, *_ = setup()
    search = MagicMock(return_value={'items': []})
    service.search_service.search = search
    answer = service.post_message('owner', cid, question)
    search.assert_called_once()
    assert answer.get('trip_citations', []) == []


def test_native_tool_selection_is_bounded_and_does_not_send_secret_owner_parameters():
    llm = OpenAILLM('test-key')
    response = SimpleNamespace(output=[SimpleNamespace(type='function_call', name='list_trips', arguments='{"query":"","limit":10}')])
    with patch('openai.OpenAI') as factory:
        client = MagicMock()
        factory.return_value.__enter__.return_value = client
        client.responses.create.return_value = response
        calls = llm.choose_tools('我手記有哪些', [{'id': 'trip', 'name': 'Kyoto'}], [])
        assert calls == [{'name': 'list_trips', 'arguments': {'query': '', 'limit': 10}}]
        request = client.responses.create.call_args.kwargs
        assert request['store'] is False and request['max_output_tokens'] == 512
        assert len(request['tools']) == 5
        assert all('owner' not in tool['parameters']['properties'] for tool in request['tools'])
