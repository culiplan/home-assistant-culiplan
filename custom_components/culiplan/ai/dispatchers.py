"""
AI provider dispatchers for the Flavorplan Home Assistant integration (task-1387).

Three dispatcher classes, one per SDK family:

    OpenAICompatibleDispatcher  — OpenAI, Ollama (OpenAI-compat), LM Studio
    AnthropicDispatcher         — Anthropic Claude
    GoogleDispatcher            — Google Gemini Direct

Each dispatcher:
  1. Accepts a PromptEnvelope (built by the Flavorplan backend).
  2. Translates it to the provider's native API format.
  3. Executes the call locally (API key NEVER leaves HA).
  4. Returns DispatchResult { text, tool_calls[] }.
  5. Supports multi-turn function-calling (loop until final text response).

Streaming responses are deferred to v2 (§13.2).

Debug mode (§13.2):
    Pass debug=True to log prompts at DEBUG level.  Logs are client-side only,
    never sent to Flavorplan.  Auto-purge TTL of 24h is noted in the log.

Retry policy (§13.6, task-1411):
    All three dispatchers retry once on 5xx with 1s backoff before raising
    ProviderUnavailableError.  No retry on 4xx (fail fast).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from .types import (
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

_LOGGER = logging.getLogger(__name__)

# Maximum multi-turn function-calling iterations to prevent runaway loops
_MAX_TOOL_TURNS = 10

# ─── Retry helper (§13.6, task-1411) ─────────────────────────────────────────

_RETRY_BACKOFF_SECONDS = 1.0  # one second between attempt 1 and the single retry


async def _retry_once_on_5xx(coro_factory, *, provider: str) -> Any:
    """
    Call ``coro_factory()`` once.  If it raises ``ProviderUnavailableError``
    (5xx), wait ``_RETRY_BACKOFF_SECONDS`` and try once more.  Any other
    exception (4xx auth/rate-limit, DispatcherError) is propagated immediately
    without a retry — fail fast on non-transient errors (AC#2, task-1411).

    The retry attempt is logged at WARN level to support audit-log visibility
    (AC#3, task-1411).

    Args:
        coro_factory: A zero-argument callable that returns the coroutine to
                      execute.  Called twice at most.
        provider:     Human-readable provider name for log messages.

    Returns:
        The return value of the successful coroutine call.

    Raises:
        ProviderUnavailableError: If both attempts return a 5xx response.
        Any other DispatcherError subclass on the first attempt.
    """
    try:
        return await coro_factory()
    except ProviderUnavailableError as exc:
        _LOGGER.warning(
            "[culiplan][%s] Provider returned 5xx — retrying once after %.1fs. "
            "Error: %s",
            provider, _RETRY_BACKOFF_SECONDS, exc,
        )
        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
        # Raises ProviderUnavailableError (or any other exception) on the second
        # attempt — let it propagate to the service layer unchanged.
        return await coro_factory()


def _tool_specs_to_openai(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec list to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _tool_specs_to_anthropic(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec list to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def _tool_specs_to_google(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert ToolSpec list to Google Gemini function declaration format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in tools
    ]


def _messages_to_openai(messages: list[Message]) -> list[dict[str, str]]:
    """Convert Message list to OpenAI messages format."""
    return [{"role": m.role, "content": m.content} for m in messages]


# ─── OpenAI-compatible dispatcher ─────────────────────────────────────────────

class OpenAICompatibleDispatcher:
    """
    Dispatcher for OpenAI-compatible endpoints.

    Covers:
    - OpenAI API (api.openai.com)
    - Ollama in OpenAI-compatible mode (default: http://localhost:11434/v1)
    - LM Studio (default: http://localhost:1234/v1)

    Requires: openai Python package (bundled in manifest.json requirements).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        debug: bool = False,
    ) -> None:
        """
        Initialise the dispatcher.

        Args:
            api_key:  Provider API key (stored in HA secrets, never sent to Flavorplan).
                      For local endpoints (Ollama/LM Studio) pass "ollama" or "lm-studio"
                      as a placeholder — the endpoint does not authenticate.
            base_url: Override the default OpenAI base URL.
                      Set to "http://localhost:11434/v1" for Ollama,
                      "http://localhost:1234/v1" for LM Studio.
            debug:    If True, log prompt content at DEBUG level (client-side only).
        """
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._debug = debug

    async def dispatch(
        self,
        envelope: PromptEnvelope,
        tool_results: list[ToolResult] | None = None,
    ) -> DispatchResult:
        """
        Execute a single AI provider turn.

        Args:
            envelope:     Prompt envelope from the backend.
            tool_results: Results from Flavorplan tool calls (for multi-turn loops).

        Returns:
            DispatchResult with text and/or tool_calls for next turn.
        """
        messages = _messages_to_openai(envelope.messages)

        # Append tool results as tool messages if we're continuing a loop
        if tool_results:
            for result in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "content": json.dumps(result.content),
                })

        tools = _tool_specs_to_openai(envelope.tools)

        if self._debug:
            _LOGGER.debug(
                "[culiplan][openai-compat] Sending prompt to provider. "
                "DEBUG MODE: prompt logged client-side, auto-purge TTL 24h. "
                "Messages: %s",
                json.dumps(messages),
            )

        async def _call() -> Any:
            try:
                from openai import APIStatusError

                return await self._client.chat.completions.create(
                    model=envelope.model,
                    messages=messages,  # type: ignore[arg-type]
                    tools=tools if tools else None,  # type: ignore[arg-type]
                    tool_choice="auto" if tools else None,
                )
            except APIStatusError as exc:
                _LOGGER.error(
                    "[culiplan][openai-compat] Provider error: %s %s",
                    exc.status_code, exc.message,
                )
                if exc.status_code == 401:
                    raise ProviderAuthError(
                        f"OpenAI-compatible provider rejected the API key: {exc.message}"
                    ) from exc
                if exc.status_code == 429:
                    raise ProviderRateLimitError(
                        f"OpenAI-compatible provider rate limit exceeded: {exc.message}"
                    ) from exc
                if exc.status_code >= 500:
                    raise ProviderUnavailableError(
                        f"OpenAI-compatible provider returned {exc.status_code}: {exc.message}"
                    ) from exc
                raise DispatcherError(
                    f"OpenAI-compatible provider error: {exc.message}"
                ) from exc

        # AC#1: retry once on 5xx with 1s backoff; fail fast on 4xx (task-1411)
        response = await _retry_once_on_5xx(_call, provider="openai-compat")

        choice = response.choices[0]
        finish_reason = choice.finish_reason

        # Extract tool calls
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    params = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    params = {}
                tool_calls.append(
                    ToolCall(
                        name=tc.function.name,
                        params=params,
                        call_id=tc.id,
                    )
                )

        text = choice.message.content

        if finish_reason == "length":
            _LOGGER.warning(
                "[culiplan][openai-compat] Response truncated (max_tokens reached). "
                "Consider raising max_tokens or reducing context size."
            )

        return DispatchResult(text=text, tool_calls=tool_calls)

    async def dispatch_multi_turn(self, envelope: PromptEnvelope) -> str:
        """
        Execute the full multi-turn function-calling loop.

        Calls dispatch() → executes tool calls via Flavorplan API → loops
        until the model produces a final text response or _MAX_TOOL_TURNS reached.

        Note: this method does NOT call Flavorplan tool endpoints directly.
        It raises NotImplementedError because tool execution must be provided
        by the caller (which has access to the Flavorplan API client).

        Use dispatch() directly and handle the tool-call loop in the service
        layer (see services.py).
        """
        raise NotImplementedError(
            "Use dispatch() and handle the tool-call loop in the service layer. "
            "See culiplan/ai/service.py for the full multi-turn orchestration."
        )


# ─── Anthropic dispatcher ─────────────────────────────────────────────────────

class AnthropicDispatcher:
    """
    Dispatcher for Anthropic Claude models.

    Requires: anthropic Python package (bundled in manifest.json requirements).
    """

    def __init__(self, api_key: str, debug: bool = False) -> None:
        """
        Args:
            api_key: Anthropic API key (stored in HA secrets, never sent to Flavorplan).
            debug:   If True, log prompt content at DEBUG level (client-side only).
        """
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._debug = debug

    async def dispatch(
        self,
        envelope: PromptEnvelope,
        tool_results: list[ToolResult] | None = None,
    ) -> DispatchResult:
        """Execute a single Anthropic provider turn."""
        # Anthropic separates system prompt from messages
        system_content: str | None = None
        conversation: list[dict[str, Any]] = []

        for msg in envelope.messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        # Append tool results for multi-turn
        if tool_results:
            for result in tool_results:
                conversation.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": result.call_id,
                            "content": json.dumps(result.content),
                        }
                    ],
                })

        tools = _tool_specs_to_anthropic(envelope.tools)

        if self._debug:
            _LOGGER.debug(
                "[culiplan][anthropic] Sending prompt to Anthropic. "
                "DEBUG MODE: prompt logged client-side, auto-purge TTL 24h. "
                "System: %s | Messages: %s",
                system_content,
                json.dumps(conversation),
            )

        async def _call() -> Any:
            try:
                from anthropic import APIStatusError

                return await self._client.messages.create(
                    model=envelope.model,
                    max_tokens=2048,
                    system=system_content or "",
                    messages=conversation,  # type: ignore[arg-type]
                    tools=tools if tools else [],  # type: ignore[arg-type]
                )
            except APIStatusError as exc:
                _LOGGER.error(
                    "[culiplan][anthropic] Provider error: %s %s",
                    exc.status_code, exc.message,
                )
                if exc.status_code == 401:
                    raise ProviderAuthError(
                        f"Anthropic rejected the API key: {exc.message}"
                    ) from exc
                if exc.status_code == 429:
                    raise ProviderRateLimitError(
                        f"Anthropic rate limit exceeded: {exc.message}"
                    ) from exc
                if exc.status_code >= 500:
                    raise ProviderUnavailableError(
                        f"Anthropic returned {exc.status_code}: {exc.message}"
                    ) from exc
                raise DispatcherError(f"Anthropic error: {exc.message}") from exc

        # AC#1: retry once on 5xx with 1s backoff; fail fast on 4xx (task-1411)
        response = await _retry_once_on_5xx(_call, provider="anthropic")

        # Extract content blocks
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=block.name,
                        params=block.input if isinstance(block.input, dict) else {},
                        call_id=block.id,
                    )
                )

        text = "\n".join(text_parts) if text_parts else None

        return DispatchResult(text=text, tool_calls=tool_calls)


