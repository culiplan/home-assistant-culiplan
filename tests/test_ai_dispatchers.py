"""
Tests for the AI provider dispatcher classes (task-1387).

AC#1 — Three dispatcher classes: OpenAICompatibleDispatcher, AnthropicDispatcher, GoogleDispatcher
AC#2 — Each accepts envelope schema and returns {text, tool_calls[]} or raises typed error
AC#3 — Multi-turn function-calling loops correctly
AC#4 — Streaming deferred (documented)
AC#5 — Optional debug mode logs prompts client-side only

Tests use pytest-asyncio with unittest.mock; no live AI provider calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.culiplan.ai.types import (
    DispatchResult,
    DispatcherError,
    Message,
    PromptEnvelope,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from custom_components.culiplan.ai.dispatchers import (
    AnthropicDispatcher,
    GoogleDispatcher,
    OpenAICompatibleDispatcher,
    create_dispatcher,
)
from custom_components.culiplan.ai.service import AIDispatchService


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def make_envelope(intent: str = "suggest_meal", model: str = "test-model") -> PromptEnvelope:
    return PromptEnvelope(
        messages=[
            Message(role="system", content="You are the Culiplan AI assistant."),
            Message(role="user", content=f"Execute intent: {intent}"),
        ],
        tools=[
            ToolSpec(
                name="add_to_shopping_list",
                description="Add item to shopping list",
                parameters={
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "Item name"},
                    },
                    "required": ["item_name"],
                },
            ),
            ToolSpec(
                name="get_meal_plan",
                description="Get today's meal plan",
                parameters={"type": "object", "properties": {}},
            ),
        ],
        model=model,
        intent_id=intent,
        mode="byok-anthropic",
    )


# ─── PromptEnvelope.from_dict ─────────────────────────────────────────────────


def test_envelope_from_dict():
    """PromptEnvelope.from_dict parses the backend response shape."""
    raw = {
        "messages": [
            {"role": "system", "content": "You are a cooking assistant."},
            {"role": "user", "content": "Suggest a meal."},
        ],
        "tools": [
            {
                "name": "get_pantry",
                "description": "Fetch pantry",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "model": "claude-sonnet-4-6",
        "intent_id": "suggest_meal",
        "mode": "byok-anthropic",
    }
    envelope = PromptEnvelope.from_dict(raw)

    assert len(envelope.messages) == 2
    assert envelope.messages[0].role == "system"
    assert len(envelope.tools) == 1
    assert envelope.tools[0].name == "get_pantry"
    assert envelope.model == "claude-sonnet-4-6"
    assert envelope.intent_id == "suggest_meal"
    assert envelope.mode == "byok-anthropic"


# ─── DispatchResult helpers ────────────────────────────────────────────────────


def test_dispatch_result_is_final_text_no_tools():
    r = DispatchResult(text="Dinner suggestion: pasta.", tool_calls=[])
    assert r.is_final is True


def test_dispatch_result_not_final_with_tool_calls():
    r = DispatchResult(text=None, tool_calls=[ToolCall(name="get_pantry", params={})])
    assert r.is_final is False


def test_dispatch_result_not_final_no_text():
    r = DispatchResult(text=None, tool_calls=[])
    assert r.is_final is False


# ─── create_dispatcher factory ────────────────────────────────────────────────


@patch("custom_components.culiplan.ai.dispatchers.OpenAICompatibleDispatcher.__init__", return_value=None)
def test_factory_byok_openai(mock_init):
    """create_dispatcher('byok-openai') returns an OpenAICompatibleDispatcher."""
    d = create_dispatcher("byok-openai", api_key="sk-test", base_url=None)
    assert isinstance(d, OpenAICompatibleDispatcher)


@patch("custom_components.culiplan.ai.dispatchers.AnthropicDispatcher.__init__", return_value=None)
def test_factory_byok_anthropic(mock_init):
    d = create_dispatcher("byok-anthropic", api_key="sk-ant-test")
    assert isinstance(d, AnthropicDispatcher)


@patch("custom_components.culiplan.ai.dispatchers.GoogleDispatcher.__init__", return_value=None)
def test_factory_byok_gemini(mock_init):
    d = create_dispatcher("byok-gemini", api_key="AIzaTest")
    assert isinstance(d, GoogleDispatcher)


@patch("custom_components.culiplan.ai.dispatchers.OpenAICompatibleDispatcher.__init__", return_value=None)
def test_factory_local_ollama(mock_init):
    d = create_dispatcher("local-ollama", base_url="http://localhost:11434/v1")
    assert isinstance(d, OpenAICompatibleDispatcher)


@patch("custom_components.culiplan.ai.dispatchers.OpenAICompatibleDispatcher.__init__", return_value=None)
def test_factory_local_lmstudio(mock_init):
    d = create_dispatcher("local-lmstudio", base_url="http://localhost:1234/v1")
    assert isinstance(d, OpenAICompatibleDispatcher)


def test_factory_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown AI mode"):
        create_dispatcher("invalid-mode")


def test_factory_cloud_mode_raises():
    """Cloud mode is not dispatched from HA — raises ValueError."""
    with pytest.raises(ValueError, match="Unknown AI mode"):
        create_dispatcher("culiplan-cloud")


# ─── OpenAICompatibleDispatcher ───────────────────────────────────────────────


@pytest.fixture
def mock_openai_client():
    """Mock the AsyncOpenAI client."""
    with patch("custom_components.culiplan.ai.dispatchers.AsyncOpenAI", autospec=True) as MockClass:
        instance = MockClass.return_value
        yield instance


class TestOpenAICompatibleDispatcher:
    """AC#1 + AC#2: dispatcher accepts envelope, returns result."""

    @pytest.mark.asyncio
    async def test_text_response_no_tool_calls(self, mock_openai_client):
        """Model returns a plain text response — no tool calls."""
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "I suggest spaghetti carbonara."
        choice.message.tool_calls = None
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope())

        assert result.text == "I suggest spaghetti carbonara."
        assert result.tool_calls == []
        assert result.is_final is True

    @pytest.mark.asyncio
    async def test_tool_call_response(self, mock_openai_client):
        """Model returns a tool call — result has tool_calls, no final text."""
        tc = MagicMock()
        tc.id = "call-001"
        tc.function.name = "get_meal_plan"
        tc.function.arguments = '{"date": "today"}'

        choice = MagicMock()
        choice.finish_reason = "tool_calls"
        choice.message.content = None
        choice.message.tool_calls = [tc]

        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope())

        assert result.text is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_meal_plan"
        assert result.tool_calls[0].params == {"date": "today"}
        assert result.tool_calls[0].call_id == "call-001"
        assert result.is_final is False

    @pytest.mark.asyncio
    async def test_tool_results_appended_as_tool_messages(self, mock_openai_client):
        """When tool_results are provided, they appear as tool messages in the API call."""
        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "Here is the final answer."
        choice.message.tool_calls = None
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        tool_results = [
            ToolResult(call_id="call-001", tool_name="get_meal_plan", content={"dinner": "pasta"})
        ]

        await dispatcher.dispatch(make_envelope(), tool_results=tool_results)

        call_args = mock_openai_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        tool_msg = next((m for m in messages if m.get("role") == "tool"), None)
        assert tool_msg is not None
        assert tool_msg["tool_call_id"] == "call-001"
        assert "pasta" in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_auth_error_raises_provider_auth_error(self, mock_openai_client):
        """401 from provider raises ProviderAuthError (AC#2 typed error)."""
        from openai import APIStatusError

        exc = APIStatusError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body={"error": {"message": "Invalid API key"}},
        )
        mock_openai_client.chat.completions.create = AsyncMock(side_effect=exc)

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        with pytest.raises(ProviderAuthError, match="rejected the API key"):
            await dispatcher.dispatch(make_envelope())

    @pytest.mark.asyncio
    async def test_rate_limit_raises_provider_rate_limit_error(self, mock_openai_client):
        """429 from provider raises ProviderRateLimitError."""
        from openai import APIStatusError

        exc = APIStatusError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "Rate limit exceeded"}},
        )
        mock_openai_client.chat.completions.create = AsyncMock(side_effect=exc)

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        with pytest.raises(ProviderRateLimitError):
            await dispatcher.dispatch(make_envelope())

    @pytest.mark.asyncio
    async def test_server_error_raises_provider_unavailable(self, mock_openai_client):
        """500 from provider raises ProviderUnavailableError."""
        from openai import APIStatusError

        exc = APIStatusError(
            message="Internal server error",
            response=MagicMock(status_code=500, headers={}),
            body={"error": {"message": "Internal server error"}},
        )
        mock_openai_client.chat.completions.create = AsyncMock(side_effect=exc)

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = False

        with pytest.raises(ProviderUnavailableError):
            await dispatcher.dispatch(make_envelope())

    @pytest.mark.asyncio
    async def test_debug_mode_logs_prompt(self, mock_openai_client, caplog):
        """AC#5: debug mode logs the prompt content at DEBUG level (client-side only)."""
        import logging

        choice = MagicMock()
        choice.finish_reason = "stop"
        choice.message.content = "Debug answer."
        choice.message.tool_calls = None
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[choice])
        )

        dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
        dispatcher._client = mock_openai_client
        dispatcher._debug = True

        with caplog.at_level(logging.DEBUG, logger="custom_components.culiplan.ai.dispatchers"):
            await dispatcher.dispatch(make_envelope())

        assert any("DEBUG MODE" in r.message for r in caplog.records)


