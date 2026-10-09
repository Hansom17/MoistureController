"""Push notifications to all members of a household (Server/specs.md Part A §11)."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from ..db.models import Membership, PushToken

if TYPE_CHECKING:
    from ..context import AppContext

log = logging.getLogger(__name__)


class PushSender:
    """Logs only: there is no push provider."""

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
        log.info("push (not sent, no push provider): %s %s to %d tokens", title, data, len(tokens))
        return []
