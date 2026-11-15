"""Sensor platform for the BGW320 Probe integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import BgwCoordinatorData, BgwProbeConfigEntry
from .entity import BgwProbeEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BgwSensorEntityDescription(SensorEntityDescription):
    """Describe a BGW320 Probe sensor."""

    value_fn: Callable[[BgwCoordinatorData], StateType | datetime]
    available_fn: Callable[[BgwCoordinatorData], bool] = lambda _: True


def _has_firewall(data: BgwCoordinatorData) -> bool:
    """Return True if the firewall status page succeeded."""
    return data.snapshot.firewall is not None


def _firewall_sensor(key: str, attr: str) -> BgwSensorEntityDescription:
    """Build a disabled-by-default diagnostic firewall sensor description."""
    return BgwSensorEntityDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        available_fn=_has_firewall,
        value_fn=lambda data: (
            getattr(data.snapshot.firewall, attr)
            if data.snapshot.firewall is not None
            else None
        ),
    )


SENSORS: tuple[BgwSensorEntityDescription, ...] = (
    # Primary / enabled-by-default entities
    BgwSensorEntityDescription(
        key="last_reboot",
        translation_key="last_reboot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_reboot,
    ),
    BgwSensorEntityDescription(
        key="speed_mbps",
        translation_key="speed_mbps",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.snapshot.broadband.speed_mbps,
    ),
    BgwSensorEntityDescription(
        key="rx_bytes",
        translation_key="rx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.rx_bytes,
    ),
    BgwSensorEntityDescription(
        key="tx_bytes",
        translation_key="tx_bytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.tx_bytes,
    ),
    BgwSensorEntityDescription(
        key="rx_packets",
        translation_key="rx_packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.rx_packets,
    ),
    BgwSensorEntityDescription(
        key="tx_packets",
        translation_key="tx_packets",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.tx_packets,
    ),
    BgwSensorEntityDescription(
        key="rx_errors",
        translation_key="rx_errors",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.rx_errors,
    ),
    BgwSensorEntityDescription(
        key="tx_errors",
        translation_key="tx_errors",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.tx_errors,
    ),
    # Secondary / disabled-by-default diagnostic entities (full bgw-probe parity)
    BgwSensorEntityDescription(
        key="network_type",
        translation_key="network_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.snapshot.broadband.network_type,
    ),
    BgwSensorEntityDescription(
        key="line_state",
        translation_key="line_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.snapshot.broadband.line_state,
    ),
    BgwSensorEntityDescription(
        key="duplex",
        translation_key="duplex",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.snapshot.broadband.duplex,
    ),
    BgwSensorEntityDescription(
        key="rx_drops",
        translation_key="rx_drops",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.rx_drops,
    ),
    BgwSensorEntityDescription(
        key="tx_drops",
        translation_key="tx_drops",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.tx_drops,
    ),
    BgwSensorEntityDescription(
        key="collisions",
        translation_key="collisions",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.collisions,
    ),
    BgwSensorEntityDescription(
        key="tx_discards",
        translation_key="tx_discards",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.snapshot.broadband.tx_discards,
    ),
    _firewall_sensor("firewall_packet_filter", "packet_filter"),
    _firewall_sensor("firewall_ip_passthrough", "ip_passthrough"),
    _firewall_sensor("firewall_nat_default_server", "nat_default_server"),
    _firewall_sensor("firewall_advanced", "advanced"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BgwProbeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BGW320 Probe sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        BgwSensorEntity(coordinator, description) for description in SENSORS
    )


class BgwSensorEntity(BgwProbeEntity, SensorEntity):
    """Representation of a BGW320 Probe sensor."""

    entity_description: BgwSensorEntityDescription

    @property
    @override
    def available(self) -> bool:
        """Return True if coordinator and backing page data are available."""
        return super().available and self.entity_description.available_fn(
            self.coordinator.data
        )

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
