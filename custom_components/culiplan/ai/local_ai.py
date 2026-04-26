"""
Local AI auto-detection for Ollama and LM Studio (task-1391).

Per §13.4: when the user enters the AI provider config flow, probe:
  - localhost:11434 (default Ollama port)
  - localhost:1234  (default LM Studio port)

If a compatible endpoint responds, surface:
  "Detected Ollama at localhost:11434 — use it for Flavorplan AI?"
  with explicit opt-in required (§13.4 rationale: HA users run multiple
  unrelated services on the same host).

The integration verifies the endpoint by querying the model list and
surfaces available models for the user to choose from.  If the user picks
a model that doesn't support function calling, we warn and fall back to a
constrained intent set (simple suggestions but not tool-calling intents).

Privacy guarantee (AC#5): the probe is purely local-network.  Nothing is
transmitted beyond localhost (or the LAN if the user specifies a custom host).
The result of the probe is never reported to Flavorplan.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Default probe targets (§13.4)
OLLAMA_DEFAULT_HOST = "localhost"
OLLAMA_DEFAULT_PORT = 11434
LMSTUDIO_DEFAULT_HOST = "localhost"
LMSTUDIO_DEFAULT_PORT = 1234

# Probe timeout per endpoint (AC#1: respects 2s timeout)
_PROBE_TIMEOUT_SEC = 2.0

# Models known to support function/tool calling.
# When the user picks a model NOT in this list, we warn about constrained-intent fallback.
_FUNCTION_CALLING_MODELS: frozenset[str] = frozenset({
    # Ollama / llama.cpp compatible
    "llama3.2",
    "llama3.1",
    "llama3.1:8b",
    "llama3.1:70b",
    "llama3",
    "llama3:8b",
    "llama3:70b",
    "qwen2.5",
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen2.5:32b",
    "qwen2.5:72b",
    "gemma3",
    "gemma3:4b",
    "gemma3:12b",
    "gemma3:27b",
    "mistral-nemo",
    "mistral",
    "mistral:7b",
    "mixtral",
    "mixtral:8x7b",
    "hermes3",
    "hermes3:8b",
    "functionary",
    "functionary-small",
    "functionary-medium",
    "deepseek-r1",
    # LM Studio bundled models typically follow llama/mistral family
    "local-model",  # placeholder shown to users for manual LM Studio
})


@dataclass
class LocalAIEndpoint:
    """A detected local AI endpoint."""
    host: str
    port: int
    provider: str              # "ollama" or "lmstudio"
    available_models: list[str] = field(default_factory=list)
    openai_compatible: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    @property
    def display_name(self) -> str:
        product = "Ollama" if self.provider == "ollama" else "LM Studio"
        return f"{product} at {self.host}:{self.port}"


def model_supports_function_calling(model_name: str) -> bool:
    """
    Check whether a model name is known to support function calling.

    Uses a prefix/exact match against the known-capable list.
    Returns True for exact match or when the model name starts with any
    known capable prefix (e.g. "llama3.2:3b" matches "llama3.2").
    """
    name_lower = model_name.lower().split(":")[0]  # strip tag (e.g. ":3b")
    return any(
        name_lower == cap.lower() or name_lower.startswith(cap.lower().split(":")[0])
        for cap in _FUNCTION_CALLING_MODELS
    )


async def _probe_ollama(
    host: str,
    port: int,
    session: aiohttp.ClientSession,
) -> LocalAIEndpoint | None:
    """
    Probe a potential Ollama endpoint.

    Queries GET /api/tags to list available models.
    Returns None if the endpoint is unreachable or doesn't look like Ollama.
    """
    url = f"http://{host}:{port}/api/tags"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=_PROBE_TIMEOUT_SEC)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            models = [
                m.get("name", "")
                for m in data.get("models", [])
                if m.get("name")
            ]
            return LocalAIEndpoint(
                host=host,
                port=port,
                provider="ollama",
                available_models=models,
                openai_compatible=True,
            )
    except (aiohttp.ClientError, asyncio.TimeoutError, Exception):
        return None


async def _probe_lmstudio(
    host: str,
    port: int,
    session: aiohttp.ClientSession,
) -> LocalAIEndpoint | None:
    """
    Probe a potential LM Studio endpoint.

    Queries GET /v1/models (OpenAI-compatible endpoint) to list models.
    Returns None if the endpoint is unreachable.
    """
    url = f"http://{host}:{port}/v1/models"
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=_PROBE_TIMEOUT_SEC)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            models = [
                m.get("id", "")
                for m in data.get("data", [])
                if m.get("id")
            ]
            return LocalAIEndpoint(
                host=host,
                port=port,
                provider="lmstudio",
                available_models=models,
                openai_compatible=True,
            )
    except (aiohttp.ClientError, asyncio.TimeoutError, Exception):
        return None


async def probe_local_ai_endpoints(
    extra_hosts: list[tuple[str, int, str]] | None = None,
) -> list[LocalAIEndpoint]:
    """
    Probe all known local AI endpoints and return detected ones.

    Probes (per §13.4):
      - localhost:11434  — Ollama
      - localhost:1234   — LM Studio

    Additional (host, port, provider) tuples can be passed via extra_hosts
    for containerised or custom-port deployments.

    Privacy guarantee (AC#5): probes are purely local network.
    This function never makes outbound calls to the internet.

    Returns:
        List of detected LocalAIEndpoint objects (may be empty).
    """
    probe_targets = [
        (OLLAMA_DEFAULT_HOST, OLLAMA_DEFAULT_PORT, "ollama"),
        (LMSTUDIO_DEFAULT_HOST, LMSTUDIO_DEFAULT_PORT, "lmstudio"),
    ]
    if extra_hosts:
        probe_targets.extend(extra_hosts)

    detected: list[LocalAIEndpoint] = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for host, port, provider in probe_targets:
            if provider == "ollama":
                tasks.append(_probe_ollama(host, port, session))
            else:
                tasks.append(_probe_lmstudio(host, port, session))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, LocalAIEndpoint):
            _LOGGER.debug(
                "[culiplan][local-ai] Detected %s with %d model(s)",
                result.display_name,
                len(result.available_models),
            )
            detected.append(result)

    return detected


async def probe_custom_endpoint(
    host: str,
    port: int,
    provider: str,
) -> LocalAIEndpoint | None:
    """
    Probe a user-specified custom endpoint (AC#4: manual entry path).

    Args:
        host:     Hostname or IP (e.g. "192.168.1.50").
        port:     Port number.
        provider: "ollama" or "lmstudio".

    Returns:
        LocalAIEndpoint if reachable, None otherwise.
    """
    async with aiohttp.ClientSession() as session:
        if provider == "ollama":
            return await _probe_ollama(host, port, session)
        return await _probe_lmstudio(host, port, session)
