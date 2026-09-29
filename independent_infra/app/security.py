from __future__ import annotations

import hashlib
import hmac
import secrets
import string


ALPHABET = string.ascii_uppercase + string.digits


def normalize_key(value: str) -> str:
    return value.strip().upper()


def generate_license_key() -> str:
    groups = ["".join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(4)]
    return "ALBIONMKT-" + "-".join(groups)


def keyed_digest(value: str, pepper: str) -> str:
    return hmac.new(
        pepper.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def license_digest(key: str, pepper: str) -> str:
    return keyed_digest(normalize_key(key), pepper)


def hwid_digest(hwid: str, pepper: str) -> str:
    return keyed_digest(hwid.strip().lower(), pepper)


def masked_key(key: str) -> str:
    normalized = normalize_key(key)
    if len(normalized) <= 14:
        return "*" * len(normalized)
    return f"{normalized[:14]}...{normalized[-5:]}"


def token_matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))

