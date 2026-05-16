"""Voice Activity Detection neural via Silero VAD.

Substitui o RMS-threshold do recorder antigo. Silero retorna probabilidade
de speech por janela de 30 ms (480 amostras @ 16 kHz). Adicionamos uma
janela "hangover" sticky pra evitar flicker (chunk único cortado dentro
de uma frase).

Importação é lazy — o módulo carrega apenas quando o usuário liga `--meter`
ou passa `--no-vad-neural` falso. Se silero-vad ou torch faltarem, levanta
ImportError com mensagem clara apontando o extra `audio-quality`.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

WINDOW_SAMPLES = 512  # silero v5 espera 512 amostras @ 16 kHz (32 ms)
SAMPLE_RATE = 16_000
WARMUP_CHUNKS = 6  # ~200 ms — descarta janelas iniciais com estado ainda quente


class SileroVAD:
    """Wrapper sticky sobre o modelo Silero v5.

    Args:
        threshold: probabilidade mínima para classificar como speech.
        hangover: nº de janelas consecutivas de silêncio antes de "soltar"
            o estado de speech (suaviza fronteiras de palavras).
        sample_rate: deve ser 16000 ou 8000 (limitação do modelo).
    """

    def __init__(
        self,
        threshold: float = 0.5,
        hangover: int = 6,
        sample_rate: int = SAMPLE_RATE,
    ):
        if sample_rate not in (8_000, 16_000):
            raise ValueError("Silero suporta apenas 8000 ou 16000 Hz")
        self.threshold = threshold
        self.hangover = hangover
        self.sample_rate = sample_rate
        self._model: Any = None
        self._silent_streak = 0
        self._warm = 0
        self._last_decision = False

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from silero_vad import load_silero_vad  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "silero-vad não instalado. Execute: poetry install --with audio-quality"
            ) from exc
        self._model = load_silero_vad()
        log.info("vad.silero.loaded threshold=%.2f hangover=%d", self.threshold, self.hangover)
        return self._model

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Decide se um chunk float32 [-1, 1] contém speech.

        Faz internamente o particionamento em janelas de 512 samples e
        retorna True se QUALQUER janela disparar acima do threshold (ou
        se ainda estiver no hangover de uma decisão anterior).
        """
        import torch  # type: ignore

        model = self._load()
        audio = np.asarray(chunk, dtype=np.float32).flatten()

        any_speech = False
        for start in range(0, len(audio) - WINDOW_SAMPLES + 1, WINDOW_SAMPLES):
            window = audio[start:start + WINDOW_SAMPLES]
            tensor = torch.from_numpy(window)
            prob = float(model(tensor, self.sample_rate).item())
            if prob >= self.threshold:
                any_speech = True
                break

        # Warm-up: descarta as primeiras janelas porque o estado do RNN
        # ainda está se acomodando — Silero não é determinístico no primeiro frame.
        if self._warm < WARMUP_CHUNKS:
            self._warm += 1
            self._last_decision = False
            return False

        if any_speech:
            self._silent_streak = 0
            self._last_decision = True
            return True

        # Hangover: mantém speech=True por N chunks após o último hit positivo.
        if self._last_decision and self._silent_streak < self.hangover:
            self._silent_streak += 1
            return True

        self._last_decision = False
        return False

    def reset(self) -> None:
        """Reinicia o estado interno (entre sessões)."""
        self._silent_streak = 0
        self._warm = 0
        self._last_decision = False
        if self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass
