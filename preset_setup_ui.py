"""Assistente Tk legado para aplicar presets antes da janela principal."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable

import bot
from app_paths import calibration_assets_dir
from calibration_presets import (
    PresetError,
    apply_preset,
    discover_presets,
    select_compatible_preset,
)
from coordinate_system import get_client_geometry, get_window_dpi, load_settings
from preset_diagnostics import write_preset_diagnostic
from preset_visual_validation import validate_buy_preset_passively


class PresetSetupWindow:
    """Seleciona, comprova e aplica um preset sem executar cliques."""

    def __init__(
        self,
        parent: tk.Tk,
        *,
        presets_dir: str | Path,
        asset_root: str | Path,
        settings_path: str | Path,
        find_albion_window: Callable[[], object | None],
        on_complete: Callable[[], None],
    ):
        self.parent = parent
        self.presets_dir = Path(presets_dir)
        self.asset_root = Path(asset_root)
        self.settings_path = Path(settings_path)
        self.find_albion_window = find_albion_window
        self.on_complete = on_complete
        self.win = None
        self.preset = None
        self.geometry_info = None

        self.presets, self.preset_errors = discover_presets(
            self.presets_dir, asset_root=self.asset_root
        )
        self.diagnostic_log_path = write_preset_diagnostic(
            "wizard_opened",
            presets_discovered=len(self.presets),
            preset_errors=list(self.preset_errors),
            presets_dir=str(self.presets_dir),
        )
        self._build()
        self.inspect_environment()

    def _log(self, event: str, **details):
        path = write_preset_diagnostic(event, **details)
        if path is not None:
            self.diagnostic_log_path = path
        return path

    def _diagnostic_hint(self) -> str:
        if self.diagnostic_log_path is None:
            return ""
        return f"\nDiagnostico salvo em: {self.diagnostic_log_path}"

    def _build(self):
        self.win = tk.Toplevel(self.parent)
        self.win.title("MKT - Configuracao automatica")
        self.win.geometry("580x560")
        self.win.minsize(580, 480)
        self.win.resizable(True, True)
        self.win.configure(bg="#070c14")
        self.win.protocol("WM_DELETE_WINDOW", self.parent.destroy)

        frame = tk.Frame(
            self.win,
            bg="#0d1c2e",
            padx=28,
            pady=24,
            highlightthickness=1,
            highlightbackground="#294866",
        )
        frame.pack(fill="both", expand=True, padx=18, pady=18)

        # Reserve o rodape antes do conteudo variavel. O diagnostico visual pode
        # crescer depois da primeira validacao; se o rodape for empacotado por
        # ultimo, o Tk pode empurra-lo para fora de uma janela com altura fixa.
        buttons = tk.Frame(frame, bg="#0d1c2e")
        buttons.pack(side="bottom", fill="x", pady=(16, 0))
        self.retry_button = tk.Button(
            buttons,
            text="VERIFICAR NOVAMENTE",
            command=self.inspect_environment,
            bg="#12243a",
            fg="#f4f1e8",
            activebackground="#17314e",
            activeforeground="#ffffff",
            relief="flat",
            padx=13,
            pady=9,
        )
        self.retry_button.pack(side="left")
        self.validate_button = tk.Button(
            buttons,
            text="VALIDAR PRESET",
            command=self.validate_and_apply,
            state="disabled",
            bg="#8e7848",
            fg="#ffffff",
            activebackground="#e7c36f",
            activeforeground="#07111e",
            disabledforeground="#70869b",
            relief="flat",
            padx=16,
            pady=9,
        )
        self.validate_button.pack(side="right")
        tk.Button(
            buttons,
            text="CONFIGURAR MANUALMENTE",
            command=self.continue_manually,
            bg="#0d1c2e",
            fg="#a4b3c3",
            activebackground="#17314e",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=9,
        ).pack(side="right", padx=(0, 8))

        tk.Label(
            frame,
            text="CONFIGURACAO AUTOMATICA",
            bg="#0d1c2e",
            fg="#e7c36f",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=(
                "O MKT detecta a janela do Albion e valida um preset certificado. "
                "Nenhum clique sera realizado durante esta verificacao."
            ),
            bg="#0d1c2e",
            fg="#a4b3c3",
            font=("Segoe UI", 10),
            justify="left",
            wraplength=500,
        ).pack(anchor="w", pady=(8, 18))

        self.detected_label = tk.Label(
            frame,
            text="Procurando o Albion...",
            bg="#12243a",
            fg="#f4f1e8",
            font=("Segoe UI Semibold", 11),
            justify="left",
            anchor="w",
            padx=14,
            pady=12,
            wraplength=470,
        )
        self.detected_label.pack(fill="x")

        self.instruction_label = tk.Label(
            frame,
            text="",
            bg="#0d1c2e",
            fg="#a4b3c3",
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
            wraplength=500,
        )
        self.instruction_label.pack(fill="x", pady=(14, 10))

        self.evidence_label = tk.Label(
            frame,
            text="",
            bg="#091624",
            fg="#8fdfc3",
            font=("Consolas", 9),
            justify="left",
            anchor="nw",
            padx=12,
            pady=10,
            wraplength=470,
        )
        self.evidence_label.pack(fill="both", expand=True)

        # A raiz permanece oculta ate a janela principal existir. Vincular este
        # assistente como ``transient`` da raiz faria o Windows oculta-lo junto.
        self.win.update_idletasks()
        screen_width = self.win.winfo_screenwidth()
        screen_height = self.win.winfo_screenheight()
        x = max(0, (screen_width - 580) // 2)
        window_height = min(560, max(480, screen_height - 80))
        y = max(0, (screen_height - window_height) // 2)
        self.win.geometry(f"580x{window_height}+{x}+{y}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.win.grab_set()
        self.win.lift()

    def inspect_environment(self):
        self.preset = None
        self.validate_button.config(state="disabled")
        self.evidence_label.config(text="")
        albion = self.find_albion_window()
        if not albion or getattr(albion, "isMinimized", False):
            self._log("environment_not_ready", reason="albion_not_found_or_minimized")
            self.detected_label.config(
                text="Albion nao encontrado ou minimizado.", fg="#d8a34a"
            )
            self.instruction_label.config(
                text="Abra/restaure o Albion e mantenha o mercado visivel. Depois tente novamente."
            )
            return
        try:
            geometry = get_client_geometry(albion)
            dpi = get_window_dpi(geometry)
        except Exception as exc:
            self._log("geometry_failed", error=str(exc))
            self.detected_label.config(text=f"Falha ao medir o Albion: {exc}", fg="#c65a65")
            return

        preset, reason = select_compatible_preset(
            self.presets, geometry, dpi=dpi, language="pt-BR"
        )
        self.geometry_info = (geometry, dpi)
        self._log(
            "environment_inspected",
            geometry={
                "left": geometry.left,
                "top": geometry.top,
                "width": geometry.width,
                "height": geometry.height,
            },
            dpi=dpi,
            selection_reason=reason,
            preset_id=preset.get("preset_id") if preset else None,
            preset_errors=list(self.preset_errors),
        )
        self.detected_label.config(
            text=f"Albion detectado: {geometry.width}x{geometry.height} | DPI {dpi}",
            fg="#8fdfc3" if preset else "#d8a34a",
        )
        if not preset:
            detail = reason
            if self.preset_errors:
                detail += "\nPacotes recusados:\n- " + "\n- ".join(self.preset_errors)
            self.instruction_label.config(
                text=(
                    f"{detail}. Esta configuracao ainda exige calibragem manual; "
                    "nenhum preset sera aplicado por aproximacao."
                    + self._diagnostic_hint()
                )
            )
            return

        self.preset = preset
        hud_scale = str(preset.get("target", {}).get("game_ui_scale") or "").strip()
        hud_instruction = f" e mantenha a escala do HUD em {hud_scale}" if hud_scale else ""
        self.instruction_label.config(
            text=(
                f"Preset encontrado: {preset['label']}\n\n"
                "Abra o mercado, selecione um item para exibir nome e precos e deixe "
                f"o Albion totalmente visivel{hud_instruction}. Em seguida clique em "
                "VALIDAR PRESET."
            )
        )
        self.validate_button.config(state="normal")

    def validate_and_apply(self):
        if not self.preset:
            return
        albion = self.find_albion_window()
        if not albion or getattr(albion, "isMinimized", False):
            self.inspect_environment()
            return

        self.validate_button.config(state="disabled")
        self.win.grab_release()
        self.win.withdraw()
        self.parent.update_idletasks()
        self.parent.update()
        try:
            result = validate_buy_preset_passively(
                albion,
                self.preset,
                load_settings(str(self.settings_path)),
                asset_root=self.asset_root,
            )
        except Exception as exc:
            result = None
            error = str(exc)
        finally:
            self.win.deiconify()
            self.win.lift()
            self.win.grab_set()

        if result is None:
            self._log("visual_validation_failed", error=error)
            self.evidence_label.config(text=f"Falha controlada: {error}", fg="#c65a65")
            self.validate_button.config(state="normal")
            return

        lines = [
            ("OK" if item.passed else "FALHA") + f"  {item.name}: {item.detail}"
            for item in result.evidence
        ]
        self._log(
            "visual_validation_completed",
            passed=result.passed,
            summary=result.summary,
            evidence=[
                {"name": item.name, "passed": item.passed, "detail": item.detail}
                for item in result.evidence
            ],
        )
        self.evidence_label.config(
            text=result.summary + "\n\n" + "\n".join(lines),
            fg="#8fdfc3" if result.passed else "#d8a34a",
        )
        if not result.passed:
            self.validate_button.config(state="normal")
            return

        try:
            geometry = get_client_geometry(albion)
            application = apply_preset(
                self.preset,
                geometry,
                self.settings_path,
                dpi=get_window_dpi(geometry),
                language="pt-BR",
                asset_root=self.asset_root,
                active_asset_dir=calibration_assets_dir(),
            )
            bot.invalidate_template_cache()
        except Exception as exc:
            self._log("preset_application_failed", error=str(exc))
            self.evidence_label.config(
                text=f"O preset foi recusado e o estado anterior foi restaurado:\n{exc}",
                fg="#c65a65",
            )
            self.validate_button.config(state="normal")
            return

        self._log(
            "preset_application_completed",
            preset_id=application.preset_id,
            validated_modes=list(application.validated_modes),
            settings_path=str(application.settings_path),
        )

        messagebox.showinfo(
            "Configuracao concluida",
            "Preset validado e aplicado. Suas preferencias pessoais foram preservadas.",
            parent=self.win,
        )
        self._finish()

    def continue_manually(self):
        if not messagebox.askyesno(
            "Calibragem manual",
            "Continuar sem aplicar preset? A automacao permanecera bloqueada ate a calibragem manual estar completa.",
            parent=self.win,
        ):
            return
        self._log("manual_configuration_selected")
        self._finish()

    def _finish(self):
        try:
            self.win.grab_release()
            self.win.destroy()
        finally:
            self.on_complete()
