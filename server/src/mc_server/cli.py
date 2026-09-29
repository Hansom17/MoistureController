"""`mc-server` command line: serve, openapi, seed-dev."""

import argparse
import asyncio
import json
import logging
import sys


def _openapi() -> dict:
    from .config import Settings
    from .main import create_app

    settings = Settings(docs_enabled=True)
    return create_app(settings, background=False).openapi()


def cmd_openapi(args) -> None:
    import yaml

    spec = _openapi()
    text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True) if args.format == "yaml" \
        else json.dumps(spec, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def cmd_serve(args) -> None:
    import uvicorn

    from .config import Settings
    from .db.migrate import upgrade
    from .main import create_app

    settings = Settings.from_env()
    if not settings.database_url.startswith("sqlite"):
        upgrade(settings.database_url)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info",
                proxy_headers=True, forwarded_allow_ips="*")


def cmd_seed_dev(args) -> None:
    from .dev_seed import seed

    asyncio.run(seed(args.uid))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="mc-server")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("serve", help="run the API, MQTT connection and jobs")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    o = sub.add_parser("openapi", help="print the OpenAPI spec (contracts/api.yaml)")
    o.add_argument("--format", choices=("yaml", "json"), default="yaml")
    o.add_argument("-o", "--output")
    o.set_defaults(func=cmd_openapi)

    d = sub.add_parser("seed-dev", help="dev only: household + simulated device for a uid")
    d.add_argument("--uid", default="dev-user")
    d.set_defaults(func=cmd_seed_dev)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
