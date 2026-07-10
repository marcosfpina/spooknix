"""Sumarização de vídeos/lectures/meetings com timestamps preservados.

Pipeline:
  segments → chunk_segments() → summarize_chunks() → stitch()

Cada chunk carrega um intervalo `[mm:ss → mm:ss]` no prompt para que o LLM
mantenha citações temporais nos bullets.

`tiktoken` é usado pra contar tokens de forma estável; se ele não estiver
instalado, caímos numa aproximação por palavras (1 token ≈ 0.75 palavras).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .timestamp_links import format_mmss, seconds_to_link

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 3000
DEFAULT_ENCODING = "o200k_base"


@dataclass
class Chunk:
    start: float
    end: float
    text: str  # text com prefixos [mm:ss] já inseridos por segmento


def _token_counter(encoding: str = DEFAULT_ENCODING):
    """Devolve callable str→int. Cai em heurística se tiktoken indisponível."""
    try:
        import tiktoken  # type: ignore
        try:
            enc = tiktoken.get_encoding(encoding)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return lambda s: len(enc.encode(s))
    except ImportError:
        log.debug("summarizer.tiktoken_missing fallback_to_word_count")
        return lambda s: int(len(s.split()) / 0.75) + 1


def chunk_segments(
    segments: Iterable[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    encoding: str = DEFAULT_ENCODING,
    source_uri: str | None = None,
) -> list[Chunk]:
    """Agrupa segmentos em chunks que cabem em `max_tokens` tokens.

    Cada segmento é renderizado como "[mm:ss → mm:ss] <texto>" antes de
    contar tokens, de modo que o LLM nunca perca o offset temporal.

    Args:
        segments: dicts com 'start', 'end', 'text' (formato faster-whisper).
        max_tokens: orçamento por chunk (default 3000 — folga vs limit do LLM).
        encoding: nome do encoding tiktoken (default o200k_base).
        source_uri: se fornecido, gera links clicáveis em vez de marcadores.

    Returns:
        Lista de Chunks na ordem original; cada um com `start`/`end` no intervalo.
    """
    count = _token_counter(encoding)
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_start: float | None = None
    buf_end: float = 0.0
    buf_tokens = 0

    for seg in segments:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        text = (seg.get("text") or "").strip()
        if not text:
            continue

        if source_uri:
            head = f"{seconds_to_link(start, source_uri)} → {format_mmss(end)}"
        else:
            head = f"[{format_mmss(start)} → {format_mmss(end)}]"
        line = f"{head} {text}"
        toks = count(line) + 1  # +newline

        if buf and buf_tokens + toks > max_tokens:
            chunks.append(Chunk(start=buf_start or 0.0, end=buf_end, text="\n".join(buf)))
            buf, buf_tokens, buf_start = [], 0, None

        if buf_start is None:
            buf_start = start
        buf.append(line)
        buf_tokens += toks
        buf_end = end

    if buf:
        chunks.append(Chunk(start=buf_start or 0.0, end=buf_end, text="\n".join(buf)))

    return chunks


def render_template(template_path: Path, **vars) -> str:
    """Renderiza um Jinja2 template. ImportError friendly."""
    try:
        from jinja2 import Template  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "jinja2 não instalado. Execute: poetry install --with summarize"
        ) from exc
    return Template(template_path.read_text(encoding="utf-8")).render(**vars)


def stitch(chunk_summaries: list[str]) -> str:
    """Concatena sumários dos chunks com separador semântico."""
    return "\n\n---\n\n".join(s.strip() for s in chunk_summaries if s and s.strip())
