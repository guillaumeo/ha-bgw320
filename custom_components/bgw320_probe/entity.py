"""Base entity for the BGW320 Probe integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BgwProbeCoordinator


class BgwProbeEntity(CoordinatorEntity[BgwProbeCoordinator]):
    """Base entity shared by BGW320 Probe platforms."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BgwProbeCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the base entity and link it to the gateway DeviceInfo."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_identifier}_{description.key}"

        gateway = coordinator.data.snapshot.gateway
        connections: set[tuple[str, str]] = (
            {(dr.CONNECTION_NETWORK_MAC, gateway.mac_address)}
            if gateway.mac_address
            else set()
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_identifier)},
            connections=connections,
            manufacturer=gateway.manufacturer or "AT&T",
            model=gateway.model,
            sw_version=gateway.firmware,
            configuration_url=coordinator.config_entry.data[CONF_URL],
        )
