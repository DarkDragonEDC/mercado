"""Typed values exposed at the legacy/application boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class BotMode(str, Enum):
    BUY = "buy"
    CLOSE = "close"


class BotStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"


@dataclass(frozen=True)
class BotControlState:
    run: bool = False
    mode: str = BotMode.BUY.value

    @property
    def status(self) -> BotStatus:
        return BotStatus.RUNNING if self.run else BotStatus.STOPPED

    @property
    def known_mode(self) -> BotMode | None:
        try:
            return BotMode(self.mode)
        except ValueError:
            return None


@dataclass(frozen=True)
class MarketItemObservation:
    item_name: str
    sell_price: int
    buy_price: int
    cost_percentage: float
    opportunity: bool


class PurchaseSource(str, Enum):
    LOG = "log"
    CALLBACK = "callback"


@dataclass(frozen=True)
class PurchaseEvent:
    estimated_profit: float
    source: PurchaseSource
    item_name: str | None = None


class LicenseStatus(str, Enum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"
    TEMPORARY_ERROR = "temporary_error"


@dataclass(frozen=True)
class LicenseState:
    status: LicenseStatus = LicenseStatus.UNKNOWN
    code: str | None = None
    message: str | None = None
    expires_at: str | None = None
    remaining_seconds: int | None = None


@dataclass(frozen=True)
class SettingsSnapshot:
    minimum_profit_percentage: float = 40.0
    max_purchase_value: int = 1_000_000
    click_delay: float = 0.3
    page_delay: float = 0.5
    category_sequence: tuple[str, ...] = ()
    category_enabled: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "category_enabled",
            MappingProxyType(dict(self.category_enabled)),
        )


class SettingsIssueKind(str, Enum):
    INVALID_JSON = "invalid_json"
    INVALID_ROOT = "invalid_root"
    INVALID_VALUE = "invalid_value"
    IO_ERROR = "io_error"


@dataclass(frozen=True)
class SettingsIssue:
    kind: SettingsIssueKind
    message: str


@dataclass(frozen=True)
class SettingsLoadResult:
    snapshot: SettingsSnapshot
    issue: SettingsIssue | None = None


@dataclass(frozen=True)
class SettingsSaveResult:
    success: bool
    issue: SettingsIssue | None = None
