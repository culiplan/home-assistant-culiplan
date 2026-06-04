"""
AI service orchestration layer (task-1387 + task-1388 + task-1389).

The service layer sits between HA service calls and the dispatcher classes:

    1. HA service call (e.g. culiplan.suggest_meal)
    2. → service.py: fetch prompt envelope from Culiplan backend
    3. → dispatchers.py: execute AI call locally (key never leaves HA)
    4. ← dispatcher returns DispatchResult with optional tool_calls
    5. If tool_calls: call Culiplan API via OAuth-scoped REST to execute them
    6. Loop back to dispatcher with tool results (multi-turn function-calling)
    7. Return final text to HA notification / Assist response

Architecture (§13.2):
    - For BYOK / Local modes, the backend's job ends at step 2.
    - Culiplan never sees the AI response content — only tool-call args
      (which are scoped data operations, not freeform content).

Streaming: deferred to v2.
"""

from __future__ import annotations

import logging
from typing import Any

from .dispatchers import (
    create_dispatcher,
)
from .types import (
    DispatchResult,
    PromptEnvelope,
    ToolCall,
    ToolResult,
)

# HTTP status codes that indicate a non-retryable client error (4xx)
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 409, 410, 422, 429})


def _is_non_retryable(exc: Exception) -> bool:
    """
    Return True when the exception signals a 4xx-class error that the model
    should not retry.

    We inspect the exception message for status codes rather than depending on
    a specific exception type — the tool calls traverse multiple layers and the
    original aiohttp exception may be wrapped.
    """
    # Check for explicit status_code attribute (aiohttp ClientResponseError)
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _NON_RETRYABLE_STATUS_CODES
    # Fallback: scan string representation for 4xx codes
    exc_str = str(exc)
    for code in _NON_RETRYABLE_STATUS_CODES:
        if str(code) in exc_str:
            return True
    return False


_LOGGER = logging.getLogger(__name__)

_MAX_TOOL_TURNS = 10  # guard against runaway function-calling loops


class AIDispatchService:
    """
    Orchestrates AI calls across all three execution modes.

    Usage:
        service = AIDispatchService(
            mode="byok-anthropic",
            api_key=stored_key,        # from HA secrets store
            culiplan_client=client,  # CuliplanApiClient
        )
        result = await service.run_intent("suggest_meal", {"mealSlot": "dinner"})
    """

    def __init__(
        self,
        mode: str,
        culiplan_client: Any,
        api_key: str = "",
        base_url: str | None = None,
        debug: bool = False,
        config_dir: str | None = None,
    ) -> None:
        self._mode = mode
        self._client = culiplan_client
        self._debug = debug
        self._dispatcher = create_dispatcher(
            mode=mode,
            api_key=api_key,
            base_url=base_url,
            debug=debug,
            config_dir=config_dir,
        )

    async def fetch_envelope(
        self, intent: str, params: dict[str, Any] | None = None
    ) -> PromptEnvelope:
        """
        Fetch the prompt envelope from the Culiplan backend.

        POST /api/ai/envelope — backend builds the prompt with live user context
        (pantry, meal plan, dietary info).  No AI keys are sent or accepted.
        """
        raw = await self._client.async_post(
            "/api/ai/envelope",
            {
                "intent": intent,
                "params": params or {},
                "aiProviderMode": self._mode,
            },
        )
        return PromptEnvelope.from_dict(raw)

    async def execute_tool_call(self, tool_call: ToolCall) -> Any:
        """
        Execute a single tool call via the Culiplan OAuth-scoped REST API.

        Tool calls route back to the backend as standard data operations.
        This is the only path through which AI responses touch Culiplan
        infrastructure — and only the structured tool-call args are sent
        (no freeform prompt or response content, per §13.6).
        """
        return await self._client.async_call_voice_tool(
            tool_call.name, tool_call.params
        )

    async def run_intent(
        self, intent: str, params: dict[str, Any] | None = None
    ) -> DispatchResult:
        """
        Execute a full intent, including multi-turn function-calling.

        Steps:
          1. Fetch prompt envelope from backend.
          2. Call AI provider with envelope (locally, key never leaves HA).
          3. If model requests tool calls, execute them via Culiplan API.
          4. Loop until final text response or _MAX_TOOL_TURNS reached.

        Returns:
            DispatchResult with the final text response.

        Raises:
            ProviderAuthError:       Key is invalid or expired.
            ProviderRateLimitError:  Provider rate-limited us.
            ProviderUnavailableError: Provider 5xx (one retry already done upstream).
            DispatcherError:         Other provider-level error.
        """
        envelope = await self.fetch_envelope(intent, params)

        current_result: DispatchResult | None = None
        tool_results: list[ToolResult] | None = None

        for turn in range(_MAX_TOOL_TURNS):
            current_result = await self._dispatcher.dispatch(envelope, tool_results)

            if current_result.is_final:
                _LOGGER.debug(
                    "[culiplan][ai-service] Intent '%s' completed in %d turn(s). "
                    "Mode: %s",
                    intent,
                    turn + 1,
                    self._mode,
                )
                return current_result

            if not current_result.tool_calls:
                # No text and no tool calls — treat as empty response
                break

            # Execute all tool calls and collect results
            tool_results = []
            for tc in current_result.tool_calls:
                _LOGGER.debug(
                    "[culiplan][ai-service] Executing tool '%s' (call_id=%s)",
                    tc.name,
                    tc.call_id,
                )
                try:
                    result_data = await self.execute_tool_call(tc)
                except Exception as exc:
                    # Log the full exception internally (AC#1) but never surface
                    # internal exception strings to the AI provider — that would
                    # leak Culiplan architecture details to BYOK providers (AC#3,
                    # task-1414).
                    _LOGGER.warning(
                        "[culiplan][ai-service] Tool '%s' (call_id=%s) failed: %s",
                        tc.name,
                        tc.call_id,
                        exc,
                        exc_info=True,
                    )
                    retryable = not _is_non_retryable(exc)
                    # AC#2: sanitised payload — no internal details
                    result_data = {
                        "error": "tool_execution_failed",
                        "tool": tc.name,
                        "retryable": retryable,
                    }

                tool_results.append(
                    ToolResult(
                        call_id=tc.call_id,
                        tool_name=tc.name,
                        content=result_data,
                    )
                )

        _LOGGER.warning(
            "[culiplan][ai-service] Intent '%s' did not resolve after %d turns. "
            "Returning last result.",
            intent,
            _MAX_TOOL_TURNS,
        )
        return current_result or DispatchResult(text=None)
