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


@pytest.mark.asyncio
async def test_sync_statistics_incremental_ingestion(hass: HomeAssistant):
    """Test incremental external statistics sync avoids duplicate compounding."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    coordinator = CdeDataUpdateCoordinator(hass, entry)
    coordinator._account_number = "123456"

    records = [
        CdeUsageRecord(timestamp="2026-10-31T00:00:00+00:00", kwh=10.0, meter_id="M123"),
        CdeUsageRecord(timestamp="2026-11-01T00:00:00+00:00", kwh=15.0, meter_id="M123"),
    ]

    # Mock recorder already having Oct 31 with sum=50.0
    last_dt_ts = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc).timestamp()
    mock_last_stats = {
        "cde_lightband:electric_consumption_123456": [
            {"start": last_dt_ts, "sum": 50.0}
        ]
    }

    with patch(
        "custom_components.cde_lightband.coordinator.get_last_statistics",
        return_value=mock_last_stats,
    ), patch(
        "custom_components.cde_lightband.coordinator.async_add_external_statistics"
    ) as mock_add_stats:
        await coordinator._async_sync_statistics(records)
        mock_add_stats.assert_called_once()
        _, args, _ = mock_add_stats.mock_calls[0]
        metadata, stat_list = args[1], args[2]

        # Only 2026-11-01 should be ingested (Oct 31 skipped)
        assert len(stat_list) == 1
        assert stat_list[0]["state"] == 15.0
        assert stat_list[0]["sum"] == 65.0  # 50.0 + 15.0
