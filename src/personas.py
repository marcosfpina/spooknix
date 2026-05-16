"""Loader de personas (Sprint 2).

Lê `personas/<name>.yaml` e devolve uma instância de `orchestrator.Persona`,
reaproveitando a dataclass existente em vez de duplicá-la.
"""

from __future__ import annotations

from pathlib import Path

from .orchestrator import Persona


PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


class PersonaNotFound(FileNotFoundError):
    """Persona não existe no diretório de configuração."""


def _personas_root(root: Path | None = None) -> Path:
    return root or PERSONAS_DIR


def list_personas(root: Path | None = None) -> list[str]:
    """Retorna nomes (sem extensão) de todas as personas disponíveis."""
    base = _personas_root(root)
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def load_persona(name: str, root: Path | None = None) -> Persona:
    """Carrega `personas/<name>.yaml` e mapeia para `Persona`.

    Args:
        name: nome do arquivo sem `.yaml` (ex: 'sarah', 'marcus').
        root: raiz alternativa (testes).

    Raises:
        PersonaNotFound: se o arquivo não existir.
        ValueError: se o YAML faltar com `name` ou `system_prompt`.
    """
    import yaml  # type: ignore

    path = _personas_root(root) / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(list_personas(root)) or "(nenhuma)"
        raise PersonaNotFound(f"Persona '{name}' não encontrada em {path}. Disponíveis: {available}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "name" not in data or "system_prompt" not in data:
        raise ValueError(f"{path}: YAML deve conter 'name' e 'system_prompt'")

    return Persona(
        name=data["name"],
        system_prompt=data["system_prompt"].strip(),
        voice_ref_audio=data.get("voice_ref_audio"),
        voice_ref_text=data.get("voice_ref_text"),
    )
