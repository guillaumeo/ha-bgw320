"""Binary sensor platform for the BGW320 Probe integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BgwCoordinatorData, BgwProbeConfigEntry
from .entity import BgwProbeEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BgwBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a BGW320 Probe binary sensor."""

    value_fn: Callable[[BgwCoordinatorData], bool | None]


BINARY_SENSORS: tuple[BgwBinarySensorEntityDescription, ...] = (
    BgwBinarySensorEntityDescription(
        key="broadband_connection",
        translation_key="broadband_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: (
            data.snapshot.broadband.connection == "up"
            and data.snapshot.broadband.line_state == "up"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BgwProbeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BGW320 Probe binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        BgwBinarySensorEntity(coordinator, description)
        for description in BINARY_SENSORS
    )


class BgwBinarySensorEntity(BgwProbeEntity, BinarySensorEntity):
    """Representation of a BGW320 Probe binary sensor."""

    entity_description: BgwBinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.value_fn(self.coordinator.data)
