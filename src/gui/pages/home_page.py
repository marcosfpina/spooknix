"""Página Home (Dashboard) — GTK4.

Mostra card de status do servidor, quick actions, e sessões recentes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

from src.gui.app_state import AppState


def _format_uptime(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


PERSONA_COLORS = {"sarah": "#89b4fa", "marcus": "#a6e3a1", "priya": "#fab387"}
DIFF_COLORS = {"easy": "#a6e3a1", "medium": "#f9e2af", "hard": "#f38ba8"}


class HomePage(Gtk.Box):
    """Dashboard — status do servidor, quick actions, doctor, sessions."""

    def __init__(self, on_navigate: Callable[[str], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_navigate = on_navigate
        self._state = AppState.instance()
        self._state.connect("server_info", self._on_server_info)
        self._state.connect("sessions", self._on_sessions)

        self.set_margin_start(20)
        self.set_margin_end(20)
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_spacing(16)

        # Scroll
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self)

        # Title
        title = Gtk.Label(label="Spooknix")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        subtitle = Gtk.Label(label="Privacy-first Speech-to-Text Engine")
        subtitle.add_css_class("caption")
        subtitle.set_halign(Gtk.Align.START)
        self.append(subtitle)

        # ── Server status card ──────────────────────────────────────────
        self._server_card = self._build_server_card()
        self.append(self._server_card)

        # ── Quick actions ───────────────────────────────────────────────
        actions_label = Gtk.Label(label="Ações rápidas")
        actions_label.add_css_class("title-2")
        actions_label.set_halign(Gtk.Align.START)
        self.append(actions_label)

        actions_grid = Gtk.FlowBox()
        actions_grid.set_max_children_per_line(2)
        actions_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        actions_grid.set_row_spacing(10)
        actions_grid.set_column_spacing(10)

        actions = [
            ("🎙️ Gravar", "Microfone ao vivo\ncom VAD e streaming", "record"),
            ("📂 Transcrever", "Arquivos de áudio/vídeo\ncom diarização", "transcribe"),
            ("🎭 Entrevista", "Simulador full-duplex\nLLM + TTS local", "interview"),
            ("📝 Summarizar", "Aulas/vídeos/reuniões\ncom timestamps", "summarize"),
        ]
        for title_text, desc, key in actions:
            card = self._make_action_card(title_text, desc, key)
            actions_grid.append(card)
        self.append(actions_grid)

        # ── Sessions ────────────────────────────────────────────────────
        sess_label = Gtk.Label(label="Sessões recentes")
        sess_label.add_css_class("title-2")
        sess_label.set_halign(Gtk.Align.START)
        self.append(sess_label)

        self._sessions_box = Gtk.ListBox()
        self._sessions_box.add_css_class("card")
        self._empty_label = Gtk.Label(label="Nenhuma sessão ainda. Comece uma entrevista!")
        self._empty_label.add_css_class("caption")
        self._empty_label.set_margin_top(12)
        self._empty_label.set_margin_bottom(12)
        self._sessions_box.append(self._empty_label)
        self.append(self._sessions_box)

    # ── Server card ─────────────────────────────────────────────────────

    def _build_server_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")

        # Header: dot + "Servidor STT" + model
        header = Gtk.Box(spacing=8)
        self._status_dot = Gtk.DrawingArea()
        self._status_dot.set_size_request(10, 10)
        self._status_dot.set_draw_func(self._draw_dot, None)
        header.append(self._status_dot)

        card_title = Gtk.Label(label="Servidor STT")
        card_title.add_css_class("title-2")
        header.append(card_title)

        self._model_label = Gtk.Label(label="—")
        self._model_label.add_css_class("caption")
        self._model_label.set_halign(Gtk.Align.END)
        self._model_label.set_hexpand(True)
        header.append(self._model_label)
        card.append(header)

        # Metrics grid
        grid = Gtk.Box(spacing=20)
        for label, key in [
            ("Dispositivo", "device"),
            ("GPU", "gpu"),
            ("Uptime", "uptime_s"),
            ("Diarização", "diarization"),
        ]:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            val = Gtk.Label(label="—")
            val.add_css_class("metric-value")
            col.append(val)
            lbl = Gtk.Label(label=label)
            lbl.add_css_class("metric-label")
            col.append(lbl)
            grid.append(col)
            setattr(self, f"_met_{key}", val)
        grid.set_halign(Gtk.Align.FILL)
        card.append(grid)

        # VRAM bar
        self._vram_label = Gtk.Label(label="VRAM —")
        self._vram_label.add_css_class("caption")
        self._vram_label.set_halign(Gtk.Align.START)
        card.append(self._vram_label)

        self._vram_bar = Gtk.LevelBar()
        self._vram_bar.set_min_value(0)
        self._vram_bar.set_max_value(100)
        self._vram_bar.set_value(0)
        card.append(self._vram_bar)

        self._dot_healthy = False
        return card

    def _draw_dot(self, area, cr, width, height, data):
        color = (
            (0x89 / 255, 0xB4 / 255, 0xFA / 255)
            if self._dot_healthy
            else (0xF3 / 255, 0x8B / 255, 0xA8 / 255)
        )
        cr.set_source_rgb(*color)
        cr.arc(5, 5, 4, 0, 6.28)
        cr.fill()

    # ── Quick action card ───────────────────────────────────────────────

    def _make_action_card(self, title: str, desc: str, key: str) -> Gtk.Button:
        btn = Gtk.Button()
        btn.add_css_class("card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        t = Gtk.Label(label=title)
        t.set_halign(Gtk.Align.START)
        d = Gtk.Label(label=desc)
        d.add_css_class("caption")
        d.set_halign(Gtk.Align.START)
        box.append(t)
        box.append(d)
        btn.set_child(box)
        btn.connect("clicked", lambda b, k=key: self._navigate(k) if self._on_navigate else None)
        return btn

    def _navigate(self, key: str) -> None:
        if self._on_navigate:
            self._on_navigate(key)

    # ── State callbacks ──────────────────────────────────────────────────

    def _on_server_info(self, info: dict) -> None:
        if not info or info.get("status") != "ok":
            return
        self._dot_healthy = True
        self._status_dot.queue_draw()

        self._model_label.set_label(info.get("model", "?"))

        device = info.get("device", "?").upper()
        self._met_device.set_label(device)

        gpu = info.get("gpu", "—").replace("NVIDIA GeForce ", "").replace(" Laptop GPU", "")
        self._met_gpu.set_label(gpu)

        uptime = _format_uptime(float(info.get("uptime_s", 0)))
        self._met_uptime_s.set_label(uptime)

        diar = "ON" if info.get("diarization") else "OFF"
        self._met_diarization.set_label(diar)

        total = info.get("vram_total_gb", 0)
        allocated = info.get("vram_allocated_gb", 0)
        free = info.get("vram_free_gb", 0)
        if total > 0:
            pct = min(int(allocated / total * 100), 100)
            self._vram_bar.set_value(pct)
            self._vram_label.set_label(
                f"VRAM {allocated:.1f} / {total:.1f} GB  ·  {free:.1f} GB livre"
            )
        else:
            self._vram_bar.set_value(0)
            self._vram_label.set_label("VRAM — CPU mode")

    def _on_sessions(self, sessions: list) -> None:
        # Remove old rows except empty label
        child = self._sessions_box.get_last_child()
        while child:
            nxt = child.get_prev_sibling()
            if child != self._empty_label:
                self._sessions_box.remove(child)
            child = nxt

        recent = sessions[:5]
        if not recent:
            self._empty_label.set_visible(True)
            return
        self._empty_label.set_visible(False)
        for s in recent:
            row = Gtk.Box(spacing=12)
            row.set_margin_start(8)
            row.set_margin_end(8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            dot_color = PERSONA_COLORS.get(s.persona.lower(), "#6c7086")
            dot = Gtk.Label(label=f'<span color="{dot_color}">●</span> {s.persona.title()}')
            dot.set_use_markup(True)
            row.append(dot)

            sc = Gtk.Label(label=s.scenario.replace("_", " ").title())
            sc.add_css_class("caption")
            row.append(sc)

            diff_color = DIFF_COLORS.get(s.difficulty, "#6c7086")
            diff = Gtk.Label(label=f'<span color="{diff_color}">{s.difficulty.upper()}</span>')
            diff.set_use_markup(True)
            diff.add_css_class("caption")
            row.append(diff)

            spacer = Gtk.Label()
            spacer.set_hexpand(True)
            row.append(spacer)

            try:
                dt = datetime.fromisoformat(s.ts)
                ts_str = dt.strftime("%d/%m %H:%M")
            except (ValueError, TypeError):
                ts_str = s.ts[:16] if len(s.ts) > 16 else s.ts
            ts = Gtk.Label(label=ts_str)
            ts.add_css_class("caption")
            row.append(ts)

            self._sessions_box.append(row)
