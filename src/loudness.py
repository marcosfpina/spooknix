"""Normalização de loudness (ITU-R BS.1770 / EBU R128).

Substitui o RMS-normalize do pipeline antigo (que era sensível a picos
isolados) por LUFS — a métrica usada em broadcast e streaming. Default
target = -23 LUFS (EBU R128). Garante volume consistente entre gravações
do mesmo microfone e entre arquivos de fontes diferentes.

Implementação via `pyloudnorm` (Steinmetz & Reiss). Buffers muito curtos
(< 0.4 s) caem em fallback de RMS-normalize, porque o block size mínimo
do Meter EBU R128 é 0.4 s.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

_DEFAULT_TARGET_LUFS = -23.0
_MIN_DURATION_S = 0.4  # block size EBU R128


class LoudnessMeter:
    """Wrapper estável sobre pyloudnorm com fallback de RMS.

    A instância segura o `pyloudnorm.Meter` cacheado por sample_rate — Meter
    pré-computa filtros K-weighting na construção, então não queremos refazer
    isso a cada chamada.
    """

    def __init__(self, sample_rate: int, target_lufs: float = _DEFAULT_TARGET_LUFS):
        self.sample_rate = sample_rate
        self.target_lufs = target_lufs
        self._meter = None  # lazy: pyloudnorm é opcional na instalação base

    def _get_meter(self):
        if self._meter is not None:
            return self._meter
        try:
            import pyloudnorm as pyln  # type: ignore
        except ImportError:
            log.debug("pyloudnorm indisponível — caindo em RMS-normalize")
            return None
        self._meter = pyln.Meter(self.sample_rate)
        return self._meter

    def measure(self, audio: np.ndarray) -> float | None:
        """Loudness integrado em LUFS. None se buffer < 0.4s ou meter ausente."""
        if audio.size / self.sample_rate < _MIN_DURATION_S:
            return None
        meter = self._get_meter()
        if meter is None:
            return None
        try:
            return float(meter.integrated_loudness(audio.astype(np.float32)))
        except Exception as exc:
            log.warning("loudness.measure_failed %s", exc)
            return None

    def normalize(self, audio: np.ndarray) -> np.ndarray:
        """Aplica gain estático para alcançar target_lufs.

        Buffers muito curtos OU sem pyloudnorm caem em RMS-normalize com
        target equivalente (gain pra RMS=0.1 ≈ -23 LUFS pra speech).
        """
        if audio.size == 0:
            return audio

        lufs = self.measure(audio)
        if lufs is None:
            return _rms_normalize(audio, target_rms=0.1)

        # gain linear = 10^((target - measured) / 20)
        gain_db = self.target_lufs - lufs
        gain = float(10.0 ** (gain_db / 20.0))
        return (audio * gain).astype(np.float32, copy=False)


def _rms_normalize(audio: np.ndarray, target_rms: float = 0.1) -> np.ndarray:
    """Fallback usado quando o buffer é curto demais pro K-weighting."""
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-8:
        return audio
    return (audio * (target_rms / rms)).astype(np.float32, copy=False)


def to_lufs(audio: np.ndarray, sample_rate: int, target: float = _DEFAULT_TARGET_LUFS) -> np.ndarray:
    """Atalho funcional: normaliza um array para `target` LUFS."""
    return LoudnessMeter(sample_rate=sample_rate, target_lufs=target).normalize(audio)
