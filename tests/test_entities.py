"""Integration tests for AT&T BGW320 coordinator, device registry, and entities."""

from __future__ import annotations

from datetime import timedelta

from conftest import BROADBAND_HTML, FIREWALL_HTML, SYSTEM_HTML
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_URL,
    CONF_VERIFY_SSL,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.bgw320.const import DEFAULT_SCAN_INTERVAL, DOMAIN

try:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )
except ModuleNotFoundError:
    from tests.common import MockConfigEntry, async_fire_time_changed


def _register_pages(
    aioclient_mock,
    base: str = "https://192.168.1.254",
    system_html: str = SYSTEM_HTML,
    broadband_html: str = BROADBAND_HTML,
    firewall_html: str | None = FIREWALL_HTML,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{base}/cgi-bin/sysinfo.ha", text=system_html)
    aioclient_mock.get(f"{base}/cgi-bin/broadbandstatistics.ha", text=broadband_html)
    if firewall_html is None:
        aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", status=503)
    else:
        aioclient_mock.get(f"{base}/cgi-bin/firewall.ha", text=firewall_html)


async def test_setup_entities_device_and_unload(
    hass: HomeAssistant,
    aioclient_mock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test primary entities, disabled diagnostic entities, device MAC link, and unload."""
    _register_pages(aioclient_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BGW320-505",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # Verify Device Registry entry and MAC connection
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "aa:bb:cc:dd:ee:ff"), entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "Nokia"
    assert device.model == "BGW320-505"
    assert device.sw_version == "6.28.7"
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections

    # Verify enabled-by-default entities
    conn_state = hass.states.get("binary_sensor.bgw320_505_broadband_connection")
    assert conn_state is not None
    assert conn_state.state == STATE_ON

    speed_state = hass.states.get("sensor.bgw320_505_negotiated_speed")
    assert speed_state is not None
    assert speed_state.state == "5000"

    rx_state = hass.states.get("sensor.bgw320_505_broadband_received")
    assert rx_state is not None
    # Home Assistant converts native B (10 GiB = 10,737,418,240 B = 10.74 GB) via suggested_unit_of_measurement
    rx_entry = entity_registry.async_get("sensor.bgw320_505_broadband_received")
    assert rx_entry is not None
    assert rx_entry.capabilities is not None or rx_state.attributes.get(
        "unit_of_measurement"
    ) in {UnitOfInformation.BYTES, UnitOfInformation.GIGABYTES}

    assert hass.states.get("sensor.bgw320_505_received_packets").state == "987654"
    assert hass.states.get("sensor.bgw320_505_transmitted_packets").state == "456789"
    assert hass.states.get("sensor.bgw320_505_receive_errors").state == "4"
    assert hass.states.get("sensor.bgw320_505_transmit_errors").state == "2"

    reboot_state = hass.states.get("sensor.bgw320_505_last_reboot")
    assert reboot_state is not None
    initial_reboot = reboot_state.state

    # Verify secondary entities are registered as disabled by integration
    disabled_ids = [
        "sensor.bgw320_505_broadband_network_type",
        "sensor.bgw320_505_line_state",
        "sensor.bgw320_505_duplex",
        "sensor.bgw320_505_receive_drops",
        "sensor.bgw320_505_transmit_drops",
        "sensor.bgw320_505_collisions",
        "sensor.bgw320_505_transmit_discards",
        "sensor.bgw320_505_firewall_packet_filter",
        "sensor.bgw320_505_ip_passthrough",
        "sensor.bgw320_505_nat_default_server",
        "sensor.bgw320_505_firewall_advanced",
    ]
    for entity_id in disabled_ids:
        reg_entry = entity_registry.async_get(entity_id)
        assert reg_entry is not None
        assert reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Test last_reboot drift stabilization (uptime advances ~61s over a 60s poll)
    drifted_system = SYSTEM_HTML.replace("02:03:04:05", "02:03:05:06")
    upgraded_system = drifted_system.replace("6.28.7", "6.30.1")
    _register_pages(aioclient_mock, system_html=upgraded_system)

    async_fire_time_changed(hass, dt_util.utcnow() + DEFAULT_SCAN_INTERVAL)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bgw320_505_last_reboot").state == initial_reboot
    updated_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "aa:bb:cc:dd:ee:ff"), entry.entry_id
    )
    assert updated_device is not None
    assert updated_device.sw_version == "6.30.1"

    # Simulate an actual router reboot (uptime resets to 00:00:15) and WAN link down
    rebooted_system = upgraded_system.replace("02:03:05:06", "00:00:00:15")
    down_broadband = BROADBAND_HTML.replace(
        "<tr><td>Broadband Connection</td><td>Up</td></tr>",
        "<tr><td>Broadband Connection</td><td>Down</td></tr>",
    )
    _register_pages(
        aioclient_mock, system_html=rebooted_system, broadband_html=down_broadband
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bgw320_505_last_reboot").state != initial_reboot
    assert (
        hass.states.get("binary_sensor.bgw320_505_broadband_connection").state
        == STATE_OFF
    )

    # Clean unload
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_enabled_diagnostic_entities_and_partial_firewall_degradation(
    hass: HomeAssistant,
    aioclient_mock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test enabling diagnostic sensors and marking only firewall sensors unavailable on 503."""
    _register_pages(aioclient_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BGW320-505",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={CONF_URL: "https://192.168.1.254", CONF_VERIFY_SSL: False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Enable firewall IP passthrough and network type sensors
    for entity_id in (
        "sensor.bgw320_505_ip_passthrough",
        "sensor.bgw320_505_broadband_network_type",
    ):
        entity_registry.async_update_entity(entity_id, disabled_by=None)

    _register_pages(aioclient_mock)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bgw320_505_ip_passthrough").state == "on"
    assert hass.states.get("sensor.bgw320_505_broadband_network_type").state == "PON"

    # Firewall page fails -> firewall sensor becomes unavailable while broadband stays live
    _register_pages(aioclient_mock, firewall_html=None)
    async_fire_time_changed(hass, dt_util.utcnow() + DEFAULT_SCAN_INTERVAL)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.bgw320_505_ip_passthrough").state == STATE_UNAVAILABLE
    )
    assert hass.states.get("sensor.bgw320_505_broadband_network_type").state == "PON"
    assert (
        hass.states.get("binary_sensor.bgw320_505_broadband_connection").state
        == STATE_ON
    )

    # Firewall page recovers + uptime & optional counter absent
    sparse_system = SYSTEM_HTML.replace(
        "<tr><td>Time Since Last Reboot</td><td>02:03:04:05</td></tr>", ""
    )
    sparse_broadband = BROADBAND_HTML.replace(
        "<tr><td>Receive Drops</td><td>3</td></tr>", ""
    )
    _register_pages(
        aioclient_mock,
        system_html=sparse_system,
        broadband_html=sparse_broadband,
        firewall_html=FIREWALL_HTML,
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bgw320_505_ip_passthrough").state == "on"
    assert hass.states.get("sensor.bgw320_505_last_reboot").state == "unknown"

    # Unparseable HTML during poll -> marks entities unavailable via UpdateFailed
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/sysinfo.ha", text="<html>broken</html>"
    )
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/broadbandstatistics.ha", text=BROADBAND_HTML
    )
    aioclient_mock.get("https://192.168.1.254/cgi-bin/firewall.ha", text=FIREWALL_HTML)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.bgw320_505_negotiated_speed").state == STATE_UNAVAILABLE
    )

    # Full gateway outage -> all entities stay unavailable
    aioclient_mock.clear_requests()
    aioclient_mock.get("https://192.168.1.254/cgi-bin/sysinfo.ha", exc=TimeoutError())
    aioclient_mock.get(
        "https://192.168.1.254/cgi-bin/broadbandstatistics.ha", exc=TimeoutError()
    )
    aioclient_mock.get("https://192.168.1.254/cgi-bin/firewall.ha", exc=TimeoutError())
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=4))
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.bgw320_505_broadband_connection").state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get("sensor.bgw320_505_negotiated_speed").state == STATE_UNAVAILABLE
    )
