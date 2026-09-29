"""Minimal diagnostic window proving the Qt architecture end to end."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....application.orchestrator import ApplicationOrchestrator
from ....application.state import ApplicationSnapshot
from ....application.types import BotMode
from ..bridge import QtApplicationBridge


class MainWindow(QMainWindow):
    def __init__(
        self,
        orchestrator: ApplicationOrchestrator,
        bridge: QtApplicationBridge,
    ) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._bridge = bridge
        self._updating_mode = False

        self.setWindowTitle("AlbionMKT")
        self.resize(1200, 720)
        self.setMinimumSize(800, 520)
        self._build_ui()
        self._connect_bridge()
        self.render_snapshot(orchestrator.snapshot())

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("AlbionMKT — Diagnóstico Qt")
        title.setObjectName("title")
        root.addWidget(title)

        summary = QGridLayout()
        summary.setSpacing(12)
        summary.addWidget(self._build_status_panel(), 0, 0)
        summary.addWidget(self._build_metrics_panel(), 0, 1)
        summary.addWidget(self._build_settings_panel(), 1, 0)
        summary.addWidget(self._build_controls_panel(), 1, 1)
        summary.setColumnStretch(0, 1)
        summary.setColumnStretch(1, 1)
        root.addLayout(summary)

        event_group = QGroupBox("Último evento")
        event_layout = QVBoxLayout(event_group)
        self.last_event_label = QLabel("Nenhuma observação recebida nesta sessão.")
        self.last_event_label.setWordWrap(True)
        event_layout.addWidget(self.last_event_label)
        root.addWidget(event_group)

        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)
        root.addStretch(1)

        self.setCentralWidget(central)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #10151c; color: #e7edf4; }
            QGroupBox { border: 1px solid #33404d; margin-top: 10px; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLabel#title { font-size: 22px; font-weight: 700; color: #e3b567; }
            QLabel#error { color: #ff8b7d; min-height: 22px; }
            QPushButton, QComboBox { background: #25313d; border: 1px solid #52606d;
                                     padding: 8px 12px; border-radius: 3px; }
            QPushButton:hover { background: #344454; }
            """
        )

    def _build_status_panel(self) -> QGroupBox:
        group = QGroupBox("Status do bot")
        form = QFormLayout(group)
        self.status_label = QLabel("Parado")
        self.mode_label = QLabel("Compra")
        form.addRow("Status:", self.status_label)
        form.addRow("Modo:", self.mode_label)
        return group

    def _build_metrics_panel(self) -> QGroupBox:
        group = QGroupBox("Métricas da sessão")
        form = QFormLayout(group)
        self.items_label = QLabel("0")
        self.opportunities_label = QLabel("0")
        self.purchases_label = QLabel("0")
        self.profit_label = QLabel("0,00")
        form.addRow("Itens analisados:", self.items_label)
        form.addRow("Oportunidades:", self.opportunities_label)
        form.addRow("Compras:", self.purchases_label)
        form.addRow("Lucro estimado:", self.profit_label)
        return group

    def _build_settings_panel(self) -> QGroupBox:
        group = QGroupBox("Configurações carregadas")
        form = QFormLayout(group)
        self.max_percentage_label = QLabel("—")
        self.max_value_label = QLabel("—")
        form.addRow("Lucro mínimo por venda:", self.max_percentage_label)
        form.addRow("Valor máximo:", self.max_value_label)
        return group

    def _build_controls_panel(self) -> QGroupBox:
        group = QGroupBox("Controles")
        layout = QVBoxLayout(group)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Compra", BotMode.BUY.value)
        self.mode_combo.addItem("Fechar ordens", BotMode.CLOSE.value)
        layout.addWidget(self.mode_combo)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Iniciar")
        self.stop_button = QPushButton("Parar")
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        layout.addLayout(buttons)

        note = QLabel("O runtime do bot ainda não é iniciado pela interface Qt.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.start_button.clicked.connect(self._start_bot)
        self.stop_button.clicked.connect(self._stop_bot)
        self.mode_combo.currentIndexChanged.connect(self._change_mode)
        return group

    def _connect_bridge(self) -> None:
        queued = Qt.ConnectionType.QueuedConnection
        self._bridge.state_changed.connect(self.render_snapshot, queued)
        self._bridge.application_error.connect(self.show_application_error, queued)

    @Slot(object)
    def render_snapshot(self, snapshot: ApplicationSnapshot) -> None:
        self.status_label.setText(
            "Executando" if snapshot.bot_status.value == "running" else "Parado"
        )
        self.mode_label.setText(
            "Fechar ordens" if snapshot.bot_mode is BotMode.CLOSE else "Compra"
        )
        self.items_label.setText(str(snapshot.items_analyzed))
        self.opportunities_label.setText(str(snapshot.opportunities))
        self.purchases_label.setText(str(snapshot.purchases_count))
        self.profit_label.setText(f"{snapshot.estimated_profit:,.2f}")
        self.max_percentage_label.setText(
            f"{snapshot.settings.minimum_profit_percentage:g}%"
        )
        self.max_value_label.setText(f"{snapshot.settings.max_purchase_value:,}")

        if snapshot.last_observation is not None:
            observation = snapshot.last_observation
            self.last_event_label.setText(
                f"{observation.item_name} — venda {observation.sell_price:,}, "
                f"compra {observation.buy_price:,}, custo "
                f"{observation.cost_percentage:g}%"
            )
        elif snapshot.last_purchase is not None:
            self.last_event_label.setText(
                f"Compra registrada — lucro estimado "
                f"{snapshot.last_purchase.estimated_profit:,.2f}"
            )

        self._updating_mode = True
        try:
            index = self.mode_combo.findData(snapshot.bot_mode.value)
            if index >= 0:
                self.mode_combo.setCurrentIndex(index)
        finally:
            self._updating_mode = False

        if snapshot.last_error is not None:
            self.show_application_error(snapshot.last_error)

    @Slot(object)
    def show_application_error(self, error: object) -> None:
        message = getattr(error, "message", str(error))
        self.error_label.setText(f"Erro: {message}")

    @Slot()
    def _start_bot(self) -> None:
        self._orchestrator.start_bot(self._selected_mode())

    @Slot()
    def _stop_bot(self) -> None:
        self._orchestrator.stop_bot()

    @Slot(int)
    def _change_mode(self, _index: int) -> None:
        if self._updating_mode:
            return
        self._orchestrator.change_bot_mode(self._selected_mode())

    def _selected_mode(self) -> BotMode:
        try:
            return BotMode(str(self.mode_combo.currentData()))
        except ValueError:
            return BotMode.BUY

    def closeEvent(self, event) -> None:
        self._bridge.cleanup()
        super().closeEvent(event)
