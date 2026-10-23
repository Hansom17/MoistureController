"""Notifier (Gateway/specs.md section 13): Telegram is sent from here; `app` is the event stream."""
import asyncio
import json
import logging
import urllib.request
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mc_hub.db.models import Setting

log = logging.getLogger("mc_hub.notify")
Send = Callable[[str, str, str], Awaitable[None]]    # token, chat_id, text


async def telegram_send(token: str, chat_id: str, text: str) -> None:
    def call() -> None:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()

    await asyncio.to_thread(call)


class Notifier:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], send: Send = telegram_send) -> None:
        self.sessions, self.send = sessions, send

    async def deliver(self, notes: list[dict]) -> list[dict]:
        """Sends the telegram parts; returns the `app` notifications to publish as events."""
        if not notes:
            return []
        async with self.sessions() as s:
            row = await s.get(Setting, "telegram")
        tg = (row.value if row else None) or {}
        app = []
        for n in notes:
            channels = list(n["channels"])
            if n["kind"] == "alert":      # alerts: telegram for the kinds the owner selected (default all)
                kinds = tg.get("kinds")
                if not kinds or n.get("alert_kind") in kinds:
                    channels.append("telegram")
            if "app" in channels:
                app.append({"text": n["text"], "kind": n["kind"]})
            if "telegram" in channels and tg.get("token") and tg.get("chat_id"):
                try:
                    await self.send(tg["token"], str(tg["chat_id"]), n["text"])
                except Exception as e:       # never let a notification failure break the hub
                    log.warning("telegram send failed: %s", type(e).__name__)
        return app
