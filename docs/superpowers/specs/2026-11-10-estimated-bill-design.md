# Estimated Bill Sensor — Design

Date: 2026-11-10
Status: Approved (in chat, by product owner)

## Intent and Why

The integration already pulls daily kWh usage from the CDE Lightband "Charts"
API and exposes the latest day's consumption as `sensor.<prefix>_daily_energy_consumption`.
The owner wants to know what the *bill* is shaping up to be: combine month-to-date
usage with CDE's published retail rates, plus the (optional) internet plan charge,
into a new `estimated_bill` sensor that updates on every coordinator refresh.

## Goals

- New sensor `sensor.<prefix>_estimated_bill` (currency, USD) computed as:
  - `month_to_date_kWh × energy_rate`
  - `+ customer_charge` ($30.50 today)
  - `+ grid_access_charge` tiered on month-to-date kWh ($2.00 at ≤1,000,
    $4.00 at 1,001–2,000, $7.00 above 2,000 — parse these from the page, don't hardcode)
  - `+ internet_plan_price` when an internet plan is selected in options
- Rates scraped live from `https://cdelightband.com/residential/energy/rates-fees/`
  on each coordinator update, so CDE's monthly rate changes are picked up
  automatically. The page labels its table with a month (e.g. "November 2026
  Retail Rate") — expose that label as an attribute.
- New options-flow field: internet plan dropdown — `none` / `300` / `600` / `1000` /
  `2500` Mbps. Prices live on `https://cdelightband.com/residential/internet/`
  ($53.95 / $73.95 / $94.95 / $123.95). Scrape them the same way (not hardcoded)
  when `internet` != none; the dropdown stores the Mbps key, the price comes
  from the page.
- Sensor attributes make the estimate auditable: month kWh total, energy rate,
  customer charge, grid access tier/charge, internet plan and price, rate-month
  label, and when rates were last fetched.
- If the rates page fetch or parse fails, keep the last-known-good rates,
  log a warning, and still publish an estimate using them. A rates failure
  must never fail the coordinator update or affect the other sensors: the
  rates fetch is wrapped independently inside `_async_update_data` and its
  errors never propagate as `UpdateFailed`. The `estimated_bill` sensor
  shows `unknown` only when no rates have ever been obtained.
- The same fail-soft + last-known-good treatment applies to internet plan
  prices when an internet plan is selected: on fetch/parse failure, reuse
  the last-known price and log a warning; never silently omit the internet
  charge from a published estimate. (Builder call, confirmed with owner.)
- Month-start edge case: if there are no usage records in the current
  calendar month, the sensor publishes `unknown` (not a fixed-charges-only
  number), so a near-empty estimate can't be mistaken for a real bill.
  (Owner decision.)

## Non-goals

- No sales tax, TVA fuel-cost adjustment, or other non-published charges.
  The estimate intentionally runs slightly low vs. the real bill. A later
  iteration may add an adjustment setting.
- No change to the existing Energy Dashboard statistics ingestion.
- No billing-cycle alignment: the estimate covers the current *calendar* month,
  matching how the Charts API buckets usage. (Owner's call.)
- Business/commercial rate schedules are out of scope — residential (RS) only.

## Constraints

- Must fit the existing integration architecture:
  - Data fetching lives in `cde_api.py` (`CdeApiClient`), parsing into small
    dataclasses like `CdeUsageRecord` / `CdeBillingData`.
  - The coordinator (`coordinator.py`) calls the client in `_async_update_data`
    and stows results in its `data` dict (`"billing"`, `"usage"`); a new
    `"rates"` key follows the same pattern.
  - Sensors subclass `CdeBaseSensor` in `sensor.py` and read coordinator data.
  - Options are read via `entry.options` with `const.py` keys and defaults.
- Scraping uses the shared aiohttp session pattern already in the coordinator;
  plain GET of the public page, no auth needed.
- Rate tables are plain HTML tables on the page; parsing should be tolerant of
  whitespace and should fail soft (return `None`) rather than raise.
- Tests use the existing `pytest-homeassistant-custom-component` harness
  (see `tests/test_sensor.py`, `tests/test_coordinator.py`); add coverage for
  the parser (with a saved HTML fixture), the estimate math including tier
  boundaries, and the options flow default.

## Decided by the Owner

- Published charges only; no tax/adjustment estimate for now.
- Internet selection is a dropdown (plan tiers), not a plain yes/no.
- Estimate resets on calendar-month boundaries.

## Left to the Builder

- Exact HTML-parsing approach for the rates page (BeautifulSoup vs regex on the
  fetched text; pick what the project's dependency set supports — check
  `requirements`/manifest before adding anything).
- Const names, attribute key names, sensor friendly name wording.
- Where the month-to-date sum is computed (coordinator helper vs sensor
  property) — pick one, keep the sensor thin like the existing ones.
- Caching strategy for "last known good rates" (in-memory on the coordinator
  is sufficient; persistence across HA restarts is optional).
- Whether the internet prices are scraped from the internet page on every
  update or only when the plan setting changes (owner doesn't care; scraping
  with the rates fetch each cycle is acceptable).
