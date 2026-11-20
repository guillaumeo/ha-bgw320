"""Tests for the AT&T BGW320 config and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

from conftest import SYSTEM_HTML, register_gateway_pages
from homeassistant.config_entries import SOURCE_USER, ConfigFlowResult
from homeassistant.const import CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.bgw320.const import DOMAIN

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    from tests.common import MockConfigEntry


async def test_user_flow_success_and_duplicate_abort(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test user config flow creates entry with MAC unique_id and blocks duplicates."""
    register_gateway_pages(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.bgw320.async_setup_entry", return_value=True
    ) as mock_setup:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: "https://192.168.1.254/", CONF_VERIFY_SSL: False},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "BGW320-505"
    assert result2["data"] == {
        CONF_URL: "https://192.168.1.254",
        CONF_VERIFY_SSL: False,
    }
    assert result2["result"].unique_id == "aa:bb:cc:dd:ee:ff"
    assert len(mock_setup.mock_calls) == 1

    # Duplicate gateway should abort even on another URL
    register_gateway_pages(aioclient_mock, base="https://10.0.0.254", clear=False)
    dup = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    dup_result = await hass.config_entries.flow.async_configure(
        dup["flow_id"],
        {CONF_URL: "https://10.0.0.254", CONF_VERIFY_SSL: False},
    )
    assert dup_result["type"] is FlowResultType.ABORT
    assert dup_result["reason"] == "already_configured"


async def test_user_flow_errors_and_recovery(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test invalid_url, cannot_connect, invalid_response, and recovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    async def _submit(url: str = "https://192.168.1.254") -> ConfigFlowResult:
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: url, CONF_VERIFY_SSL: False}
        )

    # 1. Invalid URL
    res = await _submit("not-a-url")
    assert res["type"] is FlowResultType.FORM and res["errors"] == {CONF_URL: "invalid_url"}

    # 2. Cannot connect
    aioclient_mock.get("https://192.168.1.254/cgi-bin/sysinfo.ha", exc=TimeoutError())
    res = await _submit()
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "cannot_connect"}

    # 3. Invalid HTML response
    register_gateway_pages(
        aioclient_mock, system_html="<table><tr><td>Foo</td><td>Bar</td></tr></table>"
    )
    res = await _submit()
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "invalid_response"}

    # 4. Unexpected error
    with patch(
        "custom_components.bgw320.config_flow.BgwGatewayClient.async_collect",
        side_effect=RuntimeError("boom"),
    ):
        res = await _submit()
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "unknown"}

    # 5. Recovery
    register_gateway_pages(aioclient_mock)
    with patch("custom_components.bgw320.async_setup_entry", return_value=True):
        res = await _submit()
    assert res["type"] is FlowResultType.CREATE_ENTRY


async def test_unique_id_fallbacks_when_mac_missing(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test fallback unique_id derivation when MAC is placeholder, then host:port."""
    no_mac_html = SYSTEM_HTML.replace("AA:BB:CC:DD:EE:FF", "N/A")
    no_serial_html = no_mac_html.replace(
        "<tr><td>Serial Number</td><td>SECRET-SERIAL-999</td></tr>", ""
    )
    for url, sys_html, expected_id in (
        ("https://192.168.1.254", no_mac_html, "secret-serial-999"),
        ("https://BGW-Gateway.Local:8443", no_serial_html, "bgw-gateway.local:8443"),
    ):
        register_gateway_pages(aioclient_mock, base=url, system_html=sys_html)
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        with patch("custom_components.bgw320.async_setup_entry", return_value=True):
            res = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {CONF_URL: url, CONF_VERIFY_SSL: False}
            )
        assert res["type"] is FlowResultType.CREATE_ENTRY
        assert res["result"].unique_id == expected_id


async def test_reconfigure_flow_success_and_mismatch(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test reconfiguring URL/TLS settings and rejecting mismatched gateway MACs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BGW320-505",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
    )
    entry.add_to_hass(hass)

    register_gateway_pages(aioclient_mock, base="https://192.168.10.254")
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with patch("custom_components.bgw320.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: "https://192.168.10.254/", CONF_VERIFY_SSL: True},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert entry.data == {
        CONF_URL: "https://192.168.10.254",
        CONF_VERIFY_SSL: True,
    }

    # Reconfigure pointing at a different physical gateway must abort
    other_system = SYSTEM_HTML.replace("AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66")
    register_gateway_pages(
        aioclient_mock, base="https://192.168.20.254", system_html=other_system
    )
    mismatch_flow = await entry.start_reconfigure_flow(hass)
    mismatch_res = await hass.config_entries.flow.async_configure(
        mismatch_flow["flow_id"],
        {CONF_URL: "https://192.168.20.254", CONF_VERIFY_SSL: False},
    )
    assert mismatch_res["type"] is FlowResultType.ABORT
    assert mismatch_res["reason"] == "unique_id_mismatch"
