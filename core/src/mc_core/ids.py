"""Identifiers: ULIDs, device IDs, hub IDs and hub user codes."""

import secrets

from ulid import ULID

# Crockford base32 without I, L, O, U.
CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"


def new_id() -> str:
    """ULID for rows, commands and reports (26 chars)."""
    return str(ULID())


def _random_base32(chars: int) -> str:
    return "".join(secrets.choice(CROCKFORD) for _ in range(chars))


def new_device_id() -> str:
    """`mc-` + 16 lowercase Crockford base32 chars (80 random bits), mqtt.md §2."""
    return "mc-" + _random_base32(16)


def new_hub_id() -> str:
    """`hub-` + 16 lowercase Crockford base32 chars, hub.md §2."""
    return "hub-" + _random_base32(16)


def new_user_code() -> str:
    """8 uppercase Crockford chars shown as `XXXX-XXXX` (hub.md §3.1)."""
    code = _random_base32(8).upper()
    return f"{code[:4]}-{code[4:]}"


def normalize_user_code(code: str) -> str:
    """Accepts user input with or without dash, any case; maps look-alikes."""
    cleaned = code.strip().upper().replace("-", "").replace(" ", "")
    return cleaned.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def new_psk() -> str:
    """32-byte TLS-PSK key as 64 hex chars."""
    return secrets.token_hex(32)
