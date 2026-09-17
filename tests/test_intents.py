"""Tests for _register_intents — verifies executor offload (Bug 3 fix)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_hass_mock(language: str = "en") -> MagicMock:
    """Return a minimal hass mock sufficient for _register_intents."""
    hass = MagicMock()
    hass.config.language = language
    # async_add_executor_job must be awaitable (returns a coroutine).
    hass.async_add_executor_job = AsyncMock()
    # async_create_task schedules the inner coroutine immediately in tests.
    hass.async_create_task = MagicMock()
    return hass


# ─── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_intents_is_a_coroutine(hass, mock_config_entry):
    """_register_intents is async (awaitable), not a fire-and-forget task scheduler.

    Earlier shape created a background task; current code awaits the loader
    directly so async_setup_entry can guarantee intents are registered before
    it returns. Verify the entry point is awaitable and returns None.
    """
    import inspect
    from custom_components.culiplan import _register_intents

    assert inspect.iscoroutinefunction(_register_intents)


@pytest.mark.asyncio
async def test_register_intents_uses_executor_for_yaml_load(hass, mock_config_entry):
    """The YAML read_text must be dispatched to async_add_executor_job, not called inline."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    # async_add_executor_job returns the YAML payload when called.
    sample_yaml: dict = {"intents": {"CuliplanWhatsDinnerTonight": {}}}
    hass.async_add_executor_job = AsyncMock(return_value=sample_yaml)

    with patch.object(ha_intent, "async_register"):
        await _register_intents(hass, mock_config_entry)

    # async_add_executor_job must have been called (offload happened).
    hass.async_add_executor_job.assert_awaited_once()
    # Confirm the callable passed is the blocking YAML loader, not a coroutine.
    load_callable = hass.async_add_executor_job.call_args[0][0]
    assert callable(load_callable), (
        "First arg to async_add_executor_job must be a callable"
    )


