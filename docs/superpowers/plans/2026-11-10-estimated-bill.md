# Estimated Bill Sensor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sensor.<prefix>_estimated_bill` sensor that combines month-to-date kWh from the existing Charts API with rates scraped live from CDE's public rates page, plus an optional CDE internet plan charge selected in the options flow.

**Architecture:** Rate scraping lives in `cde_api.py` as pure regex parsers over the two public web pages plus two fail-soft client fetch methods (no new dependencies — no HTML parser is installed). The coordinator fetches rates on each poll inside a never-raising wrapper, caches last-known-good values, and stows the merged `CdeRateData` under a new `"rates"` key. The sensor stays thin like the existing ones: it reads coordinator data and does only the arithmetic.

**Tech Stack:** Python 3, Home Assistant custom integration, aiohttp (existing session), stdlib `re`/`html` for parsing, `pytest-homeassistant-custom-component` for tests.

**Spec:** `docs/superpowers/specs/2026-11-10-estimated-bill-design.md`

## Global Constraints

- No new pip dependencies. Parsing uses only stdlib `re` and `html.unescape` (`manifest.json` `requirements` stays `[]`).
- Residential rate schedule (RS) only; commercial tables are ignored by the parser.
- Fail-soft contract: `fetch_rates()` and `fetch_internet_prices()` never raise — every failure path logs a warning and returns `None`. Rates failures must never fail the coordinator update or affect the other five sensors.
- All published money values are rounded to 2 decimals; `energy_rate` keeps its 5-decimal precision (e.g. `0.11010`).
- Internet option values are exactly the strings `"none"`, `"300"`, `"600"`, `"1000"`, `"2500"`.
- Sensor entity suffix: `estimated_bill`; friendly name: `Estimated bill`.
- Month-to-date means the current calendar month (UTC), matched by the first 7 chars of each record's `timestamp`.

## Review Focus

- Rates-page markup changes (CDE redesigns the table) → `parse_rates_html` returns `None`, estimate keeps last-known rates. Pinned by `test_parse_rates_html_garbage_returns_none` (Task 1).
- Grid-tier boundaries: exactly 1,000 kWh → $2.00, 1,001 → $4.00, 2,001 → $7.00. Pinned by `test_grid_access_charge_tiers` (Task 1).
- Month start with no current-month usage → sensor shows `unknown`, never a fixed-charges-only number that could be mistaken for a real bill. Pinned by `test_estimated_bill_unknown_at_month_start` (Task 5).
- Internet plan selected but its price never fetched → `unknown`, never an understated total silently missing the internet charge. Pinned by `test_estimated_bill_unknown_when_internet_price_missing` (Task 5).
- Scrape failure must not fail the coordinator update or take other sensors offline. Pinned by `test_rates_fetch_failure_does_not_fail_update` (Task 4).

---

### Task 1: Rate data model and HTML parsers

**Files:**
- Modify: `custom_components/cde_lightband/cde_api.py` (add after the `CdeUsageRecord` dataclass, ~line 74)
- Create: `tests/fixtures/rates_page.html`, `tests/fixtures/internet_page.html`
- Test: `tests/test_rates_parser.py`

**Interfaces:**
- Consumes: nothing new (stdlib `re`, `html`, `dataclasses`).
- Produces (used by Tasks 2, 4, 5):
  - `@dataclass CdeRateData` with fields `energy_rate: float`, `customer_charge: float`, `grid_access_tiers: list[tuple[float | None, float]]`, `rate_month: str`, `internet_prices: dict[str, float] = field(default_factory=dict)`, `fetched_at: str | None = None`, and method `grid_access_charge(self, kwh: float) -> float`.
  - `parse_rates_html(html: str) -> CdeRateData | None` (module-level function)
  - `parse_internet_prices_html(html: str) -> dict[str, float] | None` (module-level function)

- [ ] **Step 1: Create the test fixtures**

Create `tests/fixtures/`. For `rates_page.html`, snapshot the live Residential table (trim from the `<h2 id="residential"` heading through the first `</figure>` after it):

```bash
mkdir -p tests/fixtures
python3 - <<'EOF'
import urllib.request
html = urllib.request.urlopen(
    "https://cdelightband.com/residential/energy/rates-fees/"
).read().decode()
start = html.find('<h2 id="residential"')
end = html.find('</figure>', start) + len('</figure>')
open("tests/fixtures/rates_page.html", "w", encoding="utf-8").write(html[start:end])
EOF
grep -c "RS (122)" tests/fixtures/rates_page.html
```

