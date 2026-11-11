"""API Client for CDE Lightband (Daffron eBusiness GWT-RPC)."""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import aiohttp

from .exceptions import CdeAuthError, CdeConnectionError, CdeDataError
from .const import INTERNET_URL, RATES_URL
from .gwt_rpc import (
    CDE_MODULE_BASE,
    CDE_PERMUTATION,
    CDE_POLICY_ID,
    CDE_RPC_ENDPOINT,
    CDE_SERVICE_INTERFACE,
    GWT_STRING_TYPE,
    build_gwt_json_data_payload,
    build_gwt_payload,
    parse_gwt_response,
)

_LOGGER = logging.getLogger(__name__)


def _parse_date(date_str: str | None) -> str | None:
    """Parse common CDE date strings into ISO YYYY-MM-DD."""
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return date_str.strip()


def _parse_timestamp(date_str: str | None) -> str:
    """Parse date string into UTC ISO timestamp."""
    if date_str:
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CdeBillingData:
    """Billing metrics from CDE Lightband."""
    account_number: str
    balance_due: float
    due_date: str | None = None
    is_past_due: bool = False
    past_due_amount: float = 0.0
    last_payment_amount: float = 0.0
    last_payment_date: str | None = None
    last_bill_amount: float = 0.0
    last_bill_date: str | None = None
    service_address: str = ""


@dataclass
class CdeUsageRecord:
    """Historical or daily electric interval usage record."""
    timestamp: str
    kwh: float
    meter_id: str = ""
    reading_date: str | None = None


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


def parse_rates_html(html: str) -> CdeRateData | None:
    """Parse the published Residential rate table from the CDE rates page.

    The page renders the Residential table between the ``<h2 id="residential">``
    heading and the next section heading. Each cell's text lives inside a
    ``<div class="mtr-cell-content">`` element (the ``data-mtr-content``
    attributes only repeat the column header names), so rows are read from
    those divs. Fails soft (returns ``None``) whenever the expected structure
    is not found.
    """
    idx = html.find('<h2 id="residential"')
    if idx == -1:
        return None
    section = html[idx:]
    next_h2 = section.find('<h2 id="', len('<h2 id="residential"'))
    if next_h2 != -1:
        section = section[:next_h2]

    def _cell_texts(row_html: str) -> list[str]:
        texts = []
        for m in re.finditer(r'<div class="mtr-cell-content">(.*?)</div>', row_html, re.S):
            text = re.sub(r"<[^>]+>", "", m.group(1))
            texts.append(re.sub(r"\s+", " ", html_lib.unescape(text)).strip())
        return texts

    rows = [_cell_texts(r) for r in re.findall(r"<tr>(.*?)</tr>", section, re.S)]
    rows = [r for r in rows if len(r) == 3]

    # The header row is the first one whose third cell ends in "Retail Rate";
    # ignore any stray 3-cell rows (e.g. other tables) above it.
    header_idx = next(
        (i for i, r in enumerate(rows) if re.search(r"Retail Rate\s*$", r[2])),
        None,
    )
    if header_idx is None:
        return None

    rate_month = re.sub(r"\s*Retail Rate\s*$", "", rows[header_idx][2].strip())
    customer_charge: float | None = None
    energy_rate: float | None = None
    tiers: list[tuple[float | None, float]] = []

    for desc, ctype, amount in rows[header_idx + 1:]:
        m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", amount)
        if not m:
            continue
        value = float(m.group(1).replace(",", ""))
        label = ctype.strip()
        if label == "Customer":
            customer_charge = value
        elif label == "Energy":
            energy_rate = value
        elif "Grid Access Charge" in label:
            range_m = re.match(r"([\d,]+)\s*[–—-]\s*([\d,]+)\s*kWh", desc.strip())
            if range_m:
                tiers.append((float(range_m.group(2).replace(",", "")), value))
            else:
                single_m = re.match(r"([\d,]+)\s*kWh", desc.strip())
                if single_m:
                    tiers.append((None, value))

    if energy_rate is None or customer_charge is None or not tiers:
        return None
    return CdeRateData(
        energy_rate=energy_rate,
        customer_charge=customer_charge,
        grid_access_tiers=tiers,
        rate_month=rate_month,
    )


