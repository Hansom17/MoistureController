"""Push notifications to all members of a household (Server_Specs §11.2)."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from ..db.models import Membership, PushToken

if TYPE_CHECKING:
    from ..context import AppContext

log = logging.getLogger(__name__)


class PushSender:
    """Default sender: logs only. `FcmPushSender` sends through Firebase."""

    async def send_to_household(self, ctx: "AppContext", household_id: str, title: str,
                                data: dict) -> None:
        try:
            async with ctx.sessionmaker() as s:
                tokens = (await s.scalars(
                    select(PushToken.token)
                    .join(Membership, Membership.user_uid == PushToken.user_uid)
                    .where(Membership.household_id == household_id))).all()
            invalid = await self.deliver(list(tokens), title, {**data, "household_id": household_id})
            if invalid:
                async with ctx.sessionmaker() as s:
                    await s.execute(delete(PushToken).where(PushToken.token.in_(invalid)))
                    await s.commit()
        except Exception:
            log.exception("push to household %s failed", household_id)

    async def deliver(self, tokens: list[str], title: str, data: dict) -> list[str]:
        """Returns tokens the provider reported as invalid."""
        log.info("push (not sent, no FCM configured): %s %s to %d tokens", title, data, len(tokens))
        return []


class FcmPushSender(PushSender):
    def __init__(self, app) -> None:
        self._app = app  # firebase_admin.App

    async def deliver(self, tokens: list[str], title: str, data: dict) -> list[str]:
        if not tokens:
            return []
        import asyncio

        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title),
            data={k: str(v) for k, v in data.items()},
        )
        invalid: list[str] = []
        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    messaging.send_each_for_multicast, message, app=self._app)
                for token, r in zip(tokens, resp.responses, strict=True):
                    if not r.success and r.exception is not None and getattr(
                        r.exception, "code", "") in ("NOT_FOUND", "INVALID_ARGUMENT", "UNREGISTERED"):
                        invalid.append(token)
                return invalid
            except Exception:
                log.warning("FCM send failed (attempt %d)", attempt + 1, exc_info=True)
                await asyncio.sleep(2**attempt)
        return invalid
