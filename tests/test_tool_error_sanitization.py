"""
Unit tests for task-1414: sanitize tool-call error messages before model retry.

AC#1 — Tool-call exceptions logged at WARN level with full exception info
AC#2 — Model receives sanitized payload {error, tool, retryable}
AC#3 — No internal details leak to AI provider via tool-result content
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ─── Helper: _is_non_retryable ────────────────────────────────────────────────


def test_is_non_retryable_with_status_attr():
    from custom_components.culiplan.ai.service import _is_non_retryable

    exc_4xx = Exception("some error")
    exc_4xx.status = 404
    assert _is_non_retryable(exc_4xx) is True

    exc_5xx = Exception("server error")
    exc_5xx.status = 500
    assert _is_non_retryable(exc_5xx) is False


def test_is_non_retryable_from_string():
    from custom_components.culiplan.ai.service import _is_non_retryable

    assert _is_non_retryable(Exception("404 NOT_FOUND")) is True
    assert _is_non_retryable(Exception("422 INSUFFICIENT_STOCK")) is True
    assert _is_non_retryable(Exception("503 service unavailable")) is False
    assert _is_non_retryable(Exception("generic failure")) is False


# ─── AC#2 + AC#3: sanitized payload sent to model ────────────────────────────


@pytest.mark.asyncio
async def test_tool_error_sanitized_payload_retryable():
    """
    When a tool call raises a 5xx-ish error, model should see
    {error: 'tool_execution_failed', tool: <name>, retryable: True}.
    No internal exception string should appear.
    """
    from custom_components.culiplan.ai.service import AIDispatchService
    from custom_components.culiplan.ai.types import (
        DispatchResult,
        PromptEnvelope,
        Message,
        ToolSpec,
        ToolCall,
    )

    # Build a minimal envelope
    envelope = PromptEnvelope(
        messages=[Message(role="user", content="suggest something")],
        tools=[ToolSpec(name="get_pantry", description="Get pantry", parameters={})],
        model="test-model",
        intent_id="suggest_meal",
        mode="byok-anthropic",
    )

    # First dispatch: model asks to call "get_pantry"
    first_result = DispatchResult(
        text=None,
        tool_calls=[ToolCall(name="get_pantry", params={}, call_id="call-1")],
    )
    # Second dispatch: model produces final text after receiving tool result
    second_result = DispatchResult(text="Here is a suggestion.", tool_calls=[])

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch = AsyncMock(side_effect=[first_result, second_result])

    mock_client = AsyncMock()
    # Simulate a 5xx-ish server error leaking internal details
    internal_error = Exception(
        "500 Internal Server Error: culiplanadmin@172.24.0.9/culiplan_db query failed"
    )
    mock_client.async_call_voice_tool = AsyncMock(side_effect=internal_error)
    mock_client.async_post = AsyncMock(
        return_value={
            "messages": [{"role": "user", "content": "test"}],
            "tools": [],
            "model": "test-model",
            "intent_id": "suggest_meal",
            "mode": "byok-anthropic",
        }
    )

    service = AIDispatchService.__new__(AIDispatchService)
    service._mode = "byok-anthropic"
    service._client = mock_client
    service._debug = False
    service._dispatcher = mock_dispatcher

    # Patch fetch_envelope to return our test envelope
    service.fetch_envelope = AsyncMock(return_value=envelope)

    result = await service.run_intent("suggest_meal", {})

    # The final text should come through
    assert result.text == "Here is a suggestion."

    # Inspect what was sent to the second dispatch call as tool_results
    second_dispatch_call = mock_dispatcher.dispatch.call_args_list[1]
    tool_results_passed = second_dispatch_call[0][1]  # positional arg
    assert len(tool_results_passed) == 1

    content = tool_results_passed[0].content
    # AC#2: must have the sanitised keys
    assert content["error"] == "tool_execution_failed"
    assert content["tool"] == "get_pantry"
    assert "retryable" in content
    # AC#3: internal details must NOT be present
    assert "172.24.0.9" not in str(content)
    assert "culiplanadmin" not in str(content)
    assert "culiplan_db" not in str(content)
    assert "query failed" not in str(content)


@pytest.mark.asyncio
async def test_tool_error_non_retryable_for_4xx():
    """
    A 4xx error from a tool call should produce retryable=False.
    """
    from custom_components.culiplan.ai.service import AIDispatchService
    from custom_components.culiplan.ai.types import (
        DispatchResult,
        PromptEnvelope,
        Message,
        ToolSpec,
        ToolCall,
    )

    envelope = PromptEnvelope(
        messages=[Message(role="user", content="test")],
        tools=[ToolSpec(name="add_to_list", description="add", parameters={})],
        model="test-model",
        intent_id="fill_shopping_list",
        mode="byok-openai",
    )

    first_result = DispatchResult(
        text=None,
        tool_calls=[
            ToolCall(name="add_to_list", params={"item": "milk"}, call_id="c2")
        ],
    )
    second_result = DispatchResult(text="Done.", tool_calls=[])

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch = AsyncMock(side_effect=[first_result, second_result])

    mock_client = AsyncMock()
    not_found_error = Exception("404 PANTRY_ITEM_NOT_FOUND")
    mock_client.async_call_voice_tool = AsyncMock(side_effect=not_found_error)

    service = AIDispatchService.__new__(AIDispatchService)
    service._mode = "byok-openai"
    service._client = mock_client
    service._debug = False
    service._dispatcher = mock_dispatcher
    service.fetch_envelope = AsyncMock(return_value=envelope)

    await service.run_intent("fill_shopping_list", {})

    second_call = mock_dispatcher.dispatch.call_args_list[1]
    tool_results_passed = second_call[0][1]
    content = tool_results_passed[0].content

    assert content["retryable"] is False


# ─── AC#1: exception logged at WARN level ────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_error_logged_at_warn():
    """Full exception must be logged at WARN (not hidden or swallowed)."""
    from custom_components.culiplan.ai.service import AIDispatchService
    from custom_components.culiplan.ai.types import (
        DispatchResult,
        PromptEnvelope,
        Message,
        ToolSpec,
        ToolCall,
    )

    envelope = PromptEnvelope(
        messages=[Message(role="user", content="test")],
        tools=[ToolSpec(name="get_meal", description="get", parameters={})],
        model="test-model",
        intent_id="suggest_meal",
        mode="byok-gemini",
    )

    first_result = DispatchResult(
        text=None,
        tool_calls=[ToolCall(name="get_meal", params={}, call_id="c3")],
    )
    second_result = DispatchResult(text="Result.", tool_calls=[])

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch = AsyncMock(side_effect=[first_result, second_result])

    mock_client = AsyncMock()
    mock_client.async_call_voice_tool = AsyncMock(
        side_effect=Exception("internal db timeout")
    )

    service = AIDispatchService.__new__(AIDispatchService)
    service._mode = "byok-gemini"
    service._client = mock_client
    service._debug = False
    service._dispatcher = mock_dispatcher
    service.fetch_envelope = AsyncMock(return_value=envelope)

    with patch("custom_components.culiplan.ai.service._LOGGER") as mock_logger:
        await service.run_intent("suggest_meal", {})

        # AC#1: warning must have been called with exc_info=True
        warn_calls = mock_logger.warning.call_args_list
        assert len(warn_calls) >= 1
        # Check that exc_info=True was passed (full traceback)
        last_warn_kwargs = warn_calls[-1][1]
        assert last_warn_kwargs.get("exc_info") is True
