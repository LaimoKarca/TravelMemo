"""Synthetic, private-owner deployment checks. Pipe into the API container's Python.

prepare prints a non-secret fixture manifest; check/cleanup read it from --manifest.
Only --with-ai makes a paid OpenAI request. No email is sent.
"""

import argparse
import json
import re
from pathlib import Path
from uuid import uuid4

from backend.config import Settings
from backend.store import Neo4jStore
from backend.travel_store import Neo4jTravelRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "check", "cleanup"])
    parser.add_argument("--manifest", default="")
    parser.add_argument("--with-ai", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    store = Neo4jStore(settings)
    travel = Neo4jTravelRepository(store.driver, store.database)
    try:
        if args.mode == "prepare":
            owner = "release-qa-" + uuid4().hex
            trip = travel.create_trip(
                owner,
                {
                    "name": "TravelMemo release verification",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-03",
                    "timezone": "Asia/Tokyo",
                    "description": "Synthetic verification only",
                },
            )
            first = travel.create_event(
                owner,
                trip["id"],
                {
                    "place_name": "Release QA Tower",
                    "city": "Kyoto",
                    "category": "landmark",
                    "date": "2026-11-01",
                    "time": None,
                    "notes": "Synthetic tower visit.",
                },
            )
            second = travel.create_event(
                owner,
                trip["id"],
                {
                    "place_name": "Release QA Cafe",
                    "city": "Kyoto",
                    "category": "cafe",
                    "date": "2026-11-02",
                    "time": "11:00",
                    "notes": "Synthetic cafe visit: matcha latte and green tea cake.",
                },
            )
            print(
                json.dumps(
                    {
                        "owner_id": owner,
                        "trip_id": trip["id"],
                        "event_ids": [first["id"], second["id"]],
                    }
                )
            )
            return

        fixture = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
        owner = fixture["owner_id"]
        if not re.fullmatch(r"release-qa-[0-9a-f]{32}", owner):
            raise ValueError("Only exact synthetic release owners are permitted")
        if args.mode == "cleanup":
            store.driver.execute_query(
                "MATCH (n) WHERE n.owner_id=$owner OR (n:User AND n.id=$owner) DETACH DELETE n",
                owner=owner,
                database_=store.database,
            )
            print("RELEASE_FIXTURE_REMOVED")
            return

        from backend.retrieval import SearchService

        search = SearchService(settings, travel)
        search.initialize()
        status = search.index_status(owner)
        import time

        deadline = time.monotonic() + 60
        while status["pending"] and not status["failed"] and time.monotonic() < deadline:
            time.sleep(1)
            status = search.index_status(owner)
        assert status == {"pending": 0, "ready": 2, "failed": 0}, status
        detail = travel.get_trip_detail(owner, fixture["trip_id"])
        assert [e["id"] for e in detail["events"]] == fixture["event_ids"]
        assert len(detail["next_edges"]) == 1
        results = search.search(owner, "What was the next stop after Release QA Tower?")
        expected = fixture["event_ids"][1]
        assert any(i["event"]["id"] == expected and i["relation"] for i in results["items"])
        assert results["vector_status"] == "ready"
        assert not search.get_event("different-" + owner, expected)
        assert not search.verify_relation(
            "different-" + owner, fixture["event_ids"][0], expected, "next"
        )
        print("RELEASE_SEARCH_GRAPH_ISOLATION_OK")
        if args.with_ai:
            from backend.conversation import ConversationService
            from backend.conversation_store import Neo4jConversationStore

            conversations = Neo4jConversationStore(store.driver, store.database)
            conversations.initialize()
            service = ConversationService(settings, search, conversations)
            conversation = service.create_conversation(owner, "Release synthetic QA")
            answer = service.post_message(
                owner, conversation["id"], "Where did I drink a matcha latte?"
            )
            assert answer["status"] == "answered" and any(
                c["event_id"] == expected for c in answer["citations"]
            )
            assert service.get_usage(owner)["requests"] >= 1
            print("RELEASE_REAL_AI_CITATION_USAGE_OK")
    finally:
        store.close()


if __name__ == "__main__":
    main()
