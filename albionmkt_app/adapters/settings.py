"""Typed, non-destructive access to the legacy offsets.json settings subset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..application.types import (
    SettingsIssue,
    SettingsIssueKind,
    SettingsLoadResult,
    SettingsSaveResult,
    SettingsSnapshot,
)
from ._json_storage import atomic_write_json


class LegacySettingsAdapter:
    def __init__(self, path: str | Path = "offsets.json") -> None:
        self.path = Path(path)

    def load(self) -> SettingsLoadResult:
        payload, issue = self._read_payload()
        if issue is not None:
            return SettingsLoadResult(SettingsSnapshot(), issue)
        return self._snapshot_from(payload)

    def save(self, snapshot: SettingsSnapshot) -> SettingsSaveResult:
        payload, issue = self._read_payload()
        if issue is not None and self.path.exists():
            return SettingsSaveResult(False, issue)
        payload.update(
            {
                "financial_rule_version": 2,
                "lucro_minimo_venda": float(snapshot.minimum_profit_percentage),
                "lucro": 100.0 - float(snapshot.minimum_profit_percentage),
                "valor_max": int(snapshot.max_purchase_value),
                "delay_clique": max(0.05, float(snapshot.click_delay)),
                "delay_pagina": max(0.1, float(snapshot.page_delay)),
                "cat_sequence": list(snapshot.category_sequence),
                "cat_enabled": dict(snapshot.category_enabled),
            }
        )
        try:
            atomic_write_json(self.path, payload)
        except OSError as exc:
            return SettingsSaveResult(
                False, SettingsIssue(SettingsIssueKind.IO_ERROR, str(exc))
            )
        return SettingsSaveResult(True)

    def _read_payload(self) -> tuple[dict[str, Any], SettingsIssue | None]:
        if not self.path.exists():
            return {}, None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {}, SettingsIssue(SettingsIssueKind.INVALID_JSON, str(exc))
        except OSError as exc:
            return {}, SettingsIssue(SettingsIssueKind.IO_ERROR, str(exc))
        if not isinstance(payload, dict):
            return {}, SettingsIssue(
                SettingsIssueKind.INVALID_ROOT,
                "offsets.json must contain a JSON object",
            )
        return payload, None

    def _snapshot_from(self, payload: dict[str, Any]) -> SettingsLoadResult:
        try:
            if not payload:
                minimum_profit = 40.0
            elif "lucro_minimo_venda" in payload:
                minimum_profit = float(payload["lucro_minimo_venda"])
            else:
                minimum_profit = 100.0 - float(payload.get("lucro", 80.0))
            sequence_value = payload.get("cat_sequence", [])
            enabled_value = payload.get("cat_enabled", {})
            if not isinstance(sequence_value, list) or not all(
                isinstance(name, str) for name in sequence_value
            ):
                raise ValueError("cat_sequence must be a list of strings")
            if not isinstance(enabled_value, dict) or not all(
                isinstance(name, str) and isinstance(enabled, bool)
                for name, enabled in enabled_value.items()
            ):
                raise ValueError("cat_enabled must map strings to booleans")
            snapshot = SettingsSnapshot(
                minimum_profit_percentage=minimum_profit,
                max_purchase_value=int(float(payload.get("valor_max", 1_000_000))),
                click_delay=float(payload.get("delay_clique", 0.3)),
                page_delay=float(payload.get("delay_pagina", 0.5)),
                category_sequence=tuple(sequence_value),
                category_enabled=dict(enabled_value),
            )
        except (TypeError, ValueError) as exc:
            return SettingsLoadResult(
                SettingsSnapshot(),
                SettingsIssue(SettingsIssueKind.INVALID_VALUE, str(exc)),
            )
        return SettingsLoadResult(snapshot)

