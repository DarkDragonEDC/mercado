from __future__ import annotations

import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"


if TARGET.exists():
    raise SystemExit(f"{TARGET} ja existe; nenhum segredo foi alterado")

content = f"""ALBIONMKT_ADMIN_TOKEN={secrets.token_urlsafe(48)}
ALBIONMKT_KEY_PEPPER={secrets.token_urlsafe(48)}
ALBIONMKT_DATABASE_PATH=data/licenses.db
ALBIONMKT_RATE_LIMIT_PER_MINUTE=60
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_ADMIN_ROLE_IDS=
ALBIONMKT_BACKEND_URL=http://127.0.0.1:8000
"""
TARGET.write_text(content, encoding="utf-8", newline="\n")
print(f"Ambiente criado em {TARGET}. O arquivo e ignorado pelo Git.")

