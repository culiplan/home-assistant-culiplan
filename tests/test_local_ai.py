"""
Tests for Local AI auto-detection (Ollama + LM Studio) — task-1391.

AC#1 — Probe runs on entering AI provider config flow; respects 2s timeout
AC#2 — If detected, presents available model list from /api/tags or equivalent
AC#3 — Function-calling capability checked; warns on mismatch with constrained-intent fallback
AC#4 — Manual entry path always available
AC#5 — No telemetry leaks even on probe (purely local network)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.ai.local_ai import (
    LocalAIEndpoint,
    model_supports_function_calling,
    probe_custom_endpoint,
    probe_local_ai_endpoints,
)


# ─── LocalAIEndpoint helpers ──────────────────────────────────────────────────


def test_base_url_ollama():
    ep = LocalAIEndpoint(host="localhost", port=11434, provider="ollama")
    assert ep.base_url == "http://localhost:11434/v1"


def test_base_url_lmstudio():
    ep = LocalAIEndpoint(host="localhost", port=1234, provider="lmstudio")
    assert ep.base_url == "http://localhost:1234/v1"


def test_display_name_ollama():
    ep = LocalAIEndpoint(host="localhost", port=11434, provider="ollama")
    assert "Ollama" in ep.display_name
    assert "localhost:11434" in ep.display_name


def test_display_name_lmstudio():
    ep = LocalAIEndpoint(host="localhost", port=1234, provider="lmstudio")
    assert "LM Studio" in ep.display_name


# ─── model_supports_function_calling ─────────────────────────────────────────


def test_known_function_calling_models():
    """AC#3: well-known function-calling models return True."""
    assert model_supports_function_calling("llama3.2") is True
    assert model_supports_function_calling("llama3.2:3b") is True
    assert model_supports_function_calling("gemma3") is True
    assert model_supports_function_calling("gemma3:4b") is True
    assert model_supports_function_calling("qwen2.5") is True
    assert model_supports_function_calling("mistral") is True
    assert model_supports_function_calling("functionary") is True


def test_non_function_calling_models():
    """AC#3: models not in the known list return False (warn on mismatch)."""
    assert model_supports_function_calling("phi3") is False
    assert model_supports_function_calling("starcoder") is False
    assert model_supports_function_calling("codellama") is False
    assert model_supports_function_calling("vicuna") is False


def test_model_case_insensitive():
    """Model name matching is case-insensitive."""
    assert model_supports_function_calling("LLAMA3.2") is True
    assert model_supports_function_calling("Gemma3") is True


# ─── probe_local_ai_endpoints ─────────────────────────────────────────────────


