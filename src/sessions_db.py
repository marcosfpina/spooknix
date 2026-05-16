"""Persistência de sessões de entrevista em SQLite.

Arquivo em `~/.local/share/spooknix/sessions.db`. Schema versionado via
`PRAGMA user_version` para futuras migrations sem ferramentas externas.

Cada sessão guarda os caminhos dos artefatos (transcript.md, audio.wav,
rubric.json) ao invés de embutir os dados — o DB fica leve, e o
`--diff <a> <b>` da CLI só precisa ler colunas escalares.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .types import SessionRecord

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "spooknix" / "sessions.db"


def _default_db_path() -> Path:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


@contextmanager
def _connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Cria/atualiza schema. Idempotente."""
    cur = conn.execute("PRAGMA user_version")
    current = cur.fetchone()[0]

    if current < 1:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT    NOT NULL,
                persona         TEXT    NOT NULL,
                scenario        TEXT    NOT NULL,
                difficulty      TEXT    NOT NULL,
                duration_s      REAL    NOT NULL DEFAULT 0.0,
                audio_path      TEXT,
                transcript_path TEXT,
                rubric_json     TEXT,
                notes           TEXT    NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_ts ON sessions(ts DESC)")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def insert(record: SessionRecord, db_path: Path | None = None) -> int:
    """Insere sessão e retorna o ID atribuído."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sessions
                (ts, persona, scenario, difficulty, duration_s,
                 audio_path, transcript_path, rubric_json, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.ts,
                record.persona,
                record.scenario,
                record.difficulty,
                record.duration_s,
                record.audio_path,
                record.transcript_path,
                record.rubric_json,
                record.notes,
            ),
        )
        return int(cur.lastrowid)


def list_all(db_path: Path | None = None, limit: int = 50) -> list[SessionRecord]:
    """Sessões mais recentes primeiro."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def get(session_id: int, db_path: Path | None = None) -> SessionRecord | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_record(row) if row else None


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        ts=row["ts"],
        persona=row["persona"],
        scenario=row["scenario"],
        difficulty=row["difficulty"],
        duration_s=row["duration_s"],
        audio_path=row["audio_path"],
        transcript_path=row["transcript_path"],
        rubric_json=row["rubric_json"],
        notes=row["notes"],
    )


def rubric_dict(record: SessionRecord) -> dict:
    """Decodifica `rubric_json` ou retorna {} se vazio."""
    if not record.rubric_json:
        return {}
    try:
        return json.loads(record.rubric_json)
    except json.JSONDecodeError:
        log.warning("sessions.invalid_rubric_json id=%s", record.id)
        return {}
