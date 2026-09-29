"""Small synchronous event mechanism independent from GUI event loops."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import Callable, TypeVar

from ..types import (
    BotMode,
    BotStatus,
    LicenseState,
    MarketItemObservation,
    PurchaseEvent,
    SettingsSnapshot,
)


@dataclass(frozen=True)
class MarketObservationReceived:
    observation: MarketItemObservation


@dataclass(frozen=True)
class PurchaseRecorded:
    purchase: PurchaseEvent


@dataclass(frozen=True)
class PurchaseCallbackReceived:
    """Informative callback data; it is not a canonical purchase count."""

    purchase: PurchaseEvent


@dataclass(frozen=True)
class BotStatusChanged:
    status: BotStatus
    mode: BotMode | None = None


@dataclass(frozen=True)
class SettingsChanged:
    settings: SettingsSnapshot


@dataclass(frozen=True)
class LicenseStateChanged:
    license_state: LicenseState


@dataclass(frozen=True)
class BotErrorReceived:
    message: str
    code: str | None = None


@dataclass(frozen=True)
class SessionMetricsReset:
    pass


EventT = TypeVar("EventT")
Listener = Callable[[object], None]


class ApplicationEventDispatcher:
    """Publish application events to a snapshot of registered listeners."""

    def __init__(self) -> None:
        self._listeners: dict[type[object], list[Listener]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(
        self, event_type: type[EventT], listener: Callable[[EventT], None]
    ) -> Callable[[], None]:
        with self._lock:
            self._listeners[event_type].append(listener)  # type: ignore[arg-type]

        def unsubscribe() -> None:
            with self._lock:
                listeners = self._listeners.get(event_type, [])
                if listener in listeners:
                    listeners.remove(listener)  # type: ignore[arg-type]

        return unsubscribe

    def publish(self, event: object) -> None:
        with self._lock:
            listeners = tuple(self._listeners.get(type(event), ()))
        for listener in listeners:
            listener(event)


__all__ = [
    "ApplicationEventDispatcher",
    "BotErrorReceived",
    "BotStatusChanged",
    "LicenseStateChanged",
    "MarketObservationReceived",
    "PurchaseCallbackReceived",
    "PurchaseRecorded",
    "SessionMetricsReset",
    "SettingsChanged",
]
