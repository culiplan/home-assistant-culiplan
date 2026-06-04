"""Tests for PlannedKwhTodaySensor — task-1399 (Phase 3 Tier 3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.culiplan.const import DOMAIN
from custom_components.culiplan.coordinator import CuliplanCoordinator
from homeassistant.helpers.device_registry import DeviceInfo


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def device() -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, "test_entry_id")},
        name="Culiplan",
        manufacturer="Culiplan",
        model="Meal Planner",
        entry_type="service",
    )


@pytest.fixture
def coordinator_with_energy(hass, mock_api_client, mock_config_entry):
    """Coordinator pre-loaded with energy_today data."""
    coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
    coord.data = {
        "meal_plans": [],
        "shopping_lists": [],
        "pantry_items": [],
        "energy_today": {
            "date": "2026-04-25",
            "estimated_kwh": 1.25,
            "slot_count": 2,
            "slots": [
                {
                    "mealPlanId": "mp1",
                    "recipeId": "rec1",
                    "recipeTitle": "Pasta Carbonara",
                    "estimated_kwh": 0.75,
                },
                {
                    "mealPlanId": "mp2",
                    "recipeId": "rec2",
                    "recipeTitle": "Salad",
                    "estimated_kwh": 0.5,
                },
            ],
        },
    }
    return coord


@pytest.fixture
def coordinator_no_energy(hass, mock_api_client, mock_config_entry):
    """Coordinator with no energy_today data (first load / missing key)."""
    coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
    coord.data = {
        "meal_plans": [],
        "shopping_lists": [],
        "pantry_items": [],
    }
    return coord


@pytest.fixture
def coordinator_zero_kwh(hass, mock_api_client, mock_config_entry):
    """Coordinator with energy_today returning 0 kWh (no-cook day)."""
    coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
    coord.data = {
        "meal_plans": [],
        "shopping_lists": [],
        "pantry_items": [],
        "energy_today": {
            "date": "2026-04-25",
            "estimated_kwh": 0.0,
            "slot_count": 1,
            "slots": [
                {
                    "mealPlanId": "mp1",
                    "recipeId": "rec1",
                    "recipeTitle": "Raw Salad",
                    "estimated_kwh": 0.0,
                },
            ],
        },
    }
    return coord


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestPlannedKwhTodaySensor:

    def test_native_value_returns_estimated_kwh(self, coordinator_with_energy, device):
        """sensor.native_value returns the estimated_kwh float from energy_today."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.native_value == 1.25

    def test_native_value_returns_zero_when_no_energy_data(
        self, coordinator_no_energy, device
    ):
        """sensor.native_value returns 0.0 when energy_today key is absent."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_no_energy, device)
        assert sensor.native_value == 0.0

    def test_native_value_returns_zero_on_no_cook_day(
        self, coordinator_zero_kwh, device
    ):
        """sensor.native_value returns 0.0 when all meals are no-cook."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_zero_kwh, device)
        assert sensor.native_value == 0.0

    def test_native_value_handles_null_data(self, hass, mock_api_client, mock_config_entry, device):
        """sensor.native_value returns 0.0 when coordinator.data is None."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
        coord.data = None
        sensor = PlannedKwhTodaySensor(coord, device)
        assert sensor.native_value == 0.0

    def test_extra_state_attributes_contains_recipe_ids(
        self, coordinator_with_energy, device
    ):
        """extra_state_attributes includes recipe_ids list (ID-only, §14.3)."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        attrs = sensor.extra_state_attributes

        assert "recipe_ids" in attrs
        assert attrs["recipe_ids"] == ["rec1", "rec2"]

    def test_extra_state_attributes_excludes_recipe_titles(
        self, coordinator_with_energy, device
    ):
        """extra_state_attributes must NOT expose recipe titles (§14.3 PII rule)."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        attrs = sensor.extra_state_attributes

        # Titles are PII-adjacent data; they must not appear in HA attributes.
        assert "recipeTitle" not in attrs
        assert "recipe_titles" not in attrs

    def test_extra_state_attributes_slot_count(self, coordinator_with_energy, device):
        """extra_state_attributes includes slot_count."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.extra_state_attributes["slot_count"] == 2

    def test_extra_state_attributes_date(self, coordinator_with_energy, device):
        """extra_state_attributes includes the date string."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.extra_state_attributes["date"] == "2026-04-25"

    def test_extra_state_attributes_empty_when_no_data(
        self, coordinator_no_energy, device
    ):
        """extra_state_attributes returns empty dict when energy_today is absent."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_no_energy, device)
        assert sensor.extra_state_attributes == {}

    def test_unique_id(self, coordinator_with_energy, device):
        """Sensor unique_id must be stable and domain-prefixed."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.unique_id == f"{DOMAIN}_planned_kwh_today"

    def test_state_class_is_total(self, coordinator_with_energy, device):
        """state_class must be TOTAL for HA Energy dashboard compatibility."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor
        from homeassistant.components.sensor import SensorStateClass

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.state_class == SensorStateClass.TOTAL

    def test_device_class_is_energy(self, coordinator_with_energy, device):
        """device_class must be ENERGY for kWh unit handling in HA."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor
        from homeassistant.components.sensor import SensorDeviceClass

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.device_class == SensorDeviceClass.ENERGY

    def test_unit_of_measurement_is_kwh(self, coordinator_with_energy, device):
        """unit_of_measurement must be 'kWh'."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.native_unit_of_measurement == "kWh"

    def test_icon(self, coordinator_with_energy, device):
        """Sensor icon must be mdi:flash."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        sensor = PlannedKwhTodaySensor(coordinator_with_energy, device)
        assert sensor.icon == "mdi:flash"

    def test_slots_without_recipe_excluded_from_recipe_ids(
        self, hass, mock_api_client, mock_config_entry, device
    ):
        """Slots with no linked recipe (recipeId=None) are excluded from recipe_ids."""
        from custom_components.culiplan.sensor import PlannedKwhTodaySensor

        coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
        coord.data = {
            "energy_today": {
                "date": "2026-04-25",
                "estimated_kwh": 0.5,
                "slot_count": 2,
                "slots": [
                    {"mealPlanId": "mp1", "recipeId": "rec1", "recipeTitle": "Pasta", "estimated_kwh": 0.5},
                    {"mealPlanId": "mp2", "recipeId": None, "recipeTitle": None, "estimated_kwh": 0.0},
                ],
            }
        }
        sensor = PlannedKwhTodaySensor(coord, device)
        assert sensor.extra_state_attributes["recipe_ids"] == ["rec1"]


# ─── API client mock extension ───────────────────────────────────────────────


class TestApiClientEnergyMethod:
    """Verify async_get_energy_today is present and callable on the API client."""

    @pytest.mark.asyncio
    async def test_async_get_energy_today_exists(self, mock_api_client):
        """API client must expose async_get_energy_today method."""
        assert hasattr(mock_api_client, "async_get_energy_today")

    @pytest.mark.asyncio
    async def test_async_get_energy_today_returns_dict(self, mock_api_client):
        """async_get_energy_today returns a dict when awaited."""
        mock_api_client.async_get_energy_today.return_value = {
            "date": "2026-04-25",
            "estimated_kwh": 1.5,
            "slot_count": 1,
            "slots": [],
        }
        result = await mock_api_client.async_get_energy_today()
        assert isinstance(result, dict)
        assert result["estimated_kwh"] == 1.5


# ─── Coordinator energy refresh ──────────────────────────────────────────────


class TestCoordinatorEnergyRefresh:
    """Verify _refresh_energy updates coordinator data correctly."""

    @pytest.mark.asyncio
    async def test_refresh_energy_updates_data(self, hass, mock_api_client, mock_config_entry):
        """_refresh_energy fetches energy_today and merges it into coordinator.data."""
        from custom_components.culiplan.coordinator import CuliplanCoordinator

        mock_api_client.async_get_energy_today.return_value = {
            "date": "2026-04-25",
            "estimated_kwh": 2.0,
            "slot_count": 3,
            "slots": [],
        }

        coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
        coord.data = {"meal_plans": [], "shopping_lists": [], "pantry_items": []}

        await coord._refresh_energy()

        assert coord.data["energy_today"]["estimated_kwh"] == 2.0
        assert coord.data["energy_today"]["slot_count"] == 3
        # Existing keys must be preserved
        assert "meal_plans" in coord.data

    @pytest.mark.asyncio
    async def test_refresh_energy_handles_api_error_gracefully(
        self, hass, mock_api_client, mock_config_entry
    ):
        """_refresh_energy logs error but does not raise when API call fails."""
        from custom_components.culiplan.coordinator import CuliplanCoordinator

        mock_api_client.async_get_energy_today.side_effect = Exception("API timeout")

        coord = CuliplanCoordinator(hass, mock_api_client, mock_config_entry)
        coord.data = {"meal_plans": [], "shopping_lists": [], "pantry_items": []}

        # Must not raise
        await coord._refresh_energy()

        # Original data must be unchanged
        assert "energy_today" not in coord.data
