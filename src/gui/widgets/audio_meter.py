"""Audio Meter GTK4 — visualizador de nível de áudio.

Gtk.DrawingArea que mostra barra de nível RMS com gradiente de cor.
Atualizado via feed(level: float) onde level ∈ [0, 1].
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


class AudioMeter(Gtk.DrawingArea):
    """Barra de nível de áudio colorida."""

    def __init__(self) -> None:
        super().__init__()
        self._level: float = 0.0
        self._peak: float = 0.0
        self._peak_hold: float = 0.0
        self._peak_decay = 0.97
        self._history: list[float] = [0.0] * 60
        self.set_size_request(-1, 40)
        self.set_draw_func(self._draw)
        # Atualiza a 30 fps
        self._tick_id = GLib.timeout_add(33, self._tick)

    def feed(self, level: float) -> None:
        """Alimenta nível RMS normalizado [0, 1]."""
        self._level = max(0.0, min(1.0, level))
        self._peak = max(self._peak, self._level)
        self._history.append(self._level)
        self._history = self._history[-60:]

    def _tick(self) -> bool:
        """Decaimento do peak hold + redraw."""
        self._peak_hold = max(self._peak, self._peak_hold * self._peak_decay)
        self._peak *= 0.9  # decaimento do peak
        self.queue_draw()
        return True  # continua o timer

    def _draw(self, area, cr, width: int, height: int, data) -> None:
        # Fundo
        cr.set_source_rgb(0.19, 0.20, 0.27)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        bar_h = height * 0.5
        bar_y = (height - bar_h) / 2
        radius = bar_h / 2

        # Barra de nível com gradiente
        level_w = max(width * self._level, radius * 2)
        cr.arc(radius, bar_y + radius, radius, 1.5708, 2.3562)
        cr.arc(level_w - radius, bar_y + radius, radius, -0.7854, 0.7854)
        cr.close_path()

        # Cor baseada no nível: verde → amarelo → vermelho
        if self._level < 0.5:
            r, g, b = self._level * 2 * 1.0, 0.65 + self._level * 0.35, 0.25
        else:
            r, g, b = 0.65 + (self._level - 0.5) * 0.7, 0.65 - (self._level - 0.5) * 0.4, 0.25
        cr.set_source_rgb(r, g, b)
        cr.fill()

        # Peak hold
        if self._peak_hold > 0.01:
            px = max(width * self._peak_hold, 2)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.rectangle(px - 1, bar_y, 2, bar_h)
            cr.fill()

        # Sparkline (mini-histórico no fundo)
        if len(self._history) > 1:
            cr.set_source_rgba(1, 1, 1, 0.05)
            step = width / (len(self._history) - 1)
            cr.move_to(0, height)
            for i, v in enumerate(self._history):
                cr.line_to(i * step, height - v * height)
            cr.line_to(width, height)
            cr.close_path()
            cr.fill()
