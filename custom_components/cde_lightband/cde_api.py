"""API Client for CDE Lightband (Daffron eBusiness GWT-RPC)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
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
    build_gwt_payload,
    parse_gwt_response,
)

_LOGGER = logging.getLogger(__name__)


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
        self._account_number: str | None = None
        self._service_address: str = ""
        self._token: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @property
    def account_number(self) -> str | None:
        return self._account_number

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close client session if owned."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def _post_rpc(
        self,
        method: str,
        param_types: list[str],
        param_values: list[str],
    ) -> dict[str, Any]:
        """Low-level POST to CDE GWT RPC servlet."""
        payload = build_gwt_payload(
            service=CDE_SERVICE_INTERFACE,
            method=method,
            param_types=param_types,
            param_values=param_values,
        )

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

        self._is_authenticated = True
        _LOGGER.info("Successfully authenticated with CDE Lightband")
        return True

    async def _post_json_service(
        self,
        service: str,
        action: str,
        payload_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call getJsonData RPC wrapper for Daffron eBiz services."""
        if not self._is_authenticated:
            await self.authenticate()

        # In Daffron eBiz, getJsonData takes a JsonData object (options/metadata + data string)
        json_str = json.dumps(payload_data or {})
        # GWT RPC signature: getJsonData(JsonData)
        resp = await self._post_rpc(
            method="getJsonData",
            param_types=["com.daffron.shared.shared.JsonData/1630149208"],
            param_values=[f"{service}:{action}:{json_str}"],
        )

        if resp.get("status") == "EX":
            # Session might have expired, try re-authenticating once
            _LOGGER.warning("Service %s returned exception, attempting re-authentication", service)
            self._is_authenticated = False
            await self.authenticate()
            resp = await self._post_rpc(
                method="getJsonData",
                param_types=["com.daffron.shared.shared.JsonData/1630149208"],
                param_values=[f"{service}:{action}:{json_str}"],
            )
            if resp.get("status") == "EX":
                raise CdeDataError(f"Service {service} failed after re-auth: {resp.get('exception')}")

        return resp

    async def fetch_billing_data(self) -> CdeBillingData:
        """Fetch current billing summary from Landing/LoadBilling."""
        resp = await self._post_json_service("Landing", "LoadBilling")
        string_table = resp.get("string_table", [])

        # Parse JSON payload embedded inside string table
        billing_json: dict[str, Any] = {}
        for s in string_table:
            if s.startswith("{") and "balance" in s.lower():
                try:
                    billing_json = json.loads(s)
                    break
                except Exception:
                    continue

        account_number = str(billing_json.get("accountNumber") or self._account_number or "Unknown")
        self._account_number = account_number
        self._service_address = billing_json.get("serviceAddress", "")

        return CdeBillingData(
            account_number=account_number,
            balance_due=float(billing_json.get("balanceDue", 0.0)),
            due_date=billing_json.get("dueDate"),
            is_past_due=bool(billing_json.get("isPastDue", False)),
            past_due_amount=float(billing_json.get("pastDueAmount", 0.0)),
            last_payment_amount=float(billing_json.get("lastPaymentAmount", 0.0)),
            last_payment_date=billing_json.get("lastPaymentDate"),
            last_bill_amount=float(billing_json.get("lastBillAmount", 0.0)),
            last_bill_date=billing_json.get("lastBillDate"),
            service_address=self._service_address,
        )

    async def fetch_usage_data(self, days: int = 30) -> list[CdeUsageRecord]:
        """Fetch smart meter interval usage records from Charts/usage."""
        resp = await self._post_json_service("Charts", "usage", {"days": days})
        string_table = resp.get("string_table", [])

        records: list[CdeUsageRecord] = []
        for s in string_table:
            if s.startswith("[") and ("kwh" in s.lower() or "usage" in s.lower() or "timestamp" in s.lower()):
                try:
                    items = json.loads(s)
                    for item in items:
                        records.append(
                            CdeUsageRecord(
                                timestamp=item.get("timestamp", ""),
                                kwh=float(item.get("kwh", 0.0)),
                                meter_id=str(item.get("meter", "")),
                                reading_date=item.get("readingDate"),
                            )
                        )
                    break
                except Exception:
                    continue

        return records
