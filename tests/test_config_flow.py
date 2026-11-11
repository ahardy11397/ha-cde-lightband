"""Tests for CDE Lightband config flow and options flow."""
import pytest
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.cde_lightband.const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_HISTORY_DAYS,
    CONF_INTERNET_PLAN,
)
from custom_components.cde_lightband.exceptions import CdeAuthError, CdeConnectionError


@pytest.mark.asyncio
async def test_form_displayed(hass: HomeAssistant):
    """Test that the user form is served."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_invalid_auth_error(hass: HomeAssistant):
    """Test error handling when authentication fails."""
    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        side_effect=CdeAuthError("Invalid credentials"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "baduser", CONF_PASSWORD: "badpassword"},
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_cannot_connect_error(hass: HomeAssistant):
    """Test error handling when connection fails."""
    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        side_effect=CdeConnectionError("Network down"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_successful_config_entry(hass: HomeAssistant):
    """Test creating entry successfully after authentication."""
    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        return_value=True,
    ), patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.account_number",
        "9876543",
    ), patch(
        "custom_components.cde_lightband.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "validuser", CONF_PASSWORD: "validpassword"},
        )
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["title"] == "CDE Lightband (9876543)"
        assert result["data"] == {
            CONF_USERNAME: "validuser",
            CONF_PASSWORD: "validpassword",
        }
        assert result["result"].unique_id == "9876543"

from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.mark.asyncio
async def test_options_flow(hass: HomeAssistant):
    """Test options flow updates config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CDE Lightband (123456)",
        data={CONF_USERNAME: "user", CONF_PASSWORD: "password"},
        unique_id="123456",
        options={},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: 120, CONF_HISTORY_DAYS: 45},
    )
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_SCAN_INTERVAL: 120,
        CONF_HISTORY_DAYS: 45,
        "internet_plan": "none",
    }


@pytest.mark.asyncio
async def test_reauth_successful(hass: HomeAssistant):
    """Test reauth flow updates password on successful authentication."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CDE Lightband (123456)",
        data={CONF_USERNAME: "user", CONF_PASSWORD: "old_password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "new_password"},
        )
        assert result2["type"] == data_entry_flow.FlowResultType.ABORT
        assert result2["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == "new_password"


@pytest.mark.asyncio
async def test_reauth_invalid_auth(hass: HomeAssistant):
    """Test reauth flow error handling when credentials fail."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CDE Lightband (123456)",
        data={CONF_USERNAME: "user", CONF_PASSWORD: "old_password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        side_effect=CdeAuthError("Invalid username or password"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "wrong_password"},
        )
        assert result2["type"] == data_entry_flow.FlowResultType.FORM
        assert result2["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_reauth_cannot_connect(hass: HomeAssistant):
    """Test reauth flow error handling when connection fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CDE Lightband (123456)",
        data={CONF_USERNAME: "user", CONF_PASSWORD: "old_password"},
        unique_id="123456",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.cde_lightband.cde_api.CdeApiClient.authenticate",
        side_effect=CdeConnectionError("Network down"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "new_password"},
        )
        assert result2["type"] == data_entry_flow.FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


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
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert CONF_INTERNET_PLAN in result["data_schema"].schema

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: 60, CONF_HISTORY_DAYS: 30, CONF_INTERNET_PLAN: "300"},
    )
    await hass.async_block_till_done()
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INTERNET_PLAN] == "300"
