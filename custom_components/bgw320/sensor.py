"""Sensor platform for the AT&T BGW320 integration."""

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

from .coordinator import BgwConfigEntry, BgwCoordinatorData
from .entity import BgwEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BgwSensorEntityDescription(SensorEntityDescription):
    """Describe a AT&T BGW320 sensor."""

    value_fn: Callable[[BgwCoordinatorData], StateType | datetime]
    available_fn: Callable[[BgwCoordinatorData], bool] = lambda _: True


_TOTAL = SensorStateClass.TOTAL_INCREASING
_DIAG = EntityCategory.DIAGNOSTIC


def _bb_val(key: str) -> Callable[[BgwCoordinatorData], StateType]:
    return lambda data: getattr(data.snapshot.broadband, key)


def _bb(
    keys: tuple[str, ...],
    *,
    dc: SensorDeviceClass | None = None,
    unit: str | None = None,
    sugg: str | None = None,
    prec: int | None = None,
    sc: SensorStateClass | None = None,
    cat: EntityCategory | None = _DIAG,
    enabled: bool = True,
) -> tuple[BgwSensorEntityDescription, ...]:
    """Build broadband sensor descriptions reading each key from BroadbandInfo."""
    return tuple(
        BgwSensorEntityDescription(
            key=k,
            translation_key=k,
            device_class=dc,
            native_unit_of_measurement=unit,
            suggested_unit_of_measurement=sugg,
            suggested_display_precision=prec,
            state_class=sc,
            entity_category=cat,
            entity_registry_enabled_default=enabled,
            value_fn=_bb_val(k),
        )
        for k in keys
    )


def _fw(attr: str) -> BgwSensorEntityDescription:
    """Build a disabled-by-default diagnostic firewall sensor description."""
    key = f"firewall_{attr}"
    return BgwSensorEntityDescription(
        key=key,
        translation_key=key,
        entity_category=_DIAG,
        entity_registry_enabled_default=False,
        available_fn=lambda data: data.snapshot.firewall is not None,
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
        entity_category=_DIAG,
        value_fn=lambda data: data.last_reboot,
    ),
    *_bb(
        ("speed_mbps",),
        dc=SensorDeviceClass.DATA_RATE,
        unit=UnitOfDataRate.MEGABITS_PER_SECOND,
        sc=SensorStateClass.MEASUREMENT,
        cat=None,
    ),
    *_bb(
        ("rx_bytes", "tx_bytes"),
        dc=SensorDeviceClass.DATA_SIZE,
        unit=UnitOfInformation.BYTES,
        sugg=UnitOfInformation.GIGABYTES,
        prec=2,
        sc=_TOTAL,
        cat=None,
    ),
    *_bb(("rx_packets", "tx_packets"), sc=_TOTAL, cat=None),
    *_bb(("rx_errors", "tx_errors"), sc=_TOTAL),
    # Secondary / disabled-by-default diagnostic entities (full bgw-probe parity)
    *_bb(("network_type", "line_state", "duplex"), enabled=False),
    *_bb(("rx_drops", "tx_drops", "collisions", "tx_discards"), sc=_TOTAL, enabled=False),
    *(_fw(a) for a in ("packet_filter", "ip_passthrough", "nat_default_server", "advanced")),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BgwConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AT&T BGW320 sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        BgwSensorEntity(coordinator, description) for description in SENSORS
    )


class BgwSensorEntity(BgwEntity, SensorEntity):
    """Representation of a AT&T BGW320 sensor."""

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
        if (data := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(data)
