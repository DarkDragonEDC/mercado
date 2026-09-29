"""Minimal ports useful to the future presentation layer and unit tests."""

from typing import Protocol

from ..types import (
    BotControlState,
    BotMode,
    SettingsLoadResult,
    SettingsSaveResult,
    SettingsSnapshot,
)


class BotControlPort(Protocol):
    def read(self) -> BotControlState: ...

    def request_start(self, mode: BotMode = BotMode.BUY) -> BotControlState: ...

    def request_stop(self) -> BotControlState: ...

    def update_mode(self, mode: BotMode) -> BotControlState: ...


class SettingsPort(Protocol):
    def load(self) -> SettingsLoadResult: ...

    def save(self, snapshot: SettingsSnapshot) -> SettingsSaveResult: ...


__all__ = ["BotControlPort", "SettingsPort"]

