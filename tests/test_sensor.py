"""Tests for CDE Lightband sensor entities."""
import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorDeviceClass
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cde_lightband.const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_INTERNET_PLAN,
)
from custom_components.cde_lightband.cde_api import (
    CdeBillingData,
    CdeRateData,
    CdeUsageRecord,
)
from custom_components.cde_lightband.coordinator import CdeDataUpdateCoordinator

@pytest.mark.asyncio
async def test_sensors_created_and_updated(hass: HomeAssistant):
    """Test all CDE Lightband sensors are set up with correct states and attributes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "testuser", CONF_PASSWORD: "testpassword"},
        unique_id="12345678",
    )
    entry.add_to_hass(hass)

    mock_billing = CdeBillingData(
        account_number="12345678",
        balance_due=155.75,
        due_date="2026-11-20",
        is_past_due=False,
        past_due_amount=0.0,
        last_payment_amount=140.00,
        last_payment_date="2026-10-18",
        last_bill_amount=155.75,
        last_bill_date="2026-10-28",
        service_address="456 Power Lane, Clarksville, TN",
    )
    mock_usage = [
        CdeUsageRecord(
            timestamp="2026-11-01T00:00:00Z",
            kwh=42.8,
            meter_id="ELEC-MTR-99",
            reading_date="2026-11-01",
        )
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
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # 1. Balance Due Sensor
        balance_state = hass.states.get("sensor.cde_lightband_12345678_balance_due")
        assert balance_state is not None
        assert float(balance_state.state) == 155.75
        assert balance_state.attributes["unit_of_measurement"] == "USD"
        assert balance_state.attributes["device_class"] == SensorDeviceClass.MONETARY
        assert balance_state.attributes["account_number"] == "12345678"
        assert balance_state.attributes["service_address"] == "456 Power Lane, Clarksville, TN"

        # 2. Payment Due Date Sensor
        due_state = hass.states.get("sensor.cde_lightband_12345678_payment_due_date")
        assert due_state is not None
        assert due_state.state == "2026-11-20"
        assert due_state.attributes["device_class"] == SensorDeviceClass.DATE
        assert "days_until_due" in due_state.attributes

        # 3. Last Payment Sensor
        payment_state = hass.states.get("sensor.cde_lightband_12345678_last_payment_amount")
        assert payment_state is not None
        assert float(payment_state.state) == 140.00
        assert payment_state.attributes["last_payment_date"] == "2026-10-18"

        # 4. Last Bill Sensor
        bill_state = hass.states.get("sensor.cde_lightband_12345678_last_bill_amount")
        assert bill_state is not None
        assert float(bill_state.state) == 155.75
        assert bill_state.attributes["last_bill_date"] == "2026-10-28"

        # 5. Daily Energy Consumption Sensor
        energy_state = hass.states.get("sensor.cde_lightband_12345678_daily_energy_consumption")
        assert energy_state is not None
        assert float(energy_state.state) == 42.8
        assert energy_state.attributes["unit_of_measurement"] == "kWh"
        assert energy_state.attributes["device_class"] == SensorDeviceClass.ENERGY
        assert energy_state.attributes["meter_id"] == "ELEC-MTR-99"

        # Check device association
        assert balance_state.attributes["attribution"] == "Data provided by CDE Lightband"


mock_rates = CdeRateData(
    energy_rate=0.11010,
    customer_charge=30.50,
    grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
    rate_month="November 2026",
    internet_prices={"300": 53.95},
    fetched_at="2026-11-10T12:00:00+00:00",
)

_INTERNET_PRICES = {"300": 53.95, "600": 73.95, "1000": 94.95, "2500": 123.95}
_UNSET = object()


async def _setup_estimated_bill(hass, entry_options=None, rates=mock_rates, usage=None, kwh=42.8, internet_prices=_UNSET):
    """Set up the integration with patched client methods; returns the entry."""
    if internet_prices is _UNSET:
        internet_prices = _INTERNET_PRICES
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "testuser", CONF_PASSWORD: "testpassword"},
        options=entry_options or {},
        unique_id="12345678",
    )
    entry.add_to_hass(hass)
    mock_billing = CdeBillingData(
        account_number="12345678",
        balance_due=155.75,
        due_date="2026-11-20",
        service_address="456 Power Lane, Clarksville, TN",
    )
    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=usage if usage is not None else [],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        return_value=rates,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_internet_prices",
        new_callable=AsyncMock,
        return_value=internet_prices,
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ), patch.object(
        CdeDataUpdateCoordinator, "month_to_date_kwh", return_value=kwh
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_estimated_bill_sensor_computes_estimate(hass: HomeAssistant):
    """Estimate = kWh*rate + customer + grid access + internet price."""
    await _setup_estimated_bill(hass, {CONF_INTERNET_PLAN: "300"})
    state = hass.states.get("sensor.cde_lightband_12345678_estimated_bill")
    assert state is not None
    assert float(state.state) == 91.16  # 42.8*0.11010=4.71 + 30.50 + 2.00 + 53.95
    assert state.attributes["device_class"] == SensorDeviceClass.MONETARY
    assert state.attributes["unit_of_measurement"] == "USD"
    assert state.attributes["month_to_date_kwh"] == 42.8
    assert state.attributes["energy_rate"] == 0.11010
    assert state.attributes["customer_charge"] == 30.5
    assert state.attributes["grid_access_charge"] == 2.0
    assert state.attributes["internet_plan"] == "300"
    assert state.attributes["internet_price"] == 53.95
    assert state.attributes["rate_month"] == "November 2026"


@pytest.mark.asyncio
async def test_estimated_bill_sensor_without_internet(hass: HomeAssistant):
    """No internet plan selected: published charges only."""
    await _setup_estimated_bill(hass, {})
    state = hass.states.get("sensor.cde_lightband_12345678_estimated_bill")
    assert state is not None
    assert float(state.state) == 37.21  # 4.71 + 30.50 + 2.00
    assert "internet_price" not in state.attributes
    assert "internet_plan" not in state.attributes


@pytest.mark.asyncio
async def test_estimated_bill_unknown_before_rates_fetched(hass: HomeAssistant):
    """No rates ever obtained -> unknown state."""
    await _setup_estimated_bill(hass, {}, rates=None)
    state = hass.states.get("sensor.cde_lightband_12345678_estimated_bill")
    assert state is not None
    assert state.state == "unknown"


@pytest.mark.asyncio
async def test_estimated_bill_unknown_at_month_start(hass: HomeAssistant):
    """No usage in the current calendar month -> unknown, not a fixed-charge number."""
    await _setup_estimated_bill(hass, {CONF_INTERNET_PLAN: "300"}, kwh=0)
    state = hass.states.get("sensor.cde_lightband_12345678_estimated_bill")
    assert state is not None
    assert state.state == "unknown"


@pytest.mark.asyncio
async def test_estimated_bill_unknown_when_internet_price_missing(hass: HomeAssistant):
    """Internet plan selected but its price unavailable -> unknown, never understated."""
    rates_no_internet = CdeRateData(
        energy_rate=0.11010,
        customer_charge=30.50,
        grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
        rate_month="November 2026",
    )
    await _setup_estimated_bill(hass, {CONF_INTERNET_PLAN: "300"}, rates=rates_no_internet, internet_prices=None)
    state = hass.states.get("sensor.cde_lightband_12345678_estimated_bill")
    assert state is not None
    assert state.state == "unknown"
