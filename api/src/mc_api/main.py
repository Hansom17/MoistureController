"""FastAPI application: API, SSE and jobs in one process.

Gateways connect over the WebSocket at /gateway/v1/connect (api/gateway.py).
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from mc_core.commands import CommandRejected

from .api import activity, devices, export, gateway, households, me, plants
from .auth.verify import DevVerifier, FirebaseVerifier, TokenVerifier
from .config import Settings
from .context import AppContext
from .crypto import KeyBox
from .db.session import create_all, make_engine, make_sessionmaker
from .errors import Problem, command_rejected_handler, problem_handler, problem_response
from .jobs import runner
from .notify.push import FcmPushSender, PushSender
from .realtime.bus import EventBus

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
_VERSION = re.compile(r"^\w+/(\d+)\.(\d+)\.(\d+)")


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v)[:3])


def create_app(settings: Settings | None = None, *, verifier: TokenVerifier | None = None,
               background: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()

    if verifier is None:
        if settings.auth_mode == "dev":
            log.warning("AUTH MODE 'dev': accepting unsigned dev tokens — never expose this")
            verifier = DevVerifier()
        else:
            verifier = FirebaseVerifier(settings.firebase_credentials,
                                        settings.firebase_project_id)
    push: PushSender = (FcmPushSender(verifier.app) if isinstance(verifier, FirebaseVerifier)
                        else PushSender())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        if settings.database_url.startswith("sqlite"):
            await create_all(engine)
        ctx = AppContext(settings=settings, engine=engine,
                         sessionmaker=make_sessionmaker(engine),
                         keys=KeyBox(settings.key_encryption_key), bus=EventBus(), push=push)
        app.state.ctx = ctx
        app.state.verifier = verifier
        tasks: list[asyncio.Task] = []
        if background:
            tasks.append(asyncio.create_task(runner.run_forever(ctx), name="jobs"))
        yield
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()

    app = FastAPI(
        title="MoistureController API", version="1.0.0", lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.add_exception_handler(Problem, problem_handler)
    app.add_exception_handler(CommandRejected, command_rejected_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return problem_response(422, "validation_error", "invalid request",
                                errors=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])

    @app.middleware("http")
    async def headers_and_version(request: Request, call_next):
        min_version = settings.min_app_version
        app_header = request.headers.get("x-mc-app")
        if min_version and app_header and request.url.path.startswith(API_PREFIX):
            _, _, version = app_header.partition("/")
            if version and _version_tuple(version) < _version_tuple(min_version):
                return problem_response(426, "upgrade_required", f"minimum {min_version}")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/docs"):
            response.headers["Content-Security-Policy"] = "default-src 'none'"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                           allow_methods=["*"], allow_headers=["*"],
                           expose_headers=["Content-Disposition"])

    for r in (me.router, households.router, devices.router, plants.router, activity.router,
              gateway.router, export.router):
        app.include_router(r, prefix=API_PREFIX)
    app.include_router(gateway.enroll_router)
    app.include_router(gateway.ws_router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    return app
