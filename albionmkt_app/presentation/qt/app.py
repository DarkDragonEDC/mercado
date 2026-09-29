"""Composition root and independent entrypoint for the new Qt frontend."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from app_paths import user_data_dir

from ...adapters import (
    BotControlAdapter,
    LegacyBotLogParser,
    LegacySettingsAdapter,
    PurchaseEventNormalizer,
)
from ...application.events import ApplicationEventDispatcher
from ...application.orchestrator import ApplicationOrchestrator
from ...application.state import ApplicationState
from .bridge import QtApplicationBridge
from .windows import MainWindow


@dataclass(frozen=True)
class QtApplicationRuntime:
    application: QApplication
    orchestrator: ApplicationOrchestrator
    bridge: QtApplicationBridge
    window: MainWindow


def build_application(
    argv: Sequence[str] | None = None,
    *,
    data_directory: str | Path | None = None,
    application: QApplication | None = None,
) -> QtApplicationRuntime:
    qt_application = application or QApplication(list(argv or sys.argv))
    qt_application.setApplicationName("AlbionMKT")

    data_path = (
        Path(data_directory) if data_directory is not None else user_data_dir()
    )
    bot_control = BotControlAdapter(data_path / "bot_control.json")
    settings = LegacySettingsAdapter(data_path / "offsets.json")
    parser = LegacyBotLogParser()
    purchases = PurchaseEventNormalizer()
    dispatcher = ApplicationEventDispatcher()
    state = ApplicationState()
    orchestrator = ApplicationOrchestrator(
        bot_control,
        settings,
        parser=parser,
        purchases=purchases,
        state=state,
        events=dispatcher,
    )
    bridge = QtApplicationBridge(orchestrator, dispatcher)
    window = MainWindow(orchestrator, bridge)

    orchestrator.refresh_bot_state()
    orchestrator.load_settings()
    window.render_snapshot(orchestrator.snapshot())

    return QtApplicationRuntime(qt_application, orchestrator, bridge, window)


def main(argv: Sequence[str] | None = None) -> int:
    runtime = build_application(argv)
    runtime.window.show()
    try:
        return runtime.application.exec()
    finally:
        runtime.bridge.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

