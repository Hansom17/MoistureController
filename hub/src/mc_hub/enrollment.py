"""Device-code enrollment against the cloud API (hub.md §3)."""

import asyncio
import hashlib
import logging
import secrets

import httpx

from mc_core.contract.hub import EnrollPollResponse, EnrollStartResponse

from .config import VERSION, HubConfig

log = logging.getLogger(__name__)


def banner(start: EnrollStartResponse) -> str:
    code = start.user_code
    try:  # QR code of the claim URL if the optional library is installed
        import io

        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(start.claim_url)
        buf = io.StringIO()
        qr.print_ascii(out=buf)
        qr_text = buf.getvalue()
    except ImportError:
        qr_text = ""
    return (f"\n{qr_text}\n  Add this hub in the app (Household settings → Hub) with the code\n\n"
            f"        {code}\n\n  or open {start.claim_url}\n"
            f"  The code is valid for {start.expires_in // 60} minutes.\n")


async def enroll(cfg: HubConfig, on_code=None) -> EnrollPollResponse:
    """Runs start → poll until claimed; restarts with a new code on expiry."""
    async with httpx.AsyncClient(base_url=cfg.cloud_api_url, timeout=15) as http:
        while True:
            secret = secrets.token_bytes(32)
            try:
                r = await http.post("/hub/v1/enroll/start", json={
                    "secret_sha256": hashlib.sha256(secret).hexdigest(),
                    "agent_version": VERSION, "arch": cfg.arch})
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("enrollment start failed (%s); retrying in 30 s", e)
                await asyncio.sleep(30)
                continue
            start = EnrollStartResponse.model_validate(r.json())
            log.info(banner(start))
            if on_code:
                on_code(start)
            while True:
                await asyncio.sleep(start.interval)
                try:
                    r = await http.post("/hub/v1/enroll/poll", json={
                        "enroll_id": start.enroll_id, "secret": secret.hex()})
                except httpx.HTTPError as e:
                    log.warning("poll failed: %s", e)
                    continue
                if r.status_code == 202:
                    continue
                if r.status_code == 200:
                    return EnrollPollResponse.model_validate(r.json())
                if r.status_code == 429:
                    await asyncio.sleep(start.interval)
                    continue
                log.info("enrollment code expired (%s); getting a new one", r.status_code)
                break
