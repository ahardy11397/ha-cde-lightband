"""DataUpdateCoordinator for CDE Lightband integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import EnergyConverter

try:
    from homeassistant.components.recorder.models import (
        StatisticData,
        StatisticMetaData,
        StatisticMeanType,
    )
    from homeassistant.components.recorder.statistics import (
        async_add_external_statistics,
        get_last_statistics,
    )
    from homeassistant.components.recorder import get_instance
    RECORDER_AVAILABLE = True
except ImportError:
    RECORDER_AVAILABLE = False

from .cde_api import CdeApiClient, CdeBillingData, CdeUsageRecord
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_HISTORY_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_HISTORY_DAYS,
)
from .exceptions import CdeError

_LOGGER = logging.getLogger(__name__)


class CdeDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch CDE Lightband billing and usage metrics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        scan_minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"CDE Lightband ({entry.unique_id})",
            update_interval=timedelta(minutes=scan_minutes),
        )

        session = async_get_clientsession(hass)
        self.client = CdeApiClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            session=session,
        )
        self._account_number: str = entry.unique_id or "Unknown"

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def billing_data(self) -> CdeBillingData | None:
        """Return the current billing data."""
        if self.data:
            return self.data.get("billing")
        return None

    @property
    def usage_records(self) -> list[CdeUsageRecord]:
        """Return the latest usage records."""
        if self.data:
            return self.data.get("usage", [])
        return []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from CDE Lightband."""
        try:
            billing = await self.client.fetch_billing_data()
            if billing.account_number and billing.account_number != "Unknown":
                self._account_number = billing.account_number

            days = self.entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
            usage_records = await self.client.fetch_usage_data(days=days)

            # Ingest usage into Energy Dashboard external statistics
            if usage_records:
                await self._async_sync_statistics(usage_records)

            return {
                "billing": billing,
                "usage": usage_records,
            }
        except CdeError as err:
            raise UpdateFailed(f"Error communicating with CDE Lightband: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error in CDE coordinator: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def _async_sync_statistics(self, records: list[CdeUsageRecord]) -> None:
        """Insert historical consumption into recorder external statistics."""
        if not RECORDER_AVAILABLE:
            return

        stat_id = f"{DOMAIN}:electric_consumption_{self._account_number}"
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"CDE Lightband Electric Usage ({self._account_number})",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        statistics: list[StatisticData] = []
        running_sum = 0.0

        # Query existing last statistic to continue running sum
        try:
            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, set()
            )
            if last_stats and stat_id in last_stats and last_stats[stat_id]:
                running_sum = last_stats[stat_id][0].get("sum") or 0.0
        except Exception as err:
            _LOGGER.debug("Could not retrieve last statistics for %s: %s", stat_id, err)

        for record in records:
            try:
                # Parse timestamp
                dt: datetime
                if record.timestamp.endswith("Z"):
                    dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                elif "T" in record.timestamp:
                    dt = datetime.fromisoformat(record.timestamp)
                else:
                    dt = datetime.now(timezone.utc)

                running_sum += record.kwh
                statistics.append(
                    StatisticData(
                        start=dt,
                        state=record.kwh,
                        sum=running_sum,
                    )
                )
            except Exception as err:
                _LOGGER.warning("Could not parse usage record %s: %s", record, err)

        if statistics:
            _LOGGER.debug("Inserting %d external statistics for %s", len(statistics), stat_id)
            async_add_external_statistics(self.hass, metadata, statistics)
