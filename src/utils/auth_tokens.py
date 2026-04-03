from __future__ import annotations

import hashlib


def hash_api_key(raw: str, pepper: str) -> str:
    if not pepper:
        pepper = "dev-pepper"
    return hashlib.sha256(f"{raw}:{pepper}".encode()).hexdigest()