# ─── Google Gemini dispatcher ─────────────────────────────────────────────────

class GoogleDispatcher:
    """
    Dispatcher for Google Gemini via the google-genai SDK.

    This uses the direct Gemini API (not Vertex AI).  The user provides their
    own Google API key — this is distinct from Flavorplan's own Vertex AI usage.

    Requires: google-genai Python package (bundled in manifest.json requirements).
    """

    def __init__(self, api_key: str, debug: bool = False) -> None:
        """
        Args:
            api_key: Google/Gemini API key (stored in HA secrets).
            debug:   If True, log prompt content at DEBUG level (client-side only).
        """
        from google import genai  # type: ignore[import]

        self._client = genai.Client(api_key=api_key)
        self._debug = debug

    async def dispatch(
        self,
        envelope: PromptEnvelope,
        tool_results: list[ToolResult] | None = None,
    ) -> DispatchResult:
        """Execute a single Google Gemini provider turn."""
        from google.genai import types as genai_types  # type: ignore[import]

        # Build system instruction from system messages
        system_parts: list[str] = [
            m.content for m in envelope.messages if m.role == "system"
        ]
        system_instruction = "\n\n".join(system_parts) if system_parts else None

        # Build conversation contents
        contents: list[dict[str, Any]] = []
        for msg in envelope.messages:
            if msg.role == "system":
                continue  # handled via system_instruction
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})

        # Append tool results for multi-turn
        if tool_results:
            for result in tool_results:
                contents.append({
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": result.tool_name,
                                "response": {"result": result.content},
                            }
                        }
                    ],
                })

        # Build function declarations
        function_declarations = _tool_specs_to_google(envelope.tools)

        if self._debug:
            _LOGGER.debug(
                "[culiplan][google] Sending prompt to Gemini. "
                "DEBUG MODE: prompt logged client-side, auto-purge TTL 24h. "
                "Contents: %s",
                json.dumps(contents),
            )

        async def _call() -> Any:
            try:
                config_kwargs: dict[str, Any] = {}
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                if function_declarations:
                    config_kwargs["tools"] = [
                        genai_types.Tool(
                            function_declarations=function_declarations  # type: ignore[arg-type]
                        )
                    ]

                return await self._client.aio.models.generate_content(
                    model=envelope.model,
                    contents=contents,  # type: ignore[arg-type]
                    config=genai_types.GenerateContentConfig(**config_kwargs)
                    if config_kwargs
                    else None,
                )
            except Exception as exc:  # google-genai uses generic exceptions
                msg = str(exc)
                _LOGGER.error("[culiplan][google] Provider error: %s", msg)
                if "401" in msg or "API_KEY_INVALID" in msg:
                    raise ProviderAuthError(
                        f"Gemini rejected the API key: {msg}"
                    ) from exc
                if "429" in msg or "RATE_LIMIT" in msg:
                    raise ProviderRateLimitError(
                        f"Gemini rate limit exceeded: {msg}"
                    ) from exc
                if "500" in msg or "503" in msg:
                    raise ProviderUnavailableError(
                        f"Gemini service unavailable: {msg}"
                    ) from exc
                raise DispatcherError(f"Gemini error: {msg}") from exc

        # AC#1: retry once on 5xx with 1s backoff; fail fast on 4xx (task-1411)
        response = await _retry_once_on_5xx(_call, provider="google")

        # Extract text and function calls from candidates
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for idx, candidate in enumerate(getattr(response, "candidates", [])):
            for part in getattr(candidate.content, "parts", []):
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    # task-1412: generate a unique call_id per tool call so that
                    # two calls to the same tool in a single turn don't collide.
                    # Format: "<tool_name>-<8-char UUID fragment>"
                    call_id = f"{fc.name}-{uuid.uuid4().hex[:8]}"
                    tool_calls.append(
                        ToolCall(
                            name=fc.name,
                            params=dict(fc.args) if fc.args else {},
                            call_id=call_id,
                        )
                    )

        text = "\n".join(text_parts) if text_parts else None

        return DispatchResult(text=text, tool_calls=tool_calls)


