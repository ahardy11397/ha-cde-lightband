# CDE Lightband Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a Home Assistant custom integration (`cde_lightband`) connecting to CDE Lightband's Daffron eBiz portal (`myaccount.clarksvillede.com`) to expose billing sensors and electric energy statistics for the Home Assistant Energy Dashboard.

**Architecture:** An asynchronous Python API client (`cde_api.py`) talks to CDE Lightband's Daffron eBiz GWT-RPC servlet to authenticate and fetch billing and usage data. Home Assistant's `DataUpdateCoordinator` periodically syncs this data to billing sensor entities (`sensor.py`) and injects smart meter interval data into the Home Assistant `recorder` long-term statistics database via `async_add_external_statistics`. Setup is managed via a UI Config Flow (`config_flow.py`).

**Tech Stack:** Python 3.12+, Home Assistant Core (2026.10+), `aiohttp`, `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`.

**Spec:** `/mnt/ssd/projects/ha-cde-lightband/docs/superpowers/specs/2026-11-01-cde-lightband-integration-design.md`

## Global Constraints
- Domain: `cde_lightband`
- Host Base URL: `https://myaccount.clarksvillede.com/ebusiness/`
- RPC URL: `https://myaccount.clarksvillede.com/ebusiness/ebiz`
- Permutation: `64365524BBB2AFDF21B13502E153DBD9`
- Policy ID: `9B0246073475961F003BC947C4A4B6CF`
- Target HA Directory: `/homeassistant/custom_components/cde_lightband` on `root@homeassistant.local`

## Review Focus
- Invalid credentials: User enters incorrect password; config flow and API client must raise `CdeAuthError` with human-readable UI error `invalid_auth` without crashing.
- Session expiration: When an authenticated session cookie expires after inactivity, client must detect the session timeout and automatically re-authenticate once before failing.
- Network outage / CDE portal downtime: Network error or HTTP 500 must raise `CdeConnectionError`, causing the coordinator to raise `UpdateFailed` while retaining previous state values.
- Empty usage intervals: During meter maintenance or billing cutover where usage array is empty, sensor must report latest available reading without IndexError.
- Multi-service billing format: Broadband and electric charges on CDE bills are combined; billing sensors must extract the total balance due and due date accurately from the `Landing/LoadBilling` payload.

---

### Task 1: Project Setup & Test Scaffolding

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/pyproject.toml`
- Create: `/mnt/ssd/projects/ha-cde-lightband/tests/conftest.py`
- Create: `/mnt/ssd/projects/ha-cde-lightband/tests/test_scaffolding.py`

**Interfaces:**
- Produces: Test runner environment with pytest and asyncio fixtures.

- [ ] **Step 1: Write test verifying test environment**

```python
# tests/test_scaffolding.py
def test_environment_loads():
    assert True
```

- [ ] **Step 2: Run test to verify pytest works**

Run: `pytest tests/test_scaffolding.py`  
Expected: PASS

- [ ] **Step 3: Create pyproject.toml with test dependencies**

Define dependencies: `aiohttp`, `pytest`, `pytest-asyncio`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: setup test environment and scaffolding"
```

---

### Task 2: Daffron eBiz GWT-RPC Protocol Serializer

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/gwt_rpc.py`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_gwt_rpc.py`

**Interfaces:**
- Produces: `build_gwt_payload(service: str, method: str, param_types: list[str], param_values: list[str]) -> str`
- Produces: `parse_gwt_response(raw_text: str) -> dict`

- [ ] **Step 1: Write failing test for GWT-RPC serializer & response parser**

```python
# tests/test_gwt_rpc.py
from custom_components.cde_lightband.gwt_rpc import build_gwt_payload, parse_gwt_response

def test_build_gwt_payload_structure():
    payload = build_gwt_payload(
        service="com.daffron.ebiz.client.EBizService",
        method="signIn",
        param_types=["java.lang.String/2004016611", "java.lang.String/2004016611", "java.lang.String/2004016611"],
        param_values=["testuser", "testpass", "[1920,1080]"]
    )
    assert payload.startswith("7|0|8|")
    assert "com.daffron.ebiz.client.EBizService" in payload
    assert "signIn" in payload
    assert payload.endswith("|1|2|3|4|3|5|5|5|6|7|8|")

def test_parse_gwt_ok_response():
    resp = '//OK[0,2,1,["res1","res2"],0,7]'
    data = parse_gwt_response(resp)
    assert data["status"] == "OK"
    assert data["values"] == ["res1", "res2"]

def test_parse_gwt_ex_response():
    resp = '//EX[0,0,0,9,1,["com.daffron.shared.client.SignInException/3923402574"],0,7]'
    data = parse_gwt_response(resp)
    assert data["status"] == "EX"
    assert "SignInException" in data["exception"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gwt_rpc.py`  
