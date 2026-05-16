"""Widget Rich.Live para feedback visual de áudio durante gravação.

Mostra peak (dBFS), RMS, LUFS integrado e um sparkline da última janela.
Sem dependências extras — só rich + numpy.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np
from rich.console import Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

_SPARK_BARS = "▁▂▃▄▅▆▇█"
_HISTORY_LEN = 80


class AudioMeter:
    """Estado mutável para alimentar o `Live` da Rich.

    Uso:
        meter = AudioMeter(sample_rate=16_000)
        with Live(meter.render(), refresh_per_second=10) as live:
            for chunk in stream:
                meter.feed(chunk)
                live.update(meter.render())
    """

    def __init__(self, sample_rate: int = 16_000, target_lufs: float = -23.0):
        self.sample_rate = sample_rate
        self.target_lufs = target_lufs
        self.peak_db = -120.0
        self.rms_db = -120.0
        self.lufs: float | None = None
        self._loudness = None  # lazy
        self._history: deque[float] = deque(maxlen=_HISTORY_LEN)
        self._buffer: list[np.ndarray] = []
        self._buffered_samples = 0

    def _get_loudness(self):
        if self._loudness is not None:
            return self._loudness
        from .loudness import LoudnessMeter
        self._loudness = LoudnessMeter(self.sample_rate, target_lufs=self.target_lufs)
        return self._loudness

    def feed(self, chunk: np.ndarray) -> None:
        """Atualiza métricas com um novo chunk float32 mono."""
        if chunk.size == 0:
            return
        x = np.asarray(chunk, dtype=np.float32).flatten()
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        rms = float(np.sqrt(np.mean(x ** 2)))
        self.peak_db = 20.0 * math.log10(peak + 1e-9)
        self.rms_db = 20.0 * math.log10(rms + 1e-9)
        self._history.append(rms)

        # LUFS pede ≥0.4s — agregamos um buffer rolante de ~1s.
        self._buffer.append(x)
        self._buffered_samples += x.size
        if self._buffered_samples >= self.sample_rate:
            blob = np.concatenate(self._buffer)
            self.lufs = self._get_loudness().measure(blob)
            # mantém só a última segunda metade pro rolling
            half = blob[self._buffered_samples // 2:]
            self._buffer = [half]
            self._buffered_samples = half.size

    def _sparkline(self) -> str:
        if not self._history:
            return ""
        peak = max(self._history) or 1e-9
        return "".join(_SPARK_BARS[min(int((v / peak) * (len(_SPARK_BARS) - 1)), len(_SPARK_BARS) - 1)] for v in self._history)

    def render(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold cyan", justify="right")
        table.add_column()

        table.add_row("Peak", _db_bar(self.peak_db))
        table.add_row("RMS", _db_bar(self.rms_db))
        if self.lufs is not None:
            table.add_row("LUFS", _lufs_text(self.lufs, self.target_lufs))
        else:
            table.add_row("LUFS", Text("—  (acumulando ≥0.4s)", style="dim"))
        table.add_row("Wave", Text(self._sparkline(), style="green"))

        return Panel(Group(table), title="🎤 Audio Meter", border_style="cyan")


def _db_bar(db: float) -> Group:
    """Barra horizontal com valor em dBFS."""
    # mapeia [-60, 0] dBFS → [0, 1.0]
    pct = max(0.0, min(1.0, (db + 60.0) / 60.0))
    bar = ProgressBar(total=1.0, completed=pct, width=40,
                      complete_style="green" if db < -6.0 else "yellow" if db < -1.0 else "red")
    text = Text(f"  {db:6.1f} dBFS", style="bold")
    return Group(bar, text)


def _lufs_text(lufs: float, target: float) -> Text:
    delta = lufs - target
    color = "green" if abs(delta) < 1.0 else "yellow" if abs(delta) < 3.0 else "red"
    return Text(f"{lufs:6.1f} LUFS (Δ {delta:+.1f} dB → target {target:.1f})", style=color)
