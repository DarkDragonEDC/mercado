"""Licenciamento HTTPS do Albion Elite, sem credenciais administrativas."""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import tkinter as tk
from tkinter import messagebox, ttk

from app_paths import migrate_legacy_state, user_file
from app_version import APP_VERSION


# Serviço independente sob controle do proprietário do AlbionMKT.
# A variável ALBIONMKT_API_BASE_URL continua permitindo homologação local.
DEFAULT_API_BASE_URL = "https://albionmkt-license.albionmkt053.workers.dev"
# A copia de contingencia pode apontar para uma API isolada durante os testes.
# Sem esta variavel, o comportamento da versao atual permanece exatamente igual.
API_BASE_URL = os.environ.get("ALBIONMKT_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
ACTIVATE_URL = f"{API_BASE_URL}/api/licenses/activate"
VALIDATE_URL = f"{API_BASE_URL}/api/licenses/validate"
PURCHASE_MODULE_ID = "purchase_orders"
SALES_MODULE_ID = "sales_orders"
SUPPORTED_MODULE_IDS = frozenset({PURCHASE_MODULE_ID, SALES_MODULE_ID})
# Mantido para compatibilidade com integrações antigas que importam MODULE_ID.
MODULE_ID = PURCHASE_MODULE_ID
VALIDATION_INTERVAL_MS = 15 * 60 * 1000
REQUEST_TIMEOUT_SECONDS = (5, 12)
LICENSE_FILENAME = "license.json"

ERROR_MESSAGES = {
    "INVALID_KEY": "Key invalida. Confira o codigo informado.",
    "REVOKED": "Esta licenca foi revogada.",
    "EXPIRED": "Esta licenca esta expirada.",
    "HWID_REQUIRED": "Nao foi possivel identificar este computador.",
    "NOT_ACTIVATED": "Este computador ainda nao foi ativado.",
    "DEVICE_LIMIT": "O limite de computadores desta key foi atingido.",
    "MODULE_NOT_ALLOWED": "Esta key não possui acesso a este aplicativo.",
    "RATE_LIMIT": "Muitas tentativas. Aguarde um momento e tente novamente.",
    "SERVER_ERROR": "Falha temporaria no servidor. Tente novamente em instantes.",
}

BLOCKING_CODES = {
    "INVALID_KEY",
    "REVOKED",
    "EXPIRED",
    "HWID_REQUIRED",
    "NOT_ACTIVATED",
    "DEVICE_LIMIT",
    "MODULE_NOT_ALLOWED",
}


class LicenseError(Exception):
    def __init__(self, code: str, message: str, *, temporary: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.temporary = temporary


class HwidError(LicenseError):
    def __init__(self, message: str = ERROR_MESSAGES["HWID_REQUIRED"]):
        super().__init__("HWID_REQUIRED", message)


@dataclass(frozen=True)
class LicenseResult:
    key: str
    expires_at: str | None
    remaining_seconds: int | None
    newly_activated: bool
    modules: tuple[str, ...] | None
    raw: dict[str, Any]


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def license_path() -> Path:
    migrate_legacy_state(application_dir())
    return user_file(LICENSE_FILENAME)


def _clean_identifier(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if not cleaned:
        return None
    normalized = re.sub(r"[^A-Z0-9]", "", cleaned.upper())
    placeholders = {
        "NONE",
        "NULL",
        "UNKNOWN",
        "DEFAULTSTRING",
        "TOBEFILLEDBYOEM",
        "SYSTEMSERIALNUMBER",
        "00000000",
        "FFFFFFFF",
    }
    if len(normalized) < 4 or normalized in placeholders:
        return None
    return cleaned


def _machine_guid() -> str | None:
    try:
        import winreg

        access = winreg.KEY_READ
        if hasattr(winreg, "KEY_WOW64_64KEY"):
            access |= winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return _clean_identifier(value)
    except (OSError, ImportError):
        return None


def _cim_identifiers() -> dict[str, str]:
    script = (
        "$ErrorActionPreference='Stop';"
        "$o=[ordered]@{};"
        "$o.SystemUuid=(Get-CimInstance Win32_ComputerSystemProduct).UUID;"
        "$o.BiosSerial=(Get-CimInstance Win32_BIOS).SerialNumber;"
        "$o.BoardSerial=(Get-CimInstance Win32_BaseBoard).SerialNumber;"
        "$o.CpuId=(Get-CimInstance Win32_Processor | Select-Object -First 1).ProcessorId;"
        "$o|ConvertTo-Json -Compress"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=True,
            creationflags=flags,
        )
        parsed = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}
    result: dict[str, str] = {}
    if isinstance(parsed, dict):
        for name, value in parsed.items():
            cleaned = _clean_identifier(value)
            if cleaned:
                result[str(name)] = cleaned
    return result


def get_stable_hwid() -> str:
    """Combina identificadores estaveis do Windows e retorna somente SHA-256."""

    identifiers: dict[str, str] = {}
    machine_guid = _machine_guid()
    if machine_guid:
        identifiers["MachineGuid"] = machine_guid
    identifiers.update(_cim_identifiers())

    # Exige combinacao real, evitando fallback para usuario, IP ou MAC isolado.
    if len(identifiers) < 2:
        raise HwidError()
    canonical = "|".join(
        f"{name}={identifiers[name].strip().upper()}" for name in sorted(identifiers)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_license() -> dict[str, Any] | None:
    path = license_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    allowed = {"key", "lastValidatedAt", "expiresAt", "appVersion"}
    if set(data) - allowed or not isinstance(data.get("key"), str):
        return None
    return {name: data.get(name) for name in allowed if name in data}


def save_license(key: str, expires_at: str | None) -> None:
    data = {
        "key": key,
        "lastValidatedAt": datetime.now(timezone.utc).isoformat(),
        "expiresAt": expires_at,
        "appVersion": APP_VERSION,
    }
    path = license_path()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def _server_message(code: str, payload: dict[str, Any]) -> str:
    if code in ERROR_MESSAGES:
        return ERROR_MESSAGES[code]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "Nao foi possivel validar a licenca. Tente novamente."


def request_license(action: str, key: str, hwid: str) -> LicenseResult:
    if action not in {"activate", "validate"}:
        raise ValueError("Acao de licenca invalida.")
    url = ACTIVATE_URL if action == "activate" else VALIDATE_URL
    request_data = {"key": key, "hwid": hwid, "appVersion": APP_VERSION}
    try:
        response = requests.post(
            url,
            json=request_data,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise LicenseError(
            "NETWORK_ERROR",
            "Nao foi possivel conectar ao servidor de licencas. Verifique sua internet e tente novamente.",
            temporary=True,
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise LicenseError(
            "SERVER_ERROR", ERROR_MESSAGES["SERVER_ERROR"], temporary=True
        ) from exc
    if not isinstance(payload, dict):
        raise LicenseError("SERVER_ERROR", ERROR_MESSAGES["SERVER_ERROR"], temporary=True)

    code = str(payload.get("code") or "SERVER_ERROR")
    valid = payload.get("valid") is True and code == "OK"
    if not valid:
        temporary = code in {"RATE_LIMIT", "SERVER_ERROR"} or response.status_code >= 500
        raise LicenseError(code, _server_message(code, payload), temporary=temporary)

    modules_value = payload.get("modules")
    modules: tuple[str, ...] | None = None
    if modules_value is not None:
        if not isinstance(modules_value, list) or not all(
            isinstance(item, str) for item in modules_value
        ):
            raise LicenseError("SERVER_ERROR", ERROR_MESSAGES["SERVER_ERROR"], temporary=True)
        modules = tuple(modules_value)
        if not SUPPORTED_MODULE_IDS.intersection(modules):
            raise LicenseError(
                "MODULE_NOT_ALLOWED", ERROR_MESSAGES["MODULE_NOT_ALLOWED"]
            )

    remaining = payload.get("remainingSeconds")
    if not isinstance(remaining, int):
        remaining = None
    expires_at = payload.get("expiresAt")
    if not isinstance(expires_at, str) or not expires_at.strip():
        expires_at = None
    return LicenseResult(
        key=key,
        expires_at=expires_at,
        remaining_seconds=remaining,
        newly_activated=payload.get("newlyActivated") is True,
        modules=modules,
        raw=payload,
    )


def format_expiration(value: str | None) -> str:
    if not value:
        return "Vencimento nao informado pelo servidor."
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        local = parsed.astimezone()
        return f"Vencimento: {local:%d/%m/%Y %H:%M}"
    except ValueError:
        return f"Vencimento: {value}"


def mask_key(key: str) -> str:
    cleaned = key.strip()
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def stop_automations() -> None:
    try:
        path = user_file("bot_control.json")
        mode = "buy"
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(current, dict) and isinstance(current.get("mode"), str):
                mode = current["mode"]
        except (OSError, json.JSONDecodeError):
            pass
        path.write_text(
            json.dumps({"run": False, "mode": mode}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def run_on_tk(root: tk.Misc, callback: Callable[..., None], *args: Any) -> None:
    """Agenda uma chamada no Tk sem capturar variaveis temporarias de ``except``."""

    root.after(
        0,
        lambda scheduled_callback=callback, scheduled_args=args: scheduled_callback(
            *scheduled_args
        ),
    )


class ActivationWindow:
    def __init__(self, root: tk.Tk, on_approved: Callable[[LicenseResult], None]):
        self.root = root
        self.on_approved = on_approved
        self.hwid: str | None = None
        self.processing = False
        self.saved = load_license()

        self.window = tk.Toplevel(root)
        self.window.title("MKT - Ativacao")
        self.window.geometry("520x390")
        self.window.resizable(False, False)
        self.window.configure(bg="#121311")
        self.window.protocol("WM_DELETE_WINDOW", root.destroy)

        frame = tk.Frame(self.window, bg="#1d1d1a", padx=28, pady=24, highlightthickness=1, highlightbackground="#393730")
        frame.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(
            frame,
            text="MKT  •  ATIVACAO DE LICENCA",
            bg="#1d1d1a",
            fg="#c4a15f",
            font=("Segoe UI Semibold", 17),
        ).pack(pady=(0, 8))
        tk.Label(
            frame,
            text="Informe a chave de acesso liberada para o MKT.",
            bg="#1d1d1a",
            fg="#f0ece3",
            font=("Segoe UI", 10),
        ).pack(pady=(0, 18))

        self.key_var = tk.StringVar(value=(self.saved or {}).get("key", ""))
        self.key_entry = tk.Entry(
            frame,
            textvariable=self.key_var,
            font=("Consolas", 11),
            justify="center",
            bg="#0d0e0c",
            fg="#f0ece3",
            insertbackground="#f0ece3",
            relief="flat",
        )
        self.key_entry.pack(fill="x", ipady=10)
        self.key_entry.bind("<Return>", lambda _event: self.activate())

        self.activate_button = tk.Button(
            frame,
            text="Ativar licenca",
            command=self.activate,
            bg="#397f5e",
            fg="#f0ece3",
            activebackground="#469873",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            cursor="hand2",
        )
        self.activate_button.pack(fill="x", pady=(14, 8), ipady=7)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 8))
        self.progress.pack_forget()

        self.status = tk.Label(
            frame,
            text="",
            wraplength=430,
            justify="center",
            bg="#1d1d1a",
            fg="#9e3f47",
            font=("Segoe UI Semibold", 10),
        )
        self.status.pack(fill="x", pady=(4, 4))
        self.expiration = tk.Label(
            frame,
            text="",
            bg="#1d1d1a",
            fg="#397f5e",
            font=("Segoe UI", 10),
        )
        self.expiration.pack(fill="x")

        actions = tk.Frame(frame, bg="#1d1d1a")
        actions.pack(fill="x", pady=(12, 0))
        self.retry_button = tk.Button(
            actions,
            text="Tentar novamente",
            command=self.retry,
            bg="#2a2924",
            fg="#f0ece3",
            relief="flat",
        )
        self.retry_button.pack(side="left", expand=True, fill="x", padx=(0, 5), ipady=5)
        self.change_button = tk.Button(
            actions,
            text="Trocar key",
            command=self.change_key,
            bg="#2a2924",
            fg="#f0ece3",
            relief="flat",
        )
        self.change_button.pack(side="left", expand=True, fill="x", padx=(5, 0), ipady=5)

        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - self.window.winfo_width()) // 2
        y = (self.window.winfo_screenheight() - self.window.winfo_height()) // 2
        self.window.geometry(f"+{x}+{y}")
        self.window.after(50, self._initialize)

    def _initialize(self) -> None:
        try:
            self.hwid = get_stable_hwid()
        except LicenseError as exc:
            self._show_error(exc)
            return
        if self.saved and self.saved.get("key"):
            self._request("validate", str(self.saved["key"]))
        else:
            self.status.config(text="Digite sua key para continuar.", fg="#f0ece3")
            self.key_entry.focus_set()

    def _set_processing(self, active: bool, text: str = "") -> None:
        self.processing = active
        state = "disabled" if active else "normal"
        self.activate_button.config(state=state)
        self.retry_button.config(state=state)
        self.change_button.config(state=state)
        self.key_entry.config(state=state)
        if active:
            self.status.config(text=text, fg="#c4a15f")
            self.progress.pack(fill="x", pady=(0, 8), before=self.status)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def activate(self) -> None:
        if self.processing:
            return
        key = self.key_var.get().strip()
        if not key:
            self.status.config(text="Informe uma key para ativar.", fg="#d33b3b")
            self.key_entry.focus_set()
            return
        if not self.hwid:
            try:
                self.hwid = get_stable_hwid()
            except LicenseError as exc:
                self._show_error(exc)
                return
        self._request("activate", key)

    def retry(self) -> None:
        if self.processing:
            return
        saved_key = (self.saved or {}).get("key")
        current_key = self.key_var.get().strip()
        if saved_key and current_key == saved_key:
            self._request("validate", current_key)
        else:
            self.activate()

    def change_key(self) -> None:
        if self.processing:
            return
        self.key_var.set("")
        self.status.config(text="Informe a nova key. A key salva so sera substituida apos a aprovacao.", fg="#e6d7cc")
        self.expiration.config(text="")
        self.key_entry.focus_set()

    def _request(self, action: str, key: str) -> None:
        if not self.hwid:
            self._show_error(HwidError())
            return
        label = "Validando licenca..." if action == "validate" else "Ativando licenca..."
        self._set_processing(True, label)

        def worker() -> None:
            try:
                result = request_license(action, key, self.hwid or "")
            except LicenseError as exc:
                run_on_tk(self.root, self._show_error, exc)
            except Exception:
                error = LicenseError(
                    "SERVER_ERROR", ERROR_MESSAGES["SERVER_ERROR"], temporary=True
                )
                run_on_tk(self.root, self._show_error, error)
            else:
                run_on_tk(self.root, self._approved, result)

        threading.Thread(target=worker, name="license-request", daemon=True).start()

    def _show_error(self, error: LicenseError) -> None:
        self._set_processing(False)
        self.status.config(text=error.message, fg="#d33b3b")
        self.expiration.config(text="")

    def _approved(self, result: LicenseResult) -> None:
        try:
            save_license(result.key, result.expires_at)
        except OSError:
            self._show_error(
                LicenseError(
                    "LOCAL_STORAGE_ERROR",
                    "Licenca aprovada, mas nao foi possivel salvar a configuracao local.",
                )
            )
            return
        self.saved = load_license()
        self._set_processing(False)
        self.status.config(text="Licenca aprovada.", fg="#62c332")
        self.expiration.config(text=format_expiration(result.expires_at))
        self.root.after(1200, lambda: self._finish(result))

    def _finish(self, result: LicenseResult) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        self.on_approved(result)


class PeriodicValidator:
    def __init__(self, root: tk.Tk, key: str, hwid: str):
        self.root = root
        self.key = key
        self.hwid = hwid
        self.warning_visible = False
        self.after_id: str | None = None
        self.schedule()

    def schedule(self) -> None:
        self.after_id = self.root.after(VALIDATION_INTERVAL_MS, self._start)

    def _start(self) -> None:
        def worker() -> None:
            try:
                result = request_license("validate", self.key, self.hwid)
            except LicenseError as exc:
                run_on_tk(self.root, self._failed, exc)
            except Exception:
                error = LicenseError(
                    "SERVER_ERROR", ERROR_MESSAGES["SERVER_ERROR"], temporary=True
                )
                run_on_tk(self.root, self._failed, error)
            else:
                run_on_tk(self.root, self._passed, result)

        threading.Thread(target=worker, name="license-revalidation", daemon=True).start()

    def _passed(self, result: LicenseResult) -> None:
        try:
            save_license(result.key, result.expires_at)
        except OSError:
            pass
        self.warning_visible = False
        self.schedule()

    def _failed(self, error: LicenseError) -> None:
        if error.temporary:
            if not self.warning_visible:
                self.warning_visible = True
                messagebox.showwarning("Validacao de licenca", error.message, parent=self.root)
            self.schedule()
            return
        stop_automations()
        messagebox.showerror("Licenca bloqueada", error.message, parent=self.root)
        self.root.destroy()


def _remaining_label(seconds: int | None) -> str:
    if seconds is None:
        return "ATIVA"
    days, remainder = divmod(max(0, seconds), 86400)
    hours = remainder // 3600
    return f"{days}d {hours}h"


def result_to_key_info(result: LicenseResult) -> dict[str, Any]:
    """Adapta a resposta para o formato visual esperado pela interface existente."""

    return {
        "key": mask_key(result.key),
        "remaining": _remaining_label(result.remaining_seconds),
        "activation_date": datetime.now().strftime("%Y-%m-%d"),
        "expiresAt": result.expires_at,
        "modules": list(result.modules) if result.modules is not None else None,
        # A presença da lista indica o contrato modular novo. Respostas antigas
        # sem ``modules`` continuam com todos os menus disponíveis.
        "modulesEnforced": result.modules is not None,
    }


def has_module_access(key_info: dict[str, Any], module_id: str) -> bool:
    """Informa se a licenca permite um modulo da interface.

    Respostas antigas da API, sem o campo ``modules``, continuam liberadas para
    preservar compatibilidade com keys emitidas antes da divisao por modulos.
    """

    modules = key_info.get("modules")
    if modules is None:
        return True
    if not isinstance(modules, (list, tuple, set, frozenset)):
        return False
    return module_id in modules


def has_all_module_access(key_info: dict[str, Any], *module_ids: str) -> bool:
    """Exige todos os modulos informados, usado pelo ciclo Compra + Venda."""

    return all(has_module_access(key_info, module_id) for module_id in module_ids)
