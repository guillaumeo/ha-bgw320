"""Tests for the AT&T BGW320 config and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

from conftest import BROADBAND_HTML, FIREWALL_HTML, SYSTEM_HTML
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.bgw320.const import DOMAIN

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    from tests.common import MockConfigEntry


def _mock_gateway_pages(
    aioclient_mock,
    base: str = "https://192.168.1.254",
    system_html: str = SYSTEM_HTML,
    broadband_html: str = BROADBAND_HTML,
    firewall_html: str = FIREWALL_HTML,
) -> None:
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=system_html)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=broadband_html)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=firewall_html)


async def test_user_flow_success_and_duplicate_abort(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test user config flow creates entry with MAC unique_id and blocks duplicates."""
    _mock_gateway_pages(aioclient_mock)

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
    _mock_gateway_pages(aioclient_mock, base="https://10.0.0.254")
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

    # 1. Invalid URL
    res_invalid_url = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "not-a-url", CONF_VERIFY_SSL: False},
    )
    assert res_invalid_url["type"] is FlowResultType.FORM
    assert res_invalid_url["errors"] == {CONF_URL: "invalid_url"}

    # 2. Cannot connect
    aioclient_mock.get("https://192.168.1.254/cgi-bin/sysinfo.ha", exc=TimeoutError())
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML
    )
    aioclient_mock.get("https://192.168.1.254/cgi-bin/firewall.ha", text=FIREWALL_HTML)
    res_conn = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
    )
    assert res_conn["type"] is FlowResultType.FORM
    assert res_conn["errors"] == {"base": "cannot_connect"}

    # 3. Invalid HTML response
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/sysinfo.ha",
        text="<table><tr><td>Foo</td><td>Bar</td></tr></table>",
    )
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML
    )
    aioclient_mock.get("https://192.168.1.254/cgi-bin/firewall.ha", text=FIREWALL_HTML)
    res_parse = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
    )
    assert res_parse["type"] is FlowResultType.FORM
    assert res_parse["errors"] == {"base": "invalid_response"}

    # 4. Unexpected error
    with patch(
        "custom_components.bgw320.config_flow.BgwGatewayClient.async_collect",
        side_effect=RuntimeError("boom"),
    ):
        res_unknown = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
        )
    assert res_unknown["type"] is FlowResultType.FORM
    assert res_unknown["errors"] == {"base": "unknown"}

    # 5. Recovery
    aioclient_mock.clear_requests()
    _mock_gateway_pages(aioclient_mock)
    with patch("custom_components.bgw320.async_setup_entry", return_value=True):
        res_ok = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
        )
    assert res_ok["type"] is FlowResultType.CREATE_ENTRY


async def test_unique_id_fallbacks_when_mac_missing(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test fallback unique_id derivation when MAC is placeholder, then host:port."""
    placeholder_mac_html = SYSTEM_HTML.replace(
        "AA:BB:CC:DD:EE:FF",
        "N/A",
    )
    _mock_gateway_pages(
        aioclient_mock, base="https://192.168.1.254", system_html=placeholder_mac_html
    )
    flow1 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch("custom_components.bgw320.async_setup_entry", return_value=True):
        res1 = await hass.config_entries.flow.async_configure(
            flow1["flow_id"],
            {CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
        )
    assert res1["type"] is FlowResultType.CREATE_ENTRY
    assert res1["result"].unique_id == "secret-serial-999"

    no_mac_or_serial_html = placeholder_mac_html.replace(
        "<tr><td>Serial Number</td><td>SECRET-SERIAL-999</td></tr>", ""
    )
    aioclient_mock.clear_requests()
    _mock_gateway_pages(
        aioclient_mock,
        base="https://BGW-Gateway.Local:8443",
        system_html=no_mac_or_serial_html,
    )
    flow2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch("custom_components.bgw320.async_setup_entry", return_value=True):
        res2 = await hass.config_entries.flow.async_configure(
            flow2["flow_id"],
            {CONF_URL: "https://BGW-Gateway.Local:8443", CONF_VERIFY_SSL: False},
        )
    assert res2["type"] is FlowResultType.CREATE_ENTRY
    assert res2["result"].unique_id == "bgw-gateway.local:8443"


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

    _mock_gateway_pages(aioclient_mock, base="https://192.168.10.254")
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
    aioclient_mock.clear_requests()
    _mock_gateway_pages(
        aioclient_mock, base="https://192.168.20.254", system_html=other_system
    )
    mismatch_flow = await entry.start_reconfigure_flow(hass)
    mismatch_res = await hass.config_entries.flow.async_configure(
        mismatch_flow["flow_id"],
        {CONF_URL: "https://192.168.20.254", CONF_VERIFY_SSL: False},
    )
    assert mismatch_res["type"] is FlowResultType.ABORT
    assert mismatch_res["reason"] == "unique_id_mismatch"
