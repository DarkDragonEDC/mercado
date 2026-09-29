"""Adapter for the legacy bot_control.json contract."""

from __future__ import annotations

import json
from pathlib import Path

from ..application.types import BotControlState, BotMode
from ._json_storage import atomic_write_json


class BotControlAdapter:
    def __init__(self, path: str | Path = "bot_control.json") -> None:
        self.path = Path(path)

    def read(self) -> BotControlState:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            run = bool(payload.get("run", False))
            mode_value = payload.get("mode", BotMode.BUY.value)
            mode = mode_value if isinstance(mode_value, str) else BotMode.BUY.value
            return BotControlState(run=run, mode=mode)
        except (OSError, ValueError, AttributeError):
            return BotControlState()

    def request_start(self, mode: BotMode = BotMode.BUY) -> BotControlState:
        state = BotControlState(run=True, mode=mode.value)
        self._write(state)
        return state

    def request_stop(self) -> BotControlState:
        current = self.read()
        state = BotControlState(run=False, mode=current.mode)
        self._write(state)
        return state

    def update_mode(self, mode: BotMode) -> BotControlState:
        current = self.read()
        state = BotControlState(run=current.run, mode=mode.value)
        self._write(state)
        return state

    def _write(self, state: BotControlState) -> None:
        atomic_write_json(self.path, {"run": state.run, "mode": state.mode})

