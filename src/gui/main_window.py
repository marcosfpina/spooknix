"""Janela principal do Spooknix Desktop (GTK4).

Usa Gtk.ApplicationWindow + Gtk.Stack + Gtk.StackSwitcher para navegação.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from src.gui.app_state import AppState
from src.gui.pages.home_page import HomePage
from src.gui.pages.placeholders import (
    create_history_page,
    create_interview_page,
    create_record_page,
    create_summarize_page,
)
from src.gui.pages.transcribe_page import TranscribePage
from src.gui.workers.health_worker import HealthWorker

PAGES: list[tuple[str, str, str]] = [
    ("home", "🏠 Home", "home"),
    ("record", "🎙 Gravar", "record"),
    ("transcribe", "📂 Transcrever", "transcribe"),
    ("interview", "🎭 Entrevista", "interview"),
    ("summarize", "📝 Summarizar", "summarize"),
    ("history", "📋 Histórico", "history"),
]


class MainWindow(Gtk.ApplicationWindow):
    """Janela principal GTK4 com stack de páginas e health polling."""

    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Spooknix — Privacy-first STT")
        self.set_default_size(1100, 750)

        self._state = AppState.instance()

        # Header bar com título
        header = Adw.HeaderBar()
        header.add_css_class("flat")

        # Stack + StackSwitcher para navegação
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self._stack)
        switcher.set_halign(Gtk.Align.CENTER)
        header.set_title_widget(switcher)

        # Páginas
        self._home_page = HomePage(on_navigate=self._navigate_to)
        self._stack.add_titled(self._home_page, "home", "🏠 Home")
        self._stack.add_titled(create_record_page(), "record", "🎙 Gravar")
        self._stack.add_titled(TranscribePage(), "transcribe", "📂 Transcrever")
        self._stack.add_titled(create_interview_page(), "interview", "🎭 Entrevista")
        self._stack.add_titled(create_summarize_page(), "summarize", "📝 Summarizar")
        self._stack.add_titled(create_history_page(), "history", "📋 Histórico")

        # Layout
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.append(header)
        main.append(self._stack)

        # Status bar
        self._status_label = Gtk.Label(label="Inicializando…")
        self._status_label.add_css_class("caption")
        self._status_label.set_xalign(0)
        self._status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._status_bar.set_margin_start(12)
        self._status_bar.set_margin_end(12)
        self._status_bar.set_margin_top(4)
        self._status_bar.set_margin_bottom(4)
        self._status_bar.append(self._status_label)
        main.append(self._status_bar)

        self.set_child(main)

        # Health worker
        self._health_worker = HealthWorker(
            server_url=self._state.server_url,
            interval_s=5.0,
            on_ready=self._on_health_ready,
            on_error=self._on_health_error,
        )
        self._health_worker.start()

        # Atualizar title ao trocar de aba
        self._stack.connect("notify::visible-child", self._on_page_changed)

    def _navigate_to(self, key: str) -> None:
        child = self._stack.get_child_by_name(key)
        if child:
            self._stack.set_visible_child(child)

    def _on_page_changed(self, stack, param) -> None:
        visible = stack.get_visible_child_name()
        for icon, label, key in PAGES:
            if key == visible:
                self.set_title(f"Spooknix — {label}")
                return

    def _on_health_ready(self, data: dict) -> None:
        self._state.server_healthy = True
        self._state.server_info = data
        model = data.get("model", "—")
        uptime = data.get("uptime_s", 0)
        self._status_label.set_label(f"● {model}  ·  uptime {int(uptime // 60)}m")

    def _on_health_error(self, error: str) -> None:
        self._state.server_healthy = False
        self._status_label.set_label("○ Servidor offline — reconectando…")

    def do_close_request(self) -> None:
        self._health_worker.stop()
        return super().do_close_request()
