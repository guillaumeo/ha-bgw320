"""Base entity for the AT&T BGW320 integration."""

from __future__ import annotations

from typing import override

from homeassistant.const import CONF_URL
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BgwCoordinator


class BgwEntity(CoordinatorEntity[BgwCoordinator]):
    """Base entity shared by AT&T BGW320 platforms."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BgwCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the base entity and link it to the gateway DeviceInfo."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_identifier}_{description.key}"

        gateway = (
            coordinator.data.snapshot.gateway
            if coordinator.data is not None
            else None
        )
        connections: set[tuple[str, str]] = (
            {(dr.CONNECTION_NETWORK_MAC, gateway.mac_address)}
            if gateway and gateway.mac_address
            else set()
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_identifier)},
            connections=connections,
            manufacturer=(gateway.manufacturer if gateway else None) or "AT&T",
            model=gateway.model if gateway else None,
            sw_version=gateway.firmware if gateway else None,
            configuration_url=coordinator.config_entry.data[CONF_URL],
        )

    @property
    @override
    def available(self) -> bool:
        """Return True if coordinator has valid data."""
        return super().available and self.coordinator.data is not None
