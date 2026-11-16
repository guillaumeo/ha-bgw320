"""Unit tests for the pure-Python AT&T BGW320 API client and HTML parser."""

from __future__ import annotations

import aiohttp
import pytest
from conftest import BROADBAND_HTML, FIREWALL_HTML, SYSTEM_HTML
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.bgw320.api import (
    BgwConnectionError,
    BgwGatewayClient,
    BgwInvalidUrlError,
    BgwParseError,
    _duration_seconds,
    _int_counter,
    _mac_address,
    _number,
    _safe_error_code,
    _text,
    normalize_gateway_url,
    parse_label_value_rows,
)


def test_normalize_gateway_url() -> None:
    """Test gateway URL validation and normalization."""
    assert normalize_gateway_url(" https://192.168.1.254/ ") == "https://192.168.1.254"
    assert (
        normalize_gateway_url("http://gateway.local:8443")
        == "http://gateway.local:8443"
    )

    with pytest.raises(BgwInvalidUrlError):
        normalize_gateway_url("192.168.1.254")
    with pytest.raises(BgwInvalidUrlError):
        normalize_gateway_url("ftp://192.168.1.254")
    with pytest.raises(BgwInvalidUrlError):
        normalize_gateway_url("https://192.168.1.254/cgi-bin/sysinfo.ha")