Expected: FAIL with ModuleNotFoundError or ImportError

- [ ] **Step 3: Implement GWT-RPC serializer and parser in `custom_components/cde_lightband/gwt_rpc.py`**

Implement payload builder conforming to GWT RPC version 7 specifications and response decoder.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gwt_rpc.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/gwt_rpc.py tests/test_gwt_rpc.py
git commit -m "feat: implement GWT-RPC serializer and parser"
```

---

### Task 3: CDE Lightband API Client

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/cde_api.py`
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/exceptions.py`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_cde_api.py`

**Interfaces:**
- Consumes: `build_gwt_payload`, `parse_gwt_response` from `gwt_rpc.py`
- Produces: `class CdeApiClient`:
  - `async def authenticate() -> bool`
  - `async def fetch_billing_data() -> CdeBillingData`
  - `async def fetch_usage_data(days: int = 30) -> list[CdeUsageRecord]`
- Produces: `CdeAuthError`, `CdeConnectionError`, `CdeDataError`

- [ ] **Step 1: Write failing test for CdeApiClient with mocked aiohttp session**

```python
# tests/test_cde_api.py
import pytest
from unittest.mock import AsyncMock, patch
from custom_components.cde_lightband.cde_api import CdeApiClient
from custom_components.cde_lightband.exceptions import CdeAuthError

@pytest.mark.asyncio
async def test_auth_failure_raises_cde_auth_error():
    client = CdeApiClient(username="baduser", password="badpassword")
    with patch.object(client, "_post_rpc", return_value={"status": "EX", "exception": "SignInException/3923402574"}):
        with pytest.raises(CdeAuthError):
            await client.authenticate()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cde_api.py`  
Expected: FAIL with missing classes

- [ ] **Step 3: Implement `exceptions.py` and `CdeApiClient` in `cde_api.py`**

