"""Unit tests for the pure-Python AT&T BGW320 API client and HTML parser."""

from __future__ import annotations

import aiohttp
import pytest
from conftest import register_gateway_pages
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.bgw320.api import (
    MAX_RESPONSE_BYTES,
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
    assert normalize_gateway_url(" HTTPS://192.168.1.254/ ") == "https://192.168.1.254"
    assert (
        normalize_gateway_url("http://gateway.local:8443")
        == "http://gateway.local:8443"
    )
    assert normalize_gateway_url("https://[::1]:8443/") == "https://[::1]:8443"

    for bad in (
        "192.168.1.254",
        "ftp://192.168.1.254",
        "https://192.168.1.254/cgi-bin/sysinfo.ha",
        "https://192.168.1.254:",
        "https://192.168.1.254:0",
        "https://192.168.1.254:99999",
        "https://192.168.1.254:abc",
        "https://[bad",
        "https://u:p@192.168.1.254",
        "https://192.168.1.254 /",
        "https://192.168.1.254;foo",
        "https://192.168.1.254?a=1",
        "https://192.168.1.254#frag",
    ):
        with pytest.raises(BgwInvalidUrlError):
            normalize_gateway_url(bad)


def test_parse_helpers_and_mac_validation() -> None:
    """Test HTML table extraction, exact integer counters, float guards, and MAC validation."""
    html = """
    <table>
      <tr><th>Model Number:</th><td>BGW320&nbsp;-&nbsp;505</td><td>Extra</td></tr>
      <tr><td>Model Number</td><td>Ignored Duplicate</td></tr>
      <tr><td>SingleCellRow</td></tr>
      <tr><td>Line<br>State:<td>Up<script>bad()</script>
      <tr><td>Escaped</td><td>&amp;lt;tag&amp;gt;</td></tr>
      <tr><td>Receive Bytes:</td><td> 1,234,567 bytes </td>
    """
    rows = parse_label_value_rows(html)
    assert rows == {
        "Model Number": "BGW320 - 505",
        "Line State": "Up",
        "Escaped": "&lt;tag&gt;",
        "Receive Bytes": "1,234,567 bytes",
    }

    assert _text(None) is None
    assert _text("   ") is None
    for bad_num in (None, "   ", "not_a_number", "inf", "nan", "-1"):
        assert _number(bad_num) is None
    assert _number("2.5 Gbps") == 2.5

    # Exact 64-bit+ integer parsing without IEEE-754 float precision loss (> 2**53)
    assert _int_counter("18,014,398,509,481,985 bytes") == 18_014_398_509_481_985
    for bad_cnt in (None, "12.5", "-5", "inf"):
        assert _int_counter(bad_cnt) is None

    # MAC validation
    assert _mac_address("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
    assert _mac_address("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert _mac_address("AABBCCDDEEFF") == "aa:bb:cc:dd:ee:ff"
    for bad_mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF", "N/A", "AA:BB-CC:DD:EE:FF", None):
        assert _mac_address(bad_mac) is None

    assert _safe_error_code(aiohttp.ClientError("boom")) == "network_error"
    assert _safe_error_code(RuntimeError("boom")) == "unexpected_error"


def test_duration_seconds() -> None:
    """Test uptime string parsing across 3-part and 4-part formats."""
    assert _duration_seconds("01:02:03") == 3723
    assert _duration_seconds("02:03:04:05") == 183845
    for bad_dur in ("00:60:00", "-1:00:00", "01:xx:00", "invalid", "4294967295:00:00:00", None):
        assert _duration_seconds(bad_dur) is None


async def test_client_collect_full_snapshot(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test collecting all three pages and excluding sensitive fields like WAN IP."""
    base = "https://192.168.1.254"
    register_gateway_pages(aioclient_mock, base=base, clear=False)

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

    # Non-firewall HTML table on firewall.ha degrades as parse_error
    register_gateway_pages(
        aioclient_mock,
        base=base,
        firewall_html="<table><tr><td>Access Code</td><td>Required</td></tr></table>",
    )
    degraded = await client.async_collect()
    assert degraded.firewall is None
    assert degraded.failed_pages == {"firewall": "parse_error"}


async def test_client_fail_fast_on_required_page_errors(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Test fast-fail on required page transport or parse errors without polling remaining pages."""
    base = "https://192.168.1.254"
    client = BgwGatewayClient(base, session=async_get_clientsession(hass, verify_ssl=False))

    # HTTP 502 on sysinfo.ha -> fails immediately after 1 request
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", status=502)
    with pytest.raises(BgwConnectionError):
        await client.async_collect()
    assert aioclient_mock.call_count == 1

    # No table rows or missing Model Number on sysinfo.ha -> BgwParseError after 1 request
    for bad_sys in (
        "<html>No tables here</html>",
        "<table><tr><td>Foo</td><td>Bar</td></tr></table>",
    ):
        register_gateway_pages(aioclient_mock, base=base, system_html=bad_sys)
        with pytest.raises(BgwParseError):
            await client.async_collect()
        assert aioclient_mock.call_count == 1


async def test_client_chunked_read_and_cap() -> None:
    """Test async_fetch_page loops across chunks and enforces MAX_RESPONSE_BYTES."""

    class _Stream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._it = iter(chunks)

        async def read(self, _n: int) -> bytes:
            return next(self._it, b"")

    class _FakeClient:
        status = 200

        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = chunks

        @property
        def content(self) -> _Stream:
            return _Stream(self._chunks)

        def get(self, *_a: object, **_kw: object) -> _FakeClient:
            return self

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

    for chunks, expected_len, expected_text in (
        ([b"ab", b"cd"], 4, "abcd"),
        ([b"x" * (MAX_RESPONSE_BYTES - 1), b"yy"], MAX_RESPONSE_BYTES, None),
    ):
        client = BgwGatewayClient("https://192.168.1.254", session=_FakeClient(chunks))  # type: ignore[arg-type]
        body = await client.async_fetch_page("system")
        assert len(body) == expected_len
        if expected_text is not None:
            assert body == expected_text
