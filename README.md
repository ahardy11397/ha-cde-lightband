# CDE Lightband Home Assistant Custom Integration

[![CI](https://img.shields.io/badge/home--assistant-custom--component-blue.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A native custom integration for [Home Assistant](https://www.home-assistant.io/) connecting to **CDE Lightband** (Clarksville Department of Electricity, Clarksville, TN) to ingest utility billing information, smart meter electric consumption data, and live published rate estimates.

---

## Features

> [!NOTE]
> All entities are registered under the `CDE Lightband (<account_number>)` service device (`_attr_has_entity_name = True`) and use the entity ID format `sensor.cde_lightband_<account_number>_<key>` (for example, `sensor.cde_lightband_12345678_balance_due`).

### Sensor Reference

| Entity ID | Device Class | Unit | State Value | Extra State Attributes |
|---|---|---|---|---|
| `sensor.cde_lightband_<account>_balance_due` | `monetary` | `USD` | Current total amount owed | `account_number`, `service_address`, `is_past_due`, `past_due_amount` |
| `sensor.cde_lightband_<account>_payment_due_date` | `date` | — | Upcoming statement due date (`YYYY-MM-DD`) | `days_until_due` |
| `sensor.cde_lightband_<account>_last_payment_amount` | `monetary` | `USD` | Most recent payment amount | `last_payment_date` |
| `sensor.cde_lightband_<account>_last_bill_amount` | `monetary` | `USD` | Total of the most recent billing statement | `last_bill_date` |
| `sensor.cde_lightband_<account>_daily_energy_consumption` | `energy` | `kWh` | Most recent completed day's smart meter consumption | `meter_id`, `reading_date` |
| `sensor.cde_lightband_<account>_daily_energy_cost` | `monetary` | `USD` | Energy cost for the most recent completed meter day (`round(daily_kwh * energy_rate, 2)`) | `daily_kwh`, `energy_rate`, `reading_date`, `rate_month` |
| `sensor.cde_lightband_<account>_estimated_bill` | `monetary` | `USD` | Running calendar-month bill estimate (`round(month_to_date_kwh * energy_rate, 2) + customer_charge + grid_access_charge + internet_price`) | `month_to_date_kwh`, `energy_rate`, `customer_charge`, `grid_access_charge`, `rate_month`, `rates_fetched`, plus `internet_plan` and `internet_price` when an internet plan is selected |

Long-term Energy Dashboard statistics are also written to Home Assistant's `recorder` as the external statistic `cde_lightband:electric_consumption_<account>` (`kWh`, cumulative `sum`).

### 1. Billing Sensors
Automatically exposes account billing details as native Home Assistant entities:
* `sensor.cde_lightband_<account>_balance_due`: Current total amount owed (`USD`), with attributes for `account_number`, `service_address`, `is_past_due`, and `past_due_amount`.
* `sensor.cde_lightband_<account>_payment_due_date`: Upcoming statement due date (`date`) and `days_until_due`.
* `sensor.cde_lightband_<account>_last_payment_amount`: Most recent payment amount (`USD`) and `last_payment_date`.
* `sensor.cde_lightband_<account>_last_bill_amount`: Total of the most recent billing statement (`USD`) and `last_bill_date`.

### 2. Home Assistant Energy Dashboard Integration
* Tracks daily electric consumption via `sensor.cde_lightband_<account>_daily_energy_consumption` (`kWh`), along with `meter_id` and `reading_date`.
* Seamlessly injects smart meter daily readings directly into Home Assistant's long-term statistics database (`recorder`) via `async_add_external_statistics` (`cde_lightband:electric_consumption_<account>`).
* Add CDE Lightband as an **Electricity Grid** source under **Settings > Dashboards > Energy**.
* Automatically backfills historical smart meter readings on setup (current month by default, or current and previous month when `Historical usage days to sync` is set above `30`).

### 3. Estimated Bill Sensor
* `sensor.cde_lightband_<account>_estimated_bill`: Running estimate of the current calendar month's electric bill (`USD`), computed as `round(month_to_date_kwh * energy_rate, 2) + customer_charge + grid_access_charge + internet_price`.
* If you also subscribe to CDE Lightband internet, pick your plan (`300 Mbps` / `600 Mbps` / `1 Gig` / `2.5 Gig`) under **Configure > Options** and its monthly price is scraped and added to the estimate.
* Rates are scraped live from CDE's [Rates & Fees](https://cdelightband.com/residential/energy/rates-fees/) page (Customer Charge, Energy Rate per kWh, and tiered Grid Access Charge for `0–1,000 kWh`, `1,001–2,000 kWh`, and `>2,000 kWh`) and, when configured, from CDE's [Residential Internet](https://cdelightband.com/residential/internet/) page on every update. Rate changes are picked up automatically; if either page is temporarily unavailable or fails to parse, the integration logs a warning, reuses the last-known-good cached values, and never fails the billing/usage update.
* Shows `unknown` until rates have been fetched, the first usage day of the current calendar month has landed, and (if an internet plan is selected) the internet plan price has been fetched.
* Covers CDE's published residential (`RS`) charges only — it does not include taxes or TVA fuel-cost adjustments, so it will run slightly below the actual bill.
* Attributes show exactly how the estimate was built: `month_to_date_kwh`, `energy_rate`, `customer_charge`, `grid_access_charge`, `rate_month`, `rates_fetched`, plus `internet_plan` and `internet_price` when an internet plan is selected.

### 4. Daily Energy Cost Sensor
* `sensor.cde_lightband_<account>_daily_energy_cost`: What your most recent completed meter day cost in energy (`USD`) — `round(daily_kwh * energy_rate, 2)`.
* Updates together with `sensor.cde_lightband_<account>_daily_energy_consumption`: when one moves, the other does.
* Covers the raw energy charge only — no fixed customer/grid charges, taxes, or internet — so it shows what the daily kWh cost rather than a complete daily bill.
* Attributes: `daily_kwh`, `energy_rate`, `reading_date`, and `rate_month`.

### 5. Native UI Configuration, Options & Re-authentication
* Easily configured via **Settings > Devices & Services > Add Integration**.
* Securely manages authentication against the CDE Lightband customer portal (`myaccount.clarksvillede.com`).
* Automatically detects your account number and binds all sensors to a single device in the Home Assistant Device Registry.
* Configurable update interval, historical usage backfill window, and internet plan via the **Options Flow**.
* Built-in **Re-authentication Flow** prompts for an updated password if portal credentials change or fail, preserving entity IDs and historical statistics.

---

## How Meter Reading & Polling Work

* **Upstream Smart Meter Schedule (CDE Lightband → Portal)**: CDE Lightband reads smart meters on its own schedule and publishes **daily** consumption totals (`YYYY-MM-DD`, queried via `Charts/table` with `"TimeView": "DAILY"`) to `myaccount.clarksvillede.com`. Portal data typically lags real-time by a few hours to a day.
* **Home Assistant Polling (Integration → Portal)**: This integration does **not** trigger on-demand physical meter reads. Instead, `CdeDataUpdateCoordinator` checks the CDE portal every **60 minutes** by default (configurable from **15 to 1,440 minutes**) so newly posted daily meter readings, billing statements, and payments are picked up shortly after CDE publishes them.
* **Deduplication & Incremental Statistics**: On each refresh, the coordinator checks `get_last_statistics` in Home Assistant's `recorder` and only appends daily records with timestamps strictly newer than the last ingested statistic (`dt > last_dt`), preventing duplicate or out-of-order entries.
* **Fail-Soft Rate Scraping**: Public rate and internet pricing pages are fetched independently inside `_async_update_data`. Failures log a warning and fall back to the last-known-good cached values without causing `UpdateFailed` on billing or usage sensors.

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed and configured in Home Assistant.
2. In Home Assistant, navigate to **HACS > Integrations**.
3. Search for **CDE Lightband** (or add `https://github.com/ahardy11397/ha-cde-lightband` as a Custom Repository under HACS if not yet listed in the default store).
4. Click **Download**, then restart Home Assistant when prompted.

### Method 2: Manual Installation

1. Download the latest release from the [Releases](https://github.com/ahardy11397/ha-cde-lightband/releases) page.
2. Copy the `custom_components/cde_lightband` directory into your Home Assistant installation's `config/custom_components/` directory (so the integration resides at `custom_components/cde_lightband`).
3. Restart Home Assistant.

---

## Configuration & Setup

### 1. Pairing in the Home Assistant UI
1. In Home Assistant, navigate to **Settings > Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **CDE Lightband**.
4. Enter your login credentials for `myaccount.clarksvillede.com`:
   * **Username / Email**
   * **Password**
5. Click **Submit**. Home Assistant will authenticate with CDE Lightband, detect your account, and register all billing and energy sensors.

### 2. Configuring Options
Navigate to **Settings > Devices & Services > CDE Lightband > Configure** to adjust:

| Option | Key | Default | Allowed Values / Range | Description |
|---|---|---|---|---|
| **Update Interval (minutes)** | `scan_interval` | `60` | `15` – `1440` | How often Home Assistant polls the CDE portal and public rate pages. |
| **Historical usage days to sync** | `history_days` | `30` | `1` – `90` | Drills into the current month (and the previous month when set above `30`) to backfill daily readings. |
| **Internet Plan** | `internet_plan` | `none` | `None`, `300 Mbps`, `600 Mbps`, `1 Gig`, `2.5 Gig` | Adds the corresponding published CDE Lightband monthly internet charge to `sensor.cde_lightband_<account>_estimated_bill`. |

### 3. Re-authentication
If your CDE Lightband portal password changes or authentication fails during a scheduled poll, the coordinator raises `ConfigEntryAuthFailed` and Home Assistant surfaces a repair/re-authentication prompt (`reauth_confirm`) asking for your updated password.

### 4. Adding to the Energy Dashboard
1. Go to **Settings > Dashboards > Energy**.
2. Under **Electricity Grid**, click **Add Consumption**.
3. Select **CDE Lightband Electric Usage** (`cde_lightband:electric_consumption_<account>`).
4. Save your changes.

---

## Architecture & Technical Details

* **Backend Portal**: Daffron & Associates / Milsoft eBusiness (eBiz).
* **Protocol**: Google Web Toolkit Remote Procedure Call (GWT-RPC v7).
* **Endpoint**: `https://myaccount.clarksvillede.com/ebusiness/ebiz`
* **Permutation**: `64365524BBB2AFDF21B13502E153DBD9`
* **Policy ID**: `9B0246073475961F003BC947C4A4B6CF`
* **GWT-RPC Operations**:
  * `getInitialData()` & `signIn(username, password, "[1920,1080]")` for session establishment and token retrieval.
  * `getJsonData` bus calls: `AccountsTable/reload`, `AccountBillingHistory/table`, `AccountPayments/table`, `Charts/usage`, and `Charts/table` (`TimeView: "DAILY"`).

### Component Layout

```text
custom_components/cde_lightband/
├── __init__.py           # Config entry setup, reload listener, and shutdown
├── cde_api.py            # Async client, billing/usage models, and HTML rate parsers
├── config_flow.py        # UI config flow, reauth flow, and options flow
├── const.py              # Domain constants, URLs, option defaults, attribute keys
├── coordinator.py        # CdeDataUpdateCoordinator, rate cache, recorder statistics sync
├── exceptions.py         # CdeError, CdeAuthError, CdeConnectionError, CdeDataError
├── gwt_rpc.py            # GWT-RPC v7 payload builder and //OK / //EX response parser
├── manifest.json         # Integration metadata (iot_class: cloud_polling, after: recorder)
├── sensor.py             # 7 billing, energy, daily cost, and estimated bill sensors
├── strings.json          # Home Assistant UI string definitions
└── translations/
    └── en.json           # English localization strings
```

### CI/CD Workflows
* [`.github/workflows/validate.yml`](.github/workflows/validate.yml): Runs on pushes and pull requests to `master`/`main`; skips stale queued PR runs if the PR is no longer open, then runs `hacs/action`, `home-assistant/actions/hassfest`, and the full `pytest` suite.
* [`.github/workflows/release.yml`](.github/workflows/release.yml): Runs on pushes to `master`; detects when `custom_components/cde_lightband/manifest.json` bumps to a new version without an existing `vX.Y.Z` tag and automatically publishes the GitHub Release and tag for HACS.

---

## Knowledge Graph & Code Analysis

This project includes a [graphify](https://github.com/safishamsi/graphify) knowledge graph for interactive code exploration and architecture documentation.

### Generated Outputs

| File | Description |
|------|-------------|
| `graphify-out/graph.json` | GraphRAG-ready JSON (NetworkX compatible) |
| `graphify-out/GRAPH_REPORT.md` | Plain-language architecture report |
| `graphify-out/graph.html` | Interactive graph visualization (open in browser) |

### Quick Stats (from latest build)
- **406 nodes** · **819 edges** · **16 communities**
- **Core abstractions** (God Nodes): `CdeDataUpdateCoordinator`, `CdeApiClient`, `CdeAuthError`, `CdeBillingData`, `CdeRateData`, `CdeConnectionError`, `CdeUsageRecord`
- **Communities**: `CdeApiClient & API Tests`, `Coordinator & Sensor Entities`, `Integration Lifecycle & Constants`, `GWT-RPC Protocol & Date Parsing`, `Billing, Usage & Coordinator Tests`, `Exceptions & Config Flow Tests`, `Config & Options Flow`, `Rate Scraping & Parsing`, `Sensor & Cost Tests`, `Integration Manifest`, `Validate Workflow (CI)`, `Release Workflow (CD)`

### Explore the Graph

```bash
# Install graphify
pip install graphifyy

# Open interactive HTML
open graphify-out/graph.html

# Query the graph from CLI
graphify query "How does CdeDataUpdateCoordinator fetch billing data?"

# Trace a path between components
graphify path "CdeDataUpdateCoordinator" "CdeApiClient"

# Explain a component
graphify explain "CdeApiClient"
```

### Regenerate After Changes

```bash
# Full rebuild (after major changes)
graphify . --code-only

# Incremental update (after code edits - no LLM cost)
graphify update . --code-only

# Re-cluster only (rename communities)
graphify cluster-only .
```

---

## Local Development & Testing

Clone the repository and run the test suite:
```bash
git clone https://github.com/ahardy11397/ha-cde-lightband.git
cd ha-cde-lightband
uv run --no-project --with aiohttp --with pytest --with pytest-asyncio --with pytest-homeassistant-custom-component pytest -v
```
