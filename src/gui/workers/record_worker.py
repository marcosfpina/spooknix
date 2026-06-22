"""Worker de gravação — sounddevice em thread com VAD RMS.

Emite chunks para audio meter, detecta silêncio, salva WAV.
Callbacks via GLib.idle_add para thread-safety da UI GTK4.
"""

from __future__ import annotations

import io
import logging
import tempfile
import threading
import time
import wave
from typing import Callable

import gi
import numpy as np

gi.require_version("GLib", "2.0")
from gi.repository import GLib

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BLOCKSIZE = 1_600  # 100ms


class RecordWorker:
    """Grava do microfone em thread separada com VAD RMS."""

    def __init__(
        self,
        on_chunk: Callable[[np.ndarray], None] | None = None,
        on_speech: Callable[[bool], None] | None = None,
        on_done: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self._on_chunk = on_chunk
        self._on_speech = on_speech
        self._on_done = on_done
        self._on_error = on_error
        self._on_level = on_level
        self._running = False
        self._thread: threading.Thread | None = None

    def start(
        self,
        threshold: float = 0.01,
        silence_duration: float = 2.0,
        max_duration: float = 360.0,
        device: int | None = None,
    ) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(threshold, silence_duration, max_duration, device),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _emit(self, cb: Callable | None, *args) -> None:
        if cb:
            GLib.idle_add(lambda: (cb(*args), False))

    def _run(
        self,
        threshold: float,
        silence_duration: float,
        max_duration: float,
        device: int | None,
    ) -> None:
        import sounddevice as sd

        chunks: list[np.ndarray] = []
        stop_event = threading.Event()
        silent_chunks_needed = int(silence_duration * SAMPLE_RATE / BLOCKSIZE)
        max_chunks = int(max_duration * SAMPLE_RATE / BLOCKSIZE)
        silent_count = 0
        has_spoken = False
        chunk_idx = 0

        def callback(indata: np.ndarray, frames: int, time_info, status) -> None:
            nonlocal silent_count, has_spoken, chunk_idx

            if stop_event.is_set():
                raise sd.CallbackStop()

            chunk = indata[:, 0].copy()
            chunks.append(chunk)
            chunk_idx += 1

            rms = float(np.sqrt(np.mean(chunk**2)))
            is_speech = rms >= threshold

            # Nível RMS pra audio meter (0..1 normalizado)
            level = min(rms / 0.1, 1.0)  # 0.1 = -20dB referência
            self._emit(self._on_level, level)
            self._emit(self._on_chunk, chunk)

            if is_speech:
                if silent_count >= silent_chunks_needed and has_spoken:
                    # Transição silêncio→fala — notifica
                    pass
                silent_count = 0
                if not has_spoken:
                    has_spoken = True
                    self._emit(self._on_speech, True)
            else:
                silent_count += 1

            if has_spoken and silent_count >= silent_chunks_needed:
                stop_event.set()
                raise sd.CallbackStop()

            if chunk_idx >= max_chunks:
                stop_event.set()
                raise sd.CallbackStop()

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCKSIZE,
                callback=callback,
                device=device,
            ):
                stop_event.wait(timeout=max_duration + 5)
        except sd.PortAudioError as exc:
            self._emit(self._on_error, f"Erro no dispositivo de áudio: {exc}")
            return
        except Exception as exc:
            self._emit(self._on_error, str(exc))
            return
        finally:
            stop_event.set()

        if not chunks:
            self._emit(self._on_error, "Nenhum áudio capturado")
            return

        self._emit(self._on_speech, False)

        # Salva WAV
        wav_path = self._save_wav(chunks)
        self._emit(self._on_done, wav_path)

    def _save_wav(self, chunks: list[np.ndarray]) -> str:
        audio = np.concatenate(chunks)
        audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())
        return tmp.name
