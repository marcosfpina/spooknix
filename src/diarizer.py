# src/diarizer.py
"""Diarização de speakers via pyannote-audio (feature opcional).

Requer:
  poetry install --with diarization
  HF_TOKEN=<token> no ambiente  (aceitar termos em hf.co/pyannote/speaker-diarization-3.1)

Importação lazy — o servidor não falha se pyannote não estiver instalado.
"""

from __future__ import annotations

import os


def diarize(audio_path: str) -> list[dict]:
    """Roda pipeline pyannote e retorna [{start, end, speaker}].

    Args:
        audio_path: Caminho para o arquivo WAV/MP3/etc.

    Returns:
        Lista de segmentos com speaker label.

    Raises:
        ImportError: pyannote-audio não instalado.
        RuntimeError: HF_TOKEN ausente ou pipeline falhou.
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pyannote-audio não instalado. "
            "Execute: poetry install --with diarization"
        ) from exc

    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "HF_TOKEN não configurado. "
            "Defina HF_TOKEN com seu token HuggingFace e aceite os termos em "
            "hf.co/pyannote/speaker-diarization-3.1"
        )

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
    )

    # Mover para GPU se disponível
    try:
        import torch
        if torch.cuda.is_available():
            pipeline = pipeline.to(torch.device("cuda"))
    except Exception:
        pass

    diarization = pipeline(audio_path)

    segments: list[dict] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": speaker,
        })

    return segments


def assign_speakers(
    segments: list[dict],
    diarization: list[dict],
    split_at_boundaries: bool = False,
) -> list[dict]:
    """Adiciona campo 'speaker' a cada segmento de transcrição.

    A atribuição é feita por maior sobreposição temporal entre o segmento
    de transcrição e os turnos de diarização.

    Quando `split_at_boundaries=True`, segmentos do Whisper que cruzam
    múltiplos speakers são quebrados nas fronteiras da diarização. O
    texto é particionado proporcionalmente à duração de cada parte
    (heurística simples; precisão depende de word_timestamps).

    Args:
        segments: Segmentos de transcrição [{start, end, text, ...}].
        diarization: Resultado de diarize() [{start, end, speaker}].
        split_at_boundaries: Se True, divide segmentos que cruzam speakers.

    Returns:
        Segmentos com campo 'speaker' adicionado (possivelmente mais que
        a entrada quando `split_at_boundaries=True`).
    """
    if not split_at_boundaries:
        return [
            {**seg, "speaker": _best_speaker(seg["start"], seg["end"], diarization)}
            for seg in segments
        ]

    result: list[dict] = []
    for seg in segments:
        result.extend(_split_segment_at_boundaries(seg, diarization))
    return result

def _best_speaker(start: float, end: float, diarization: list[dict]) -> str:
    best_speaker = "Unknown"
    best_overlap = 0.0
    for d in diarization:
        overlap = min(end, d["end"]) - max(start, d["start"])
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = d["speaker"]
    return best_speaker

def _split_segment_at_boundaries(seg: dict, diarization: list[dict]) -> list[dict]:
    """Quebra `seg` em sub-segmentos toda vez que o speaker muda."""
    seg_start = float(seg["start"])
    seg_end = float(seg["end"])
    if seg_end <= seg_start:
        return [{**seg, "speaker": _best_speaker(seg_start, seg_end, diarization)}]

    # Coleta fronteiras dentro do segmento, em ordem.
    cuts = sorted({
        b for d in diarization
        for b in (d["start"], d["end"])
        if seg_start < b < seg_end
    })
    if not cuts:
        return [{**seg, "speaker": _best_speaker(seg_start, seg_end, diarization)}]

    points = [seg_start, *cuts, seg_end]
    total = seg_end - seg_start
    text = (seg.get("text") or "").strip()

    # Particiona texto proporcionalmente — fallback simples se word_timestamps ausente.
    words = seg.get("words") or []
    sub_segments: list[dict] = []
    for a, b in zip(points, points[1:]):
        speaker = _best_speaker(a, b, diarization)
        if words:
            piece_words = [w for w in words if a <= w.get("start", 0.0) < b]
            piece_text = "".join(w.get("word", "") for w in piece_words).strip()
        else:
            frac_a = (a - seg_start) / total
            frac_b = (b - seg_start) / total
            piece_text = _slice_text(text, frac_a, frac_b)
        sub_segments.append({
            **seg,
            "start": a,
            "end": b,
            "text": piece_text,
            "speaker": speaker,
        })
    return sub_segments


def _slice_text(text: str, frac_a: float, frac_b: float) -> str:
    """Pega uma fatia do texto correspondente ao intervalo proporcional [a, b]."""
    n = len(text)
    i = max(0, min(n, int(round(n * frac_a))))
    j = max(i, min(n, int(round(n * frac_b))))
    return text[i:j].strip()
