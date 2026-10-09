"""The FastAPI application (Gateway/specs.md section 6)."""
import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import delete, or_
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .bus.hub_client import HubClient
from .clock import Clock
from .config import Settings
from .convert import to_api
from .db.models import Token
from .errors import ApiError
from .realtime.bus import EventBus
from .routers import data, hubapi, live, meta_auth, users
from .state import App

log = logging.getLogger("mc_api")
PROBLEM = "application/problem+json"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; frame-ancestors 'none'")


def problem(e: ApiError) -> JSONResponse:
    headers = {"Retry-After": str(e.extra["retry_after"])} if "retry_after" in e.extra else None
    return JSONResponse(e.body(), status_code=e.status, media_type=PROBLEM, headers=headers)


async def cleanup_tokens(mc: App) -> None:
    """Revoked tokens after 30 days, unused ones after the configured age."""
    now = int(mc.clock.now())
    async with mc.sessions() as s:
        await s.execute(delete(Token).where(or_(
            Token.revoked_at < now - 30 * 86400,
            (Token.last_used_at.is_(None)) & (Token.created_at < now - mc.settings.token_max_age_days * 86400),
            Token.last_used_at < now - mc.settings.token_max_age_days * 86400)))
        await s.commit()


async def startup(mc: App) -> None:
    async def on_event(kind: str, body: dict) -> None:
        mc.events.publish(kind, to_api(body))

    async def on_resync() -> None:
        mc.events.publish("resync")

    async def on_status() -> None:
        mc.events.publish("status", {"hub": mc.hub.online})

    mc.hub.on_event, mc.hub.on_resync, mc.hub.on_status = on_event, on_resync, on_status
    await mc.hub.start()
    await meta_auth.setup_code(mc)
    await cleanup_tokens(mc)


def create_app(settings: Settings, transport, sessions, clock: Clock | None = None, engine=None,
               ping_s: float = 25.0) -> FastAPI:
    clock = clock or Clock()
    mc = App(settings, sessions, HubClient(transport, settings.instance, clock, settings.request_timeout_s),
             EventBus(clock.now), clock, engine)
    tasks: list[asyncio.Task] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await startup(mc)

        async def hourly() -> None:
            while True:
                await asyncio.sleep(3600)
                try:
                    await cleanup_tokens(mc)
                except Exception:
                    log.exception("token cleanup failed")

        tasks.append(asyncio.create_task(hourly()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="MoistureController", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs" if settings.docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if settings.docs else None)
    app.state.mc = mc
    app.state.ping_s = ping_s

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return problem(e)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        detail = "; ".join(f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}" for err in e.errors())
        return problem(ApiError("validation", "The request is not valid", detail))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        t = {404: "not_found", 405: "validation", 401: "unauthorized", 403: "forbidden"}.get(e.status_code, "internal")
        return problem(ApiError(t, str(e.detail), status=e.status_code))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return problem(ApiError("internal", "Something went wrong", status=500))

    @app.middleware("http")
    async def headers(request: Request, call_next):
        if int(request.headers.get("content-length", "0") or 0) > 65536:
            return problem(ApiError("validation", "The request is too large", status=413))
        resp: Response = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/api/"):
            resp.headers.setdefault("Content-Security-Policy", CSP)
        elif request.url.path.startswith("/api/v1") and not mc.hub.online:
            resp.headers["X-MC-Stale"] = "true"        # reads come from the last snapshot
        return resp

    for r in (meta_auth.router, users.router, hubapi.router, live.router, data.router):
        app.include_router(r, prefix="/api/v1")

    web = settings.web_dir
    if web is not None and Path(web).is_dir():
        root = Path(web).resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                raise StarletteHTTPException(404, "Not found")
            f = (root / path).resolve()
            if path and f.is_file() and root in f.parents:
                return FileResponse(f, media_type=mimetypes.guess_type(f.name)[0])
            return FileResponse(root / "index.html", media_type="text/html")

    return app
