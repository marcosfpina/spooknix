"""Worker de transcrição — envia arquivo via HTTP multipart em thread.

Usa threading.Thread + GLib.idle_add para não bloquear a UI.
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

SUPPORTED_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]


class TranscribeWorker:
    """Envia arquivo ao POST /transcribe e retorna resultado JSON."""

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        on_result: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self._url = server_url.rstrip("/")
        self._on_result = on_result
        self._on_error = on_error
        self._on_progress = on_progress
        self._running = False

    def transcribe(
        self,
        file_path: str,
        language: str = "pt",
        model_size: str | None = None,
        diarize: bool = False,
    ) -> None:
        """Inicia transcrição em background thread."""
        self._running = True
        thread = threading.Thread(
            target=self._run,
            args=(file_path, language, model_size, diarize),
            daemon=True,
        )
        thread.start()

    def _emit(self, cb: Callable, *args) -> None:
        GLib.idle_add(lambda: (cb(*args), False))

    def _run(
        self,
        file_path: str,
        language: str,
        model_size: str | None,
        diarize: bool,
    ) -> None:
        path = Path(file_path)
        if not path.exists():
            self._emit(self._on_error or (lambda _: None), f"Arquivo não encontrado: {file_path}")
            return

        if model_size and model_size not in SUPPORTED_MODELS:
            self._emit(
                self._on_error or (lambda _: None),
                f"Modelo inválido: {model_size}. Opções: {SUPPORTED_MODELS}",
            )
            return

        try:
            self._emit(self._on_progress or (lambda _: None), "Lendo arquivo…")
            file_bytes = path.read_bytes()

            # multipart/form-data manual (sem dependência extra)
            boundary = "spooknix_boundary_42"
            body = b""

            def _add_field(name: str, value: str) -> None:
                nonlocal body
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                body += f"{value}\r\n".encode()

            def _add_file(name: str, filename: str, data: bytes) -> None:
                nonlocal body
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
                body += "Content-Type: application/octet-stream\r\n\r\n".encode()
                body += data
                body += b"\r\n"

            _add_file("file", path.name, file_bytes)
            _add_field("language", language)
            if model_size:
                _add_field("model_size", model_size)
            if diarize:
                _add_field("diarize", "true")
            body += f"--{boundary}--\r\n".encode()

            self._emit(self._on_progress or (lambda _: None), "Enviando para o servidor…")

            req = urllib.request.Request(
                f"{self._url}/transcribe",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
            )

            self._emit(self._on_progress or (lambda _: None), "Transcrevendo (aguarde)…")

            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())

            if "error" in result:
                self._emit(self._on_error or (lambda _: None), result["error"])
            else:
                self._emit(self._on_result or (lambda _: None), result)

        except urllib.error.URLError as exc:
            self._emit(
                self._on_error or (lambda _: None),
                f"Servidor indisponível em {self._url}\n{exc}",
            )
        except Exception as exc:
            self._emit(self._on_error or (lambda _: None), str(exc))
        finally:
            self._running = False
