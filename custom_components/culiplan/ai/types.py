"""Shared type definitions for the AI dispatcher layer (task-1387)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── Prompt envelope ──────────────────────────────────────────────────────────

@dataclass
class Message:
    """A single chat message in the prompt envelope."""
    role: str        # "system" | "user" | "assistant"
    content: str


@dataclass
class ToolSpec:
    """OpenAPI-style tool specification."""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class PromptEnvelope:
    """
    Prompt envelope returned by POST /api/ai/envelope.

    The backend builds this; the dispatcher executes it locally against
    the AI provider.  API keys never transit Flavorplan infrastructure.
    """
    messages: list[Message]
    tools: list[ToolSpec]
    model: str
    intent_id: str
    mode: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptEnvelope":
        return cls(
            messages=[Message(**m) for m in data["messages"]],
            tools=[ToolSpec(**t) for t in data["tools"]],
            model=data["model"],
            intent_id=data["intent_id"],
            mode=data["mode"],
        )


# ─── Dispatcher result ────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """A single tool call emitted by the model."""
    name: str
    params: dict[str, Any]
    call_id: str = ""   # provider-specific call identifier for multi-turn loop


@dataclass
class DispatchResult:
    """
    Normalised result from an AI provider call.

    If tool_calls is non-empty, the caller should execute the tools via the
    Flavorplan API and loop back to the dispatcher with the results appended.
    """
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        """True when the model produced a text response with no pending tool calls."""
        return self.text is not None and not self.tool_calls


# ─── Tool result (for multi-turn loops) ──────────────────────────────────────

@dataclass
class ToolResult:
    """Result of a Flavorplan tool call, forwarded back to the model."""
    call_id: str
    tool_name: str
    content: Any   # JSON-serialisable


# ─── Dispatcher errors ────────────────────────────────────────────────────────

class DispatcherError(Exception):
    """Base class for dispatcher-level errors."""


class ProviderRateLimitError(DispatcherError):
    """Provider returned a 429 rate-limit response."""


class ProviderAuthError(DispatcherError):
    """Provider returned a 401/403 — key is invalid or expired."""


class ProviderUnavailableError(DispatcherError):
    """Provider returned 5xx or network error (retry once then surface Repairs)."""
