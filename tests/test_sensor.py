"""Tests for CDE Lightband sensor entities."""
import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorDeviceClass
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cde_lightband.const import DOMAIN, CONF_USERNAME, CONF_PASSWORD
from custom_components.cde_lightband.cde_api import CdeBillingData, CdeUsageRecord

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
