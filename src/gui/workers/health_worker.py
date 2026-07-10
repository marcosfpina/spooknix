"""Worker de health check (thread + GLib.idle_add).

Faz polling HTTP do /health e notifica via callbacks na main thread.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


class HealthWorker:
    """Polling periódico de /health. Callbacks executados na main thread."""

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        interval_s: float = 5.0,
        on_ready: Callable[[dict], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._url = server_url.rstrip("/")
        self._interval = interval_s
        self._on_ready = on_ready
        self._on_error = on_error
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while self._running:
            try:
                with urllib.request.urlopen(f"{self._url}/health", timeout=3) as resp:
                    data = json.loads(resp.read())
                if self._on_ready:
                    GLib.idle_add(lambda d=data: (self._on_ready(d), False))
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                if self._on_error:
                    GLib.idle_add(lambda e=str(exc): (self._on_error(e), False))
            time.sleep(self._interval)