Expected: `1`. The fixture must contain cells with `data-mtr-content` attributes: the header `November 2026 Retail Rate`, rows `RS (122)/Customer/$30.50`, `All kWh/Energy/$0.11010 / kWh`, and three Grid Access Charge rows (`0 – 1,000 kWh` → $2.00, `1,001 – 2,000 kWh` → $4.00, `2,000 kWh` → $7.00, en dash U+2013 in the ranges).

For `tests/fixtures/internet_page.html`, write this faithful-structure excerpt verbatim (real page: each price is `$<dollars></h2>` followed by an `.<cents>/month</h2>`, preceded by a speed `<h2>`; Gig tiers carry the suffix inside the h2, Mbps tiers are bare numbers followed by a `<p>Mpbs</p>` — the site's own typo):

```html
<div class="wp-block-column">
  <h2 class="wp-block-heading" style="font-size:50px">300</h2>
  <p>Mpbs</p>
  <h2 class="wp-block-heading" style="font-size:50px">$53</h2>
  <h2 class="wp-block-heading" style="font-size:50px">.95/month</h2>
</div>
<div class="wp-block-column">
  <h2 class="wp-block-heading" style="font-size:50px">600</h2>
  <p>Mpbs</p>
  <h2 class="wp-block-heading" style="font-size:50px">$73</h2>
  <h2 class="wp-block-heading" style="font-size:50px">.95/month</h2>
</div>
<div class="wp-block-column">
  <h2 class="wp-block-heading" style="font-size:50px">1 Gig</h2>
  <p>1,000 Mbps</p>
  <h2 class="wp-block-heading" style="font-size:50px">$94</h2>
  <h2 class="wp-block-heading" style="font-size:50px">.95/month</h2>
</div>
<div class="wp-block-column">
  <h2 class="wp-block-heading" style="font-size:50px">2.5 Gig</h2>
  <p>2,500 Mbps</p>
  <h2 class="wp-block-heading" style="font-size:50px">$123</h2>
  <h2 class="wp-block-heading" style="font-size:50px">.95/month</h2>
</div>
```

- [ ] **Step 2: Write the failing tests in `tests/test_rates_parser.py`**

```python
"""Tests for parsing CDE Lightband public rate pages."""
from pathlib import Path

from custom_components.cde_lightband.cde_api import (
    CdeRateData,
    parse_internet_prices_html,
    parse_rates_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rates_html_extracts_residential_table():
    rates = parse_rates_html((FIXTURES / "rates_page.html").read_text(encoding="utf-8"))
    assert rates is not None
    assert rates.customer_charge == 30.50
    assert rates.energy_rate == 0.11010
    assert rates.grid_access_tiers == [(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)]
    assert rates.rate_month == "November 2026"


def test_parse_rates_html_garbage_returns_none():
    assert parse_rates_html("<html><body>hello</body></html>") is None
    assert parse_rates_html("") is None


def test_grid_access_charge_tiers():
    rates = CdeRateData(
        energy_rate=0.11,
        customer_charge=30.5,
        grid_access_tiers=[(1000.0, 2.0), (2000.0, 4.0), (None, 7.0)],
        rate_month="November 2026",
    )
    assert rates.grid_access_charge(500) == 2.0
    assert rates.grid_access_charge(1000) == 2.0
    assert rates.grid_access_charge(1001) == 4.0
    assert rates.grid_access_charge(2000) == 4.0
    assert rates.grid_access_charge(2001) == 7.0


def test_parse_internet_prices_html():
    prices = parse_internet_prices_html(
        (FIXTURES / "internet_page.html").read_text(encoding="utf-8")
    )
    assert prices == {"300": 53.95, "600": 73.95, "1000": 94.95, "2500": 123.95}


def test_parse_internet_prices_html_garbage_returns_none():
    assert parse_internet_prices_html("<p>no prices here</p>") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_rates_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'CdeRateData'`

- [ ] **Step 4: Implement the dataclass and parsers in `custom_components/cde_lightband/cde_api.py`**

Add imports `import html as html_lib` and `from dataclasses import dataclass, field` (extend the existing `dataclass` import). Add after `CdeUsageRecord`:

```python
@dataclass
class CdeRateData:
    """Published residential rates from the CDE Lightband website."""
    energy_rate: float
    customer_charge: float
    grid_access_tiers: list[tuple[float | None, float]]
    rate_month: str
    internet_prices: dict[str, float] = field(default_factory=dict)
    fetched_at: str | None = None

    def grid_access_charge(self, kwh: float) -> float:
        """Tiered grid access charge for a month-to-date kWh total."""
        for upper, charge in self.grid_access_tiers:
            if upper is None or kwh <= upper:
                return charge
        return self.grid_access_tiers[-1][1]
```

`parse_rates_html` algorithm (pinned — the parser keys off the table's `data-mtr-content` attributes):
1. `idx = html.find('<h2 id="residential"')`; if `-1` return `None`. Take the section from `idx` to the next `<h2 id="` after it (or end of string).
2. `cells = [html_lib.unescape(c) for c in re.findall(r'data-mtr-content="([^"]*)"', section)]`. If fewer than 9 cells (3 headers + 2 rows) or `len(cells[3:]) % 3 != 0`, return `None`.
3. `rate_month` = third header with a trailing ` Retail Rate` stripped.
4. Walk the remaining cells in chunks of 3 `(description, charge_type, amount)`. Extract the first dollar amount with `re.search(r'\$?\s*([\d,]+(?:\.\d+)?)', amount)`. Map on stripped `charge_type`: `Customer` → `customer_charge`; `Energy` → `energy_rate`; anything containing `Grid Access Charge` → a tier parsed from the description: range `^([\d,]+)\s*[–—-]\s*([\d,]+)\s*kWh` → `(float(second), charge)`; single `^([\d,]+)\s*kWh` → `(None, charge)` (open-ended top tier). Strip commas.
5. If `energy_rate` or `customer_charge` is missing or `grid_access_tiers` is empty, return `None`. Otherwise return the `CdeRateData`.

`parse_internet_prices_html` algorithm (pinned — validated against the live page: every price is a `\$<dollars></h2>` followed within 400 chars by `.<cents>\s*/\s*month`, and the nearest preceding speed heading matches `>([\d.]+)(\s*Gig)?\s*</h2>`):
1. For each `re.finditer(r'\$([0-9,]+)</h2>', html)` match: find cents with `re.search(r'\.([0-9]{2})\s*/\s*month', html[m.end():m.end() + 400])`; if absent, skip. Find all speed headings before the match with `re.findall(r'>([\d.]+)(\s*Gig)?\s*</h2>', html[:m.start()])`; if none, skip.
2. Convert the last speed heading: take group 1 as float; if group 2 (`Gig`) matched, multiply by 1000. Key = the integer as a string (`"300"`, `"600"`, `"1000"`, `"2500"`).
3. Price = `float(f"{dollars}.{cents}")` (build the float from the string so `53.95` in tests compares equal).
4. Return the dict, or `None` if empty.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_rates_parser.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures tests/test_rates_parser.py custom_components/cde_lightband/cde_api.py
git commit -m "feat: parse CDE published residential rates and internet prices"
```

### Task 2: Fail-soft client fetch methods

**Files:**
- Modify: `custom_components/cde_lightband/const.py` (add URL constants), `custom_components/cde_lightband/cde_api.py` (add methods to `CdeApiClient`)
- Test: `tests/test_cde_api.py`

**Interfaces:**
- Consumes: `parse_rates_html`, `parse_internet_prices_html` (Task 1).
- Produces (used by Task 4):
  - `CdeApiClient.fetch_rates(self) -> CdeRateData | None` — GETs the rates page, parses, stamps `fetched_at`, never raises.
  - `CdeApiClient.fetch_internet_prices(self) -> dict[str, float] | None` — GETs the internet page, parses, never raises.
  - Constants in `const.py`: `RATES_URL = "https://cdelightband.com/residential/energy/rates-fees/"`, `INTERNET_URL = "https://cdelightband.com/residential/internet/"`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_cde_api.py`, following the file's existing style)**

```python
class _FakeResponse:
    def __init__(self, status, text):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def get(self, url, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_fetch_rates_parses_published_table():
    html = (Path(__file__).parent / "fixtures" / "rates_page.html").read_text(encoding="utf-8")
    client = CdeApiClient(username="u", password="p", session=_FakeSession(_FakeResponse(200, html)))
    rates = await client.fetch_rates()
    assert rates is not None
    assert rates.energy_rate == 0.11010
    assert rates.customer_charge == 30.50
    assert rates.fetched_at is not None


@pytest.mark.asyncio
async def test_fetch_rates_http_error_returns_none():
    client = CdeApiClient(username="u", password="p", session=_FakeSession(_FakeResponse(500, "")))
    assert await client.fetch_rates() is None


@pytest.mark.asyncio
async def test_fetch_rates_connection_error_returns_none():
    client = CdeApiClient(username="u", password="p", session=_FakeSession(exc=aiohttp.ClientError("boom")))
    assert await client.fetch_rates() is None


@pytest.mark.asyncio
async def test_fetch_internet_prices_parses_published_prices():
    html = (Path(__file__).parent / "fixtures" / "internet_page.html").read_text(encoding="utf-8")
    client = CdeApiClient(username="u", password="p", session=_FakeSession(_FakeResponse(200, html)))
    prices = await client.fetch_internet_prices()
    assert prices == {"300": 53.95, "600": 73.95, "1000": 94.95, "2500": 123.95}


@pytest.mark.asyncio
async def test_fetch_internet_prices_failure_returns_none():
    client = CdeApiClient(username="u", password="p", session=_FakeSession(_FakeResponse(404, "")))
    assert await client.fetch_internet_prices() is None
```

(Add `from pathlib import Path` and `import aiohttp` to the test file imports if missing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cde_api.py -v -k fetch_rates or fetch_internet`
Expected: FAIL with `AttributeError: 'CdeApiClient' object has no attribute 'fetch_rates'`

- [ ] **Step 3: Implement the methods**

Add `RATES_URL` and `INTERNET_URL` to `const.py` (import them into `cde_api.py` with the existing relative import block). Methods follow the fail-soft contract exactly — every failure path logs a warning and returns `None`:

```python
async def fetch_rates(self) -> CdeRateData | None:
    """Fetch and parse the published residential rates from the CDE website."""
    try:
        async with self._session.get(RATES_URL) as resp:
            if resp.status != 200:
                _LOGGER.warning("CDE rates page returned HTTP %s", resp.status)
                return None
            body = await resp.text()
    except Exception as err:
        _LOGGER.warning("Could not fetch CDE rates page: %s", err)
        return None
    rates = parse_rates_html(body)
    if rates is None:
        _LOGGER.warning("Could not parse residential rates from the CDE rates page")
        return None
    rates.fetched_at = datetime.now(timezone.utc).isoformat()
    return rates
```

`fetch_internet_prices` mirrors it: GET `INTERNET_URL`, parse with `parse_internet_prices_html`, return the dict or `None` (same warning + return-None on non-200, exception, and unparseable body; no `fetched_at` stamping).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cde_api.py -v`
Expected: all PASS (existing tests too)

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/cde_api.py custom_components/cde_lightband/const.py tests/test_cde_api.py
git commit -m "feat: fail-soft fetch of published rates and internet prices"
```

### Task 3: Internet plan option in the options flow

**Files:**
- Modify: `custom_components/cde_lightband/const.py` (option constants), `custom_components/cde_lightband/config_flow.py:157-168` (options schema)
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by Tasks 4, 5): `CONF_INTERNET_PLAN = "internet_plan"`, `DEFAULT_INTERNET_PLAN = "none"`, and `INTERNET_PLAN_OPTIONS = {"none": "None", "300": "300 Mbps", "600": "600 Mbps", "1000": "1 Gig", "2500": "2.5 Gig"}` in `const.py`. The options flow stores the selected key string in `entry.options[CONF_INTERNET_PLAN]`.

- [ ] **Step 1: Write the failing test (append to `tests/test_config_flow.py`, following its existing options-flow test pattern)**

```python
@pytest.mark.asyncio
async def test_options_flow_includes_internet_plan(hass: HomeAssistant):
    """Options flow shows the internet plan dropdown and stores the choice."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert CONF_INTERNET_PLAN in result["data_schema"].schema

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: 60, CONF_HISTORY_DAYS: 30, CONF_INTERNET_PLAN: "300"},
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INTERNET_PLAN] == "300"
```

(Import `FlowResultType` from `homeassistant.data_entry_flow` and the new const names; adapt names to what the file already imports.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_flow.py -v -k internet_plan`
Expected: FAIL with `ImportError: cannot import name 'CONF_INTERNET_PLAN'`

- [ ] **Step 3: Implement**

In `const.py` add:

```python
CONF_INTERNET_PLAN = "internet_plan"
DEFAULT_INTERNET_PLAN = "none"
INTERNET_PLAN_OPTIONS = {
    "none": "None",
    "300": "300 Mbps",
    "600": "600 Mbps",
    "1000": "1 Gig",
    "2500": "2.5 Gig",
}
```

In `CdeOptionsFlowHandler.async_step_init` schema (config_flow.py), add a third `vol.Optional` entry and extend the imports from `.const`:

```python
vol.Optional(
    CONF_INTERNET_PLAN,
    default=options.get(CONF_INTERNET_PLAN, DEFAULT_INTERNET_PLAN),
): vol.In(INTERNET_PLAN_OPTIONS),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/const.py custom_components/cde_lightband/config_flow.py tests/test_config_flow.py
git commit -m "feat: internet plan dropdown in options flow"
```

### Task 4: Coordinator rate fetching and month-to-date helper

**Files:**
- Modify: `custom_components/cde_lightband/coordinator.py` (`__init__` ~line 68, `_async_update_data` ~line 98-115, new methods after `_async_sync_statistics`), `tests/test_coordinator.py` (existing success test + new tests)
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `CdeRateData`, `CdeApiClient.fetch_rates()`, `CdeApiClient.fetch_internet_prices()` (Task 2), `CONF_INTERNET_PLAN` / `DEFAULT_INTERNET_PLAN` (Task 3).
- Produces (used by Task 5):
  - `CdeDataUpdateCoordinator.rate_data` property → `CdeRateData | None` (from `self.data.get("rates")`).
  - `CdeDataUpdateCoordinator.month_to_date_kwh(self, now: datetime | None = None) -> float`.
  - Coordinator data dict gains a `"rates"` key holding `CdeRateData | None`.

- [ ] **Step 1: Update the existing success test and write the failing tests**

The existing `test_coordinator_update_success` must also patch `fetch_rates` (it is not patched today, so the new call would hit the network):

```python
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        return_value=None,
    ):
```

and assert `data["rates"] is None`.

New tests (same MockConfigEntry setup as the file's existing tests):

```python
@pytest.mark.asyncio
async def test_coordinator_stores_rates_and_internet_price(hass: HomeAssistant):
    """Successful update stores parsed rates with the selected internet price."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        options={"internet_plan": "300"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)
    mock_rates = CdeRateData(
        energy_rate=0.11010,
        customer_charge=30.50,
        grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
        rate_month="November 2026",
    )

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,  # same mock_billing as the success test
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        return_value=mock_rates,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_internet_prices",
        new_callable=AsyncMock,
        return_value={"300": 53.95},
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        data = await coordinator._async_update_data()
        assert data["rates"] is not None
        assert data["rates"].energy_rate == 0.11010
        assert data["rates"].internet_prices == {"300": 53.95}
        assert coordinator.rate_data is data["rates"]


@pytest.mark.asyncio
async def test_rates_scrape_failure_keeps_last_known_rates(hass: HomeAssistant):
    """A rates-page outage must not fail the update or lose last-known rates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)
    mock_rates = CdeRateData(
        energy_rate=0.11010,
        customer_charge=30.50,
        grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
        rate_month="November 2026",
    )

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_billing_data",
        new_callable=AsyncMock,
        return_value=mock_billing,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_usage_data",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.fetch_rates",
        new_callable=AsyncMock,
        side_effect=[mock_rates, None],
    ), patch(
        "custom_components.cde_lightband.coordinator.CdeDataUpdateCoordinator._async_sync_statistics",
        new_callable=AsyncMock,
    ):
        coordinator = CdeDataUpdateCoordinator(hass, entry)
        first = await coordinator._async_update_data()
        assert first["rates"] is mock_rates
        second = await coordinator._async_update_data()  # scrape fails this cycle
        assert second["rates"] is not None
        assert second["rates"].energy_rate == 0.11010


@pytest.mark.asyncio
async def test_rates_fetch_exception_does_not_fail_update(hass: HomeAssistant):
    """An unexpected rates exception must not raise UpdateFailed."""
    # Same patches as the previous test but fetch_rates side_effect=Exception("boom")
    # for both updates; both _async_update_data() calls must return normally and
    # the other sensors' data keys remain populated.
```

```python
@pytest.mark.asyncio
async def test_month_to_date_kwh_filters_by_calendar_month(hass: HomeAssistant):
    """Only records inside the current calendar month are summed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)
    coordinator = CdeDataUpdateCoordinator(hass, entry)
    coordinator.data = {
        "billing": None,
        "usage": [
            CdeUsageRecord(timestamp="2026-10-31T00:00:00+00:00", kwh=9.9, meter_id="M1"),
            CdeUsageRecord(timestamp="2026-11-01T00:00:00+00:00", kwh=42.8, meter_id="M1"),
            CdeUsageRecord(timestamp="2026-11-02T00:00:00+00:00", kwh=1.2, meter_id="M1"),
        ],
        "rates": None,
    }
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    assert coordinator.month_to_date_kwh(now) == 44.0
    assert coordinator.month_to_date_kwh(datetime(2026, 12, 1, tzinfo=timezone.utc)) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_coordinator.py -v`
Expected: new tests FAIL (`AttributeError: ... no attribute 'rate_data'` / no `month_to_date_kwh`); the updated success test also fails until `"rates"` is added.

- [ ] **Step 3: Implement in `coordinator.py`**

In `__init__` (after `self._account_number`):

```python
self._last_rates: CdeRateData | None = None
self._last_internet_prices: dict[str, float] = {}
```

In `_async_update_data`, after the usage fetch and before the return:

```python
plan = self.entry.options.get(CONF_INTERNET_PLAN, DEFAULT_INTERNET_PLAN)
rates = await self._async_fetch_rates(plan)
```

and change the return to `return {"billing": billing, "usage": usage_records, "rates": rates}`.

New methods:

```python
async def _async_fetch_rates(self, plan: str) -> CdeRateData | None:
    """Fetch published rates, caching last-known-good values. Never raises."""
    try:
        rates = await self.client.fetch_rates()
        if rates is not None:
            self._last_rates = rates
        if plan != DEFAULT_INTERNET_PLAN:
            prices = await self.client.fetch_internet_prices()
            if prices is not None:
                self._last_internet_prices = prices
    except Exception as err:
        _LOGGER.warning("Could not refresh CDE rates: %s", err)
    if self._last_rates is None:
        return None
    return dataclasses.replace(
        self._last_rates,
        internet_prices=dict(self._last_internet_prices) if plan != DEFAULT_INTERNET_PLAN else {},
    )

@property
def rate_data(self) -> CdeRateData | None:
    """Return the latest parsed rate data."""
    if self.data:
        return self.data.get("rates")
    return None

def month_to_date_kwh(self, now: datetime | None = None) -> float:
    """Sum usage records in the current calendar month (UTC)."""
    current = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    return sum(r.kwh for r in self.usage_records if r.timestamp[:7] == current)
```

(`dataclasses.replace` needs `import dataclasses`; `CdeRateData` and the two new const names join the existing relative imports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/cde_lightband/coordinator.py tests/test_coordinator.py
git commit -m "feat: coordinator fetches published rates with last-known-good caching"
```

### Task 5: Estimated bill sensor

**Files:**
- Modify: `custom_components/cde_lightband/const.py` (attribute keys), `custom_components/cde_lightband/sensor.py` (new class + registration), `tests/test_sensor.py` (existing test + new tests), `README.md` (document the sensor and option)
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `CdeRateData` (Task 1), coordinator `rate_data` / `month_to_date_kwh` (Task 4), `CONF_INTERNET_PLAN` / `DEFAULT_INTERNET_PLAN` (Task 3).
- Produces: entity `sensor.cde_lightband_<account>_estimated_bill`, device class `MONETARY`, unit USD, friendly name `Estimated bill`.

- [ ] **Step 1: Add attribute keys to `const.py`**

```python
ATTR_MONTH_TO_DATE_KWH = "month_to_date_kwh"
ATTR_ENERGY_RATE = "energy_rate"
ATTR_CUSTOMER_CHARGE = "customer_charge"
ATTR_GRID_ACCESS_CHARGE = "grid_access_charge"
ATTR_INTERNET_PLAN = "internet_plan"
ATTR_INTERNET_PRICE = "internet_price"
ATTR_RATE_MONTH = "rate_month"
ATTR_RATES_FETCHED = "rates_fetched"
```

- [ ] **Step 2: Update the existing sensor test and write the failing tests**

The existing `test_sensors_created_and_updated` must also patch `fetch_rates` (AsyncMock returning `None`) alongside its current patches. Append:

```python
from custom_components.cde_lightband.cde_api import CdeRateData  # extend existing import line

mock_rates = CdeRateData(
    energy_rate=0.11010,
    customer_charge=30.50,
    grid_access_tiers=[(1000.0, 2.00), (2000.0, 4.00), (None, 7.00)],
    rate_month="November 2026",
    internet_prices={"300": 53.95},
    fetched_at="2026-11-10T12:00:00+00:00",
)


async def _setup_with(entry_options=None, rates=mock_rates, usage=None):
    """Shared setup: MockConfigEntry + patched client methods. Returns (entry,)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "testuser", CONF_PASSWORD: "testpassword"},
        options=entry_options or {},
        unique_id="12345678",
    )
    entry.add_to_hass(hass)
    ...
```

The five tests (each `@pytest.mark.asyncio`, each patching `fetch_billing_data`, `fetch_usage_data`, `fetch_rates`, and `_async_sync_statistics` as the existing test does, and patching `CdeDataUpdateCoordinator.month_to_date_kwh` with `patch.object(..., return_value=42.8)` so tests don't depend on the wall clock):

1. `test_estimated_bill_sensor_computes_estimate` — entry options `{CONF_INTERNET_PLAN: "300"}`. Assert on `sensor.cde_lightband_12345678_estimated_bill`: state `91.16` (42.8 × 0.11010 → 4.71, + 30.50 + 2.00 + 53.95); device class `MONETARY`; unit `USD`; attributes: `month_to_date_kwh == 42.8`, `energy_rate == 0.11010`, `customer_charge == 30.5`, `grid_access_charge == 2.0`, `internet_price == 53.95`, `rate_month == "November 2026"`.
2. `test_estimated_bill_sensor_without_internet` — options `{}` (default "none"): state `37.21` (4.71 + 30.50 + 2.00); attribute `internet_price` absent or `None`.
3. `test_estimated_bill_unknown_before_rates_fetched` — `fetch_rates` returns `None`: state `"unknown"`.
4. `test_estimated_bill_unknown_at_month_start` — `patch.object(CdeDataUpdateCoordinator, "month_to_date_kwh", return_value=0)`: state `"unknown"` (never a fixed-charges-only number).
5. `test_estimated_bill_unknown_when_internet_price_missing` — options `{CONF_INTERNET_PLAN: "300"}` but `mock_rates.internet_prices = {}`: state `"unknown"`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sensor.py -v -k estimated_bill`
Expected: FAIL — entity `sensor.cde_lightband_12345678_estimated_bill` does not exist (state `None`)

- [ ] **Step 4: Implement in `sensor.py`**

Add to `async_setup_entry`'s entity list: `CdeEstimatedBillSensor(coordinator),`.

New class after `CdeDailyEnergySensor` (mirror `CdeBalanceDueSensor`'s monetary device-class/unit attribute pattern):

```python
class CdeEstimatedBillSensor(CdeBaseSensor):
    """Sensor for the estimated current-month electric bill (USD)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"  # same value the balance sensor publishes
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
        return round(energy_cost + rates.customer_charge + rates.grid_access_charge(kwh) + internet_price, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rates = self.coordinator.rate_data
        if not rates:
            return {}
        plan = self._plan()
        kwh = self.coordinator.month_to_date_kwh()
        attrs = {
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
```

(Extend the `.const` and `.cde_api`-derived imports as needed. `CdeRateData` itself is not imported by the sensor — it only reads attributes.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py -v`
Expected: all PASS

- [ ] **Step 6: Update `README.md`**

Add a short section for the estimated-bill sensor: what it estimates (published charges only — customer + energy + grid access + optional internet plan; no taxes/adjustments), that rates are scraped from the CDE website each update, and how to pick the internet plan in Configure → Options. Keep it to a few sentences in the style of the existing sensor documentation.

- [ ] **Step 7: Run the full suite and commit**

Run: `pytest tests/ -v`
Expected: all PASS

```bash
git add custom_components/cde_lightband/const.py custom_components/cde_lightband/sensor.py tests/test_sensor.py README.md
git commit -m "feat: estimated bill sensor from month-to-date usage and published rates"
```
