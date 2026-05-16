"""Tipos canônicos do Spooknix.

Consumido por Sprints 2 (interview suite) e 3 (summarize). Mantém o formato
de saída consistente entre transcriber, orchestrator, sessions_db e summarizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None
    avg_confidence: float = 0.0


@dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]
    language: str
    duration: float


@dataclass
class SessionRecord:
    """Uma sessão de entrevista persistida."""
    id: int | None
    ts: str
    persona: str
    scenario: str
    difficulty: str
    duration_s: float
    audio_path: str | None
    transcript_path: str | None
    rubric_json: str | None
    notes: str = ""

    @classmethod
    def new(cls, persona: str, scenario: str, difficulty: str) -> "SessionRecord":
        return cls(
            id=None,
            ts=datetime.now().isoformat(timespec="microseconds"),
            persona=persona,
            scenario=scenario,
            difficulty=difficulty,
            duration_s=0.0,
            audio_path=None,
            transcript_path=None,
            rubric_json=None,
        )


def outputs_path_for(persona: str, ts: str | None = None, root: Path | None = None) -> Path:
    """Diretório padrão para artefatos de uma sessão: outputs/interviews/<ts>-<persona>/.

    Args:
        persona: Nome da persona (slugificado em lowercase).
        ts: Timestamp ISO (default: agora, segundos).
        root: Raiz alternativa (default: cwd/outputs).

    Returns:
        Path do diretório (não cria — caller decide).
    """
    if ts is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    else:
        # Normaliza timestamps ISO para uso em filesystem
        ts = ts.replace(":", "").replace("-", "").replace("T", "-")
    slug = persona.lower().replace(" ", "_")
    base = (root or Path.cwd() / "outputs") / "interviews"
    return base / f"{ts}-{slug}"


def segment_from_dict(d: dict[str, Any]) -> Segment:
    """Converte o dict do faster-whisper (formato legado) em Segment."""
    words = [
        Word(start=w["start"], end=w["end"], word=w["word"], probability=w.get("probability", 0.0))
        for w in d.get("words", []) or []
    ]
    return Segment(
        start=d["start"],
        end=d["end"],
        text=d.get("text", "").strip(),
        words=words,
        speaker=d.get("speaker"),
        avg_confidence=d.get("avg_confidence", 0.0),
    )
