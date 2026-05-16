"""Links com âncora temporal para vídeos/áudios em sumários.

`seconds_to_link(754, "lecture.mp4")` → "[12:34](lecture.mp4#t=754)".

A âncora `#t=` é entendida nativamente por navegadores HTML5, players
locais (mpv/VLC) e por players embarcados em renderizadores Markdown
(GitHub, vscode, obsidian).
"""

from __future__ import annotations


def format_mmss(seconds: float) -> str:
    """Formata segundos como [mm:ss] (ou [h:mm:ss] se ≥1h)."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def seconds_to_link(seconds: float, source_uri: str | None = None) -> str:
    """Markdown link clicável; sem URI vira apenas `[mm:ss]`."""
    label = format_mmss(seconds)
    if not source_uri:
        return f"[{label}]"
    anchor = f"#t={int(seconds)}"
    return f"[{label}]({source_uri}{anchor})"
