"""
Cliente assíncrono 100% local para o Worker TTS (ex: XTTS-v2, F5-TTS, Piper).
Não possui dependências de nuvem ou pacotes de terceiros como OpenAI.
"""

import hashlib
import io
import logging
import os
import time
import wave
from pathlib import Path

import aiohttp
import numpy as np
from . import metrics as m


log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0
CACHE_DIR = Path(os.path.expanduser("~/.cache/spooknix/tts"))


class LocalTTSClient:
    """Cliente para interagir diretamente com o container TTS local via REST."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_s: float | None = None,
        enable_cache: bool = True,
    ):
        """
        Inicializa o cliente local.
        """
        resolved_base_url = (
            base_url
            or os.getenv("TTS_BASE_URL")
            or os.getenv("XTTS_BASE_URL")
            or os.getenv("CHATTERBOX_BASE_URL")
            or os.getenv("F5_TTS_URL")
            or "http://localhost:8001"
        )
        self.base_url = resolved_base_url.rstrip("/")
        self.api_path = os.getenv("TTS_API_PATH", "/tts")
        self.default_voice = os.getenv("TTS_VOICE", "default_voice")
        self.default_language = os.getenv("TTS_LANGUAGE", "en")
        self.timeout_s = float(
            timeout_s if timeout_s is not None else os.getenv("TTS_TIMEOUT_S", DEFAULT_TIMEOUT_S)
        )
        self.enable_cache = enable_cache
        if self.enable_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        log.debug("TTSClient initialized at %s%s (cache=%s)", self.base_url, self.api_path, self.enable_cache)

    def _get_cache_path(self, text: str, voice: str, language: str) -> Path:
        """Gera um path de cache determinístico baseado no conteúdo."""
        key = f"{text}|{voice}|{language}".encode("utf-8")
        digest = hashlib.sha256(key).hexdigest()
        return CACHE_DIR / f"{digest}.wav"

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """
        Envia a string de texto para o container local de TTS com suporte a cache.
        """
        v = voice or self.default_voice
        l = self.default_language
        
        if self.enable_cache:
            cache_path = self._get_cache_path(text, v, l)
            if cache_path.exists():
                log.debug("tts.cache_hit key=%s", cache_path.stem[:8])
                return cache_path.read_bytes()

        payload = {
            "text": text,
            "voice": v,
            "language": l,
        }
        endpoint = f"{self.base_url}{self.api_path}"
        log.debug("tts.request endpoint=%s voice=%s chars=%d", endpoint, payload["voice"], len(text))

        t0 = time.perf_counter()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, timeout=self.timeout_s) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        
                        m.tts_synthesize_latency_ms.observe((time.perf_counter() - t0) * 1000)
                        log.debug("tts.response status=200 bytes=%d", len(data))
                        
                        if self.enable_cache and data:
                            cache_path = self._get_cache_path(text, v, l)
                            cache_path.write_bytes(data)
                            
                        return data
                    err = await resp.text()
                    log.warning("tts.bad_status status=%d body=%s", resp.status, err[:200])
                    return b""
        except Exception as e:
            log.error("tts.error url=%s err=%s", endpoint, e)
            return b""

    def decode_wav(self, wav_bytes: bytes) -> tuple[np.ndarray, int]:
        """Converte WAV bytes brutos em ndarray float32 e extrai a sample rate."""
        if not wav_bytes:
            return np.array([], dtype=np.float32), 24000

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                samplerate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                audio_int16 = np.frombuffer(frames, dtype=np.int16)
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                return audio_float32, samplerate
        except Exception as e:
            log.error("Failed to parse WAV bytes: %s", e)
            return np.array([], dtype=np.float32), 24000