# ─── AnthropicDispatcher ──────────────────────────────────────────────────────


@pytest.fixture
def mock_anthropic_client():
    with patch("custom_components.culiplan.ai.dispatchers.AsyncAnthropic", autospec=True) as MockClass:
        instance = MockClass.return_value
        yield instance


class TestAnthropicDispatcher:
    """AC#1 + AC#2: Anthropic dispatcher accepts envelope, returns result."""

    @pytest.mark.asyncio
    async def test_text_response(self, mock_anthropic_client):
        """Anthropic returns a plain text content block."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I recommend tacos tonight."

        mock_anthropic_client.messages.create = AsyncMock(
            return_value=MagicMock(content=[text_block])
        )

        dispatcher = AnthropicDispatcher.__new__(AnthropicDispatcher)
        dispatcher._client = mock_anthropic_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope())

        assert result.text == "I recommend tacos tonight."
        assert result.tool_calls == []
        assert result.is_final is True

    @pytest.mark.asyncio
    async def test_tool_use_response(self, mock_anthropic_client):
        """Anthropic returns a tool_use content block."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "add_to_shopping_list"
        tool_block.input = {"item_name": "pasta"}
        tool_block.id = "toolu_01"

        mock_anthropic_client.messages.create = AsyncMock(
            return_value=MagicMock(content=[tool_block])
        )

        dispatcher = AnthropicDispatcher.__new__(AnthropicDispatcher)
        dispatcher._client = mock_anthropic_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope())

        assert result.text is None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "add_to_shopping_list"
        assert result.tool_calls[0].params == {"item_name": "pasta"}
        assert result.tool_calls[0].call_id == "toolu_01"
        assert result.is_final is False

    @pytest.mark.asyncio
    async def test_system_prompt_separated(self, mock_anthropic_client):
        """System message is passed as `system=` kwarg, not in messages list."""
        mock_anthropic_client.messages.create = AsyncMock(
            return_value=MagicMock(content=[])
        )

        dispatcher = AnthropicDispatcher.__new__(AnthropicDispatcher)
        dispatcher._client = mock_anthropic_client
        dispatcher._debug = False

        await dispatcher.dispatch(make_envelope())

        call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
        assert "system" in call_kwargs
        assert call_kwargs["system"] == "You are the Culiplan AI assistant."
        # System message should not appear in messages list
        messages = call_kwargs["messages"]
        for msg in messages:
            assert msg.get("role") != "system"

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_anthropic_client):
        from anthropic import APIStatusError

        exc = APIStatusError(
            message="Authentication failed",
            response=MagicMock(status_code=401, headers={}),
            body={},
        )
        mock_anthropic_client.messages.create = AsyncMock(side_effect=exc)

        dispatcher = AnthropicDispatcher.__new__(AnthropicDispatcher)
        dispatcher._client = mock_anthropic_client
        dispatcher._debug = False

        with pytest.raises(ProviderAuthError, match="rejected the API key"):
            await dispatcher.dispatch(make_envelope())

    @pytest.mark.asyncio
    async def test_tool_results_forwarded_as_user_content(self, mock_anthropic_client):
        """Tool results are appended as user content with type=tool_result."""
        mock_anthropic_client.messages.create = AsyncMock(
            return_value=MagicMock(content=[])
        )

        dispatcher = AnthropicDispatcher.__new__(AnthropicDispatcher)
        dispatcher._client = mock_anthropic_client
        dispatcher._debug = False

        tool_results = [
            ToolResult(call_id="toolu_01", tool_name="get_pantry", content={"items": ["eggs"]})
        ]
        await dispatcher.dispatch(make_envelope(), tool_results=tool_results)

        messages = mock_anthropic_client.messages.create.call_args.kwargs["messages"]
        tool_msg = next(
            (m for m in messages if m.get("role") == "user" and isinstance(m.get("content"), list)),
            None,
        )
        assert tool_msg is not None
        content_block = tool_msg["content"][0]
        assert content_block["type"] == "tool_result"
        assert content_block["tool_use_id"] == "toolu_01"


