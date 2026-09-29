"""Atualizador externo e reversivel do MKT.

O executavel deste modulo deve ficar fora da pasta instalada do MKT. Assim ele
consegue substituir a aplicacao depois que o processo principal for encerrado.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - modo CLI ainda deve funcionar em ambientes sem Tk.
    tk = None
    ttk = None


MAX_PACKAGE_BYTES = 4 * 1024 * 1024 * 1024
STATUS_FILENAME = "update-status.json"


class UpdateError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def wait_for_process(pid: int, timeout: float = 30.0) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if os.name != "nt":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.1)
        raise UpdateError("O MKT nao encerrou a tempo.")

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        if result == wait_timeout:
            raise UpdateError("O MKT nao encerrou a tempo.")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def download_package(url: str, destination: Path, expected_size: int, *, on_progress=None) -> None:
    if not url.lower().startswith("https://"):
        raise UpdateError("O pacote de atualizacao precisa usar HTTPS.")
    if expected_size <= 0 or expected_size > MAX_PACKAGE_BYTES:
        raise UpdateError("Tamanho de pacote invalido.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "MKT-Updater/1.0"})
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > expected_size or received > MAX_PACKAGE_BYTES:
                    raise UpdateError("O pacote recebido excede o tamanho informado.")
                output.write(block)
                if on_progress is not None:
                    on_progress(received, expected_size)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"Falha ao baixar a atualizacao: {exc}") from exc
    if received != expected_size:
        destination.unlink(missing_ok=True)
        raise UpdateError("O tamanho do pacote baixado nao confere.")


def verify_sha256(path: Path, expected_sha256: str, expected_size: int) -> None:
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise UpdateError("SHA-256 esperado invalido.")
    try:
        if path.stat().st_size != expected_size:
            raise UpdateError("O tamanho do pacote nao confere.")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise UpdateError(f"Nao foi possivel ler o pacote: {exc}") from exc
    if digest.hexdigest() != expected:
        raise UpdateError("A verificacao SHA-256 do pacote falhou.")


def _safe_archive_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return False
    # Bloqueia links simbolicos Unix armazenados em ZIP.
    mode = (info.external_attr >> 16) & 0o170000
    return mode != 0o120000


def extract_payload(package: Path, destination: Path) -> Path:
    try:
        with zipfile.ZipFile(package) as archive:
            members = archive.infolist()
            if not members or any(not _safe_archive_member(info) for info in members):
                raise UpdateError("O pacote contem caminhos inseguros.")
            uncompressed = sum(info.file_size for info in members)
            if uncompressed <= 0 or uncompressed > MAX_PACKAGE_BYTES:
                raise UpdateError("Conteudo descompactado invalido.")
            archive.extractall(destination)
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(f"Pacote de atualizacao invalido: {exc}") from exc
    payload = destination / "app"
    if not payload.is_dir():
        raise UpdateError("O pacote nao possui a pasta app esperada.")
    return payload


def apply_update(package: Path, install_dir: Path, *, executable_name: str = "MKT.exe", on_stage=None) -> Path:
    install = install_dir.resolve()
    if not install.is_dir() or not (install / executable_name).is_file():
        raise UpdateError("A instalacao atual do MKT nao foi encontrada.")
    parent = install.parent
    backup = parent / f"{install.name}.previous"
    staging_root = Path(tempfile.mkdtemp(prefix="mkt-update-", dir=parent))
    moved_current = False
    try:
        if on_stage is not None:
            on_stage("Preparando os arquivos da nova versao...")
        payload = extract_payload(package, staging_root)
        if not (payload / executable_name).is_file():
            raise UpdateError("A nova versao nao contem o executavel do MKT.")
        if backup.exists():
            shutil.rmtree(backup)
        if on_stage is not None:
            on_stage("Preservando a versao anterior para retorno seguro...")
        os.replace(install, backup)
        moved_current = True
        if on_stage is not None:
            on_stage("Instalando a nova versao...")
        os.replace(payload, install)
        if not (install / executable_name).is_file():
            raise UpdateError("A nova instalacao nao foi validada.")
        return backup
    except Exception:
        if moved_current:
            try:
                if install.exists():
                    shutil.rmtree(install)
                os.replace(backup, install)
            except OSError as rollback_error:
                raise UpdateError(f"Falha ao atualizar e ao restaurar: {rollback_error}")
        raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def launch_application(install_dir: Path, executable_name: str) -> None:
    executable = install_dir / executable_name
    if not executable.is_file():
        raise UpdateError("Executavel nao encontrado depois da atualizacao.")
    os.startfile(str(executable))


def _format_size(value: int) -> str:
    if value < 1024 * 1024:
        return f"{value / 1024:.0f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _parse_notes(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(note).strip() for note in parsed if str(note).strip()][:8]


def perform_update(args, *, on_stage=None, on_progress=None) -> Path:
    """Executa a troca verificavel sem depender da interface grafica."""

    status_path = args.status_file or (
        Path(os.environ.get("LOCALAPPDATA", ".")) / "AlbionMKT" / STATUS_FILENAME
    )
    downloaded: Path | None = None
    try:
        if on_stage is not None:
            on_stage("Aguardando o MKT encerrar com seguranca...")
        wait_for_process(args.pid)
        package = args.package
        if args.url:
            download_dir = status_path.parent / "downloads"
            downloaded = download_dir / "mkt-update.zip"
            if on_stage is not None:
                on_stage("Baixando a atualizacao protegida...")
            download_package(args.url, downloaded, args.size, on_progress=on_progress)
            package = downloaded
        if package is None:
            raise UpdateError("Pacote nao informado.")
        if on_stage is not None:
            on_stage("Verificando a integridade do pacote...")
        verify_sha256(package, args.sha256, args.size)
        backup = apply_update(
            package,
            args.install_dir,
            executable_name=args.executable,
            on_stage=on_stage,
        )
        _atomic_json(status_path, {"ok": True, "backup": str(backup), "message": "Atualizacao aplicada."})
        return backup
    except Exception as exc:
        _atomic_json(status_path, {"ok": False, "message": str(exc)})
        raise
    finally:
        if downloaded is not None:
            downloaded.unlink(missing_ok=True)


class UpdateProgressWindow:
    """Janela externa que permanece ativa enquanto o MKT e substituido."""

    def __init__(self, args):
        self.args = args
        self.root = tk.Tk()
        self.root.title("MKT - Atualizando")
        self.root.geometry("620x430")
        self.root.resizable(False, False)
        self.root.configure(bg="#07111e")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.attributes("-topmost", True)
        self.result = 1
        self._build()

    def _build(self):
        panel = tk.Frame(self.root, bg="#0d1c2e", padx=30, pady=26)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        version = self.args.version or "nova versao"
        tk.Label(panel, text="ATUALIZANDO O MKT", bg="#0d1c2e", fg="#e7c36f",
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(panel, text=f"Versao {version}", bg="#0d1c2e", fg="#8fdfc3",
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(5, 16))
        tk.Label(panel, text="Nao feche esta janela. O MKT vai reabrir automaticamente\n"
                 "quando a atualizacao terminar.", bg="#0d1c2e", fg="#d5deea",
                 justify="left").pack(anchor="w")

        self.stage = tk.StringVar(value="Preparando atualizacao...")
        tk.Label(panel, textvariable=self.stage, bg="#091624", fg="#f4f1e8",
                 font=("Segoe UI Semibold", 10), anchor="w", padx=12, pady=10).pack(fill="x", pady=(18, 8))
        self.progress_value = tk.DoubleVar(value=0)
        ttk.Style(self.root).configure("MKT.Horizontal.TProgressbar", troughcolor="#091624", background="#35a97c")
        ttk.Progressbar(panel, style="MKT.Horizontal.TProgressbar", maximum=100,
                        variable=self.progress_value).pack(fill="x")
        self.detail = tk.StringVar(value="0%")
        tk.Label(panel, textvariable=self.detail, bg="#0d1c2e", fg="#a4b3c3",
                 anchor="e").pack(fill="x", pady=(5, 0))

        notes = _parse_notes(self.args.notes_json)
        if notes:
            tk.Label(panel, text="O QUE ESTA SENDO ATUALIZADO", bg="#0d1c2e", fg="#e7c36f",
                     font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(18, 6))
            tk.Label(panel, text="\n".join(f"• {note}" for note in notes), bg="#091624",
                     fg="#c9d8e7", justify="left", anchor="nw", padx=12, pady=10,
                     wraplength=500).pack(fill="x")

        self.close_button = tk.Button(panel, text="FECHAR", command=self.root.destroy,
                                      state="disabled", bg="#12243a", fg="#f4f1e8",
                                      relief="flat", padx=18, pady=8)
        self.close_button.pack(side="bottom", anchor="e", pady=(16, 0))

    def _schedule(self, callback):
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _stage(self, text: str):
        self._schedule(lambda: self.stage.set(text))

    def _progress(self, received: int, total: int):
        percentage = min(100.0, (received / total * 100) if total else 0.0)
        self._schedule(lambda: (
            self.progress_value.set(percentage),
            self.detail.set(f"{percentage:.0f}%  •  {_format_size(received)} de {_format_size(total)}"),
        ))

    def _worker(self):
        try:
            perform_update(self.args, on_stage=self._stage, on_progress=self._progress)
        except Exception as exc:
            self._schedule(lambda: self._failed(str(exc)))
            return
        self._schedule(self._succeeded)

    def _failed(self, message: str):
        self.stage.set("Atualizacao nao concluida. Sua versao anterior foi preservada.")
        self.detail.set(message)
        self.close_button.config(state="normal")

    def _succeeded(self):
        self.progress_value.set(100)
        self.stage.set("Atualizacao concluida. Abrindo o MKT...")
        self.detail.set("Pronto. Suas configuracoes foram preservadas.")
        self.result = 0
        self.root.after(900, self._restart_and_close)

    def _restart_and_close(self):
        try:
            if not self.args.no_restart:
                launch_application(self.args.install_dir.resolve(), self.args.executable)
        finally:
            self.root.destroy()

    def run(self) -> int:
        threading.Thread(target=self._worker, name="mkt-update", daemon=True).start()
        self.root.mainloop()
        return self.result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atualizador seguro do MKT")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", type=Path)
    source.add_argument("--url")
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--executable", default="MKT.exe")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--version", default="")
    parser.add_argument("--notes-json", default="[]")
    parser.add_argument("--no-ui", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.no_ui or tk is None:
            perform_update(args)
            if not args.no_restart:
                launch_application(args.install_dir.resolve(), args.executable)
            return 0
        return UpdateProgressWindow(args).run()
    except Exception:
        # ``perform_update`` ja registra um status detalhado que o MKT consegue
        # exibir na proxima abertura; o atualizador nao deve mostrar traceback.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
