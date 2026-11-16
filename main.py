"""TravelMemo's Python entry point."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="TravelMemo")
    parser.add_argument("command", choices=["serve", "init-db", "check-config"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
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
        )
    elif args.command == "init-db":
        from backend.config import get_settings
        from backend.store import Neo4jStore

        store = Neo4jStore(get_settings())
        try:
            store.initialize()
            from backend.travel_store import Neo4jTravelRepository

            Neo4jTravelRepository(store.driver, store.database).initialize()
            print("Neo4j constraints initialized.")
        finally:
            store.close()
    else:
        from backend.config import get_settings

        config = get_settings()
        print(
            f"Configuration valid: environment={config.app_env}, "
            f"allowed_emails={len(config.emails)}, smtp_configured={bool(config.smtp_host)}"
        )


if __name__ == "__main__":
    main()