# ─── GoogleDispatcher ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_google_client():
    with patch("custom_components.culiplan.ai.dispatchers.genai") as MockGenai:
        instance = MagicMock()
        MockGenai.Client.return_value = instance
        yield instance


class TestGoogleDispatcher:
    """AC#1 + AC#2: Google dispatcher accepts envelope, returns result."""

    @pytest.mark.asyncio
    async def test_text_response(self, mock_google_client):
        """Gemini returns a text part."""
        part = MagicMock()
        part.text = "How about pizza tonight?"
        part.function_call = None

        candidate = MagicMock()
        candidate.content.parts = [part]

        mock_google_client.aio.models.generate_content = AsyncMock(
            return_value=MagicMock(candidates=[candidate])
        )

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._client = mock_google_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope(model="gemini-2.5-flash"))

        assert result.text == "How about pizza tonight?"
        assert result.tool_calls == []
        assert result.is_final is True

    @pytest.mark.asyncio
    async def test_function_call_response(self, mock_google_client):
        """Gemini returns a function_call part."""
        fc = MagicMock()
        fc.name = "get_meal_plan"
        fc.args = {"date": "today"}

        part = MagicMock()
        part.text = None
        del part.text  # ensure hasattr check fails cleanly
        part.function_call = fc

        # Rebuild with proper hasattr support
        part2 = MagicMock(spec=["function_call"])
        part2.function_call = fc

        candidate = MagicMock()
        candidate.content.parts = [part2]

        mock_google_client.aio.models.generate_content = AsyncMock(
            return_value=MagicMock(candidates=[candidate])
        )

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._client = mock_google_client
        dispatcher._debug = False

        result = await dispatcher.dispatch(make_envelope(model="gemini-2.5-flash"))

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_meal_plan"

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_google_client):
        """API_KEY_INVALID in error message → ProviderAuthError."""
        mock_google_client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("API_KEY_INVALID: The provided API key is invalid.")
        )

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._client = mock_google_client
        dispatcher._debug = False

        with pytest.raises(ProviderAuthError, match="rejected the API key"):
            await dispatcher.dispatch(make_envelope(model="gemini-2.5-flash"))


