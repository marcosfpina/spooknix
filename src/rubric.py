"""Rubric estruturada para avaliar respostas de entrevista (Sprint 2).

Dataclass + parser tolerante: o LLM retorna JSON puro OU JSON fenceado
em ```json. Se falhar, tentamos um regex no maior bloco JSON-like.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field


AXES = ("communication", "technical_depth", "confidence", "clarity", "examples")


@dataclass
class Axis:
    score: int = 0          # 0–5
    comment: str = ""


@dataclass
class Rubric:
    communication: Axis = field(default_factory=Axis)
    technical_depth: Axis = field(default_factory=Axis)
    confidence: Axis = field(default_factory=Axis)
    clarity: Axis = field(default_factory=Axis)
    examples: Axis = field(default_factory=Axis)
    overall_comment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def weighted_score(self, weights: dict[str, float] | None = None) -> float:
        """Média ponderada [0, 5]. Sem pesos = média aritmética."""
        weights = weights or {a: 1.0 for a in AXES}
        total_w = sum(weights.get(a, 0) for a in AXES) or 1.0
        return sum(getattr(self, a).score * weights.get(a, 0) for a in AXES) / total_w


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_FALLBACK_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def parse_rubric(text: str) -> Rubric:
    """Tenta extrair Rubric de qualquer texto do LLM.

    Aceita: JSON puro, JSON dentro de ```json…```, ou o maior bloco JSON-like
    encontrado no texto. Campos ausentes ficam com defaults da dataclass.
    """
    if not text:
        return Rubric()

    payload = _extract_json(text)
    if payload is None:
        return Rubric()

    return _from_payload(payload)


def _extract_json(text: str) -> dict | None:
    # 1) JSON cru
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2) JSON fenceado
    m = _FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3) Maior bloco JSON-like
    candidates = _FALLBACK_RE.findall(text)
    candidates.sort(key=len, reverse=True)
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    return None


def _from_payload(d: dict) -> Rubric:
    def _axis(key: str) -> Axis:
        raw = d.get(key, {})
        if isinstance(raw, dict):
            return Axis(
                score=int(raw.get("score", 0)),
                comment=str(raw.get("comment", "")),
            )
        # Permitir o LLM mandar só o score: { "clarity": 4 }
        try:
            return Axis(score=int(raw), comment="")
        except (TypeError, ValueError):
            return Axis()

    return Rubric(
        communication=_axis("communication"),
        technical_depth=_axis("technical_depth"),
        confidence=_axis("confidence"),
        clarity=_axis("clarity"),
        examples=_axis("examples"),
        overall_comment=str(d.get("overall_comment", "")),
    )
