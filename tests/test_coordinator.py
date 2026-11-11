"""Tests for CDE Lightband DataUpdateCoordinator."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cde_lightband.const import DOMAIN, CONF_USERNAME, CONF_PASSWORD
from custom_components.cde_lightband.coordinator import CdeDataUpdateCoordinator
from custom_components.cde_lightband.cde_api import CdeBillingData, CdeRateData, CdeUsageRecord
from custom_components.cde_lightband.exceptions import CdeAuthError, CdeConnectionError

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
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ) as mock_sync_stats:
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        data = await coordinator._async_update_data()
        assert data["billing"] == mock_billing
        assert data["usage"] == mock_usage
        assert data["rates"] is None
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
async def test_coordinator_auth_error_raises_config_entry_auth_failed(hass: HomeAssistant):
    """Test auth error raises ConfigEntryAuthFailed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        side_effect=CdeAuthError("Invalid credentials"),
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        with pytest.raises(ConfigEntryAuthFailed):
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


def _rates_entry(hass: HomeAssistant, options: dict | None = None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        options=options or {},
        unique_id="123456",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_coordinator_stores_rates_and_internet_price(hass: HomeAssistant):
    """Successful update stores parsed rates with the selected internet price."""
    entry = _rates_entry(hass, {"internet_plan": "300"})
    mock_billing = CdeBillingData(
        account_number="123456",
        balance_due=75.50,
        due_date="2026-11-20",
        last_payment_amount=80.00,
        service_address="100 Main St",
    )
    mock_rates = CdeRateData(
        energy_rate=0.11010,
        customer_charge=30.50,
        grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
        rate_month="November 2026",
    )

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        return_value=mock_rates,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_internet_prices",
        new_callable=AsyncMock,
        return_value={"300": 53.95},
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        data = await coordinator._async_update_data()
        coordinator.data = data  # _async_update_data() called directly does not store into self.data
        assert data["rates"] is not None
        assert data["rates"].energy_rate == 0.11010
        assert data["rates"].internet_prices == {"300": 53.95}
        assert coordinator.rate_data is data["rates"]


@pytest.mark.asyncio
async def test_rates_scrape_failure_keeps_last_known_rates(hass: HomeAssistant):
    """A rates-page outage must not fail the update or lose last-known rates."""
    entry = _rates_entry(hass)
    mock_billing = CdeBillingData(
        account_number="123456",
        balance_due=75.50,
        due_date="2026-11-20",
        last_payment_amount=80.00,
        service_address="100 Main St",
    )
    mock_rates = CdeRateData(
        energy_rate=0.11010,
        customer_charge=30.50,
        grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
        rate_month="November 2026",
    )

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        side_effect=[mock_rates, None],
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        first = await coordinator._async_update_data()
        assert first["rates"] is not None
        second = await coordinator._async_update_data()  # scrape fails this cycle
        assert second["rates"] is not None
        assert second["rates"].energy_rate == 0.11010


@pytest.mark.asyncio
async def test_rates_fetch_exception_does_not_fail_update(hass: HomeAssistant):
    """An unexpected rates exception must not raise UpdateFailed."""
    entry = _rates_entry(hass)
    mock_billing = CdeBillingData(
        account_number="123456",
        balance_due=75.50,
        due_date="2026-11-20",
        last_payment_amount=80.00,
        service_address="100 Main St",
    )

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        side_effect=Exception("boom"),
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        data = await coordinator._async_update_data()
        assert data["billing"] is mock_billing
        assert data["rates"] is None


@pytest.mark.asyncio
async def test_month_to_date_kwh_filters_by_calendar_month(hass: HomeAssistant):
    """Only records inside the current calendar month are summed."""
    entry = _rates_entry(hass)
    coordinator = CdeDataUpdateCoordinator(hass, entry)
    coordinator.data = {
        "billing": None,
        "usage": [
            CdeUsageRecord(timestamp="2026-10-31T00:00:00+00:00", kwh=9.9, meter_id="M1"),
            CdeUsageRecord(timestamp="2026-11-01T00:00:00+00:00", kwh=42.8, meter_id="M1"),
            CdeUsageRecord(timestamp="2026-11-02T00:00:00+00:00", kwh=1.2, meter_id="M1"),
        ],
        "rates": None,
    }
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert coordinator.month_to_date_kwh(now) == 44.0
    assert coordinator.month_to_date_kwh(datetime(2026, 12, 1, tzinfo=timezone.utc)) == 0.0
