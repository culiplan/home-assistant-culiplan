"""Regression tests for BYOK/Local AI mode dispatch (B1 from E2E review).

Verifies that _build_dispatch_mode() returns the correct compound key for
every AI mode so that create_dispatcher() never raises ValueError.
"""

from __future__ import annotations


from custom_components.culiplan.const import (
    AI_MODE_BYOK,
    AI_MODE_CLOUD,
    AI_MODE_LOCAL,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    CONF_LOCAL_ENDPOINT,
)
from custom_components.culiplan.services import _build_dispatch_mode


# ─── _build_dispatch_mode unit tests ─────────────────────────────────────────


class TestBuildDispatchMode:
    """_build_dispatch_mode must return a string accepted by create_dispatcher."""

    def test_cloud_mode_passthrough(self) -> None:
        result = _build_dispatch_mode(AI_MODE_CLOUD, {CONF_AI_MODE: AI_MODE_CLOUD})
        assert result == AI_MODE_CLOUD

    def test_byok_openai(self) -> None:
        config = {CONF_AI_MODE: AI_MODE_BYOK, CONF_BYOK_PROVIDER: "openai"}
        assert _build_dispatch_mode(AI_MODE_BYOK, config) == "byok-openai"

    def test_byok_anthropic(self) -> None:
        config = {CONF_AI_MODE: AI_MODE_BYOK, CONF_BYOK_PROVIDER: "anthropic"}
        assert _build_dispatch_mode(AI_MODE_BYOK, config) == "byok-anthropic"

    def test_byok_google_maps_to_gemini(self) -> None:
        """BYOK_PROVIDERS stores "google" but dispatcher expects "byok-gemini"."""
        config = {CONF_AI_MODE: AI_MODE_BYOK, CONF_BYOK_PROVIDER: "google"}
        assert _build_dispatch_mode(AI_MODE_BYOK, config) == "byok-gemini"

    def test_local_ollama_default_port(self) -> None:
        config = {
            CONF_AI_MODE: AI_MODE_LOCAL,
            CONF_LOCAL_ENDPOINT: "http://localhost:11434",
        }
        assert _build_dispatch_mode(AI_MODE_LOCAL, config) == "local-ollama"

    def test_local_lmstudio_port(self) -> None:
        config = {
            CONF_AI_MODE: AI_MODE_LOCAL,
            CONF_LOCAL_ENDPOINT: "http://localhost:1234",
        }
        assert _build_dispatch_mode(AI_MODE_LOCAL, config) == "local-lmstudio"

    def test_local_no_endpoint_defaults_to_ollama(self) -> None:
        config = {CONF_AI_MODE: AI_MODE_LOCAL, CONF_LOCAL_ENDPOINT: ""}
        assert _build_dispatch_mode(AI_MODE_LOCAL, config) == "local-ollama"

    def test_local_missing_endpoint_key_defaults_to_ollama(self) -> None:
        config: dict = {CONF_AI_MODE: AI_MODE_LOCAL}
        assert _build_dispatch_mode(AI_MODE_LOCAL, config) == "local-ollama"


# ─── create_dispatcher integration: no ValueError for any mode ───────────────


class TestCreateDispatcherNoValueError:
    """All compound mode strings produced by _build_dispatch_mode must be
    accepted by create_dispatcher without raising ValueError."""

    def _make_config(self, provider: str) -> dict:
        return {CONF_AI_MODE: AI_MODE_BYOK, CONF_BYOK_PROVIDER: provider}

    def _make_local_config(self, endpoint: str) -> dict:
        return {CONF_AI_MODE: AI_MODE_LOCAL, CONF_LOCAL_ENDPOINT: endpoint}

    def test_byok_openai_no_error(self) -> None:
        from custom_components.culiplan.ai.dispatchers import create_dispatcher

        mode = _build_dispatch_mode(AI_MODE_BYOK, self._make_config("openai"))
        dispatcher = create_dispatcher(mode=mode, api_key="sk-test")
        assert dispatcher is not None

    def test_byok_anthropic_no_error(self) -> None:
        from custom_components.culiplan.ai.dispatchers import create_dispatcher

        mode = _build_dispatch_mode(AI_MODE_BYOK, self._make_config("anthropic"))
        dispatcher = create_dispatcher(mode=mode, api_key="sk-ant-test")
        assert dispatcher is not None

    def test_byok_gemini_no_error(self) -> None:
        from custom_components.culiplan.ai.dispatchers import create_dispatcher

        mode = _build_dispatch_mode(AI_MODE_BYOK, self._make_config("google"))
        dispatcher = create_dispatcher(mode=mode, api_key="AIza-test")
        assert dispatcher is not None

    def test_local_ollama_no_error(self) -> None:
        from custom_components.culiplan.ai.dispatchers import create_dispatcher

        mode = _build_dispatch_mode(
            AI_MODE_LOCAL, self._make_local_config("http://localhost:11434")
        )
        dispatcher = create_dispatcher(mode=mode, api_key="ollama")
        assert dispatcher is not None

    def test_local_lmstudio_no_error(self) -> None:
        from custom_components.culiplan.ai.dispatchers import create_dispatcher

        mode = _build_dispatch_mode(
            AI_MODE_LOCAL, self._make_local_config("http://localhost:1234")
        )
        dispatcher = create_dispatcher(mode=mode, api_key="lmstudio")
        assert dispatcher is not None