class TestProbeLocalAIEndpoints:
    """AC#1: probe respects 2s timeout; AC#2: returns model list."""

    @pytest.mark.asyncio
    async def test_ollama_detected_with_models(self):
        """Ollama endpoint reachable → detected with model list."""
        ollama_resp = MagicMock()
        ollama_resp.status = 200
        ollama_resp.json = AsyncMock(
            return_value={
                "models": [
                    {"name": "llama3.2"},
                    {"name": "gemma3:4b"},
                ]
            }
        )
        ollama_resp.__aenter__ = AsyncMock(return_value=ollama_resp)
        ollama_resp.__aexit__ = AsyncMock(return_value=None)

        lmstudio_resp = MagicMock()
        lmstudio_resp.status = 404  # not running
        lmstudio_resp.__aenter__ = AsyncMock(return_value=lmstudio_resp)
        lmstudio_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=[ollama_resp, lmstudio_resp])

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            detected = await probe_local_ai_endpoints(MagicMock())

        assert len(detected) == 1
        ep = detected[0]
        assert ep.provider == "ollama"
        assert ep.port == 11434
        assert "llama3.2" in ep.available_models
        assert "gemma3:4b" in ep.available_models

    @pytest.mark.asyncio
    async def test_lmstudio_detected(self):
        """LM Studio endpoint reachable → detected."""
        ollama_resp = MagicMock()
        ollama_resp.status = 404  # not running
        ollama_resp.__aenter__ = AsyncMock(return_value=ollama_resp)
        ollama_resp.__aexit__ = AsyncMock(return_value=None)

        lmstudio_resp = MagicMock()
        lmstudio_resp.status = 200
        lmstudio_resp.json = AsyncMock(
            return_value={"data": [{"id": "local-model"}, {"id": "phi3"}]}
        )
        lmstudio_resp.__aenter__ = AsyncMock(return_value=lmstudio_resp)
        lmstudio_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=[ollama_resp, lmstudio_resp])

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            detected = await probe_local_ai_endpoints(MagicMock())

        assert len(detected) == 1
        ep = detected[0]
        assert ep.provider == "lmstudio"
        assert ep.port == 1234

    @pytest.mark.asyncio
    async def test_no_endpoints_detected(self):
        """Neither endpoint running → empty list returned (no error)."""
        resp = MagicMock()
        resp.status = 404
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=resp)

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            detected = await probe_local_ai_endpoints(MagicMock())

        assert detected == []

    @pytest.mark.asyncio
    async def test_connection_timeout_handled_gracefully(self):
        """AC#1: timeout (2s) is handled gracefully — no exception propagation."""

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            detected = await probe_local_ai_endpoints(MagicMock())

        # Should not raise, just return empty
        assert detected == []

    @pytest.mark.asyncio
    async def test_both_endpoints_detected(self):
        """Both Ollama and LM Studio running → both detected."""
        ollama_resp = MagicMock()
        ollama_resp.status = 200
        ollama_resp.json = AsyncMock(return_value={"models": [{"name": "llama3.2"}]})
        ollama_resp.__aenter__ = AsyncMock(return_value=ollama_resp)
        ollama_resp.__aexit__ = AsyncMock(return_value=None)

        lmstudio_resp = MagicMock()
        lmstudio_resp.status = 200
        lmstudio_resp.json = AsyncMock(return_value={"data": [{"id": "local-model"}]})
        lmstudio_resp.__aenter__ = AsyncMock(return_value=lmstudio_resp)
        lmstudio_resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=[ollama_resp, lmstudio_resp])

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            detected = await probe_local_ai_endpoints(MagicMock())

        assert len(detected) == 2
        providers = {ep.provider for ep in detected}
        assert "ollama" in providers
        assert "lmstudio" in providers


# ─── probe_custom_endpoint (AC#4: manual entry) ───────────────────────────────


class TestProbeCustomEndpoint:
    """AC#4: manual entry path for users on different host/port."""

    @pytest.mark.asyncio
    async def test_custom_ollama_endpoint_reachable(self):
        """Custom host:port probe returns endpoint if reachable."""
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"models": [{"name": "gemma3"}]})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=resp)

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            ep = await probe_custom_endpoint(
                MagicMock(), "192.168.1.50", 11434, "ollama"
            )

        assert ep is not None
        assert ep.host == "192.168.1.50"
        assert ep.port == 11434
        assert "gemma3" in ep.available_models

    @pytest.mark.asyncio
    async def test_custom_endpoint_unreachable_returns_none(self):
        """Unreachable custom endpoint returns None (no error)."""
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())

        # The probe uses HA's shared aiohttp session via
        # aiohttp_client.async_get_clientsession (per Platinum
        # `inject-websession`), so patch that helper rather than
        # aiohttp.ClientSession itself.
        with patch(
            "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            ep = await probe_custom_endpoint(
                MagicMock(), "192.168.99.99", 11434, "ollama"
            )

        assert ep is None


# ─── AC#5: no telemetry leaks ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_makes_no_external_calls():
    """AC#5: probe only connects to the specified local addresses.

    Verify that every URL the probe touches is localhost (or 127.0.0.1).
    Internet calls would be a privacy regression — Culiplan must NEVER
    learn whether the user has a local model running.
    """
    captured: list[str] = []

    # The probe gets HA's shared session; we intercept .get() to record URLs.
    class _GetCtx:
        async def __aenter__(self) -> MagicMock:
            m = MagicMock()
            m.status = 404
            return m

        async def __aexit__(self, *_args: object) -> None:
            return None

    def _record_get(url: str, **_kwargs: object) -> _GetCtx:
        captured.append(url)
        return _GetCtx()

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=_record_get)

    with patch(
        "custom_components.culiplan.ai.local_ai.aiohttp_client.async_get_clientsession",
        return_value=mock_session,
    ):
        await probe_local_ai_endpoints(MagicMock())

    assert captured, "Expected at least one probe URL to be requested"
    for url in captured:
        assert "localhost" in url or "127.0.0.1" in url, (
            f"Probe URL '{url}' must only target localhost"
        )
