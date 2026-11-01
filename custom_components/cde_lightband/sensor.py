"""Sensor platform for CDE Lightband integration."""
from __future__ import annotations

from typing import Any
from datetime import datetime, date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_ACCOUNT_NUMBER,
    ATTR_SERVICE_ADDRESS,
    ATTR_IS_PAST_DUE,
    ATTR_PAST_DUE_AMOUNT,
    ATTR_LAST_PAYMENT_DATE,
    ATTR_LAST_BILL_DATE,
    ATTR_METER_ID,
    ATTR_READING_DATE,
)
from .coordinator import CdeDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CDE Lightband sensor entities based on a config entry."""
    coordinator: CdeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        CdeBalanceDueSensor(coordinator),
        CdePaymentDueDateSensor(coordinator),
        CdeLastPaymentSensor(coordinator),
        CdeLastBillSensor(coordinator),
        CdeDailyEnergySensor(coordinator),
    ]

    async_add_entities(entities)


class CdeBaseSensor(CoordinatorEntity[CdeDataUpdateCoordinator], SensorEntity):
    """Base sensor for CDE Lightband."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by CDE Lightband"

    def __init__(
        self,
        coordinator: CdeDataUpdateCoordinator,
        key: str,
        name: str,
    ) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.account_number}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.account_number)},
            name=f"CDE Lightband ({coordinator.account_number})",
            manufacturer="CDE Lightband",
            model="Power & Broadband",
            entry_type=DeviceEntryType.SERVICE,
        )


class CdeBalanceDueSensor(CdeBaseSensor):
    """Sensor for current balance due."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "balance_due", "Balance due")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.billing_data:
            return self.coordinator.billing_data.balance_due
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.billing_data
        if not data:
            return {}
        return {
            ATTR_ACCOUNT_NUMBER: data.account_number,
            ATTR_SERVICE_ADDRESS: data.service_address,
            ATTR_IS_PAST_DUE: data.is_past_due,
            ATTR_PAST_DUE_AMOUNT: data.past_due_amount,
        }


class CdePaymentDueDateSensor(CdeBaseSensor):
    """Sensor for payment due date."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "payment_due_date", "Payment due date")

    @property
    def native_value(self) -> date | None:
        if self.coordinator.billing_data and self.coordinator.billing_data.due_date:
            due_val = self.coordinator.billing_data.due_date
            if isinstance(due_val, date):
                return due_val
            for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(due_val.strip(), fmt).date()
                except ValueError:
                    pass
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.billing_data
        if not data or not data.due_date:
            return {}
        attrs: dict[str, Any] = {}
        try:
            if isinstance(data.due_date, date):
                due_d = data.due_date
            else:
                due_d = datetime.strptime(data.due_date, "%Y-%m-%d").date()
            attrs["days_until_due"] = (due_d - date.today()).days
        except ValueError:
            pass
        return attrs


class CdeLastPaymentSensor(CdeBaseSensor):
    """Sensor for most recent payment amount."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "last_payment_amount", "Last payment amount")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.billing_data:
            return self.coordinator.billing_data.last_payment_amount
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.billing_data
        if not data or not data.last_payment_date:
            return {}
        return {ATTR_LAST_PAYMENT_DATE: data.last_payment_date}


class CdeLastBillSensor(CdeBaseSensor):
    """Sensor for latest generated bill total."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "last_bill_amount", "Last bill amount")

    @property
    def native_value(self) -> float | None:
        if self.coordinator.billing_data:
            return self.coordinator.billing_data.last_bill_amount
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.billing_data
        if not data or not data.last_bill_date:
            return {}
        return {ATTR_LAST_BILL_DATE: data.last_bill_date}


class CdeDailyEnergySensor(CdeBaseSensor):
    """Sensor for daily energy consumption (kWh)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "daily_energy_consumption", "Daily energy consumption")

    @property
    def native_value(self) -> float | None:
        records = self.coordinator.usage_records
        if records:
            return records[-1].kwh
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        records = self.coordinator.usage_records
        if not records:
            return {}
        latest = records[-1]
        return {
            ATTR_METER_ID: latest.meter_id,
            ATTR_READING_DATE: latest.reading_date or latest.timestamp,
        }
