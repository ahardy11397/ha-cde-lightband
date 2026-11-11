# CDE Lightband Home Assistant Custom Integration

[![CI](https://img.shields.io/badge/home--assistant-custom--component-blue.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A native custom integration for [Home Assistant](https://www.home-assistant.io/) connecting to **CDE Lightband** (Clarksville Department of Electricity, Clarksville, TN) to ingest both utility billing information and smart meter electric consumption data.

---

## Features

### 1. Billing Sensors
Automatically exposes account billing details as native Home Assistant entities:
* `sensor.cde_balance_due`: Current total amount owed (`USD`), with attributes for account number, service address, and past due status.
* `sensor.cde_payment_due_date`: Upcoming statement due date (`date`).
* `sensor.cde_last_payment_amount`: Most recent payment amount (`USD`) and payment date.
* `sensor.cde_last_bill_amount`: Total of the most recent billing statement.

### 2. Home Assistant Energy Dashboard Integration
* Tracks daily electric consumption via `sensor.cde_daily_energy_consumption` (`kWh`).
* Seamlessly injects smart meter interval readings directly into Home Assistant's long-term statistics database (`recorder`) via `async_add_external_statistics` (`cde_lightband:electric_consumption_<account_number>`).
* Add CDE Lightband as an **Electricity Grid** source under **Settings > Dashboards > Energy**.
* Automatically backfills historical smart meter readings on setup.

### 3. Estimated Bill Sensor
* `sensor.cde_estimated_bill`: Running estimate of the current calendar month's electric bill (`USD`), computed as month-to-date kWh × the published energy rate, plus the customer charge and tiered grid access charge.
* If you also subscribe to CDE Lightband internet, pick your plan (300 Mbps / 600 Mbps / 1 Gig / 2.5 Gig) under **Configure > Options** and its monthly price is added to the estimate.
* Rates are scraped live from CDE's [Rates & Fees](https://cdelightband.com/residential/energy/rates-fees/) page on every update, so rate changes are picked up automatically; if the page is temporarily unavailable the last-known rates are used.
* Shows `unknown` until rates have been fetched and the first usage day of the current month has landed.
* Covers CDE's published charges only — it does not include taxes or TVA fuel-cost adjustments, so it will run slightly below the actual bill.
* Attributes show exactly how the estimate was built: `month_to_date_kwh`, `energy_rate`, `customer_charge`, `grid_access_charge`, `internet_plan`, `internet_price`, `rate_month`, and `rates_fetched`.

### 4. Native UI Configuration (Config Flow)
* Easily configured via **Settings > Devices & Services > Add Integration**.
* Securely manages authentication against the CDE Lightband customer portal (`myaccount.clarksvillede.com`).
* Automatically detects your account number and binds to a single device in the Home Assistant Device Registry.
* Configurable update intervals and history backfill windows via the **Options Flow**.

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
5. Click **Submit**. Home Assistant will authenticate with CDE Lightband, detect your account, and register all billing and energy sensors!

### 2. Adding to the Energy Dashboard
1. Go to **Settings > Dashboards > Energy**.
2. Under **Electricity Grid**, click **Add Consumption**.
3. Select **CDE Lightband Electric Usage**.
4. Save your changes.

---

## Architecture & Technical Details

* **Backend Portal**: Daffron & Associates / Milsoft eBusiness (eBiz).
* **Protocol**: Google Web Toolkit Remote Procedure Call (GWT-RPC).
* **Endpoint**: `https://myaccount.clarksvillede.com/ebusiness/ebiz`
* **Permutation**: `64365524BBB2AFDF21B13502E153DBD9`
* **Policy ID**: `9B0246073475961F003BC947C4A4B6CF`

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
- **262 nodes** · **493 edges** · **13 communities**
- **Core abstractions** (God Nodes): `CdeDataUpdateCoordinator`, `CdeApiClient`, `CdeConnectionError`, `CdeUsageRecord`, `CdeBillingData`
- **Communities**: `CdeApiClient` (API & auth), `CdeDataUpdateCoordinator` (coordinator & sensors), `gwt_rpc.py` (GWT protocol), `CdeUsageRecord` (usage & tests), `test_config_flow.py`, `steps` (GitHub Actions), `manifest.json`, `async_setup_entry` (lifecycle)

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
uv run pytest
```
