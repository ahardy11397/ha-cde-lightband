# CDE Lightband Custom Home Assistant Integration Design

**Date**: 2026-11-01  
**Project Location**: `/mnt/ssd/projects/ha-cde-lightband`  
**Target Installation**: `/homeassistant/custom_components/cde_lightband` on `root@homeassistant.local`  

---

## 1. Overview & Goals
The goal of this project is to build and deploy a native Home Assistant custom integration (`cde_lightband`) that connects to CDE Lightband (Clarksville Department of Electricity in Clarksville, TN) to ingest both utility billing information and electric energy consumption metrics directly into Home Assistant.

### Key Capabilities
1. **Billing Tracking**: Exposes current balance due, payment due date, last payment amount/date, and last statement total as Home Assistant sensors.
2. **Energy Dashboard Integration**: Ingests electric smart meter consumption data (kWh) via Home Assistant's `recorder` external statistics (`async_add_external_statistics`) for seamless use in the native HA Energy Dashboard.
3. **UI Setup (Config Flow)**: Configured securely via **Settings > Devices & Services > Add Integration** using CDE account credentials (username/email and password).
4. **Automated Polling & Synchronization**: Uses `DataUpdateCoordinator` to sync billing and usage data periodically (default: 60 minutes) without triggering rate limits.

---

## 2. Protocol & Architecture Discovery

### 2.1 Backend Platform Identification
While many electric cooperatives utilize NISC SmartHub, investigation of `myaccount.clarksvillede.com` confirmed CDE Lightband runs on **Daffron & Associates / Milsoft eBusiness (eBiz)**, an enterprise utility customer portal utilizing Google Web Toolkit (GWT).

### 2.2 Endpoint & GWT-RPC Protocol Specifications
* **Base URL**: `https://myaccount.clarksvillede.com/ebusiness/`
* **RPC Endpoint**: `https://myaccount.clarksvillede.com/ebusiness/ebiz`
* **Active Permutation**: `64365524BBB2AFDF21B13502E153DBD9`
* **Serialization Policy ID**: `9B0246073475961F003BC947C4A4B6CF`
* **Policy File**: `https://myaccount.clarksvillede.com/ebusiness/9B0246073475961F003BC947C4A4B6CF.gwt.rpc`
* **Service Interface**: `com.daffron.ebiz.client.EBizService`

### 2.3 Verified RPC Call Signatures
* `getInitialData()`: Initializes cookie session and baseline portal metadata.
* `signIn(username: String, password: String, resolution: String)`:
  * Headers:
    * `Content-Type: text/x-gwt-rpc; charset=utf-8`
    * `X-GWT-Permutation: 64365524BBB2AFDF21B13502E153DBD9`
    * `X-GWT-Module-Base: https://myaccount.clarksvillede.com/ebusiness/`
  * Payload format:
    `7|0|8|https://myaccount.clarksvillede.com/ebusiness/|9B0246073475961F003BC947C4A4B6CF|com.daffron.ebiz.client.EBizService|signIn|java.lang.String/2004016611|<user>|<pass>|[1920,1080]|1|2|3|4|3|5|5|5|6|7|8|`
  * Response: Returns `SignedInToken` on success, or `SignInException/3923402574` on invalid credentials.
* `getJsonData(data: JsonData)`:
  * Executes service bus operations.
  * `Landing` with action `LoadBilling`: Returns account balances, due dates, past due amounts, and last payment dates.
  * `Charts` with action `usage` or `table`: Returns smart meter interval readings (kWh) and timestamps.
  * `AccountBillingHistory` with action `table`: Returns past bill history.
* `signOut()`: Terminates the remote session cleanly.

---

## 3. Component Architecture & Directory Layout

The custom integration will reside in:
`custom_components/cde_lightband/`

