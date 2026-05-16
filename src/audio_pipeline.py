# src/audio_pipeline.py
"""Pré-processamento de áudio para pipeline de streaming STT.

Pipeline (ordem fixa):
  float32 → high-pass 80 Hz → denoise (opcional) → pre-emphasis (opcional)
        → LUFS normalize OU RMS normalize → clip protection.

Cada stage é togglável via PipelineConfig. Coeficientes do filtro são
calculados uma única vez no __init__ e reutilizados em todos os frames.

Denoise e LUFS são opcionais e default-off para preservar o comportamento
histórico dos testes — para ativar, instale `poetry install --with audio-quality`
e construa o pipeline com `denoise=True, lufs_normalize=True`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class PipelineConfig:
    normalize: bool = True
    target_rms: float = 0.1
    high_pass: bool = True
    high_pass_cutoff_hz: float = 80.0
    clip_ceiling: float = 0.99
    # ── Sprint 1 extensions ──────────────────────────────────────────────
    denoise: bool = False
    lufs_normalize: bool = False
    target_lufs: float = -23.0
    pre_emphasis: bool = False
    pre_emphasis_coef: float = 0.97


class AudioPipeline:
    """Pipeline de pré-processamento de áudio — coeficientes calculados uma vez."""

    def __init__(self, config: PipelineConfig | None = None, sample_rate: int = 16_000):
        self.config = config or PipelineConfig()
        self.sample_rate = sample_rate
        self._b: np.ndarray | None = None
        self._a: np.ndarray | None = None
        self._denoiser: Any = None
        self._loudness: Any = None
        if self.config.high_pass:
            self._b, self._a = self._design_highpass()

    def _design_highpass(self) -> tuple[np.ndarray, np.ndarray]:
        """Butterworth high-pass de 2ª ordem."""
        from scipy.signal import butter  # type: ignore
        b, a = butter(
            2,
            self.config.high_pass_cutoff_hz / (self.sample_rate / 2),
            btype="high",
        )
        return np.asarray(b, dtype=np.float64), np.asarray(a, dtype=np.float64)

    def _get_denoiser(self):
        if self._denoiser is not None:
            return self._denoiser
        from .denoise import DeepFilterNetDenoiser
        self._denoiser = DeepFilterNetDenoiser(sample_rate=self.sample_rate)
        return self._denoiser

    def _get_loudness(self):
        if self._loudness is not None:
            return self._loudness
        from .loudness import LoudnessMeter
        self._loudness = LoudnessMeter(
            sample_rate=self.sample_rate, target_lufs=self.config.target_lufs
        )
        return self._loudness

    def _apply(self, audio: np.ndarray) -> np.ndarray:
        """Aplica o pipeline a um array float32 já concatenado."""
        audio = audio.astype(np.float32, copy=True)

        if self.config.high_pass and self._b is not None:
            from scipy.signal import lfilter  # type: ignore
            audio = lfilter(self._b, self._a, audio).astype(np.float32)

        if self.config.denoise:
            audio = self._get_denoiser().denoise(audio).astype(np.float32)

        if self.config.pre_emphasis and audio.size > 1:
            coef = float(self.config.pre_emphasis_coef)
            audio = np.concatenate(
                ([audio[0]], audio[1:] - coef * audio[:-1])
            ).astype(np.float32)

        if self.config.lufs_normalize:
            audio = self._get_loudness().normalize(audio)
        elif self.config.normalize:
            rms = float(np.sqrt(np.mean(audio ** 2)))
            if rms > 1e-8:
                audio = audio * (self.config.target_rms / rms)

        if self.config.clip_ceiling < 1.0:
            audio = np.clip(audio, -self.config.clip_ceiling, self.config.clip_ceiling)

        return audio.astype(np.float32, copy=False)

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Processa um único chunk float32."""
        return self._apply(chunk)

    def process_buffer(self, chunks: list[np.ndarray]) -> np.ndarray:
        """Concatena e processa uma lista de chunks em uma única passagem."""
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return self._apply(np.concatenate(chunks))
