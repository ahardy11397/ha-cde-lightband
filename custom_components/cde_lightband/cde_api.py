"""API Client for CDE Lightband (Daffron eBusiness GWT-RPC)."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import aiohttp

from .exceptions import CdeAuthError, CdeConnectionError, CdeDataError
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


class CdeApiClient:
    """Asynchronous client connecting to CDE Lightband portal via GWT-RPC."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self._session = session
        self._own_session = session is None
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

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close client session if owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def _post_gwt(self, payload: str) -> dict[str, Any]:
        """Low-level POST of raw GWT payload to CDE GWT RPC servlet."""
        headers = {
            "Content-Type": "text/x-gwt-rpc; charset=utf-8",
            "X-GWT-Permutation": CDE_PERMUTATION,
            "X-GWT-Module-Base": CDE_MODULE_BASE,
            "User-Agent": "HomeAssistant-CdeLightband",
        }

        try:
            session = await self._get_session()
            async with session.post(
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

        is_past_due = self._total_due > 0
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
