"""Página Gravar — GTK4.

Gravação ao vivo com audio meter, VAD RMS, transcrição automática.
"""

from __future__ import annotations

import math
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk

from src.gui.app_state import AppState
from src.gui.pages.transcribe_page import _format_size, _format_time
from src.gui.widgets.audio_meter import AudioMeter
from src.gui.workers.record_worker import RecordWorker
from src.gui.workers.transcribe_worker import TranscribeWorker


class RecordPage(Gtk.Box):
    """Página de gravação ao vivo com audio meter."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._state = AppState.instance()
        self._recording = False
        self._wav_path: str | None = None

        self.set_margin_start(20)
        self.set_margin_end(20)
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_spacing(16)

        # ── Title ───────────────────────────────────────────────────────
        title = Gtk.Label(label="Gravar Microfone")
        title.add_css_class("title-1")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # ── Audio Meter ──────────────────────────────────────────────────
        meter_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        meter_frame.add_css_class("card")
        meter_label = Gtk.Label(label="Nível de áudio")
        meter_label.add_css_class("metric-label")
        meter_label.set_halign(Gtk.Align.START)
        meter_frame.append(meter_label)

        self._meter = AudioMeter()
        meter_frame.append(self._meter)

        self._level_label = Gtk.Label(label="— dB")
        self._level_label.add_css_class("caption")
        self._level_label.set_halign(Gtk.Align.END)
        meter_frame.append(self._level_label)

        self.append(meter_frame)

        # ── Controls ─────────────────────────────────────────────────────
        controls = Gtk.Box(spacing=12)

        # Threshold
        th_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        th_lbl = Gtk.Label(label="Sensibilidade")
        th_lbl.add_css_class("metric-label")
        th_lbl.set_halign(Gtk.Align.START)
        th_box.append(th_lbl)

        th_row = Gtk.Box(spacing=8)
        self._threshold_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.001, 0.1, 0.001
        )
        self._threshold_scale.set_value(0.01)
        self._threshold_scale.set_size_request(150, -1)
        self._threshold_scale.set_draw_value(False)
        th_row.append(self._threshold_scale)
        self._threshold_label = Gtk.Label(label="0.010")
        self._threshold_label.add_css_class("caption")
        self._threshold_label.set_width_chars(6)
        th_row.append(self._threshold_label)
        th_box.append(th_row)
        controls.append(th_box)

        # Silence
        sil_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sil_lbl = Gtk.Label(label="Silêncio (s)")
        sil_lbl.add_css_class("metric-label")
        sil_lbl.set_halign(Gtk.Align.START)
        sil_box.append(sil_lbl)

        sil_row = Gtk.Box(spacing=8)
        self._silence_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 5.0, 0.5)
        self._silence_scale.set_value(2.0)
        self._silence_scale.set_size_request(150, -1)
        self._silence_scale.set_draw_value(False)
        sil_row.append(self._silence_scale)
        self._silence_label = Gtk.Label(label="2.0")
        self._silence_label.add_css_class("caption")
        self._silence_label.set_width_chars(4)
        sil_row.append(self._silence_label)
        sil_box.append(sil_row)
        controls.append(sil_box)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        controls.append(spacer)

        self.append(controls)

        # Connect scale signals
        self._threshold_scale.connect("value-changed", self._on_threshold_changed)
        self._silence_scale.connect("value-changed", self._on_silence_changed)

        # ── Record button ─────────────────────────────────────────────────
        btn_row = Gtk.Box(spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)

        self._record_btn = Gtk.Button(label="● Gravar")
        self._record_btn.add_css_class("suggested-action")
        self._record_btn.set_size_request(200, 48)
        self._record_btn.connect("clicked", self._on_record_clicked)
        btn_row.append(self._record_btn)

        self.append(btn_row)

        # ── Status label ──────────────────────────────────────────────────
        self._status_label = Gtk.Label(label="Pronto para gravar")
        self._status_label.add_css_class("caption")
        self._status_label.set_halign(Gtk.Align.CENTER)
        self.append(self._status_label)

        # ── Results area (hidden initially) ───────────────────────────────
        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._results_box.set_visible(False)

        self._full_text_label = Gtk.Label()
        self._full_text_label.set_wrap(True)
        self._full_text_label.set_selectable(True)
        self._full_text_label.set_xalign(0)
        self._full_text_label.add_css_class("card")
        self._full_text_label.set_margin_start(12)
        self._full_text_label.set_margin_end(12)
        self._full_text_label.set_margin_top(8)
        self._full_text_label.set_margin_bottom(8)
        self._results_box.append(self._full_text_label)

        actions = Gtk.Box(spacing=8)
        copy_btn = Gtk.Button(label="📋 Copiar")
        copy_btn.add_css_class("flat")
        copy_btn.connect("clicked", self._on_copy)
        actions.append(copy_btn)
        self._results_box.append(actions)

        self.append(self._results_box)

        # ── Workers ──────────────────────────────────────────────────────
        self._record_worker = RecordWorker(
            on_level=self._on_level,
            on_speech=self._on_speech,
            on_done=self._on_recording_done,
            on_error=self._on_record_error,
        )

        self._transcribe_worker = TranscribeWorker(
            server_url=self._state.server_url,
            on_result=self._on_transcribe_result,
            on_error=self._on_transcribe_error,
        )

        # Pulse timer (30fps para animar o botão durante gravação)
        self._pulse_val = 0.0
        self._pulse_up = True
        self._pulse_timer = GLib.timeout_add(33, self._pulse_tick)

    # ── Controls ─────────────────────────────────────────────────────────

    def _on_threshold_changed(self, scale: Gtk.Scale) -> None:
        v = scale.get_value()
        self._threshold_label.set_label(f"{v:.3f}")

    def _on_silence_changed(self, scale: Gtk.Scale) -> None:
        v = scale.get_value()
        self._silence_label.set_label(f"{v:.1f}")

    # ── Record ───────────────────────────────────────────────────────────

    def _on_record_clicked(self, btn: Gtk.Button) -> None:
        if self._recording:
            self._record_worker.stop()
            self._recording = False
            btn.set_label("● Gravar")
            btn.remove_css_class("destructive-action")
            btn.add_css_class("suggested-action")
            self._status_label.set_label("Parando…")
        else:
            threshold = self._threshold_scale.get_value()
            silence = self._silence_scale.get_value()
            self._record_worker.start(
                threshold=threshold,
                silence_duration=silence,
            )
            self._recording = True
            btn.set_label("■ Parar")
            btn.remove_css_class("suggested-action")
            btn.add_css_class("destructive-action")
            self._status_label.set_label("🔴 Gravando… fale algo")
            # Esconde resultados anteriores
            self._results_box.set_visible(False)

    def _on_level(self, level: float) -> None:
        self._meter.feed(level)
        # dB aproximado
        db = 20 * math.log10(level + 1e-9) if level > 0 else -120
        self._level_label.set_label(f"{db:.0f} dB")

    def _on_speech(self, speaking: bool) -> None:
        if self._recording:
            self._status_label.set_label("🗣 Falando…" if speaking else "🔇 Silêncio…")

    def _on_recording_done(self, wav_path: str) -> None:
        self._recording = False
        self._wav_path = wav_path
        self._record_btn.set_label("● Gravar")
        self._record_btn.remove_css_class("destructive-action")
        self._record_btn.add_css_class("suggested-action")
        self._status_label.set_label("⏳ Transcrevendo…")

        # Transcrever o WAV automaticamente
        self._transcribe_worker.transcribe(
            file_path=wav_path,
            language=self._state.language,
        )

    def _on_record_error(self, msg: str) -> None:
        self._recording = False
        self._record_btn.set_label("● Gravar")
        self._record_btn.remove_css_class("destructive-action")
        self._record_btn.add_css_class("suggested-action")
        self._status_label.set_label(f"❌ {msg}")

    # ── Transcription ────────────────────────────────────────────────────

    def _on_transcribe_result(self, result: dict) -> None:
        self._status_label.set_label("✅ Transcrição concluída")
        text = result.get("text", "").strip()
        self._full_text_label.set_label(text)
        self._results_box.set_visible(True)

        # Limpa WAV temporário
        if self._wav_path:
            Path(self._wav_path).unlink(missing_ok=True)
            self._wav_path = None

    def _on_transcribe_error(self, msg: str) -> None:
        self._status_label.set_label(f"❌ Erro na transcrição: {msg}")
        self._results_box.set_visible(True)

    # ── Actions ──────────────────────────────────────────────────────────

    def _on_copy(self, btn: Gtk.Button) -> None:
        text = self._full_text_label.get_label()
        if text:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
            self._status_label.set_label("📋 Texto copiado!")

    # ── Pulse animation ──────────────────────────────────────────────────

    def _pulse_tick(self) -> bool:
        if not self._recording:
            return True  # continua timer

        # Oscila transparência do botão entre 1.0 e 0.7
        if self._pulse_up:
            self._pulse_val += 0.05
            if self._pulse_val >= 1.0:
                self._pulse_up = False
        else:
            self._pulse_val -= 0.05
            if self._pulse_val <= 0.7:
                self._pulse_up = True

        self._record_btn.set_opacity(self._pulse_val)
        return True
