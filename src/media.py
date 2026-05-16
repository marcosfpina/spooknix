"""Conversão de mídia para o pipeline de áudio.

Encapsula chamadas ao ffmpeg para extrair áudio de qualquer container (.mp4,
.mkv, .m4a, .webm, etc.) em WAV 16 kHz mono PCM — o formato esperado pelo
faster-whisper e pelo pyannote.

Usa subprocess ao invés do binding `ffmpeg-python` para reduzir dependências:
ffmpeg está sempre disponível via flake.nix:95.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


class MediaError(RuntimeError):
    """Falha ao processar mídia via ffmpeg."""


def extract_audio(
    input_path: str | Path,
    sample_rate: int = SAMPLE_RATE,
    mono: bool = True,
) -> Path:
    """Extrai áudio para WAV PCM int16 em arquivo temporário.

    Args:
        input_path: caminho do arquivo (qualquer formato suportado pelo ffmpeg).
        sample_rate: taxa de saída (default 16 kHz — Whisper).
        mono: True → 1 canal; False → preserva original.

    Returns:
        Path do WAV temporário. O caller é responsável pela remoção.

    Raises:
        MediaError: se ffmpeg falhar ou retornar arquivo vazio.
        FileNotFoundError: se o arquivo de entrada não existir.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(src)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    out_path = Path(tmp.name)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-ar", str(sample_rate),
        "-ac", "1" if mono else "2",
        "-c:a", "pcm_s16le",
        str(out_path),
    ]
    log.info("media.extract src=%s sr=%d mono=%s", src, sample_rate, mono)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        out_path.unlink(missing_ok=True)
        raise MediaError("ffmpeg não encontrado no PATH") from exc
    except subprocess.TimeoutExpired as exc:
        out_path.unlink(missing_ok=True)
        raise MediaError(f"ffmpeg excedeu timeout em {src}") from exc

    if result.returncode != 0:
        out_path.unlink(missing_ok=True)
        raise MediaError(f"ffmpeg falhou: {result.stderr.strip()}")

    if out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise MediaError(f"ffmpeg produziu WAV vazio para {src}")

    return out_path


def is_video_or_compressed(path: str | Path) -> bool:
    """Heurística por extensão: True se precisa de extract_audio antes de diarizar."""
    ext = Path(path).suffix.lower()
    return ext in {".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".aac", ".flac", ".ogg", ".opus", ".mov"}
