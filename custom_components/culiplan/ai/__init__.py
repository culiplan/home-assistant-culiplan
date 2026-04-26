"""AI provider dispatcher package for the Flavorplan integration.

Three dispatcher classes — one per provider SDK family — accept a normalised
prompt envelope (fetched from POST /api/ai/envelope) and return a structured
result:  { "text": str | None, "tool_calls": list[dict] }

Provider families:
    OpenAICompatibleDispatcher  — covers OpenAI, Ollama (OpenAI-compat mode),
                                   and LM Studio.
    AnthropicDispatcher         — Anthropic Claude models.
    GoogleDispatcher            — Google Gemini Direct API (distinct from
                                   Flavorplan's own Vertex AI usage).

Architecture note (§13.2 zero-custody):
    API keys NEVER leave Home Assistant.  Flavorplan's backend only builds the
    prompt envelope; the AI call itself is made directly from this module to
    the AI provider.  Tool-call results are routed back through the existing
    OAuth-scoped REST endpoints on api.culiplan.com.

Streaming:
    Deferred to v2 (§13.2).  All dispatchers use blocking/batch calls.

Debug mode (§13.2):
    If CONF_DEBUG_AI is set in the config entry options, prompts are logged at
    DEBUG level on the HA side with a 24-hour auto-purge TTL note.  They are
    NEVER sent to Flavorplan.
"""
