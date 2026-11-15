"""Shared pytest fixtures for BGW320 Probe tests."""

from __future__ import annotations

import importlib.util
from collections.abc import Generator

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
