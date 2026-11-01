"""Unit tests for CdeApiClient."""
import pytest
from unittest.mock import AsyncMock, patch
from custom_components.cde_lightband.cde_api import CdeApiClient, CdeBillingData, CdeUsageRecord
from custom_components.cde_lightband.exceptions import CdeAuthError, CdeConnectionError, CdeDataError

@pytest.mark.asyncio
async def test_auth_failure_raises_cde_auth_error():
    client = CdeApiClient(username="baduser", password="badpassword")
    with patch.object(client, "_post_rpc", new_callable=AsyncMock) as mock_post:
        # Mock initialData ok, then signIn failure
        mock_post.side_effect = [
            {"status": "OK", "string_table": ["InitialData"]},
            {"status": "EX", "exception": "SignInException/3923402574"}
        ]
        with pytest.raises(CdeAuthError):
            await client.authenticate()
    await client.close()

@pytest.mark.asyncio
async def test_auth_success():
    client = CdeApiClient(username="gooduser", password="goodpassword")
    with patch.object(client, "_post_rpc", new_callable=AsyncMock) as mock_post, \
         patch.object(client, "_post_json_service", new_callable=AsyncMock) as mock_json:
        mock_post.side_effect = [
            {"status": "OK", "string_table": ["InitialData"]},
            {"status": "OK", "string_table": ["SignedInToken/2206797227", "Nov 1, 2026", "9876543210"]}
        ]
        mock_json.return_value = {
            "summary": {"totalDue": "0.00"},
            "data": [{
                "ACCT": "1234567",
                "SUB": "001",
                "MSSERV": "1",
                "LOMETE": "9999999",
                "LOCADDR": "123 Main St, Clarksville, TN",
                "RSP": "     ",
            }]
        }
        success = await client.authenticate()
        assert success is True
        assert client.is_authenticated is True
        assert client.account_number == "1234567"
        assert client.meter_id == "9999999"
    await client.close()

@pytest.mark.asyncio
async def test_fetch_billing_data_parses_fields():
    client = CdeApiClient(username="user", password="pass")
    client._is_authenticated = True
    client._token = "9876543210"
    client._account_number = "1234567"
    client._sub_account = "001"
    client._msserv = "1"
    client._rsp = "     "
    client._service_address = "123 Main St, Clarksville, TN"

    async def mock_post_json(service, action, payload=None):
        if service == "AccountsTable":
            return {"summary": {"totalDue": "145.50"}}
        elif service == "AccountBillingHistory":
            return {
                "history": [
                    {"DATE": "Nov 15, 2026", "DUE": "145.50", "USAGE": "1200"}
                ]
            }
        elif service == "AccountPayments":
            return {
                "paymentData": [
                    {"DATE": "Oct 14, 2026", "AMOUNT": "120.00", "TIME": "10:00 am"}
                ]
            }
        return {}

    with patch.object(client, "_post_json_service", side_effect=mock_post_json):
        billing = await client.fetch_billing_data()
        assert isinstance(billing, CdeBillingData)
        assert billing.account_number == "1234567"
        assert billing.balance_due == 145.50
        assert billing.due_date == "2026-11-15"
        assert billing.last_payment_amount == 120.00
        assert billing.last_payment_date == "Oct 14, 2026"
        assert billing.last_bill_amount == 145.50
        assert billing.last_bill_date == "Nov 15, 2026"
        assert billing.service_address == "123 Main St, Clarksville, TN"
    await client.close()

@pytest.mark.asyncio
async def test_fetch_usage_data_parses_records():
    client = CdeApiClient(username="user", password="pass")
    client._is_authenticated = True
    client._token = "9876543210"
    client._account_number = "1234567"
    client._sub_account = "001"
    client._msserv = "1"
    client._meter_id = "MTR1234"

    async def mock_post_json(service, action, payload=None):
        if service == "Charts" and action == "usage":
            return {
                "data": [
                    [{"value": "November 2026", "lParm": "Nov, 2026"}]
                ]
            }
        elif service == "Charts" and action == "table":
            return {
                "data": [
                    [{"value": "Oct 31, 2026"}, {"value": "32.5"}],
                    [{"value": "Nov 1, 2026"}, {"value": "28.0"}]
                ]
            }
        return {}

    with patch.object(client, "_post_json_service", side_effect=mock_post_json):
        records = await client.fetch_usage_data(days=30)
        assert len(records) == 2
        assert records[0].kwh == 32.5
        assert records[1].kwh == 28.0
        assert records[0].meter_id == "MTR1234"
        assert records[0].reading_date == "2026-10-31"
        assert records[1].reading_date == "2026-11-01"
    await client.close()

@pytest.mark.asyncio
async def test_connection_error_on_network_failure():
    client = CdeApiClient(username="user", password="pass")
    with patch("aiohttp.ClientSession.post", side_effect=Exception("Connection refused")):
        with pytest.raises(CdeConnectionError):
            await client.authenticate()
    await client.close()
