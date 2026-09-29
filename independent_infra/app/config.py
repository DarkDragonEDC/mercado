from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < 32:
        raise RuntimeError(f"{name} deve possuir pelo menos 32 caracteres")
    return value


@dataclass(frozen=True)
class Settings:
    database_path: Path
    admin_token: str
    key_pepper: str
    rate_limit_per_minute: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        rate_limit = int(os.getenv("ALBIONMKT_RATE_LIMIT_PER_MINUTE", "60"))
        if rate_limit < 1 or rate_limit > 10_000:
            raise RuntimeError("ALBIONMKT_RATE_LIMIT_PER_MINUTE invalido")
        return cls(
            database_path=Path(
                os.getenv("ALBIONMKT_DATABASE_PATH", "data/licenses.db")
            ).expanduser(),
            admin_token=_required_secret("ALBIONMKT_ADMIN_TOKEN"),
            key_pepper=_required_secret("ALBIONMKT_KEY_PEPPER"),
            rate_limit_per_minute=rate_limit,
        )

