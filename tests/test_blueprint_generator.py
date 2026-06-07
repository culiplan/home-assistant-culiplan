"""
Tests for blueprint_generator.py (task-1400).

Covers:
  AC#1 — Service call triggers correct Culiplan API endpoint
  AC#2 — Cloud AI mode: 403 raises PremiumRequiredError + Repairs issue created
  AC#3 — BYOK mode: key never leaves HA; backend returns envelope; local dispatcher used
  AC#4 — Successful generation fires culiplan_blueprint_generated event
  AC#5 — install=True writes blueprint file to config/blueprints/automation/culiplan/
  AC#6 — _make_slug produces filesystem-safe names
  AC#7 — _extract_name_from_yaml / _extract_description_from_yaml helpers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.culiplan.blueprint_generator import (
    _make_slug,
    _extract_name_from_yaml,
    _extract_description_from_yaml,
    handle_generate_blueprint,
    EVENT_BLUEPRINT_GENERATED,
)
from custom_components.culiplan.services import PremiumRequiredError
from custom_components.culiplan.const import (
    AI_MODE_CLOUD,
    AI_MODE_BYOK,
    CONF_AI_MODE,
    CONF_BYOK_PROVIDER,
    DOMAIN,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

VALID_BLUEPRINT_YAML = """
blueprint:
  name: "Daily meal notification"
  description: "Sends a daily meal plan notification at 7am."
  domain: automation
  source_url: https://github.com/culiplan/home-assistant-culiplan/blob/main/blueprints/automation/culiplan/daily_meal.yaml

trigger:
  - platform: time
    at: "07:00:00"

action:
  - service: notify.persistent_notification
    data:
      title: "Today's Meals"
      message: "Check Culiplan for today's meal plan."

