"""Passwords (argon2id), tokens and codes (only SHA-256 hashes are stored)."""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()                       # argon2id with the library's current defaults
_DUMMY = _ph.hash("not-a-password")          # compared against when a username is unknown (constant work)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hash_: str | None, password: str) -> bool:
    try:
        return _ph.verify(hash_ or _DUMMY, password) and hash_ is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)         # 256 bits


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_code() -> str:
    """Invite / setup codes: 20 URL-safe characters, readable enough to type."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(20))
