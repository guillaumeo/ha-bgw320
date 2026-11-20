"""Shared pytest fixtures for AT&T BGW320 tests."""

from __future__ import annotations

import importlib.util
from collections.abc import Generator
from typing import Any

import pytest

if importlib.util.find_spec("pytest_homeassistant_custom_component") is not None:
    pytest_plugins = ["pytest_homeassistant_custom_component"]
else:
    pytest_plugins = ["tests.conftest"]


SYSTEM_HTML = """
<table>
  <tr><td>Manufacturer</td><td>Nokia</td></tr>
  <tr><td>Model Number</td><td>BGW320-505</td></tr>
  <tr><td>Serial Number</td><td>SECRET-SERIAL-999</td></tr>
  <tr><td>Software Version</td><td>6.28.7</td></tr>
  <tr><td>MAC Address</td><td>AA:BB:CC:DD:EE:FF</td></tr>
  <tr><td>Time Since Last Reboot</td><td>02:03:04:05</td></tr>
</table>
"""

BROADBAND_HTML = """
<table>
  <tr><td>Broadband Connection</td><td>Up</td></tr>
  <tr><td>Broadband Network Type</td><td>PON</td></tr>
  <tr><td>Broadband IPv4 Address</td><td>203.0.113.42</td></tr>
  <tr><td>Line State</td><td>Up</td></tr>
  <tr><td>Current Speed (Mbps)</td><td>5000</td></tr>
  <tr><td>Current Duplex</td><td>Full</td></tr>
  <tr><td>Receive Packets</td><td>987,654</td></tr>
  <tr><td>Transmit Packets</td><td>456,789</td></tr>
  <tr><td>Receive Bytes</td><td>10,737,418,240</td></tr>
  <tr><td>Transmit Bytes</td><td>5,368,709,120</td></tr>
  <tr><td>Receive Drops</td><td>3</td></tr>
  <tr><td>Transmit Drops</td><td>1</td></tr>
  <tr><td>Receive Errors</td><td>4</td></tr>
  <tr><td>Transmit Errors</td><td>2</td></tr>
  <tr><td>Collisions</td><td>0</td></tr>
  <tr><td>Transmit Discards</td><td>7</td></tr>
</table>
"""

FIREWALL_HTML = """
<table>
  <tr><td>Packet Filter</td><td>On</td></tr>
  <tr><td>IP Passthrough</td><td>On</td></tr>
  <tr><td>NAT Default Server</td><td>Off</td></tr>
  <tr><td>Firewall Advanced</td><td>On</td></tr>
</table>
"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Automatically enable custom integrations in all tests."""
    yield


def register_gateway_pages(
    aioclient_mock: Any,
    base: str = "https://192.168.1.254",
    system_html: str = SYSTEM_HTML,
    broadband_html: str = BROADBAND_HTML,
    firewall_html: str | None = FIREWALL_HTML,
    *,
    clear: bool = True,
) -> None:
    """Register mocked gateway HTML status pages."""
    if clear:
        aioclient_mock.clear_requests()
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=system_html)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=broadband_html)
    if firewall_html is None:
        aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", status=503)
    else:
        aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=firewall_html)
