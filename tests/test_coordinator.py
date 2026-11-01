"""Tests for CDE Lightband DataUpdateCoordinator."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cde_lightband.const import DOMAIN, CONF_USERNAME, CONF_PASSWORD
from custom_components.cde_lightband.coordinator import CdeDataUpdateCoordinator
from custom_components.cde_lightband.cde_api import CdeBillingData, CdeUsageRecord
from custom_components.cde_lightband.exceptions import CdeConnectionError

@pytest.mark.asyncio
async def test_coordinator_update_success(hass: HomeAssistant):
    """Test successful data update in coordinator."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    mock_billing = CdeBillingData(
        account_number="123456",
        balance_due=75.50,
        due_date="2026-11-20",
        last_payment_amount=80.00,
        service_address="100 Main St",
    )
    mock_usage = [
        CdeUsageRecord(timestamp="2026-11-01T00:00:00Z", kwh=25.4, meter_id="M123")
    ]

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=mock_usage,
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ) as mock_sync_stats:
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        data = await coordinator._async_update_data()
        assert data["billing"] == mock_billing
        assert data["usage"] == mock_usage
        assert coordinator.account_number == "123456"
        mock_sync_stats.assert_called_once_with(mock_usage)


@pytest.mark.asyncio
async def test_coordinator_update_failure_raises_update_failed(hass: HomeAssistant):
    """Test connection error raises UpdateFailed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        side_effect=CdeConnectionError("Connection timeout"),
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
