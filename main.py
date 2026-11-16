"""TravelMemo's Python entry point."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="TravelMemo")
    parser.add_argument(
        "command",
        choices=["serve", "init-db", "check-config", "download-model", "rebuild-index", "evaluate"],
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--benchmark-root", default="data/benchmark")
    parser.add_argument("--output", default="data/evaluation")
    parser.add_argument("--limit-queries", type=int, default=0)
    parser.add_argument(
        "--ann", action="store_true", help="Evaluate in a separate EVAL_NEO4J_URI database"
    )
    parser.add_argument(
        "--explicit-adjacency",
        action="store_true",
        help="Separate immediately-after query diagnostic",
    )
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        from backend.config import get_settings

        settings = get_settings()

        uvicorn.run(
            "backend.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            proxy_headers=bool(settings.trusted_proxy_ips.strip()),
            forwarded_allow_ips=settings.trusted_proxy_ips,
            workers=1,
        )
    elif args.command == "init-db":
        from backend.config import get_settings
        from backend.store import Neo4jStore

        store = Neo4jStore(get_settings())
        try:
            store.initialize()
            from backend.travel_store import Neo4jTravelRepository

            Neo4jTravelRepository(store.driver, store.database).initialize()
            from backend.conversation_store import Neo4jConversationStore
            from backend.retrieval import SearchService

            SearchService(
                get_settings(), Neo4jTravelRepository(store.driver, store.database)
            ).initialize()
            Neo4jConversationStore(store.driver, store.database).initialize()
            print("Neo4j constraints and retrieval indexes initialized.")
        finally:
            store.close()
    elif args.command == "download-model":
        from backend.config import get_settings
        from backend.embedding import EmbeddingModel

        if EmbeddingModel(get_settings()).download() is False:
            raise SystemExit("Model download failed; inspect network and model directory.")
        print("Pinned E5 model downloaded.")
    elif args.command == "rebuild-index":
        from backend.config import get_settings
        from backend.retrieval import SearchService
        from backend.store import Neo4jStore
        from backend.travel_store import Neo4jTravelRepository

        settings = get_settings()
        store = Neo4jStore(settings)
        try:
            service = SearchService(settings, Neo4jTravelRepository(store.driver, store.database))
            service.initialize()
            service.rebuild()
            while service.process_pending():
                pass
            status = service.index_status()
            print(status)
            if status.get("failed") or status.get("pending"):
                raise SystemExit("Index rebuild incomplete; inspect model files and retry.")
        finally:
            store.close()
    elif args.command == "evaluate":
        from experiments.evaluate import evaluate

        output = args.output
        if args.explicit_adjacency and output == "data/evaluation":
            output = "data/evaluation-adjacency"
        evaluate(
            args.benchmark_root,
            output,
            limit=args.limit_queries,
            ann=args.ann,
            explicit_adjacency=args.explicit_adjacency,
        )
    else:
        from backend.config import get_settings

        config = get_settings()
        print(
            f"Configuration valid: environment={config.app_env}, "
            f"allowed_emails={len(config.emails)}, smtp_configured={bool(config.smtp_host)}"
        )


if __name__ == "__main__":
    main()
