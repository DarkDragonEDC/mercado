"""Portao de atualizacao executado antes da abertura da janela principal."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app_version import APP_VERSION
from update_client import check_in_background, launch_updater


CURRENT_RELEASE_NOTES = (
    "Painel de novidades exibido antes da tela principal.",
    "Atualizacoes automaticas continuam protegidas e preservam suas configuracoes.",
    "Nas proximas versoes, as melhorias e orientacoes aparecerao neste painel.",
)


def _show_startup_dialog(win, root) -> None:
    """Mostra um modal mesmo enquanto a janela principal ainda esta oculta."""
    try:
        root_visible = str(root.state()) != "withdrawn"
    except Exception:
        root_visible = False
    if root_visible:
        win.transient(root)
    win.attributes("-topmost", True)
    win.lift()
    win.focus_force()
    win.after(300, lambda: win.attributes("-topmost", False))


def show_current_release_notes(root, on_continue) -> None:
    """Apresenta a versao instalada uma vez a cada abertura do MKT.

    Esta tela e local e nao depende da internet. Assim, mesmo sem atualizacao
    pendente ou numa instalacao nova, o usuario entende qual versao esta usando
    e como as proximas atualizacoes serao comunicadas.
    """

    ReleaseNotesDialog(root, on_continue).show()


def start_startup_update_check(root, on_continue) -> bool:
    """Procura uma versao nova e sempre conclui em uma unica rota segura.

    O callback de rede roda em background. Toda interacao Tk volta para a thread
    principal por ``after``. Se o app nao for uma instalacao compilada ou a rede
    falhar, a abertura do MKT continua normalmente.
    """

    state = {"resolved": False}

    def schedule(callback):
        try:
            root.after(0, callback)
        except Exception:
            pass

    def continue_once():
        if state["resolved"]:
            return
        state["resolved"] = True
        on_continue()

    def offer(manifest):
        def show_offer():
            if state["resolved"]:
                return
            UpdatePreparationDialog(root, manifest, continue_once, state).show()

        schedule(show_offer)

    def no_update():
        schedule(continue_once)

    def failed(_error):
        # A indisponibilidade temporaria do GitHub nao pode bloquear a abertura do MKT.
        schedule(continue_once)

    started = check_in_background(
        offer,
        on_error=failed,
        on_no_update=no_update,
    )
    if not started:
        continue_once()
    return started


class UpdatePreparationDialog:
    """Explica a transicao enquanto o atualizador externo assume o processo.

    A versao legada do atualizador nao possuia janela. Esta tela evita que a
    troca de processo pareca uma falha, e os atualizadores novos exibem depois
    o progresso detalhado de download e instalacao.
    """

    def __init__(self, root, manifest, on_continue, state):
        self.root = root
        self.manifest = manifest
        self.on_continue = on_continue
        self.state = state
        self.win = None

    def show(self):
        self.win = tk.Toplevel(self.root)
        self.win.title("MKT - Atualizacao disponivel")
        self.win.geometry("560x420")
        self.win.resizable(False, False)
        self.win.configure(bg="#07111e")
        self.win.grab_set()
        _show_startup_dialog(self.win, self.root)

        panel = tk.Frame(self.win, bg="#0d1c2e", padx=28, pady=24)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(panel, text="ATUALIZACAO DISPONIVEL", bg="#0d1c2e", fg="#e7c36f",
                 font=("Segoe UI Semibold", 17)).pack(anchor="w")
        tk.Label(panel, text=f"MKT {self.manifest.version}", bg="#0d1c2e", fg="#8fdfc3",
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(6, 15))
        tk.Label(panel, text="O MKT vai fechar por alguns instantes para atualizar com seguranca.\n"
                 "Suas configuracoes e calibragens serao preservadas.",
                 bg="#0d1c2e", fg="#d5deea", justify="left", wraplength=480).pack(anchor="w")

        notes = list(getattr(self.manifest, "release_notes", ()) or ())
        if notes:
            tk.Label(panel, text="NESTA VERSAO", bg="#0d1c2e", fg="#e7c36f",
                     font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(18, 6))
            tk.Label(panel, text="\n".join(f"• {note}" for note in notes), bg="#091624",
                     fg="#c9d8e7", justify="left", anchor="nw", padx=12, pady=10,
                     wraplength=455).pack(fill="x")

        footer = tk.Frame(panel, bg="#0d1c2e")
        footer.pack(side="bottom", fill="x", pady=(18, 0))
        tk.Button(footer, text="DEPOIS", command=self._continue, bg="#12243a", fg="#f4f1e8",
                  relief="flat", padx=18, pady=9).pack(side="left")
        tk.Button(footer, text="ATUALIZAR AGORA", command=self._update, bg="#328866", fg="#ffffff",
                  activebackground="#43a97e", relief="flat", padx=18, pady=9).pack(side="right")

    def _continue(self):
        if self.win is not None:
            self.win.destroy()
        self.on_continue()

    def _update(self):
        try:
            launch_updater(self.manifest)
        except Exception as exc:
            messagebox.showerror("Atualizacao", f"Nao foi possivel iniciar a atualizacao:\n{exc}", parent=self.win)
            return
        self.state["resolved"] = True
        self.root.destroy()


class ReleaseNotesDialog:
    """Tela informativa apresentada antes da interface principal."""

    def __init__(self, root, on_continue):
        self.root = root
        self.on_continue = on_continue
        self.win = None
        self.resolved = False

    def show(self):
        self.win = tk.Toplevel(self.root)
        self.win.title("MKT - Novidades")
        self.win.geometry("570x430")
        self.win.resizable(False, False)
        self.win.configure(bg="#07111e")
        self.win.grab_set()
        _show_startup_dialog(self.win, self.root)
        self.win.protocol("WM_DELETE_WINDOW", self._continue)

        panel = tk.Frame(self.win, bg="#0d1c2e", padx=28, pady=24)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(panel, text="NOVIDADES DO MKT", bg="#0d1c2e", fg="#e7c36f",
                 font=("Segoe UI Semibold", 17)).pack(anchor="w")
        tk.Label(panel, text=f"Versao instalada: MKT {APP_VERSION}", bg="#0d1c2e",
                 fg="#8fdfc3", font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(6, 15))
        tk.Label(panel,
                 text="Seu MKT esta pronto. Este painel aparece antes da interface "
                      "para deixar claras as melhorias da versao e como voce recebera "
                      "as proximas atualizacoes.",
                 bg="#0d1c2e", fg="#d5deea", justify="left", wraplength=480).pack(anchor="w")

        tk.Label(panel, text="NESTA VERSAO", bg="#0d1c2e", fg="#e7c36f",
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(18, 6))
        tk.Label(panel, text="\n".join(f"• {note}" for note in CURRENT_RELEASE_NOTES),
                 bg="#091624", fg="#c9d8e7", justify="left", anchor="nw", padx=12, pady=10,
                 wraplength=455).pack(fill="x")

        tk.Label(panel,
                 text="Quando houver uma nova versao, o MKT avisara antes de baixar e "
                      "mostrara o progresso da atualizacao.",
                 bg="#0d1c2e", fg="#9fb1c4", justify="left", wraplength=470).pack(anchor="w", pady=(16, 0))
        tk.Button(panel, text="CONTINUAR PARA O MKT", command=self._continue,
                  bg="#328866", fg="#ffffff", activebackground="#43a97e",
                  relief="flat", padx=18, pady=10).pack(side="bottom", anchor="e", pady=(16, 0))

    def _continue(self):
        if self.resolved:
            return
        self.resolved = True
        if self.win is not None:
            try:
                self.win.grab_release()
            except Exception:
                pass
            self.win.destroy()
        self.on_continue()