# ─── Factory ──────────────────────────────────────────────────────────────────

def create_dispatcher(
    mode: str,
    api_key: str = "",
    base_url: str | None = None,
    debug: bool = False,
) -> "OpenAICompatibleDispatcher | AnthropicDispatcher | GoogleDispatcher":
    """
    Factory: return the correct dispatcher for the given AI mode.

    Args:
        mode:     One of the AIMode values from const.py.
        api_key:  Provider API key (empty string for local endpoints).
        base_url: Optional endpoint override (for Ollama / LM Studio).
        debug:    Enable client-side prompt logging.

    Raises:
        ValueError: If mode is not a recognised BYOK or Local mode.
    """
    if mode in ("byok-openai", "local-ollama", "local-lmstudio"):
        return OpenAICompatibleDispatcher(
            api_key=api_key or "ollama",  # local endpoints don't need a real key
            base_url=base_url,
            debug=debug,
        )
    if mode == "byok-anthropic":
        return AnthropicDispatcher(api_key=api_key, debug=debug)
    if mode == "byok-gemini":
        return GoogleDispatcher(api_key=api_key, debug=debug)
    raise ValueError(
        f"Unknown AI mode '{mode}'. "
        "Expected one of: byok-openai, byok-anthropic, byok-gemini, "
        "local-ollama, local-lmstudio."
    )
