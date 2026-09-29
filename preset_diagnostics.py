"""Diagnostico local e sem dados sensiveis do assistente de presets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_paths import logs_dir


def write_preset_diagnostic(event: str, **details: Any) -> Path | None:
    """Acrescenta um evento JSONL; falhas de log nunca bloqueiam o aplicativo."""

    try:
        now = datetime.now(timezone.utc)
        path = logs_dir() / f"configuracao-automatica-{now:%Y-%m-%d}.log"
        record = {
            "timestamp_utc": now.isoformat(),
            "event": str(event),
            "details": details,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return path
    except (OSError, TypeError, ValueError):
        return None
