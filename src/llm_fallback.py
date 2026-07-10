"""Fallback de LLM via llama.cpp server (Sprint 2).

Quando o usuário não tem `OPENAI_API_KEY` nem `LLM_BASE_URL` configurados,
sondamos o `llama-server` em `http://localhost:8081/v1/models`. Se um
modelo estiver carregado, devolvemos um `LLMClient` apontando para a API
OpenAI-compatível do llama.cpp.

Padrão da voidnxlabs: llama.cpp em 8081 (não Ollama).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request


log = logging.getLogger(__name__)

DEFAULT_LLAMACPP_URL = os.getenv("LLAMACPP_URL", "http://localhost:8081")
DEFAULT_LLAMACPP_MODEL = os.getenv("LLAMACPP_MODEL")  # opcional: força um modelo específico


def probe(url: str = DEFAULT_LLAMACPP_URL, timeout: float = 1.5) -> list[str]:
    """Retorna lista de modelos servidos pelo llama.cpp, ou [] se offline.

    Usa `GET /v1/models` (OpenAI-compatible) — devolve modelo carregado
    sem precisar de variável de ambiente extra.
    """
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/v1/models", timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log.debug("llamacpp.probe_failed url=%s err=%s", url, exc)
        return []
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def pick_model(available: list[str], preferred: str | None = DEFAULT_LLAMACPP_MODEL) -> str | None:
    """Escolhe um modelo razoável: preferred → primeiro disponível.

    llama-server geralmente serve UM modelo de cada vez, então a lista
    tem 1 elemento e a escolha é trivial.
    """
    if not available:
        return None
    if preferred and preferred in available:
        return preferred
    return available[0]


def maybe_build_client(url: str = DEFAULT_LLAMACPP_URL):
    """Retorna `LLMClient` apontando pro llama.cpp OU None se indisponível.

    Import local de LLMClient pra evitar ciclo com `src.llm_client`.
    """
    available = probe(url)
    model = pick_model(available)
    if model is None:
        return None

    from .llm_client import LLMClient

    base_url = f"{url.rstrip('/')}/v1"
    log.info("llm.fallback.llamacpp url=%s model=%s", base_url, model)
    return LLMClient(base_url=base_url, api_key="llamacpp", model=model)
