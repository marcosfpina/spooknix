"""Loader de cenários de entrevista (Sprint 2).

Lê `scenarios/<name>.yaml`, escolhe um nível de dificuldade e devolve
um `orchestrator.Scenario` enriquecido com `prompt_addendum` e
`rubric_weights` (usado pelo evaluator).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .orchestrator import Scenario


SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"
DIFFICULTIES = ("easy", "standard", "hard")


class ScenarioNotFound(FileNotFoundError):
    """Cenário não existe no diretório de configuração."""


@dataclass
class ScenarioConfig:
    """Cenário carregado de YAML + metadados específicos do nível."""
    scenario: Scenario
    prompt_addendum: str
    rubric_weights: dict[str, float]
    base_prompt_addendum: str  # do topo do YAML, comum a todos os níveis


def _scenarios_root(root: Path | None = None) -> Path:
    return root or SCENARIOS_DIR


def list_scenarios(root: Path | None = None) -> list[str]:
    base = _scenarios_root(root)
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def load_scenario(name: str, difficulty: str = "standard", root: Path | None = None) -> ScenarioConfig:
    """Carrega `scenarios/<name>.yaml` para o nível pedido.

    Raises:
        ScenarioNotFound: arquivo não existe.
        ValueError: difficulty inválido ou YAML mal-formado.
    """
    import yaml  # type: ignore

    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Dificuldade '{difficulty}' inválida. Opções: {DIFFICULTIES}")

    path = _scenarios_root(root) / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(list_scenarios(root)) or "(nenhum)"
        raise ScenarioNotFound(f"Cenário '{name}' não encontrado em {path}. Disponíveis: {available}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    levels = data.get("difficulty_levels", {})
    if difficulty not in levels:
        raise ValueError(f"{path}: nível '{difficulty}' ausente em difficulty_levels")

    level = levels[difficulty]
    scenario = Scenario(
        interview_type=data["interview_type"],
        target_role=data["target_role"],
        difficulty=difficulty,
        duration_mins=int(level.get("duration_mins", 30)),
    )

    return ScenarioConfig(
        scenario=scenario,
        prompt_addendum=str(level.get("prompt_addendum", "")).strip(),
        rubric_weights=dict(level.get("rubric_weights", {})),
        base_prompt_addendum=str(data.get("prompt_addendum", "")).strip(),
    )
