"""Denoise via DeepFilterNet (model `df-3`).

DeepFilterNet trabalha nativamente em 48 kHz, então fazemos resample na
borda (entrada 16 kHz → 48 kHz → denoise → 48 kHz → 16 kHz). O modelo é
singleton — carregado lazy.

Plugado em `audio_pipeline.AudioPipeline` quando `PipelineConfig.denoise=True`.
Pode ser desativado via `--no-denoise` na CLI (caro em CPU; bom em GPU).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

DF_SR = 48_000


class DeepFilterNetDenoiser:
    """Wrapper sticky sobre DeepFilterNet.

    Args:
        sample_rate: taxa de amostragem do áudio de entrada (16 kHz no
            pipeline padrão do Spooknix).
    """

    def __init__(self, sample_rate: int = 16_000):
        self.sample_rate = sample_rate
        self._model: Any = None
        self._df_state: Any = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from df.enhance import enhance, init_df  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "deepfilternet não instalado. Execute: poetry install --with audio-quality"
            ) from exc
        log.info("denoise.deepfilternet.load")
        self._model, self._df_state, _ = init_df(log_level="WARNING")
        self._enhance = enhance

    def denoise(self, audio: np.ndarray) -> np.ndarray:
        """Denoise um buffer float32. Retorna mesmo shape, mesma sample_rate.

        Args:
            audio: float32 [-1, 1] na taxa `self.sample_rate`.

        Returns:
            float32 com o ruído atenuado.
        """
        if audio.size == 0:
            return audio
        self._load()

        import torch  # type: ignore
        import torchaudio.functional as F  # type: ignore

        audio = np.asarray(audio, dtype=np.float32).flatten()
        tensor = torch.from_numpy(audio).unsqueeze(0)  # (1, N)

        if self.sample_rate != DF_SR:
            tensor = F.resample(tensor, self.sample_rate, DF_SR)

        enhanced = self._enhance(self._model, self._df_state, tensor)

        if self.sample_rate != DF_SR:
            enhanced = F.resample(enhanced, DF_SR, self.sample_rate)

        out = enhanced.squeeze(0).cpu().numpy().astype(np.float32, copy=False)
        # Garantir mesmo tamanho (resample pode adicionar/remover 1-2 amostras)
        if out.size != audio.size:
            out = out[:audio.size] if out.size > audio.size else np.pad(out, (0, audio.size - out.size))
        return out