Implement session setup (`getInitialData`), authentication (`signIn`), billing retrieval (`Landing/LoadBilling`), and usage interval retrieval (`Charts/usage`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cde_api.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/cde_api.py custom_components/cde_lightband/exceptions.py tests/test_cde_api.py
git commit -m "feat: implement CdeApiClient with authentication and data methods"
```

---

### Task 4: Integration Manifest, Constants, and Translations

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/manifest.json`
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/const.py`
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/strings.json`
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/translations/en.json`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_manifest.py`

**Interfaces:**
- Produces: Standard Home Assistant integration metadata and constants.

- [ ] **Step 1: Write test verifying manifest and translation schemas**

```python
# tests/test_manifest.py
import json

def test_manifest_valid():
    with open("custom_components/cde_lightband/manifest.json") as f:
        data = json.load(f)
    assert data["domain"] == "cde_lightband"
    assert data["config_flow"] is True
    assert "version" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_manifest.py`  
Expected: FAIL with FileNotFoundError

- [ ] **Step 3: Create manifest.json, const.py, strings.json, and translations/en.json**

Fill with CDE Lightband constants, documentation URL, and English string templates.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_manifest.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/manifest.json custom_components/cde_lightband/const.py custom_components/cde_lightband/strings.json custom_components/cde_lightband/translations/ tests/test_manifest.py
git commit -m "feat: add manifest, constants, and localization"
```

---

### Task 5: Config Flow & Options Flow

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/config_flow.py`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_config_flow.py`

**Interfaces:**
- Consumes: `CdeApiClient`, `CdeAuthError`, `CdeConnectionError`
- Produces: `CdeConfigFlow(config_entries.ConfigFlow)`
- Produces: `CdeOptionsFlowHandler(config_entries.OptionsFlow)`

- [ ] **Step 1: Write failing test for config flow user step**

```python
# tests/test_config_flow.py
from unittest.mock import AsyncMock, patch
from custom_components.cde_lightband.config_flow import CdeConfigFlow
from custom_components.cde_lightband.exceptions import CdeAuthError

# Test auth failure shows invalid_auth, test success creates entry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_flow.py`  
Expected: FAIL

- [ ] **Step 3: Implement ConfigFlow and OptionsFlow in `config_flow.py`**

Implement schema with `CONF_USERNAME` and `CONF_PASSWORD`, unique ID binding via account number, and options flow for polling interval.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config_flow.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/config_flow.py tests/test_config_flow.py
git commit -m "feat: implement UI config flow and options flow"
```

---

### Task 6: Data Update Coordinator & Statistics Synchronization

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/coordinator.py`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_coordinator.py`

**Interfaces:**
- Consumes: `CdeApiClient`
- Produces: `CdeDataUpdateCoordinator(DataUpdateCoordinator)`:
  - `async def _async_update_data() -> dict`
  - `async def _async_sync_statistics(records: list[CdeUsageRecord]) -> None`

- [ ] **Step 1: Write failing test for coordinator update and stats ingestion**

```python
# tests/test_coordinator.py
# Verify coordinator aggregates billing + usage and calls recorder statistics
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coordinator.py`  
Expected: FAIL

- [ ] **Step 3: Implement coordinator in `coordinator.py`**

Implement 60-minute interval polling, error conversion to `UpdateFailed`, and external statistics injection using `async_add_external_statistics`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_coordinator.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/coordinator.py tests/test_coordinator.py
git commit -m "feat: implement coordinator with long-term statistics sync"
```

---

### Task 7: Sensor Entities & Component Lifecycle

**Files:**
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/sensor.py`
- Create: `/mnt/ssd/projects/ha-cde-lightband/custom_components/cde_lightband/__init__.py`
- Test: `/mnt/ssd/projects/ha-cde-lightband/tests/test_sensor.py`

**Interfaces:**
- Consumes: `CdeDataUpdateCoordinator`
- Produces: `async_setup_entry`, `async_unload_entry` in `__init__.py`
- Produces: `CdeBillingSensor`, `CdeEnergySensor` in `sensor.py`

- [ ] **Step 1: Write failing test for sensor entity definitions and properties**

```python
# tests/test_sensor.py
# Check device class, native units, state values, and device_info
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sensor.py`  
Expected: FAIL

- [ ] **Step 3: Implement sensor entities in `sensor.py` and lifecycle hooks in `__init__.py`**

Define `sensor.cde_balance_due`, `sensor.cde_payment_due_date`, `sensor.cde_last_payment_amount`, `sensor.cde_last_bill_amount`, and `sensor.cde_daily_energy_consumption`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sensor.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/sensor.py custom_components/cde_lightband/__init__.py tests/test_sensor.py
git commit -m "feat: implement sensor entities and integration lifecycle"
```

---

### Task 8: Server Deployment & Home Assistant Verification

**Files:**
- Deploy to: `root@homeassistant.local:/homeassistant/custom_components/cde_lightband/`

**Interfaces:**
- Consumes: All completed component files
- Produces: Running, active CDE Lightband integration ready for UI pairing on Home Assistant.

- [ ] **Step 1: Deploy files to Home Assistant server via rsync/scp**

```bash
scp -r custom_components/cde_lightband root@homeassistant.local:/homeassistant/custom_components/
```

- [ ] **Step 2: Run Home Assistant configuration check**

```bash
ssh root@homeassistant.local "ha core check"
```
Expected: `Command completed successfully`

- [ ] **Step 3: Restart Home Assistant core**

```bash
ssh root@homeassistant.local "ha core restart"
```
Expected: Core restarts cleanly

- [ ] **Step 4: Verify Home Assistant core logs**

```bash
ssh root@homeassistant.local "ha core logs | grep -i cde_lightband"
```
Expected: Component registered successfully without syntax or dependency errors.

- [ ] **Step 5: Commit deployment verification documentation**

```bash
git add README.md
git commit -m "docs: add installation and configuration guide"
```