mode: single
""".strip()

CLOUD_RESPONSE = {
    "yaml": VALID_BLUEPRINT_YAML,
    "name": "Daily meal notification",
    "description": "Sends a daily meal plan notification at 7am.",
    "validation": {"valid": True, "warnings": []},
}

BYOK_ENVELOPE_RESPONSE = {
    "envelope": {
        "messages": [
            {"role": "system", "content": "You are a blueprint generator."},
            {"role": "user", "content": "Generate a blueprint."},
        ],
        "tools": [],
        "model": "gpt-4o",
        # PromptEnvelope.from_dict requires intent_id + mode inside the
        # envelope itself (top-level intent_id is unrelated).
        "intent_id": "generate_blueprint",
        "mode": "byok-openai",
    },
}


def make_hass(ai_mode=AI_MODE_CLOUD, byok_provider="openai"):
    """Create a minimal HomeAssistant mock for blueprint tests."""
    hass = MagicMock()
    hass.config.config_dir = "/tmp/ha_test"
    hass.bus.async_fire = MagicMock()
    hass.services.async_call = AsyncMock()

    # Setup config entry data
    entry_data = {
        "client": AsyncMock(),
    }
    entry_data["client"].async_post = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_AI_MODE: ai_mode,
        CONF_BYOK_PROVIDER: byok_provider,
    }
    # Must be a real dict so `{**entry.data, **entry.options}` works in
    # blueprint_generator.handle_generate_blueprint (otherwise MagicMock
    # auto-attrs blow up the spread).
    entry.options = {}

    hass.data = {
        DOMAIN: {
            "test_entry_id": entry_data,
        }
    }
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    return hass, entry_data, entry


def make_service_call(
    prompt="Notify me at 7am with today's meal plan",
    available_entities=None,
    install=False,
):
    call = MagicMock()
    call.data = {
        "prompt": prompt,
        "install": install,
    }
    if available_entities is not None:
        call.data["available_entities"] = available_entities
    return call


# ─── Unit tests: helpers ──────────────────────────────────────────────────────


class TestMakeSlug:
    def test_basic_name(self):
        assert _make_slug("Daily meal notification") == "daily_meal_notification"

    def test_special_chars(self):
        # `!` and other punctuation collapse to `_`; trailing `_` is stripped
        # because `<slug>.yaml` reads cleaner without dangling underscores.
        assert _make_slug("Notify me at 7am!") == "notify_me_at_7am"

    def test_empty_name(self):
        assert _make_slug("") == "blueprint"

    def test_leading_trailing_underscores(self):
        result = _make_slug("  hello  ")
        # Strips underscores at edges
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_already_clean(self):
        assert _make_slug("my_blueprint") == "my_blueprint"


class TestExtractHelpers:
    def test_extract_name_found(self):
        name = _extract_name_from_yaml(VALID_BLUEPRINT_YAML)
        assert name == "Daily meal notification"

    def test_extract_name_missing(self):
        name = _extract_name_from_yaml("blueprint:\n  domain: automation\n")
        assert name == "blueprint"

    def test_extract_description_found(self):
        desc = _extract_description_from_yaml(VALID_BLUEPRINT_YAML)
        assert desc == "Sends a daily meal plan notification at 7am."

    def test_extract_description_missing(self):
        desc = _extract_description_from_yaml("blueprint:\n  name: test\n")
        assert desc == ""

    def test_extract_name_quoted(self):
        yaml = 'blueprint:\n  name: "My blueprint"\n  domain: automation\n'
        assert _extract_name_from_yaml(yaml) == "My blueprint"


# ─── Integration tests: Cloud AI mode ────────────────────────────────────────


class TestCloudAIMode:
    @pytest.mark.asyncio
    async def test_cloud_success_fires_event(self):
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        client = entry_data["client"]
        client.async_post.return_value = CLOUD_RESPONSE

        with (
            patch(
                "custom_components.culiplan.blueprint_generator.async_create_premium_repair"
            ) as mock_repair,
            patch(
                "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
            ) as mock_resolve,
        ):
            await handle_generate_blueprint(hass, make_service_call(), "test_entry_id")

        # API was called with correct endpoint and payload
        client.async_post.assert_called_once()
        path, payload = client.async_post.call_args[0]
        assert path == "/api/blueprints/generate"
        assert payload["aiProviderMode"] == "culiplan-cloud"
        assert "prompt" in payload

        # Event was fired
        hass.bus.async_fire.assert_called_once()
        event_type, event_data = hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_BLUEPRINT_GENERATED
        assert event_data["name"] == "Daily meal notification"
        assert event_data["valid"] is True
        assert event_data["yaml"] == VALID_BLUEPRINT_YAML

        # Premium repair was resolved (not created)
        mock_resolve.assert_called_once_with(hass, "ai.blueprint")
        mock_repair.assert_not_called()

    @pytest.mark.asyncio
    async def test_cloud_403_raises_premium_error(self):
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        client = entry_data["client"]
        upgrade_url = "https://culiplan.com/premium"
        client.async_post.side_effect = Exception(
            f'403 {{"error": "premium_required", "upgradeUrl": "{upgrade_url}"}}'
        )

        with patch(
            "custom_components.culiplan.blueprint_generator.async_create_premium_repair"
        ) as mock_repair:
            with pytest.raises(PremiumRequiredError) as exc_info:
                await handle_generate_blueprint(
                    hass, make_service_call(), "test_entry_id"
                )

        assert exc_info.value.feature == "ai.blueprint"
        assert "premium" in exc_info.value.upgrade_url.lower()
        mock_repair.assert_called_once()

    @pytest.mark.asyncio
    async def test_cloud_passes_available_entities(self):
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        client = entry_data["client"]
        client.async_post.return_value = CLOUD_RESPONSE
        entities = ["calendar.culiplan_meal_plan", "light.kitchen"]

        with patch(
            "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
        ):
            await handle_generate_blueprint(
                hass,
                make_service_call(available_entities=entities),
                "test_entry_id",
            )

        _, payload = client.async_post.call_args[0]
        assert payload["context"]["available_entities"] == entities

    @pytest.mark.asyncio
    async def test_cloud_truncates_available_entities_at_100(self):
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        client = entry_data["client"]
        client.async_post.return_value = CLOUD_RESPONSE
        entities = [f"sensor.entity_{i}" for i in range(150)]

        with patch(
            "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
        ):
            await handle_generate_blueprint(
                hass,
                make_service_call(available_entities=entities),
                "test_entry_id",
            )

        _, payload = client.async_post.call_args[0]
        assert len(payload["context"]["available_entities"]) == 100


# ─── Integration tests: BYOK mode ────────────────────────────────────────────


class TestBYOKMode:
    @pytest.mark.asyncio
    async def test_byok_uses_envelope(self):
        """BYOK mode: backend returns envelope; dispatcher executes locally."""
        hass, entry_data, entry = make_hass(AI_MODE_BYOK, byok_provider="openai")
        client = entry_data["client"]
        client.async_post.return_value = BYOK_ENVELOPE_RESPONSE

        mock_result = MagicMock()
        mock_result.text = VALID_BLUEPRINT_YAML

        mock_dispatcher = AsyncMock()
        mock_dispatcher.dispatch = AsyncMock(return_value=mock_result)

        with (
            patch(
                "custom_components.culiplan.blueprint_generator.BYOKKeyStore"
            ) as MockKeyStore,
            patch(
                "custom_components.culiplan.blueprint_generator.create_dispatcher",
                return_value=mock_dispatcher,
            ),
            patch(
                "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
            ),
            patch(
                "custom_components.culiplan.blueprint_generator.async_create_premium_repair"
            ),
        ):
            # BYOKKeyStore: `async_load` is async, `get_key` is sync.
            mock_ks_instance = MagicMock()
            mock_ks_instance.async_load = AsyncMock(return_value=None)
            mock_ks_instance.get_key = MagicMock(return_value="sk-test-key")
            MockKeyStore.return_value = mock_ks_instance

            await handle_generate_blueprint(hass, make_service_call(), "test_entry_id")

        # Backend was called for envelope
        client.async_post.assert_called_once()
        path, payload = client.async_post.call_args[0]
        assert path == "/api/blueprints/generate"
        assert payload["aiProviderMode"] == "byok-openai"

        # Dispatcher was used to execute locally
        mock_dispatcher.dispatch.assert_called_once()

        # Event was fired with YAML
        hass.bus.async_fire.assert_called_once()
        event_type, event_data = hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_BLUEPRINT_GENERATED
        assert event_data["yaml"] == VALID_BLUEPRINT_YAML

    @pytest.mark.asyncio
    async def test_byok_missing_key_raises_error(self):
        """BYOK mode without a stored key raises HomeAssistantError."""
        from homeassistant.exceptions import HomeAssistantError

        hass, entry_data, entry = make_hass(AI_MODE_BYOK)

        with patch(
            "custom_components.culiplan.blueprint_generator.BYOKKeyStore"
        ) as MockKeyStore:
            mock_ks_instance = MagicMock()
            mock_ks_instance.async_load = AsyncMock(return_value=None)
            mock_ks_instance.get_key = MagicMock(return_value="")
            MockKeyStore.return_value = mock_ks_instance

            # The error surfaces via translation_key "byok_key_missing", which
            # HA renders as a generic "key missing" message — match the
            # underlying translation_key in the cause chain rather than the
            # rendered text (which varies by HA version).
            with pytest.raises(HomeAssistantError) as excinfo:
                await handle_generate_blueprint(
                    hass, make_service_call(), "test_entry_id"
                )
            assert getattr(excinfo.value, "translation_key", "") == "byok_key_missing"


# ─── Integration tests: blueprint install ────────────────────────────────────


class TestBlueprintInstall:
    @pytest.mark.asyncio
    async def test_install_writes_file(self, tmp_path):
        """install=True writes YAML to blueprints dir and calls blueprint.reload."""
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        hass.config.config_dir = str(tmp_path)
        client = entry_data["client"]
        client.async_post.return_value = CLOUD_RESPONSE

        # async_add_executor_job should execute the callable directly in tests
        async def fake_executor_job(fn, *args):
            fn(*args)

        hass.async_add_executor_job = fake_executor_job

        with patch(
            "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
        ):
            await handle_generate_blueprint(
                hass,
                make_service_call(install=True),
                "test_entry_id",
            )

        # Blueprint file should exist
        blueprint_dir = tmp_path / "blueprints" / "automation" / "culiplan"
        yaml_files = list(blueprint_dir.glob("*.yaml"))
        assert len(yaml_files) == 1
        content = yaml_files[0].read_text()
        assert "Daily meal notification" in content

        # blueprint.reload was called
        hass.services.async_call.assert_called_once_with(
            "blueprint", "reload", {}, blocking=False
        )

    @pytest.mark.asyncio
    async def test_install_false_does_not_write(self, tmp_path):
        """install=False (default) does NOT write any file."""
        hass, entry_data, entry = make_hass(AI_MODE_CLOUD)
        hass.config.config_dir = str(tmp_path)
        client = entry_data["client"]
        client.async_post.return_value = CLOUD_RESPONSE

        with patch(
            "custom_components.culiplan.blueprint_generator.async_resolve_premium_repair"
        ):
            await handle_generate_blueprint(
                hass,
                make_service_call(install=False),
                "test_entry_id",
            )

        blueprint_dir = tmp_path / "blueprints"
        assert not blueprint_dir.exists()


# ─── Extra coverage for _cloud_generate_blueprint (v0.13.0) ──────────────────


@pytest.mark.asyncio
async def test_cloud_generate_blueprint_403_premium_required():
    from custom_components.culiplan.blueprint_generator import _cloud_generate_blueprint
    from custom_components.culiplan.services import PremiumRequiredError

    client = AsyncMock()
    client.async_post = AsyncMock(
        side_effect=Exception(
            '403 {"error":"premium_required","upgradeUrl":"https://x.test"}'
        )
    )
    with pytest.raises(PremiumRequiredError) as excinfo:
        await _cloud_generate_blueprint(client, "prompt", None)
    assert excinfo.value.upgrade_url == "https://x.test"


@pytest.mark.asyncio
async def test_cloud_generate_blueprint_403_unparseable_body():
    """A 403 with non-JSON body still raises PremiumRequiredError with default URL."""
    from custom_components.culiplan.blueprint_generator import _cloud_generate_blueprint
    from custom_components.culiplan.services import PremiumRequiredError

    client = AsyncMock()
    client.async_post = AsyncMock(
        side_effect=Exception("403 Forbidden — premium_required")
    )
    with pytest.raises(PremiumRequiredError) as excinfo:
        await _cloud_generate_blueprint(client, "prompt", None)
    assert "culiplan.com" in excinfo.value.upgrade_url


@pytest.mark.asyncio
async def test_cloud_generate_blueprint_other_error_wraps():
    from custom_components.culiplan.blueprint_generator import _cloud_generate_blueprint
    from homeassistant.exceptions import HomeAssistantError

    client = AsyncMock()
    client.async_post = AsyncMock(side_effect=RuntimeError("network"))
    with pytest.raises(HomeAssistantError) as excinfo:
        await _cloud_generate_blueprint(client, "prompt", None)
    assert (
        getattr(excinfo.value, "translation_key", "")
        == "blueprint_generation_failed"
    )


@pytest.mark.asyncio
async def test_cloud_generate_blueprint_appends_available_entities():
    """available_entities are truncated to 100 + passed in context."""
    from custom_components.culiplan.blueprint_generator import _cloud_generate_blueprint

    client = AsyncMock()
    client.async_post = AsyncMock(return_value={"yaml": "", "validation": {}})
    await _cloud_generate_blueprint(
        client, "prompt", available_entities=[f"e{i}" for i in range(150)]
    )
    payload = client.async_post.call_args[0][1]
    assert payload["context"]["available_entities"][-1] == "e99"
    assert len(payload["context"]["available_entities"]) == 100


# ─── _extract_name_from_yaml / _extract_description_from_yaml ────────────────


def test_extract_name_from_yaml_matches():
    from custom_components.culiplan.blueprint_generator import _extract_name_from_yaml

    assert (
        _extract_name_from_yaml('blueprint:\n  name: "My BP"\n')
        == "My BP"
    )


def test_extract_name_from_yaml_fallback():
    from custom_components.culiplan.blueprint_generator import _extract_name_from_yaml

    assert _extract_name_from_yaml("blueprint:") == "blueprint"


def test_extract_description_from_yaml_matches():
    from custom_components.culiplan.blueprint_generator import (
        _extract_description_from_yaml,
    )

    assert (
        _extract_description_from_yaml(
            'blueprint:\n  description: "My description"\n'
        )
        == "My description"
    )


def test_extract_description_from_yaml_fallback():
    from custom_components.culiplan.blueprint_generator import (
        _extract_description_from_yaml,
    )

    assert _extract_description_from_yaml("blueprint:") == ""