# ─── AIDispatchService multi-turn loop (AC#3) ─────────────────────────────────


class TestAIDispatchServiceMultiTurn:
    """AC#3: multi-turn function-calling loops correctly."""

    @pytest.mark.asyncio
    async def test_single_turn_no_tools(self):
        """Single turn, model gives a text response immediately."""
        mock_client = AsyncMock()
        mock_client.async_post = AsyncMock(return_value={
            "messages": [
                {"role": "system", "content": "You are a cooking assistant."},
                {"role": "user", "content": "Execute intent: suggest_meal"},
            ],
            "tools": [],
            "model": "test-model",
            "intent_id": "suggest_meal",
            "mode": "byok-anthropic",
        })

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(
            return_value=DispatchResult(text="I suggest pasta.", tool_calls=[])
        )

        service = AIDispatchService.__new__(AIDispatchService)
        service._mode = "byok-anthropic"
        service._client = mock_client
        service._debug = False
        service._dispatcher = mock_dispatcher

        result = await service.run_intent("suggest_meal")

        assert result.text == "I suggest pasta."
        mock_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_two_turn_tool_call_then_final(self):
        """Model calls a tool first, then gives final answer after tool result."""
        mock_client = AsyncMock()
        mock_client.async_post = AsyncMock(return_value={
            "messages": [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "Execute intent: suggest_meal"},
            ],
            "tools": [
                {
                    "name": "get_pantry",
                    "description": "Get pantry",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "model": "test-model",
            "intent_id": "suggest_meal",
            "mode": "byok-anthropic",
        })
        mock_client.async_call_voice_tool = AsyncMock(
            return_value={"items": ["eggs", "milk"]}
        )

        # Turn 1: model asks for tool
        # Turn 2: model gives final answer
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(side_effect=[
            DispatchResult(
                text=None,
                tool_calls=[ToolCall(name="get_pantry", params={}, call_id="tc-001")],
            ),
            DispatchResult(text="Based on your pantry, I suggest omelette.", tool_calls=[]),
        ])

        service = AIDispatchService.__new__(AIDispatchService)
        service._mode = "byok-anthropic"
        service._client = mock_client
        service._debug = False
        service._dispatcher = mock_dispatcher

        result = await service.run_intent("suggest_meal")

        assert result.text == "Based on your pantry, I suggest omelette."
        assert mock_dispatcher.dispatch.call_count == 2
        # Tool was executed via Culiplan REST API
        mock_client.async_call_voice_tool.assert_called_once_with("get_pantry", {})

    @pytest.mark.asyncio
    async def test_max_turns_guard(self):
        """If model never produces a final response, loop stops at _MAX_TOOL_TURNS."""
        from custom_components.culiplan.ai.service import _MAX_TOOL_TURNS

        mock_client = AsyncMock()
        mock_client.async_post = AsyncMock(return_value={
            "messages": [{"role": "user", "content": "test"}],
            "tools": [],
            "model": "test-model",
            "intent_id": "suggest_meal",
            "mode": "byok-anthropic",
        })
        mock_client.async_call_voice_tool = AsyncMock(return_value={})

        # Always return a tool call (never final)
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch = AsyncMock(
            return_value=DispatchResult(
                text=None,
                tool_calls=[ToolCall(name="get_pantry", params={}, call_id="tc-loop")],
            )
        )

        service = AIDispatchService.__new__(AIDispatchService)
        service._mode = "byok-anthropic"
        service._client = mock_client
        service._debug = False
        service._dispatcher = mock_dispatcher

        result = await service.run_intent("suggest_meal")

        # Service should stop gracefully at max turns
        assert mock_dispatcher.dispatch.call_count == _MAX_TOOL_TURNS
        # Returns the last result (which has no text)
        assert result.text is None


# ─── AC#4: streaming deferred ─────────────────────────────────────────────────


def test_dispatch_multi_turn_raises_not_implemented():
    """AC#4: dispatch_multi_turn raises NotImplementedError to document deferral."""
    dispatcher = OpenAICompatibleDispatcher.__new__(OpenAICompatibleDispatcher)
    dispatcher._client = MagicMock()
    dispatcher._debug = False

    with pytest.raises(NotImplementedError, match="service layer"):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            dispatcher.dispatch_multi_turn(make_envelope())
        )
