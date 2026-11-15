"""The BGW320 Probe integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BgwGatewayClient
from .const import DEFAULT_TIMEOUT, DEFAULT_VERIFY_SSL
from .coordinator import BgwProbeConfigEntry, BgwProbeCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: BgwProbeConfigEntry) -> bool:
    """Set up BGW320 Probe from a config entry."""
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = BgwGatewayClient(
        base_url=entry.data[CONF_URL],
        session=session,
        timeout=DEFAULT_TIMEOUT,
    )

    coordinator = BgwProbeCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BgwProbeConfigEntry) -> bool:
    """Unload a BGW320 Probe config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
