"""Estado global do Spooknix Desktop (GTK4).

AppState é um singleton puro Python. Componentes registram callbacks
para reagir a mudanças de estado. As atualizações de UI vindas de
threads usam GLib.idle_add.

Uso:
    state = AppState.instance()
    state.connect("server_healthy", my_callback)
    state.server_healthy = True
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

Listener = Callable[[Any], None]


def _idle(callback: Callable[[], None]) -> None:
    """Agenda callback para rodar na main thread GTK."""
    GLib.idle_add(lambda *_: (callback(), False))


class AppState:
    """Estado reativo — notifica listeners na main thread via GLib.idle_add."""

    _instance: AppState | None = None

    def __init__(self) -> None:
        if AppState._instance is not None:
            raise RuntimeError("Use AppState.instance()")
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self._values: dict[str, Any] = {
            "server_url": "http://localhost:8000",
            "server_healthy": False,
            "server_info": {},
            "is_recording": False,
            "speech_state": False,
            "vad_mode": "rms",
            "threshold": 0.01,
            "silence_duration": 2.0,
            "language": "pt",
            "model": "large-v3",
            "segments": [],
            "text": "",
            "persona": "sarah",
            "scenario": "behavioral",
            "difficulty": "medium",
            "interview_state": "IDLE",
            "sessions": [],
        }

    @classmethod
    def instance(cls) -> AppState:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Observer pattern ─────────────────────────────────────────────────

    def connect(self, key: str, callback: Listener) -> None:
        self._listeners[key].append(callback)

    def disconnect(self, key: str, callback: Listener) -> None:
        try:
            self._listeners[key].remove(callback)
        except ValueError:
            pass

    def _notify(self, key: str, value: Any) -> None:
        for cb in self._listeners.get(key, []):
            _idle(lambda: cb(value))

    # ── Generic get/set ──────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        if self._values.get(key) != value:
            self._values[key] = value
            self._notify(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    # ── Convenience properties ─────────────────────────────────────────────

    @property
    def server_url(self) -> str:
        return self._values["server_url"]

    @server_url.setter
    def server_url(self, value: str) -> None:
        self.set("server_url", value)

    @property
    def server_healthy(self) -> bool:
        return self._values["server_healthy"]

    @server_healthy.setter
    def server_healthy(self, value: bool) -> None:
        self.set("server_healthy", value)

    @property
    def server_info(self) -> dict:
        return self._values["server_info"]

    @server_info.setter
    def server_info(self, value: dict) -> None:
        self.set("server_info", value)

    @property
    def is_recording(self) -> bool:
        return self._values["is_recording"]

    @is_recording.setter
    def is_recording(self, value: bool) -> None:
        self.set("is_recording", value)

    @property
    def language(self) -> str:
        return self._values["language"]

    @language.setter
    def language(self, value: str) -> None:
        self.set("language", value)

    @property
    def model(self) -> str:
        return self._values["model"]

    @model.setter
    def model(self, value: str) -> None:
        self.set("model", value)

    @property
    def persona(self) -> str:
        return self._values["persona"]

    @persona.setter
    def persona(self, value: str) -> None:
        self.set("persona", value)

    @property
    def sessions(self) -> list:
        return self._values["sessions"]

    @sessions.setter
    def sessions(self, value: list) -> None:
        self.set("sessions", value)
