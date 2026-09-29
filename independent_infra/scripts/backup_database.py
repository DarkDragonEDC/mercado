from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
source = Path(os.getenv("ALBIONMKT_DATABASE_PATH", ROOT / "data" / "licenses.db"))
if not source.is_absolute():
    source = ROOT / source
if not source.is_file():
    raise SystemExit(f"Banco nao encontrado: {source}")

backup_dir = ROOT / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
destination = backup_dir / f"licenses-{timestamp}.db"

with sqlite3.connect(source) as origin, sqlite3.connect(destination) as target:
    origin.backup(target)

print(destination)

