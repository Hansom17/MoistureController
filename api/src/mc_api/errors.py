"""RFC 9457 problem responses with stable `type`s (Api_Specs §6)."""

from fastapi import Request
from fastapi.responses import JSONResponse

from mc_core.commands import CommandRejected


class Problem(Exception):
    def __init__(self, status: int, type_: str, detail: str | None = None, **extra):
        super().__init__(f"{status} {type_}: {detail}")
        self.status = status
        self.type = type_
        self.detail = detail
        self.extra = extra


def not_found(what: str = "not_found") -> Problem:
    return Problem(404, "not_found", what)


def problem_response(status: int, type_: str, detail: str | None = None, **extra) -> JSONResponse:
    body = {"type": type_, "title": type_.replace("_", " "), "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    return problem_response(exc.status, exc.type, exc.detail, **exc.extra)


async def command_rejected_handler(request: Request, exc: CommandRejected) -> JSONResponse:
    return problem_response(exc.status, exc.code, exc.detail)
