"""Tests for BGW320 Probe diagnostics redaction."""

from __future__ import annotations

from conftest import BROADBAND_HTML, FIREWALL_HTML, SYSTEM_HTML
from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant

from custom_components.bgw320_probe.const import DOMAIN
from custom_components.bgw320_probe.diagnostics import (
    async_get_config_entry_diagnostics,
)

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    from tests.common import MockConfigEntry


async def test_diagnostics_redacts_identifiers_and_url(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Verify URL, MAC, serial, and unique_id are redacted in diagnostics output."""
    base = "https://192.168.1.254"
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=SYSTEM_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML)
    aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=FIREWALL_HTML)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BGW320-505",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={CONF_URL: base, CONF_VERIFY_SSL: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["unique_id"] == REDACTED
    assert diag["entry"]["data"][CONF_URL] == REDACTED
    assert diag["snapshot"]["gateway"]["mac_address"] == REDACTED
    assert diag["snapshot"]["gateway"]["serial_number"] == REDACTED
    assert diag["snapshot"]["gateway"]["model"] == "BGW320-505"
    assert diag["snapshot"]["broadband"]["speed_mbps"] == 5000

    rendered = repr(diag)
    assert "AA:BB:CC:DD:EE:FF" not in rendered
    assert "aa:bb:cc:dd:ee:ff" not in rendered
    assert "SECRET-SERIAL-999" not in rendered
    assert "192.168.1.254" not in rendered
    assert "203.0.113.42" not in rendered
