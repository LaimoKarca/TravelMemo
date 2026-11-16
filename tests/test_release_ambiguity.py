from backend.embedding import E5_REVISION
from backend.retrieval import SearchService
from backend.travel_store import MemoryTravelRepository


def test_broad_after_does_not_assume_or_traverse_next():
    class Encoder:
        revision = E5_REVISION

        def encode_query(self, text):
            return [1.0] + [0.0] * 383

    repo = MemoryTravelRepository()
    trip = repo.create_trip(
        "qa", {"name": "Trip", "start_date": "2026-11-01", "end_date": "2026-11-02"}
    )
    repo.create_event(
        "qa", trip["id"], {"place_name": "Tower", "category": "landmark", "date": "2026-11-01"}
    )
    repo.create_event(
        "qa", trip["id"], {"place_name": "Cafe", "category": "cafe", "date": "2026-11-02"}
    )
    service = SearchService(None, repo, embedder=Encoder())

    def forbidden(*args, **kwargs):
        raise AssertionError("Ambiguous after must not traverse NEXT before clarification")

    service.store.get_adjacent_events = forbidden
    result = service.search("qa", "Which cafe did I visit after Tower?")
    assert result["clarification"]
    assert all(item["relation"] is None for item in result["items"])
