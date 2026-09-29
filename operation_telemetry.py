"""Persistencia leve de logs e telemetria do MKT.

Este modulo nao conhece Tkinter nem a automacao. A interface apenas enfileira os
registros; uma thread dedicada grava os arquivos para que o caminho de cliques
nunca espere pelo disco.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime


class BackgroundLogWriter:
    """Grava o log humano e eventos JSONL em lotes, fora da thread da UI."""

    def __init__(self, log_dir: str, *, session_id: str | None = None):
        self.log_dir = log_dir
        self.session_id = session_id or uuid.uuid4().hex
        self._queue: queue.Queue = queue.Queue(maxsize=10_000)
        self._closed = False
        self.dropped_records = 0
        os.makedirs(self.log_dir, exist_ok=True)
        self._thread = threading.Thread(
            target=self._run,
            name="mkt-log-writer",
            daemon=True,
        )
        self._thread.start()

    def raw_path_for(self, moment: datetime | None = None) -> str:
        moment = moment or datetime.now()
        return os.path.join(self.log_dir, f"operacoes-{moment:%Y-%m-%d}.log")

    def telemetry_path_for(self, moment: datetime | None = None) -> str:
        moment = moment or datetime.now()
        return os.path.join(self.log_dir, f"telemetria-{moment:%Y-%m-%d}.jsonl")

    def submit(self, message: str, event: dict | None = None) -> bool:
        if self._closed:
            return False
        record = {
            "timestamp": datetime.now(),
            "message": str(message),
            "event": dict(event) if event else None,
        }
        try:
            self._queue.put_nowait(record)
            return True
        except queue.Full:
            self.dropped_records += 1
            return False

    def flush(self, timeout: float = 1.0) -> bool:
        """Espera apenas em encerramentos/testes; nunca e usado em um clique."""
        deadline = time.monotonic() + max(0.0, timeout)
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def close(self, timeout: float = 1.0) -> None:
        self._closed = True
        self.flush(timeout)

    def _run(self) -> None:
        while True:
            try:
                first = self._queue.get(timeout=0.25)
            except queue.Empty:
                if self._closed:
                    return
                continue

            batch = [first]
            for _ in range(127):
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            try:
                self._write_batch(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _write_batch(self, batch: list[dict]) -> None:
        raw_by_path: dict[str, list[str]] = {}
        json_by_path: dict[str, list[str]] = {}
        for record in batch:
            moment = record["timestamp"]
            raw_path = self.raw_path_for(moment)
            raw_by_path.setdefault(raw_path, []).append(
                f"[{moment:%Y-%m-%d %H:%M:%S}] {record['message']}\n"
            )

            event = record.get("event")
            if event:
                payload = {
                    "timestamp": moment.isoformat(timespec="milliseconds"),
                    "session_id": self.session_id,
                    **event,
                }
                telemetry_path = self.telemetry_path_for(moment)
                json_by_path.setdefault(telemetry_path, []).append(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
                )

        try:
            for path, lines in raw_by_path.items():
                with open(path, "a", encoding="utf-8") as handle:
                    handle.writelines(lines)
            for path, lines in json_by_path.items():
                with open(path, "a", encoding="utf-8") as handle:
                    handle.writelines(lines)
        except OSError:
            # Falha de diagnostico nunca pode interromper uma automacao.
            return