def parse_internet_prices_html(html: str) -> dict[str, float] | None:
    """Parse residential internet plan prices from the CDE internet page.

    Every plan renders its price as ``$<dollars></h2>`` followed within a
    few hundred characters by ``.<cents>/month</h2>``, preceded by a speed
    heading (``300``/``600`` Mbps as bare numbers, ``1 Gig``/``2.5 Gig``
    with a suffix inside the heading). Returns ``None`` when nothing
    parseable is found.
    """
    prices: dict[str, float] = {}
    for m in re.finditer(r"\$([0-9,]+)</h2>", html):
        cents_m = re.search(r"\.([0-9]{2})\s*/\s*month", html[m.end():m.end() + 400])
        if not cents_m:
            continue
        speed_matches = re.findall(r">([\d.]+)(\s*Gig)?\s*</h2>", html[:m.start()])
        if not speed_matches:
            continue
        speed_str, gig_suffix = speed_matches[-1]
        speed = float(speed_str)
        if gig_suffix:
            speed *= 1000
        prices[str(int(speed))] = float(f"{int(m.group(1).replace(',', ''))}.{cents_m.group(1)}")
    return prices or None


class CdeApiClient:
    """Asynchronous client connecting to CDE Lightband portal via GWT-RPC.

    The caller is responsible for providing and managing the aiohttp.ClientSession lifecycle.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self.username = username
        self.password = password
        self._session = session
        self._is_authenticated = False
        self._token: str | None = None

        # Discovered account parameters
        self._account_number: str | None = None
        self._sub_account: str = ""
        self._msserv: str = "1"
        self._rsp: str = "     "
        self._meter_id: str = ""
        self._service_address: str = ""
        self._total_due: float = 0.0

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @property
    def account_number(self) -> str | None:
        return self._account_number

    @property
    def meter_id(self) -> str:
        return self._meter_id

    @property
    def service_address(self) -> str:
        return self._service_address

    async def close(self) -> None:
        """No-op: session lifecycle is managed by the caller."""

    async def _post_gwt(self, payload: str) -> dict[str, Any]:
        """Low-level POST of raw GWT payload to CDE GWT RPC servlet."""
        headers = {
            "Content-Type": "text/x-gwt-rpc; charset=utf-8",
            "X-GWT-Permutation": CDE_PERMUTATION,
            "X-GWT-Module-Base": CDE_MODULE_BASE,
            "User-Agent": "HomeAssistant-CdeLightband",
        }

        try:
            async with self._session.post(
                CDE_RPC_ENDPOINT,
                data=payload.encode("utf-8"),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise CdeConnectionError(f"HTTP error {response.status} from CDE portal")
                return parse_gwt_response(text)
        except CdeConnectionError:
            raise
        except Exception as err:
            raise CdeConnectionError(f"Connection failure communicating with CDE portal: {err}") from err

    async def _post_rpc(
        self,
        method: str,
        param_types: list[str],
        param_values: list[str],
    ) -> dict[str, Any]:
        """Low-level POST to CDE GWT RPC servlet for basic RPC calls."""
        payload = build_gwt_payload(
            service=CDE_SERVICE_INTERFACE,
            method=method,
            param_types=param_types,
            param_values=param_values,
        )
        return await self._post_gwt(payload)

    async def authenticate(self) -> bool:
        """Establish session and authenticate user credentials."""
        # 1. Initialize session cookies
        init_resp = await self._post_rpc(
            method="getInitialData",
            param_types=[],
            param_values=[],
        )
        if init_resp.get("status") != "OK":
            _LOGGER.warning("InitialData response not OK: %s", init_resp)

        # 2. Call signIn
        sign_in_resp = await self._post_rpc(
            method="signIn",
            param_types=[GWT_STRING_TYPE, GWT_STRING_TYPE, GWT_STRING_TYPE],
            param_values=[self.username, self.password, "[1920,1080]"],
        )

        if sign_in_resp.get("status") == "EX":
            exception = sign_in_resp.get("exception", "")
            _LOGGER.error("CDE Lightband authentication failed with exception: %s", exception)
            raise CdeAuthError(f"Authentication failed: {exception}")

        if sign_in_resp.get("status") != "OK":
            raise CdeConnectionError("Unexpected response status during sign in")

        string_table = sign_in_resp.get("string_table", [])
        if any("SignInException" in s for s in string_table):
            raise CdeAuthError("Invalid username or password")

        # In Daffron eBiz, SignedInToken string table format is:
        # ['com.daffron.shared.client.SignedInToken/...', '<date>', '<token_id>']
        token: str | None = None
        for s in string_table:
            if re.match(r"^\d{6,15}$", s):
                token = s
                break
        if not token and len(string_table) > 2:
            token = string_table[2]

        if not token:
            raise CdeAuthError("Could not retrieve session token from sign in response")

        self._token = token
        self._is_authenticated = True

        # 3. Fetch AccountsTable to discover account, meter, and address
        accounts_json = await self._post_json_service("AccountsTable", "reload", {})
        summary = accounts_json.get("summary", {}) if isinstance(accounts_json, dict) else {}
        self._total_due = float(summary.get("totalDue", 0.0))

        data_items = accounts_json.get("data", []) if isinstance(accounts_json, dict) else []
        # Find electric service (MSSERV == "1") or default to first
        electric = next((item for item in data_items if str(item.get("MSSERV", "")).strip() == "1"), None)
        if not electric and data_items:
            electric = data_items[0]

        if electric:
            self._account_number = str(electric.get("ACCT", ""))
            self._sub_account = str(electric.get("SUB", ""))
            self._msserv = str(electric.get("MSSERV", "1"))
            self._rsp = str(electric.get("RSP", "     "))
            self._meter_id = str(electric.get("LOMETE", ""))
            self._service_address = str(electric.get("LOCADDR", "")).strip()

        _LOGGER.info(
            "Successfully authenticated with CDE Lightband (Account: %s, Meter: %s)",
            self._account_number,
            self._meter_id,
        )
        return True

    async def _post_json_service(
        self,
        service: str,
        action: str,
        payload_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Call getJsonData RPC wrapper for Daffron eBiz services."""
        if not self._is_authenticated or not self._token:
            await self.authenticate()

        async def _do_post() -> dict[str, Any]:
            payload = build_gwt_json_data_payload(
                service_method=service,
                action=action,
                token=self._token or "",
                data_dict=payload_data,
            )
            return await self._post_gwt(payload)

        resp = await _do_post()

        if resp.get("status") == "EX":
            # Session token may have expired, attempt re-authentication once
            _LOGGER.warning("Service %s returned exception, attempting re-authentication", service)
            self._is_authenticated = False
            self._token = None
            await self.authenticate()
            resp = await _do_post()
            if resp.get("status") == "EX":
                raise CdeDataError(f"Service {service} failed after re-auth: {resp.get('exception')}")

        string_table = resp.get("string_table", [])
        for s in string_table:
            if s.startswith("{") or s.startswith("["):
                try:
                    return json.loads(s)
                except Exception:
                    continue

        return {}

    async def fetch_billing_data(self) -> CdeBillingData:
        """Fetch current billing summary from AccountsTable, BillingHistory, and Payments."""
        if not self._is_authenticated:
            await self.authenticate()

        # 1. AccountsTable reload for balance
        acc_resp = await self._post_json_service("AccountsTable", "reload", {})
        if isinstance(acc_resp, dict):
            summary = acc_resp.get("summary", {})
            self._total_due = float(summary.get("totalDue", self._total_due))

        # 2. AccountBillingHistory for latest statement
        bill_data: dict[str, Any] = {}
        if self._account_number:
            params = {
                "ACCT": self._account_number,
                "SUB": self._sub_account,
                "MSSERV": self._msserv,
                "RSP": self._rsp,
            }
            bill_resp = await self._post_json_service("AccountBillingHistory", "table", params)
            if isinstance(bill_resp, dict):
                history = bill_resp.get("history", [])
                if history:
                    # Chronological ascending; last item is the most recent bill
                    bill_data = history[-1]

        # 3. AccountPayments for latest payment
        pay_data: dict[str, Any] = {}
        if self._account_number:
            params = {
                "ACCT": self._account_number,
                "SUB": self._sub_account,
                "MSSERV": self._msserv,
                "RSP": self._rsp,
            }
            pay_resp = await self._post_json_service("AccountPayments", "table", params)
            if isinstance(pay_resp, dict):
                payments = pay_resp.get("paymentData", [])
                if payments:
                    # Reverse chronological; first item is the most recent payment
                    pay_data = payments[0]

        last_bill_date = bill_data.get("DATE")
        due_date = _parse_date(last_bill_date)
        last_bill_amount = float(bill_data.get("DUE", 0.0))

        last_payment_date = pay_data.get("DATE")
        last_payment_amount = float(pay_data.get("AMOUNT", 0.0))

        # Check if past due: positive balance and current date strictly past due date
        is_past_due = False
        if self._total_due > 0 and due_date:
            try:
                due_d = datetime.strptime(due_date, "%Y-%m-%d").date()
                is_past_due = datetime.now(timezone.utc).date() > due_d
            except ValueError:
                pass
        past_due_amount = self._total_due if is_past_due else 0.0

        return CdeBillingData(
            account_number=self._account_number or "Unknown",
            balance_due=self._total_due,
            due_date=due_date,
            is_past_due=is_past_due,
            past_due_amount=past_due_amount,
            last_payment_amount=last_payment_amount,
            last_payment_date=last_payment_date,
            last_bill_amount=last_bill_amount,
            last_bill_date=last_bill_date,
            service_address=self._service_address,
        )

    async def fetch_rates(self) -> CdeRateData | None:
        """Fetch and parse the published residential rates from the CDE website.

        Fail-soft: every failure path logs a warning and returns ``None``.
        """
        try:
            async with self._session.get(RATES_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
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

    async def fetch_internet_prices(self) -> dict[str, float] | None:
        """Fetch and parse residential internet plan prices from the CDE website.

        Fail-soft: every failure path logs a warning and returns ``None``.
        """
        try:
            async with self._session.get(INTERNET_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    _LOGGER.warning("CDE internet page returned HTTP %s", resp.status)
                    return None
                body = await resp.text()
        except Exception as err:
            _LOGGER.warning("Could not fetch CDE internet page: %s", err)
            return None
        prices = parse_internet_prices_html(body)
        if prices is None:
            _LOGGER.warning("Could not parse internet prices from the CDE internet page")
            return None
        return prices

    async def fetch_usage_data(self, days: int = 30) -> list[CdeUsageRecord]:
        """Fetch smart meter interval usage records from Charts drilldown."""
        if not self._is_authenticated:
            await self.authenticate()

        if not self._account_number:
            return []

        # 1. Fetch available months from Charts usage
        charts_resp = await self._post_json_service(
            "Charts",
            "usage",
            {
                "ACCT": self._account_number,
                "SUB": self._sub_account,
                "MSSERV": self._msserv,
            },
        )

        month_rows = charts_resp.get("data", []) if isinstance(charts_resp, dict) else []
        months_to_drill: list[str] = []
        if month_rows:
            # Most recent month
            recent_month = month_rows[-1][0].get("lParm")
            if recent_month:
                months_to_drill.append(recent_month)
            # If requested days > 30 and there is a previous month, drill into that too
            if days > 30 and len(month_rows) > 1:
                prev_month = month_rows[-2][0].get("lParm")
                if prev_month:
                    months_to_drill.append(prev_month)

        records: list[CdeUsageRecord] = []
        for month_parm in months_to_drill:
            try:
                daily_resp = await self._post_json_service(
                    "Charts",
                    "table",
                    {
                        "ACCT": self._account_number,
                        "SUB": self._sub_account,
                        "MSSERV": self._msserv,
                        "TimeView": "DAILY",
                        "drilldownData": month_parm,
                    },
                )
                daily_rows = daily_resp.get("data", []) if isinstance(daily_resp, dict) else []
                for row in daily_rows:
                    if len(row) >= 2:
                        raw_date = row[0].get("value", "")
                        try:
                            kwh = float(row[1].get("value", 0.0))
                        except (ValueError, TypeError):
                            kwh = 0.0
                        ts = _parse_timestamp(raw_date)
                        iso_d = _parse_date(raw_date)
                        records.append(
                            CdeUsageRecord(
                                timestamp=ts,
                                kwh=kwh,
                                meter_id=self._meter_id,
                                reading_date=iso_d,
                            )
                        )
            except Exception as err:
                _LOGGER.warning("Could not fetch daily drilldown for %s: %s", month_parm, err)

        # Sort chronologically ascending
        records.sort(key=lambda r: r.timestamp)
        return records