```
custom_components/cde_lightband/
├── __init__.py           # Integration entry point, setup/unload entry logic
├── manifest.json         # Integration manifest (domain, dependencies, version)
├── const.py              # Constants, configuration keys, API URLs, defaults
├── cde_api.py            # Async Python client implementing Daffron eBiz GWT-RPC
├── config_flow.py        # UI configuration and options flow handler
├── coordinator.py        # DataUpdateCoordinator & external statistics ingestion
├── sensor.py             # Billing and energy sensor entity implementations
├── strings.json          # Translation strings and error definitions
└── translations/
    └── en.json           # English localization
```

---

## 4. Entity & Data Model Specifications

### 4.1 Device Representation
* **Device Name**: `CDE Lightband (<Account Number>)`
* **Manufacturer**: `CDE Lightband`
* **Model**: `Power & Broadband`
* **Identifiers**: `{(DOMAIN, account_number)}`
* **Entry Type**: `service`

### 4.2 Billing Sensors
| Entity ID | Device Class | Unit | State Value | Attributes |
|---|---|---|---|---|
| `sensor.cde_balance_due` | `monetary` | `USD` | Current balance owed | `account_number`, `service_address`, `is_past_due`, `past_due_amount` |
| `sensor.cde_payment_due_date` | `date` | None | Due date (YYYY-MM-DD) | `days_until_due` |
| `sensor.cde_last_payment_amount` | `monetary` | `USD` | Last payment amount | `last_payment_date` |
| `sensor.cde_last_bill_amount` | `monetary` | `USD` | Total of most recent bill | `bill_date` |

### 4.3 Energy Dashboard & Consumption Sensors
| Entity ID | Device Class | State Class | Unit | Purpose |
|---|---|---|---|---|
| `sensor.cde_daily_energy_consumption` | `energy` | `total_increasing` | `kWh` | Daily energy tracking sensor |

#### Long-Term Statistics Ingestion
* **Statistic ID**: `cde_lightband:electric_consumption_<account_number>`
* **Metadata**:
  * `source`: `cde_lightband`
  * `unit_of_measurement`: `kWh`
  * `has_sum`: `True`
  * `has_mean`: `False`
* **Ingestion Method**: `async_add_external_statistics`
* **Behavior**:
  * On initial setup: Backfills up to 30 days of daily/hourly consumption data.
  * On recurring updates: Ingests new interval usage data reported by CDE's smart meter.

---

## 5. Configuration Flow & Options Flow

### 5.1 Config Flow
* Step `user`:
  * Inputs: `username` (string), `password` (string).
  * Validation: Connects to CDE Lightband and calls `signIn`.
  * Errors: `invalid_auth`, `cannot_connect`, `unknown`.
  * Unique ID: Set to the CDE Account Number to prevent duplicate configurations.

### 5.2 Options Flow
* Configurable parameters:
  * `update_interval`: Polling frequency in minutes (default: 60, min: 15, max: 1440).
  * `history_days`: Days of usage history to backfill on setup (default: 30, max: 90).

---

## 6. Error Handling & Edge Cases
1. **Session Expiry**: If a request fails with an authentication error or invalid token, the client automatically clears cookies and re-authenticates.
2. **Maintenance / Portal Downtime**: Connection timeouts raise `UpdateFailed` in the coordinator, maintaining existing state and retrying on the next poll.
3. **Missing Usage Data**: CDE smart meter data typically lags real-time by a few hours to a day. The coordinator verifies timestamps before appending new records to prevent duplicate or out-of-order statistics.
4. **Service Types**: CDE accounts combine Electric and Broadband services on a single bill. The billing sensors represent the unified account bill, while usage sensors specifically isolate the electric meter.

---

## 7. Deployment & Verification Plan
1. Local git repository initialized at `/mnt/ssd/projects/ha-cde-lightband`.
2. Unit and API tests written and verified with pytest.
3. Deployment over SSH to `root@homeassistant.local:/homeassistant/custom_components/cde_lightband`.
4. Run `ha core check` to validate Home Assistant configuration schema.
5. Restart Home Assistant core (`ha core restart`).
6. Inspect `home-assistant.log` to confirm error-free component registration.
