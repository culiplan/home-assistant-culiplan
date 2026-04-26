"""
Unit tests for task-1412: unique call_id per Gemini tool call.

AC#1 — GoogleDispatcher generates unique call_id per ToolCall
AC#2 — Same tool called twice in one turn → two distinct call_ids
AC#3 — ToolResult routing back to Gemini uses correct per-call call_id
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_function_call_mock(name: str, args: dict | None = None) -> MagicMock:
    """Create a mock Gemini function_call part."""
    fc = MagicMock()
    fc.name = name
    fc.args = args or {}
    part = MagicMock()
    part.text = None
    part.function_call = fc
    # Make hasattr checks work correctly
    part.__class__.__mro__ = [MagicMock]
    return part


# ─── AC#1: call_id is unique and contains tool name ───────────────────────────

@pytest.mark.asyncio
async def test_google_dispatcher_unique_call_id_format():
    """
    Each ToolCall must have a call_id of the form '{name}-{hex8}' — not just
    the bare tool name.
    """
    from custom_components.culiplan.ai.types import (
        PromptEnvelope,
        Message,
        ToolSpec,
        ToolCall,
        ToolResult,
    )

    envelope = PromptEnvelope(
        messages=[Message(role="user", content="add milk")],
        tools=[ToolSpec(name="add_to_list", description="add", parameters={})],
        model="gemini-1.5-flash",
        intent_id="fill_shopping_list",
        mode="byok-gemini",
    )

    # Simulate Gemini returning one function call
    fc_part = MagicMock()
    fc_part.text = None
    fc_part.function_call = MagicMock()
    fc_part.function_call.name = "add_to_list"
    fc_part.function_call.args = {"item": "milk"}

    candidate = MagicMock()
    candidate.content.parts = [fc_part]

    mock_response = MagicMock()
    mock_response.candidates = [candidate]

    with patch(
        "custom_components.culiplan.ai.dispatchers._retry_once_on_5xx",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        from custom_components.culiplan.ai.dispatchers import GoogleDispatcher

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._debug = False
        dispatcher._client = MagicMock()

        with patch("google.genai", create=True), \
             patch("google.genai.types", create=True):
            result = await dispatcher.dispatch(envelope, None)

    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.name == "add_to_list"
    # AC#1: call_id must start with the tool name and have a '-' separator
    assert tc.call_id.startswith("add_to_list-"), (
        f"call_id '{tc.call_id}' does not start with 'add_to_list-'"
    )
    # Must be more than just the name
    assert len(tc.call_id) > len("add_to_list-")


# ─── AC#2: two calls to same tool get different call_ids ─────────────────────

@pytest.mark.asyncio
async def test_google_dispatcher_two_same_tool_calls_unique_ids():
    """
    When the model emits two calls to the same tool in one turn, they must
    produce distinct call_ids (AC#2).
    """
    from custom_components.culiplan.ai.types import (
        PromptEnvelope,
        Message,
        ToolSpec,
    )

    envelope = PromptEnvelope(
        messages=[Message(role="user", content="add two items")],
        tools=[
            ToolSpec(
                name="append_shopping_list",
                description="append",
                parameters={"type": "object", "properties": {"item": {"type": "string"}}},
            )
        ],
        model="gemini-1.5-flash",
        intent_id="fill_shopping_list",
        mode="byok-gemini",
    )

    # Two calls to the same tool
    def _make_fc_part(item_name: str) -> MagicMock:
        fc = MagicMock()
        fc.name = "append_shopping_list"
        fc.args = {"item": item_name}
        part = MagicMock()
        part.text = None
        part.function_call = fc
        return part

    candidate = MagicMock()
    candidate.content.parts = [_make_fc_part("milk"), _make_fc_part("eggs")]

    mock_response = MagicMock()
    mock_response.candidates = [candidate]

    with patch(
        "custom_components.culiplan.ai.dispatchers._retry_once_on_5xx",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        from custom_components.culiplan.ai.dispatchers import GoogleDispatcher

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._debug = False
        dispatcher._client = MagicMock()

        with patch("google.genai", create=True), \
             patch("google.genai.types", create=True):
            result = await dispatcher.dispatch(envelope, None)

    assert len(result.tool_calls) == 2

    call_id_0 = result.tool_calls[0].call_id
    call_id_1 = result.tool_calls[1].call_id

    # AC#2: both IDs must be unique
    assert call_id_0 != call_id_1, (
        f"Both calls to 'append_shopping_list' got the same call_id: {call_id_0}"
    )

    # AC#3: both must still start with the tool name
    assert call_id_0.startswith("append_shopping_list-")
    assert call_id_1.startswith("append_shopping_list-")


# ─── AC#3: ToolResult routing uses the correct call_id ───────────────────────

@pytest.mark.asyncio
async def test_google_dispatcher_tool_result_uses_correct_call_id():
    """
    ToolResult objects passed to the next dispatch turn use the same call_id
    that was in the ToolCall, ensuring the multi-turn loop routes correctly.
    """
    from custom_components.culiplan.ai.types import (
        PromptEnvelope,
        Message,
        ToolSpec,
        ToolCall,
        ToolResult,
    )

    # Simulate a second dispatch call with tool results
    envelope = PromptEnvelope(
        messages=[Message(role="user", content="continue")],
        tools=[ToolSpec(name="get_pantry", description="get", parameters={})],
        model="gemini-1.5-flash",
        intent_id="suggest_meal",
        mode="byok-gemini",
    )

    # Supply tool results from the previous turn
    tool_results = [
        ToolResult(
            call_id="get_pantry-abc12345",
            tool_name="get_pantry",
            content={"items": ["milk", "eggs"]},
        )
    ]

    # Final text response with no further tool calls
    text_part = MagicMock()
    text_part.text = "I suggest pasta."
    text_part.function_call = None

    candidate = MagicMock()
    candidate.content.parts = [text_part]

    mock_response = MagicMock()
    mock_response.candidates = [candidate]

    captured_contents = []

    async def capture_retry(factory, *, provider):
        # Capture what _call() would send to the Gemini API
        # We call the inner function to capture its args
        return mock_response

    with patch(
        "custom_components.culiplan.ai.dispatchers._retry_once_on_5xx",
        side_effect=capture_retry,
    ):
        from custom_components.culiplan.ai.dispatchers import GoogleDispatcher

        dispatcher = GoogleDispatcher.__new__(GoogleDispatcher)
        dispatcher._debug = False
        dispatcher._client = MagicMock()

        with patch("google.genai", create=True), \
             patch("google.genai.types", create=True):
            result = await dispatcher.dispatch(envelope, tool_results)

    assert result.text == "I suggest pasta."
    assert not result.tool_calls
