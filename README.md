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

### 3. Native UI Configuration (Config Flow)
* Easily configured via **Settings > Devices & Services > Add Integration**.
* Securely manages authentication against the CDE Lightband customer portal (`myaccount.clarksvillede.com`).
* Automatically detects your account number and binds to a single device in the Home Assistant Device Registry.
* Configurable update intervals and history backfill windows via the **Options Flow**.

---

## Installation & Setup

### 1. Verification of Server Installation
The integration has been installed directly onto your Home Assistant server at:
`/homeassistant/custom_components/cde_lightband`

### 2. Pairing in the Home Assistant UI
1. In Home Assistant, navigate to **Settings > Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **CDE Lightband**.
4. Enter your login credentials for `myaccount.clarksvillede.com`:
   * **Username / Email**
   * **Password**
5. Click **Submit**. Home Assistant will authenticate with CDE Lightband, detect your account, and register all billing and energy sensors!

### 3. Adding to the Energy Dashboard
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

## Local Development & Testing

Run tests in the project repository:
```bash
cd /mnt/ssd/projects/ha-cde-lightband
source .venv/bin/activate
pytest
```
