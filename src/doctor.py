"""`spooknix doctor` — verificação de ambiente.

Roda uma bateria de checagens leves e renderiza uma tabela Rich:
  • CUDA disponível e VRAM
  • Servidor STT em /health
  • Dispositivos de áudio (sounddevice)
  • Baseline RMS de 1 s de microfone (detecta mic mudo)
  • Presença do ffmpeg no PATH
  • Probe do llama.cpp em http://localhost:8081/v1/models

Modo `--brev`: substitui o probe de llama.cpp por uma bateria voltada
ao deploy Brev (STT + LLM em :8080 + TTS em :8001 end-to-end).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from rich.console import Console
from rich.table import Table


_LLAMACPP_URL = os.getenv("LLAMACPP_URL", "http://localhost:8081")
_DEFAULT_STT_URL = os.getenv("SPOOKNIX_URL", "http://localhost:8000")
_BREV_LLM_URL = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")
_BREV_TTS_URL = os.getenv("TTS_BASE_URL", "http://localhost:8001")
_BREV_TTS_HEALTH = os.getenv("TTS_HEALTH_URL")  # opcional


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    value: str
    hint: str = ""


def _cuda_check() -> Check:
    try:
        import torch  # type: ignore
    except ImportError:
        return Check("CUDA", "fail", "torch não instalado", "poetry install")
    if not torch.cuda.is_available():
        return Check(
            "CUDA", "warn", "indisponível (CPU mode)",
            "instale drivers NVIDIA + cudaPackages.cudatoolkit",
        )
    name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    return Check("CUDA", "ok", f"{name} ({vram:.1f} GB)")


def _stt_health_check(url: str = _DEFAULT_STT_URL) -> Check:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as resp:
            info = json.loads(resp.read())
        model = info.get("model", "?")
        device = info.get("device", "?")
        return Check("STT server", "ok", f"{url} | {model} on {device}")
    except (urllib.error.URLError, OSError) as exc:
        return Check(
            "STT server", "warn", f"indisponível em {url}",
            f"docker compose up -d  ({exc})",
        )


def _audio_devices_check() -> Check:
    try:
        import sounddevice as sd  # type: ignore
    except ImportError:
        return Check("Audio devices", "fail", "sounddevice não instalado")
    try:
        devices = sd.query_devices()
    except Exception as exc:
        return Check("Audio devices", "fail", f"sd.query_devices falhou: {exc}")
    inputs = [
        (i, d) for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0
    ]
    if not inputs:
        return Check("Audio devices", "fail", "nenhum dispositivo de entrada", "verifique PortAudio/PipeWire")
    default_in = sd.default.device[0] if hasattr(sd.default.device, "__getitem__") else sd.default.device
    summary = f"{len(inputs)} input device(s); default={default_in}"
    return Check("Audio devices", "ok", summary, f"--device {default_in}")


def _mic_baseline_check(duration: float = 1.0) -> Check:
    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore
    except ImportError:
        return Check("Mic baseline", "fail", "numpy/sounddevice ausentes")
    try:
        rec = sd.rec(int(duration * 16_000), samplerate=16_000, channels=1, dtype="float32")
        sd.wait()
        rms = float(np.sqrt(np.mean(rec ** 2)))
    except Exception as exc:
        return Check("Mic baseline", "warn", f"captura falhou: {exc}", "spooknix doctor sem mic é ok")
    if rms < 1e-6:
        return Check("Mic baseline", "warn", f"RMS={rms:.2e} (mudo?)", "fale algo ou cheque permissões")
    return Check("Mic baseline", "ok", f"RMS={rms:.4f}")


def _ffmpeg_check() -> Check:
    path = shutil.which("ffmpeg")
    if not path:
        return Check("ffmpeg", "fail", "não encontrado", "adicione ffmpeg ao PATH (já está no flake.nix)")
    return Check("ffmpeg", "ok", path)


def _llamacpp_check(url: str = _LLAMACPP_URL) -> Check:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/v1/models", timeout=2) as resp:
            data = json.loads(resp.read())
        models = [m.get("id", "?") for m in data.get("data", [])]
        if not models:
            return Check(
                "llama.cpp", "warn", f"online mas sem modelos em {url}",
                "carregue um GGUF com `llama-server -m model.gguf --port 8081`",
            )
        return Check("llama.cpp", "ok", f"{url} | {', '.join(models[:2])}")
    except (urllib.error.URLError, OSError):
        return Check(
            "llama.cpp", "warn", f"offline em {url}",
            "llama-server -m model.gguf --port 8081  (fallback LLM local)",
        )

def _brev_llm_check(url: str = _BREV_LLM_URL) -> Check:
    """LLM em /v1/models — qualquer backend OpenAI-compatible (vLLM/llama.cpp/etc.)."""
    # Aceita base com ou sem /v1 final
    base = url.rstrip("/")
    target = base if base.endswith("/v1") else f"{base}/v1"
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(f"{target}/models", timeout=3) as resp:
            data = json.loads(resp.read())
        latency_ms = (time.monotonic() - t0) * 1000
        ids = [m.get("id", "?") for m in data.get("data", [])]
        if not ids:
            return Check("Brev LLM", "warn", f"online em {target} sem modelos servidos",
                         "carregue um modelo no worker antes do interview")
        return Check("Brev LLM", "ok", f"{target} | {ids[0]} ({latency_ms:.0f} ms)")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return Check("Brev LLM", "fail", f"indisponível em {target}",
                     "docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d llm")


def _brev_tts_check(url: str = _BREV_TTS_URL, health_url: str | None = _BREV_TTS_HEALTH) -> Check:
    """TTS: tenta /health (ou TTS_HEALTH_URL); end-to-end fica no smoke script."""
    target = health_url or f"{url.rstrip('/')}/health"
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(target, timeout=3) as resp:
            _ = resp.read(128)
        latency_ms = (time.monotonic() - t0) * 1000
        return Check("Brev TTS", "ok", f"{target} respondendo ({latency_ms:.0f} ms)")
    except (urllib.error.URLError, OSError):
        # TTS images têm endpoints inconsistentes — não bloqueia
        return Check("Brev TTS", "warn", f"{target} não respondeu",
                     "imagens TTS variam — valide com synthesize() manual ou ajuste TTS_HEALTH_URL")




_DEFAULT_CHECKS: list[Callable[[], Check]] = [
    _cuda_check,
    _stt_health_check,
    _audio_devices_check,
    _ffmpeg_check,
    _llamacpp_check,
]

_BREV_CHECKS: list[Callable[[], Check]] = [
    _cuda_check,
    _stt_health_check,
    _audio_devices_check,
    _ffmpeg_check,
    _brev_llm_check,
    _brev_tts_check,
]
def run_checks(include_mic: bool = False, brev: bool = False) -> list[Check]:
    """Executa todas as checagens. `include_mic=True` grava 1s do microfone.

    `brev=True` troca o probe de llama.cpp pelo par LLM:8080 + TTS:8001
    esperado em deploys Brev (companion workers).
    """
    checks = [c() for c in (_BREV_CHECKS if brev else _DEFAULT_CHECKS)]
    if include_mic:
        checks.append(_mic_baseline_check())
    return checks


def render(checks: list[Check], console: Console | None = None) -> None:
    """Renderiza tabela Rich com cores semânticas."""
    console = console or Console()
    table = Table(title="Spooknix Doctor", show_header=True, header_style="bold")
    table.add_column("Check", style="bold cyan")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_column("Hint", style="dim")

    style_map = {"ok": "green", "warn": "yellow", "fail": "red"}
    icon_map = {"ok": "✓", "warn": "!", "fail": "✗"}

    for c in checks:
        color = style_map.get(c.status, "white")
        status_cell = f"[{color}]{icon_map.get(c.status, '?')} {c.status}[/{color}]"
        table.add_row(c.name, status_cell, c.value, c.hint)

    console.print(table)
