"""Unit tests for CdeApiClient."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
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
    with patch.object(client, "_post_rpc", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [
            {"status": "OK", "string_table": ["InitialData"]},
            {"status": "OK", "string_table": ["SignedInToken/2206797227", "token123", "account456"]}
        ]
        success = await client.authenticate()
        assert success is True
        assert client.is_authenticated is True
    await client.close()

@pytest.mark.asyncio
async def test_fetch_billing_data_parses_fields():
    client = CdeApiClient(username="user", password="pass")
    client._is_authenticated = True
    
    mock_billing_response = {
        "status": "OK",
        "string_table": [
            "LoadBilling",
            '{"accountNumber":"1234567","balanceDue":145.50,"dueDate":"2026-11-15","lastPaymentAmount":120.00,"lastPaymentDate":"2026-10-14","lastBillAmount":145.50,"serviceAddress":"123 Main St, Clarksville, TN"}'
        ]
    }
    with patch.object(client, "_post_json_service", new_callable=AsyncMock) as mock_json_call:
        mock_json_call.return_value = mock_billing_response
        billing = await client.fetch_billing_data()
        assert isinstance(billing, CdeBillingData)
        assert billing.account_number == "1234567"
        assert billing.balance_due == 145.50
        assert billing.due_date == "2026-11-15"
        assert billing.last_payment_amount == 120.00
        assert billing.service_address == "123 Main St, Clarksville, TN"
    await client.close()

@pytest.mark.asyncio
async def test_fetch_usage_data_parses_records():
    client = CdeApiClient(username="user", password="pass")
    client._is_authenticated = True

    mock_usage_response = {
        "status": "OK",
        "string_table": [
            "Charts",
            '[{"timestamp":"2026-10-31T00:00:00Z","kwh":32.5,"meter":"MTR1234"},{"timestamp":"2026-11-01T00:00:00Z","kwh":28.0,"meter":"MTR1234"}]'
        ]
    }
    with patch.object(client, "_post_json_service", new_callable=AsyncMock) as mock_json_call:
        mock_json_call.return_value = mock_usage_response
        records = await client.fetch_usage_data(days=2)
        assert len(records) == 2
        assert records[0].kwh == 32.5
        assert records[1].kwh == 28.0
        assert records[0].meter_id == "MTR1234"
    await client.close()

@pytest.mark.asyncio
async def test_connection_error_on_network_failure():
    client = CdeApiClient(username="user", password="pass")
    with patch("aiohttp.ClientSession.post", side_effect=Exception("Connection refused")):
        with pytest.raises(CdeConnectionError):
            await client.authenticate()
    await client.close()
