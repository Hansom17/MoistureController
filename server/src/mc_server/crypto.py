"""AES-256-GCM encryption of PSKs at rest (Server_Specs §4)."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyBox:
    def __init__(self, key_hex: str):
        key = bytes.fromhex(key_hex)
        if len(key) != 32:
            raise ValueError("MC_KEY_ENCRYPTION_KEY must be 32 bytes (64 hex chars)")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        return base64.b64encode(nonce + self._aead.encrypt(nonce, plaintext.encode(), None)).decode()

    def decrypt(self, token: str) -> str:
        raw = base64.b64decode(token)
        return self._aead.decrypt(raw[:12], raw[12:], None).decode()
