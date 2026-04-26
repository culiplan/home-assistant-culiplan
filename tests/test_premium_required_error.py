"""
Unit tests for task-1416: typed PremiumRequiredError in api.py.

AC#1 — PremiumRequiredError importable from ai.types (not services)
AC#2 — api.py raises PremiumRequiredError with feature + upgrade_url on 403 premium body
AC#3 — services.py catches PremiumRequiredError without string parsing
AC#4 — 403 with premium_required body → PremiumRequiredError with both fields
AC#5 — 403 with non-premium body → HomeAssistantError (not PremiumRequiredError)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── AC#1: PremiumRequiredError lives in ai.types ─────────────────────────────

def test_premium_required_error_importable_from_ai_types():
    """PremiumRequiredError must be importable from the shared types module."""
    from custom_components.culiplan.ai.types import PremiumRequiredError
    assert PremiumRequiredError is not None


def test_premium_required_error_not_defined_in_services():
    """services.py should re-export (import) PremiumRequiredError, not define it."""
    import inspect
    import custom_components.culiplan.services as svc_mod
    import custom_components.culiplan.ai.types as types_mod

    # Both should refer to the *same* class object
    from custom_components.culiplan.services import PremiumRequiredError as SvcErr
    from custom_components.culiplan.ai.types import PremiumRequiredError as TypesErr
    assert SvcErr is TypesErr, (
        "services.PremiumRequiredError and ai.types.PremiumRequiredError must be the same class"
    )


# ─── AC#4: 403 premium_required body → PremiumRequiredError ──────────────────

@pytest.mark.asyncio
async def test_post_raises_premium_required_error_on_premium_403():
    """
    api.py._post must raise PremiumRequiredError (not a generic Exception) when
    the server returns 403 with {error: premium_required, feature, upgradeUrl}.
    """
    from custom_components.culiplan.api import FlavorplanApiClient
    from custom_components.culiplan.ai.types import PremiumRequiredError

    premium_body = {
        "error": "premium_required",
        "feature": "ai.suggestion",
        "upgradeUrl": "https://culiplan.com/premium?source=ha",
    }

    mock_resp = AsyncMock()
    mock_resp.status = 403
    mock_resp.ok = False
    mock_resp.json = AsyncMock(return_value=premium_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp

    client = FlavorplanApiClient(session=mock_session, access_token="tok")

    with pytest.raises(PremiumRequiredError) as exc_info:
        await client._post("/api/voice/ha-assist", {"tool": "suggest_meal", "params": {}})

    err = exc_info.value
    assert err.feature == "ai.suggestion"
    assert err.upgrade_url == "https://culiplan.com/premium?source=ha"


# ─── AC#5: 403 non-premium body → HomeAssistantError ─────────────────────────

@pytest.mark.asyncio
async def test_post_raises_ha_error_on_non_premium_403():
    """
    api.py._post must raise HomeAssistantError (not PremiumRequiredError) when
    the server returns 403 with a body that does NOT have error==premium_required
    (e.g. forbidden scope).
    """
    from custom_components.culiplan.api import FlavorplanApiClient
    from custom_components.culiplan.ai.types import PremiumRequiredError
    from homeassistant.exceptions import HomeAssistantError

    forbidden_body = {"error": "forbidden", "message": "Insufficient scope"}

    mock_resp = AsyncMock()
    mock_resp.status = 403
    mock_resp.ok = False
    mock_resp.json = AsyncMock(return_value=forbidden_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp

    client = FlavorplanApiClient(session=mock_session, access_token="tok")

    with pytest.raises(HomeAssistantError) as exc_info:
        await client._post("/api/some/endpoint", {})

    # Must NOT be a PremiumRequiredError
    assert not isinstance(exc_info.value, PremiumRequiredError)


# ─── AC#3: services.py catches typed error — no string parsing ───────────────

@pytest.mark.asyncio
async def test_run_cloud_intent_re_raises_premium_required_error():
    """
    _run_cloud_intent must re-raise PremiumRequiredError directly without
    inspecting exc.args or the string representation.
    """
    from custom_components.culiplan.services import _run_cloud_intent
    from custom_components.culiplan.ai.types import PremiumRequiredError

    mock_client = AsyncMock()
    mock_client.async_call_voice_tool = AsyncMock(
        side_effect=PremiumRequiredError(
            feature="ai.suggestion",
            upgrade_url="https://culiplan.com/premium?source=ha",
        )
    )

    with pytest.raises(PremiumRequiredError) as exc_info:
        await _run_cloud_intent(mock_client, "suggest_meal", {})

    assert exc_info.value.feature == "ai.suggestion"
    assert "culiplan.com/premium" in exc_info.value.upgrade_url


@pytest.mark.asyncio
async def test_scale_servings_re_raises_premium_required_error():
    """
    _call_scale_servings must re-raise PremiumRequiredError directly (no
    string-parse of exc.args).
    """
    from custom_components.culiplan.services import _call_scale_servings
    from custom_components.culiplan.ai.types import PremiumRequiredError

    mock_client = AsyncMock()
    mock_client.async_post = AsyncMock(
        side_effect=PremiumRequiredError(
            feature="household.presence_scaling",
            upgrade_url="https://culiplan.com/premium?source=ha",
        )
    )

    with pytest.raises(PremiumRequiredError) as exc_info:
        await _call_scale_servings(mock_client, 3, None)

    assert exc_info.value.feature == "household.presence_scaling"
