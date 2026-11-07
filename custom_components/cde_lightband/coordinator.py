"""DataUpdateCoordinator for CDE Lightband integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
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
from .exceptions import CdeAuthError, CdeError

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
            config_entry=entry,
            name=f"CDE Lightband ({entry.unique_id})",
            update_interval=timedelta(minutes=scan_minutes),
        )

        self._session: aiohttp.ClientSession = async_create_clientsession(hass)
        self.client = CdeApiClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            session=self._session,
        )
        self._account_number: str = entry.unique_id or "Unknown"

    async def async_shutdown(self) -> None:
        """Close the dedicated aiohttp session."""
        await super().async_shutdown()
        if self.client:
            await self.client.close()
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def account_number(self) -> str:
        if self.client and self.client.account_number:
            return self.client.account_number
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
        except CdeAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
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
            mean_type=StatisticMeanType.NONE,
            name=f"CDE Lightband Electric Usage ({self._account_number})",
            source=DOMAIN,
            statistic_id=stat_id,
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        statistics: list[StatisticData] = []
        running_sum = 0.0
        last_dt: datetime | None = None

        # Query existing last statistic to continue running sum and avoid duplicate ingestion
        try:
            last_stats = await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, {"start", "sum"}
            )
            if last_stats and stat_id in last_stats and last_stats[stat_id]:
                last_stat = last_stats[stat_id][0]
                running_sum = last_stat.get("sum") or 0.0
                last_start = last_stat.get("start")
                if isinstance(last_start, (int, float)):
                    last_dt = datetime.fromtimestamp(last_start, tz=timezone.utc)
                elif isinstance(last_start, datetime):
                    last_dt = last_start if last_start.tzinfo else last_start.replace(tzinfo=timezone.utc)
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
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.now(timezone.utc)

                # Skip records that are already ingested or older than the last recorded statistic
                if last_dt and dt <= last_dt:
                    continue

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