def test_parse_helpers_and_mac_validation() -> None:
    """Test HTML table extraction, exact integer counters, float guards, and MAC validation."""
    html = """
    <table>
      <tr><th>Model Number:</th><td>BGW320&nbsp;-&nbsp;505</td></tr>
      <tr><td>Model Number</td><td>Ignored Duplicate</td></tr>
      <tr><td>SingleCellRow</td></tr>
      <tr><td>Receive Bytes:</td><td> 1,234,567 bytes </td></tr>
    </table>
    """
    rows = parse_label_value_rows(html)
    assert rows == {
        "Model Number": "BGW320 - 505",
        "Receive Bytes": "1,234,567 bytes",
    }

    assert _text(None) is None
    assert _text("   ") is None
    assert _number(None) is None
    assert _number("   ") is None
    assert _number("not_a_number") is None
    assert _number("inf") is None
    assert _number("nan") is None
    assert _number("2.5 Gbps") == 2.5

    # Exact 64-bit+ integer parsing without IEEE-754 float precision loss (> 2**53)
    assert _int_counter("18,014,398,509,481,985 bytes") == 18_014_398_509_481_985
    assert _int_counter(None) is None
    assert _int_counter("12.5") is None
    assert _int_counter("-5") is None
    assert _int_counter("inf") is None

    # MAC validation
    assert _mac_address("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
    assert _mac_address("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert _mac_address("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"
    assert _mac_address("00:00:00:00:00:00") is None
    assert _mac_address("FF:FF:FF:FF:FF:FF") is None
    assert _mac_address("N/A") is None
    assert _mac_address("AA:BB-CC:DD:EE:FF") is None
    assert _mac_address(None) is None

    assert _safe_error_code(aiohttp.ClientError("boom")) == "network_error"
    assert _safe_error_code(RuntimeError("boom")) == "unexpected_error"


def test_duration_seconds() -> None:
    """Test uptime string parsing across 3-part, 4-part, and word-day formats."""
    assert _duration_seconds("01:02:03") == 3723
    assert _duration_seconds("02:03:04:05") == 183845
    assert _duration_seconds("2 days, 03:04:05") == 183845
    assert _duration_seconds("2d 03:04:05") == 183845
    assert _duration_seconds("00:60:00") is None
    assert _duration_seconds("-1:00:00") is None
    assert _duration_seconds("01:xx:00") is None
    assert _duration_seconds("invalid") is None
    assert _duration_seconds(None) is None


def test_parser_resilience_scripts_nested_tables_and_unclosed_cells() -> None:
    """Test parser survives inline scripts/styles, nested layout tables, and unclosed cells."""
    html = """
    <div class="wrapper">
      <td>stray-cell-outside-tr</td></td></tr>
      <table class="layout-shell">
        <tr>
          <td>
            <style>.hidden { display: none; }</style>
            <table class="inner-stats">
              <tr>
                <th>Model Number<script><span>ignored()</span></script>:</th>
                <td>
                  <script type="text/javascript">var secret = "ignore_me";</script>
                  <script src="/noop.js" />
                  <br/>
                  <span>BGW320-500</span>
                </td>
              </tr>
              <tr><th>MODEL_NUMBER<td>Ignored Case-Insensitive Duplicate</tr>
              <tr><th>Current Speed<td>10,000 Mbps</tr>
              <tr><td></td><td>EmptyLabelIgnored</td></tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """
    rows = parse_label_value_rows(html)
    assert rows == {
        "Model Number": "BGW320-500",
        "Current Speed": "10,000 Mbps",
    }


async def test_client_survives_label_case_punctuation_and_alias_drift(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test snapshot collection survives firmware label casing, punctuation, and alias changes."""
    base = "https://192.168.1.254"
    drifted_system = """
    <table><tr><td>
      <table>
        <tr><th>Device Model</th><td>BGW320-500</td></tr>
        <tr><th>vendor:</th><td>HUMAX</td></tr>
        <tr><th>Firmware Version</th><td>6.40.4</td></tr>
        <tr><th>System Uptime</th><td>3 days, 01:02:03</td></tr>
        <tr><th>device_mac</th><td>BC-9A-8E-BF-3F-80</td></tr>
      </table>
    </td></tr></table>
    """
    drifted_broadband = """
    <table>
      <tr><th>connection_status<td>UP</tr>
      <tr><th>Network Type<td>XGS-PON</tr>
      <tr><th>PON Link Status<td>Up</tr>
      <tr><th>Current_Speed<td>10,000 Mbps</tr>
      <tr><th>Duplex<td>Full</tr>
      <tr><th>RX Bytes<td>1000</tr>
      <tr><th>TX Bytes<td>2000</tr>
      <tr><th>RX Packets<td>10</tr>
      <tr><th>TX Packets<td>20</tr>
    </table>
    """
    drifted_firewall = """
    <table>
      <tr><td>ip-passthrough</td><td>ON</td></tr>
      <tr><td>Advanced</td><td>off</td></tr>
    </table>
    """
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=drifted_system)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=drifted_broadband)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=drifted_firewall)

    session = async_get_clientsession(hass, verify_ssl=False)
    client = BgwGatewayClient(base, session=session)
    snapshot = await client.async_collect()

    assert snapshot.gateway.model == "BGW320-500"
    assert snapshot.gateway.manufacturer == "HUMAX"
    assert snapshot.gateway.firmware == "6.40.4"
    assert snapshot.gateway.uptime_seconds == 262923
    assert snapshot.gateway.mac_address == "bc:9a:8e:bf:3f:80"
    assert snapshot.broadband.connection == "up"
    assert snapshot.broadband.network_type == "XGS-PON"
    assert snapshot.broadband.line_state == "up"
    assert snapshot.broadband.speed_mbps == 10000
    assert snapshot.broadband.duplex == "full"
    assert snapshot.broadband.rx_bytes == 1000
    assert snapshot.broadband.tx_bytes == 2000
    assert snapshot.broadband.rx_packets == 10
    assert snapshot.broadband.tx_packets == 20
    assert snapshot.broadband.rx_errors is None
    assert snapshot.firewall is not None
    assert snapshot.firewall.ip_passthrough == "on"
    assert snapshot.firewall.advanced == "off"
    assert snapshot.firewall.packet_filter is None


async def test_client_collect_full_snapshot(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test collecting all three pages and excluding sensitive fields like WAN IP."""
    base = "https://192.168.1.254"
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=SYSTEM_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=FIREWALL_HTML)

    session = async_get_clientsession(hass, verify_ssl=False)
    client = BgwGatewayClient(base, session=session)
    snapshot = await client.async_collect()

    assert snapshot.gateway.manufacturer == "Nokia"
    assert snapshot.gateway.model == "BGW320-505"
    assert snapshot.gateway.firmware == "6.28.7"
    assert snapshot.gateway.uptime_seconds == 183845
    assert snapshot.gateway.mac_address == "aa:bb:cc:dd:ee:ff"
    assert snapshot.broadband.connection == "up"
    assert snapshot.broadband.network_type == "PON"
    assert snapshot.broadband.line_state == "up"
    assert snapshot.broadband.speed_mbps == 5000
    assert snapshot.broadband.duplex == "full"
    assert snapshot.broadband.rx_bytes == 10737418240
    assert snapshot.broadband.tx_bytes == 5368709120
    assert snapshot.broadband.rx_packets == 987654
    assert snapshot.broadband.tx_packets == 456789
    assert snapshot.broadband.rx_drops == 3
    assert snapshot.broadband.tx_drops == 1
    assert snapshot.broadband.rx_errors == 4
    assert snapshot.broadband.tx_errors == 2
    assert snapshot.broadband.collisions == 0
    assert snapshot.broadband.tx_discards == 7
    assert snapshot.firewall is not None
    assert snapshot.firewall.packet_filter == "on"
    assert snapshot.firewall.ip_passthrough == "on"
    assert snapshot.firewall.nat_default_server == "off"
    assert snapshot.firewall.advanced == "on"
    assert snapshot.failed_pages == {}
    assert "203.0.113.42" not in repr(snapshot)


async def test_client_partial_firewall_failure(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test degraded snapshot when firewall page fails without leaking error strings."""
    base = "https://192.168.1.254"
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=SYSTEM_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML)
    aioclient_mock.get(
        f"{base}/cgi-bin/firewall.ha",
        exc=TimeoutError("secret-internal-gateway.lan"),
    )

    session = async_get_clientsession(hass, verify_ssl=False)
    client = BgwGatewayClient(base, session=session)
    snapshot = await client.async_collect()

    assert snapshot.firewall is None
    assert snapshot.failed_pages == {"firewall": "timeout"}
    assert "secret-internal-gateway.lan" not in repr(snapshot)


async def test_client_fail_fast_on_required_page_errors(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test fast-fail on required page transport or parse errors without polling remaining pages."""
    base = "https://192.168.1.254"
    session = async_get_clientsession(hass, verify_ssl=False)
    client = BgwGatewayClient(base, session=session)

    # HTTP 502 on sysinfo.ha -> fails immediately after 1 request
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", status=502)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=FIREWALL_HTML)
    with pytest.raises(BgwConnectionError):
        await client.async_collect()
    assert aioclient_mock.call_count == 1

    # No table rows on sysinfo.ha -> BgwParseError immediately after 1 request
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text="<html>No tables here</html>")
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=FIREWALL_HTML)
    with pytest.raises(BgwParseError):
        await client.async_collect()
    assert aioclient_mock.call_count == 1
