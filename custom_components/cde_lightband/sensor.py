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
    ATTR_MONTH_TO_DATE_KWH,
    ATTR_DAILY_KWH,
    ATTR_ENERGY_RATE,
    ATTR_CUSTOMER_CHARGE,
    ATTR_GRID_ACCESS_CHARGE,
    ATTR_INTERNET_PLAN,
    ATTR_INTERNET_PRICE,
    ATTR_RATE_MONTH,
    ATTR_RATES_FETCHED,
    CONF_INTERNET_PLAN,
    DEFAULT_INTERNET_PLAN,
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
        CdeDailyEnergyCostSensor(coordinator),
        CdeEstimatedBillSensor(coordinator),
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


class CdeDailyEnergyCostSensor(CdeBaseSensor):
    """Sensor for the daily energy cost (kWh * published energy rate, USD).

    Tracks the same meter record as ``CdeDailyEnergySensor``, so the two
    update together: daily kWh times the energy rate only — no fixed
    charges, taxes, or internet.
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "daily_energy_cost", "Daily energy cost")

    @property
    def native_value(self) -> float | None:
        rates = self.coordinator.rate_data
        records = self.coordinator.usage_records
        if rates is None or not records:
            return None
        return round(records[-1].kwh * rates.energy_rate, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rates = self.coordinator.rate_data
        records = self.coordinator.usage_records
        if rates is None or not records:
            return {}
        latest = records[-1]
        return {
            ATTR_DAILY_KWH: latest.kwh,
            ATTR_ENERGY_RATE: rates.energy_rate,
            ATTR_READING_DATE: latest.reading_date or latest.timestamp,
            ATTR_RATE_MONTH: rates.rate_month,
        }


class CdeEstimatedBillSensor(CdeBaseSensor):
    """Sensor for the estimated current-month electric bill (USD)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: CdeDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "estimated_bill", "Estimated bill")

    def _plan(self) -> str:
        return self.coordinator.entry.options.get(CONF_INTERNET_PLAN, DEFAULT_INTERNET_PLAN)

    @property
    def native_value(self) -> float | None:
        rates = self.coordinator.rate_data
        if rates is None:
            return None
        kwh = self.coordinator.month_to_date_kwh()
        if kwh <= 0:
            return None
        plan = self._plan()
        internet_price = 0.0
        if plan != DEFAULT_INTERNET_PLAN:
            internet_price = rates.internet_prices.get(plan)
            if internet_price is None:
                return None  # never publish an estimate missing the internet charge
        energy_cost = round(kwh * rates.energy_rate, 2)
        return round(
            energy_cost + rates.customer_charge + rates.grid_access_charge(kwh) + internet_price,
            2,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rates = self.coordinator.rate_data
        if not rates:
            return {}
        plan = self._plan()
        kwh = self.coordinator.month_to_date_kwh()
        attrs: dict[str, Any] = {
            ATTR_MONTH_TO_DATE_KWH: kwh,
            ATTR_ENERGY_RATE: rates.energy_rate,
            ATTR_CUSTOMER_CHARGE: rates.customer_charge,
            ATTR_GRID_ACCESS_CHARGE: rates.grid_access_charge(kwh),
            ATTR_RATE_MONTH: rates.rate_month,
            ATTR_RATES_FETCHED: rates.fetched_at,
        }
        if plan != DEFAULT_INTERNET_PLAN:
            attrs[ATTR_INTERNET_PLAN] = plan
            attrs[ATTR_INTERNET_PRICE] = rates.internet_prices.get(plan)
        return attrs