@pytest.mark.asyncio
async def test_register_intents_yaml_error_is_non_fatal(hass, mock_config_entry):
    """A broken YAML file must log an error but not raise."""
    from custom_components.culiplan import _register_intents

    hass.async_add_executor_job = AsyncMock(side_effect=OSError("file missing"))

    # Should not raise even though the executor job fails.
    await _register_intents(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_register_intents_registers_known_intents(hass, mock_config_entry):
    """Known intents in the YAML are registered via intent.async_register."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    yaml_data = {
        "intents": {
            "CuliplanWhatsDinnerTonight": {},
            "CuliplanGetWeekMeals": {},
        }
    }
    hass.async_add_executor_job = AsyncMock(return_value=yaml_data)

    with patch.object(ha_intent, "async_register") as mock_register:
        await _register_intents(hass, mock_config_entry)

    # Two intents → two registrations
    assert mock_register.call_count == 2


# ─── CuliplanAddToPantry ─────────────────────────────────────────────────────

from pathlib import Path

import yaml

from custom_components.culiplan.const import DOMAIN, PANTRY_LOCATIONS

_INTENTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "culiplan"
    / "intents"
)
_LANGS = ("en", "nl", "de", "fr", "es")


def _intent_obj(
    slots: dict[str, str], language: str | None = "en", connected: bool = True
) -> MagicMock:
    client = MagicMock()
    intent_obj = MagicMock()
    intent_obj.language = language
    intent_obj.slots = {k: {"value": v} for k, v in slots.items()}
    intent_obj.hass = MagicMock()
    intent_obj.hass.config.language = "en"
    intent_obj.hass.data = (
        {DOMAIN: {"test_entry_id": {"client": client}}} if connected else {DOMAIN: {}}
    )
    response = MagicMock()
    intent_obj.create_response.return_value = response
    return intent_obj


def _spoken(intent_obj: MagicMock) -> str:
    return intent_obj.create_response.return_value.async_set_speech.call_args[0][0]


def _pantry_handler():
    from custom_components.culiplan import _make_pantry_add_intent_handler

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return _make_pantry_add_intent_handler(entry)


@pytest.mark.asyncio
async def test_register_intents_wires_pantry_add_handler(hass, mock_config_entry):
    """CuliplanAddToPantry gets the dedicated handler, not the voice-tool proxy."""
    from custom_components.culiplan import _register_intents
    from homeassistant.helpers import intent as ha_intent

    hass.async_add_executor_job = AsyncMock(
        return_value={
            "intents": {"CuliplanAddToPantry": {}, "CuliplanWhatsInPantry": {}}
        }
    )
    with patch.object(ha_intent, "async_register") as mock_register:
        await _register_intents(hass, mock_config_entry)

    by_type = {c.args[1].intent_type: c.args[1] for c in mock_register.call_args_list}
    assert set(by_type) == {"CuliplanAddToPantry", "CuliplanWhatsInPantry"}
    assert type(by_type["CuliplanAddToPantry"]).__name__ == "_PantryAddHandler"
    assert type(by_type["CuliplanWhatsInPantry"]).__name__ == "_Handler"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "location", "expected"),
    [
        ("en", "fridge", "Added milk to your fridge."),
        ("en-GB", "spice_rack", "Added milk to your spice rack."),
        ("nl", "fridge", "milk toegevoegd aan je koelkast."),
        ("de", "freezer", "milk zum Gefrierschrank hinzugefügt."),
        ("fr", "counter", "milk ajouté sur le plan de travail."),
        ("es", "pantry", "milk añadido a la despensa."),
    ],
)
async def test_pantry_add_intent_speaks_localised_confirmation(
    language, location, expected
):
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "milk ", "location": location}, language=language)
    client = intent_obj.hass.data[DOMAIN]["test_entry_id"]["client"]

    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(return_value={"success": True, "speakableResponse": "backend"}),
    ) as helper:
        await handler.async_handle(intent_obj)

    # Wildcard slot text is stripped; the language is reduced to its base code.
    helper.assert_awaited_once_with(
        client, "milk", location=location, language=language.split("-")[0]
    )
    assert _spoken(intent_obj) == expected


@pytest.mark.asyncio
async def test_pantry_add_intent_defaults_location_to_pantry():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "bread"})
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(return_value={"success": True}),
    ) as helper:
        await handler.async_handle(intent_obj)
    assert helper.call_args.kwargs["location"] == "pantry"
    assert _spoken(intent_obj) == "Added bread to your pantry."


@pytest.mark.asyncio
async def test_pantry_add_intent_unknown_location_falls_back_to_pantry():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "bread", "location": "garage"})
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(return_value={"success": True}),
    ) as helper:
        await handler.async_handle(intent_obj)
    assert helper.call_args.kwargs["location"] == "pantry"


@pytest.mark.asyncio
async def test_pantry_add_intent_unlisted_language_uses_backend_speakable():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "leite"}, language="pt")
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(
            return_value={
                "success": True,
                "speakableResponse": "leite adicionado à sua despensa.",
            }
        ),
    ):
        await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "leite adicionado à sua despensa."


@pytest.mark.asyncio
async def test_pantry_add_intent_unlisted_language_without_backend_text_uses_english():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "leite"}, language="pt")
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(return_value={"success": True}),
    ):
        await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Added leite to your pantry."


@pytest.mark.asyncio
async def test_pantry_add_intent_falls_back_to_hass_language():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "melk"}, language=None)
    intent_obj.hass.config.language = "nl-BE"
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(return_value={"success": True}),
    ) as helper:
        await handler.async_handle(intent_obj)
    assert helper.call_args.kwargs["language"] == "nl"
    assert _spoken(intent_obj) == "melk toegevoegd aan je voorraad."


@pytest.mark.asyncio
async def test_pantry_add_intent_not_connected():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "milk"}, connected=False)
    with patch(
        "custom_components.culiplan._call_pantry_add", new=AsyncMock()
    ) as helper:
        await handler.async_handle(intent_obj)
    helper.assert_not_awaited()
    assert _spoken(intent_obj) == "Culiplan is not connected."


@pytest.mark.asyncio
async def test_pantry_add_intent_empty_item():
    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "   "})
    with patch(
        "custom_components.culiplan._call_pantry_add", new=AsyncMock()
    ) as helper:
        await handler.async_handle(intent_obj)
    helper.assert_not_awaited()
    assert _spoken(intent_obj) == "Sorry, I didn't catch what to add."


@pytest.mark.asyncio
async def test_pantry_add_intent_backend_failure_is_spoken_not_raised():
    from homeassistant.exceptions import HomeAssistantError

    handler = _pantry_handler()
    intent_obj = _intent_obj({"item": "milk"})
    with patch(
        "custom_components.culiplan._call_pantry_add",
        new=AsyncMock(side_effect=HomeAssistantError("boom")),
    ):
        await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Sorry, Culiplan couldn't add that to your pantry."


def test_pantry_add_speech_covers_every_location_in_every_language():
    from custom_components.culiplan import _PANTRY_ADD_SPEECH

    assert set(_PANTRY_ADD_SPEECH) == set(_LANGS)
    for template, locations in _PANTRY_ADD_SPEECH.values():
        assert "{item}" in template and "{location}" in template
        assert set(locations) == set(PANTRY_LOCATIONS)


@pytest.mark.parametrize("lang", _LANGS)
def test_intent_yaml_declares_pantry_add(lang):
    data = yaml.safe_load((_INTENTS_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
    assert data["language"] == lang
    assert data["lists"]["item"] == {"wildcard": True}
    outs = {v["out"] for v in data["lists"]["culiplan_location"]["values"]}
    assert outs == {"pantry", "fridge", "freezer", "counter", "spice_rack"}
    blocks = data["intents"]["CuliplanAddToPantry"]["data"]
    with_location = [
        b for b in blocks if "{culiplan_location:location}" in " ".join(b["sentences"])
    ]
    without_location = [
        b for b in blocks if b.get("slots", {}).get("location") == "pantry"
    ]
    assert with_location and without_location
    assert "{{ slots.item }}" in data["responses"]["intents"]["CuliplanAddToPantry"]


@pytest.mark.parametrize(
    ("lang", "sentence", "item", "location"),
    [
        ("en", "add milk to the fridge", "milk", "fridge"),
        ("en", "put bread in my freezer", "bread", "freezer"),
        ("en", "add cumin to the spice rack", "cumin", "spice_rack"),
        ("en", "I bought apples", "apples", "pantry"),
        ("nl", "zet melk in de koelkast", "melk", "fridge"),
        ("nl", "voeg brood toe aan mijn voorraad", "brood", "pantry"),
        ("de", "füge Milch zum Kühlschrank hinzu", "milch", "fridge"),
        ("de", "lege Brot in den Gefrierschrank", "brot", "freezer"),
        ("fr", "ajoute du lait au frigo", "du lait", "fridge"),
        ("fr", "mets le pain dans le congélateur", "le pain", "freezer"),
        ("es", "añade leche a la nevera", "leche", "fridge"),
        ("es", "pon pan en el congelador", "pan", "freezer"),
    ],
)
def test_intent_yaml_sentences_recognise_with_hassil(lang, sentence, item, location):
    """The shipped sentences parse with hassil and yield the expected slots."""
    from hassil import Intents, recognize

    data = yaml.safe_load((_INTENTS_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
    intents = Intents.from_dict(
        {
            "language": lang,
            "lists": data["lists"],
            "intents": {"CuliplanAddToPantry": data["intents"]["CuliplanAddToPantry"]},
        }
    )
    result = recognize(sentence, intents)
    assert result is not None, sentence
    assert result.intent.name == "CuliplanAddToPantry"
    # hassil 1.x lowercases wildcard text, 2.x/3.x keep the user's casing
    # ("Milch" in German). The backend normalises names, so compare
    # case-insensitively here.
    assert result.entities["item"].value.strip().lower() == item
    assert result.entities["location"].value == location


# ─── Generic (voice-tool) intent handler ─────────────────────────────────────

# Tool names present in Flavorplan/packages/backend/src/services/voice/
# voiceToolRegistry.ts (snapshot 2026-09-17). Guards _INTENT_TO_TOOL against
# pointing at a tool that does not exist — "get_expiring_pantry" once did.
_BACKEND_VOICE_TOOLS = {
    "ask_other_domain", "query_pantry", "add_to_pantry", "remove_from_pantry",
    "get_expiring_items", "get_pantry_summary", "get_low_stock", "search_recipes",
    "suggest_from_pantry", "get_recipe_detail", "get_similar_recipes", "get_meal_plan",
    "schedule_meal", "get_nutrition_info", "set_nutrition_goal", "smart_meal_suggestion",
    "weekly_nutrition_summary", "get_shopping_list", "add_to_shopping_list",
    "generate_shopping_list", "query_wine_collection", "suggest_wine_pairing",
    "query_frozen_stash", "use_frozen_portion", "get_upcoming_events", "mark_as_cooked",
    "get_cook_history", "get_trending_recipes", "whats_for_dinner", "whats_in_pantry",
    "mark_pantry_depleted", "start_cooking_mode", "next_cooking_step", "set_recipe_timer",
    "get_guided_cooking_steps", "get_todays_meals", "get_week_meals", "get_user_preferences",
}  # fmt: skip


def test_intent_to_tool_names_exist_in_backend_registry():
    from custom_components.culiplan import _INTENT_TO_TOOL

    missing = set(_INTENT_TO_TOOL.values()) - _BACKEND_VOICE_TOOLS
    assert not missing, f"tools missing from backend registry: {missing}"
    assert _INTENT_TO_TOOL["CuliplanWhatsExpiringSoon"] == "get_expiring_items"


def test_every_yaml_intent_has_a_handler_mapping():
    """Each intent declared in the shipped YAML is routed somewhere."""
    from custom_components.culiplan import (
        _COOKING_INTENT_TO_SERVICE,
        _INTENT_TO_TOOL,
        _PANTRY_ADD_INTENT,
    )

    routed = (
        set(_INTENT_TO_TOOL) | set(_COOKING_INTENT_TO_SERVICE) | {_PANTRY_ADD_INTENT}
    )
    for lang in _LANGS:
        data = yaml.safe_load(
            (_INTENTS_DIR / f"{lang}.yaml").read_text(encoding="utf-8")
        )
        assert set(data["intents"]) <= routed, lang
        assert set(data["responses"]["intents"]) == set(data["intents"]), lang


def _generic_handler(intent_name: str):
    from custom_components.culiplan import _make_intent_handler

    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return _make_intent_handler(intent_name, entry)


def _client_of(intent_obj: MagicMock) -> MagicMock:
    return intent_obj.hass.data[DOMAIN]["test_entry_id"]["client"]


@pytest.mark.asyncio
async def test_generic_intent_executes_voice_tool_with_renamed_slots():
    """add {item} → add_to_shopping_list(name=...) on /api/voice/execute."""
    handler = _generic_handler("CuliplanAddToShoppingList")
    intent_obj = _intent_obj({"item": "milk "}, language="nl-BE")
    client = _client_of(intent_obj)
    client.async_execute_voice_tool = AsyncMock(
        return_value={"success": True, "speakableResponse": "melk toegevoegd."}
    )
    client.async_call_voice_tool = AsyncMock()

    await handler.async_handle(intent_obj)

    client.async_execute_voice_tool.assert_awaited_once_with(
        "add_to_shopping_list", {"name": "milk"}, language="nl"
    )
    client.async_call_voice_tool.assert_not_awaited()  # never /voice/ha-assist
    assert _spoken(intent_obj) == "melk toegevoegd."


@pytest.mark.asyncio
async def test_generic_intent_without_slots_sends_empty_params():
    handler = _generic_handler("CuliplanWhatsExpiringSoon")
    intent_obj = _intent_obj({"item": "  "})  # blank wildcard is dropped
    client = _client_of(intent_obj)
    client.async_execute_voice_tool = AsyncMock(
        return_value={"success": True, "speakableResponse": "3 items expiring."}
    )
    await handler.async_handle(intent_obj)
    client.async_execute_voice_tool.assert_awaited_once_with(
        "get_expiring_items", {}, language="en"
    )
    assert _spoken(intent_obj) == "3 items expiring."


@pytest.mark.asyncio
async def test_generic_intent_success_false_speaks_backend_error():
    handler = _generic_handler("CuliplanWhatsDinnerTonight")
    intent_obj = _intent_obj({})
    _client_of(intent_obj).async_execute_voice_tool = AsyncMock(
        return_value={
            "success": False,
            "speakableResponse": "Sorry, something went wrong.",
        }
    )
    await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Sorry, something went wrong."


@pytest.mark.asyncio
async def test_generic_intent_success_false_without_text_uses_fallback():
    handler = _generic_handler("CuliplanWhatsDinnerTonight")
    intent_obj = _intent_obj({})
    _client_of(intent_obj).async_execute_voice_tool = AsyncMock(
        return_value={"success": False}
    )
    await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Sorry, Culiplan couldn't complete that request."


@pytest.mark.asyncio
async def test_generic_intent_transport_error_is_spoken_not_raised():
    handler = _generic_handler("CuliplanWhatsInPantry")
    intent_obj = _intent_obj({})
    _client_of(intent_obj).async_execute_voice_tool = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Sorry, Culiplan couldn't complete that request."


@pytest.mark.asyncio
async def test_generic_intent_success_without_text_says_done():
    handler = _generic_handler("CuliplanGetShoppingList")
    intent_obj = _intent_obj({})
    _client_of(intent_obj).async_execute_voice_tool = AsyncMock(
        return_value={"success": True}
    )
    await handler.async_handle(intent_obj)
    assert _spoken(intent_obj) == "Done."


@pytest.mark.asyncio
async def test_generic_intent_not_connected_and_unmapped():
    intent_obj = _intent_obj({}, connected=False)
    await _generic_handler("CuliplanWhatsInPantry").async_handle(intent_obj)
    assert _spoken(intent_obj) == "Culiplan is not connected."

    intent_obj = _intent_obj({})
    await _generic_handler("CuliplanNoSuchIntent").async_handle(intent_obj)
    assert _spoken(intent_obj) == "That intent is not configured."


@pytest.mark.parametrize("lang", _LANGS)
def test_intent_yaml_lists_do_not_collide_with_builtin_names(lang):
    """Our list / rule names must not override HA's built-in ones on merge."""
    from home_assistant_intents import get_intents

    builtin = get_intents(lang) or {}
    data = yaml.safe_load((_INTENTS_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
    assert set(data) <= {"language", "intents", "lists", "responses"}
    assert not set(data.get("lists", {})) & set(builtin.get("lists", {}))
    assert not set(data.get("lists", {})) & set(builtin.get("expansion_rules", {}))
    assert not set(data["intents"]) & set(builtin.get("intents", {}))


# ─── custom_sentences installation ───────────────────────────────────────────


def _make_src(tmp_path: Path, **files: str) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    for lang, text in files.items():
        (src / f"{lang}.yaml").write_text(text, encoding="utf-8")
    return src


def test_sync_custom_sentences_first_run_copies(tmp_path):
    from custom_components.culiplan import _sync_custom_sentences_sync

    src = _make_src(tmp_path, en="language: en\n", nl="language: nl\n")
    config = tmp_path / "config"
    written = _sync_custom_sentences_sync(src, config)

    assert sorted(written) == [
        config / "custom_sentences" / "en" / "culiplan.yaml",
        config / "custom_sentences" / "nl" / "culiplan.yaml",
    ]
    assert (
        config / "custom_sentences" / "en" / "culiplan.yaml"
    ).read_bytes() == b"language: en\n"
    assert not (config / "custom_sentences" / "de").exists()  # no source → nothing


def test_sync_custom_sentences_unchanged_is_skipped(tmp_path):
    from custom_components.culiplan import _sync_custom_sentences_sync

    src = _make_src(tmp_path, en="language: en\n")
    config = tmp_path / "config"
    assert _sync_custom_sentences_sync(src, config)

    with patch.object(Path, "write_bytes") as write_bytes:
        assert _sync_custom_sentences_sync(src, config) == []
    write_bytes.assert_not_called()


def test_sync_custom_sentences_changed_is_overwritten(tmp_path):
    from custom_components.culiplan import _sync_custom_sentences_sync

    src = _make_src(tmp_path, en="language: en\n")
    config = tmp_path / "config"
    _sync_custom_sentences_sync(src, config)
    (src / "en.yaml").write_text("language: en\nintents: {}\n", encoding="utf-8")

    written = _sync_custom_sentences_sync(src, config)
    assert written == [config / "custom_sentences" / "en" / "culiplan.yaml"]
    assert written[0].read_bytes() == b"language: en\nintents: {}\n"


def test_sync_custom_sentences_real_files_are_valid_custom_sentences(tmp_path):
    """The shipped files copy as-is and parse as HA custom_sentences YAML."""
    from custom_components.culiplan import _INTENTS_DIR as real_dir
    from custom_components.culiplan import _sync_custom_sentences_sync

    written = _sync_custom_sentences_sync(real_dir, tmp_path)
    assert {p.parent.name for p in written} == set(_LANGS)
    for dest in written:
        data = yaml.safe_load(dest.read_text(encoding="utf-8"))
        assert set(data) <= {"language", "intents", "lists", "responses"}
        assert data["language"] == dest.parent.name
        assert data["intents"]


def _sync_hass(tmp_path: Path, *, conversation_loaded: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.config.config_dir = str(tmp_path)
    hass.config.components = {"conversation"} if conversation_loaded else set()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    hass.services.async_call = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_async_sync_custom_sentences_reloads_only_when_written(tmp_path):
    from custom_components.culiplan import _async_sync_custom_sentences

    hass = _sync_hass(tmp_path)
    await _async_sync_custom_sentences(hass)
    hass.services.async_call.assert_awaited_once_with(
        "conversation", "reload", {}, blocking=True
    )
    assert (tmp_path / "custom_sentences" / "en" / "culiplan.yaml").is_file()

    hass.services.async_call.reset_mock()
    await _async_sync_custom_sentences(hass)  # second setup: nothing changed
    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_sync_custom_sentences_no_reload_without_conversation(tmp_path):
    from custom_components.culiplan import _async_sync_custom_sentences

    hass = _sync_hass(tmp_path, conversation_loaded=False)
    await _async_sync_custom_sentences(hass)
    assert (tmp_path / "custom_sentences" / "nl" / "culiplan.yaml").is_file()
    hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_sync_custom_sentences_write_failure_does_not_raise(
    tmp_path, caplog
):
    from custom_components.culiplan import _async_sync_custom_sentences

    hass = _sync_hass(tmp_path)
    hass.async_add_executor_job = AsyncMock(
        side_effect=OSError("read-only file system")
    )
    await _async_sync_custom_sentences(hass)  # must not raise
    hass.services.async_call.assert_not_awaited()
    assert "read-only file system" in caplog.text


@pytest.mark.asyncio
async def test_async_sync_custom_sentences_reload_failure_does_not_raise(
    tmp_path, caplog
):
    from custom_components.culiplan import _async_sync_custom_sentences

    hass = _sync_hass(tmp_path)
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("no such service"))
    await _async_sync_custom_sentences(hass)  # must not raise
    assert "no such service" in caplog.text


@pytest.mark.asyncio
async def test_async_sync_custom_sentences_bad_config_dir_does_not_raise():
    """A MagicMock config (as in the setup wiring test) degrades to a warning."""
    from custom_components.culiplan import _async_sync_custom_sentences

    hass = MagicMock()
    hass.async_add_executor_job = MagicMock()  # not awaitable → TypeError inside
    await _async_sync_custom_sentences(hass)
    hass.services.async_call.assert_not_called()
