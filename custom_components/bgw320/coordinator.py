"""DataUpdateCoordinator for the AT&T BGW320 integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BgwConnectionError, BgwError, BgwGatewayClient, BgwSnapshot
from .const import BOOT_TIME_DRIFT_TOLERANCE, DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER

type BgwConfigEntry = ConfigEntry[BgwCoordinator]


@dataclass(frozen=True, slots=True)
class BgwCoordinatorData:
    """Processed gateway snapshot and stabilized boot timestamp."""

    snapshot: BgwSnapshot
    last_reboot: datetime | None


class BgwCoordinator(DataUpdateCoordinator[BgwCoordinatorData]):
    """Coordinate periodic polling of an AT&T BGW gateway."""

    config_entry: BgwConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BgwConfigEntry,
        client: BgwGatewayClient,
    ) -> None:
        """Initialize the AT&T BGW320 coordinator."""
        super().__init__(
            hass,
            logger=LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{client.base_url}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.device_identifier: str = config_entry.unique_id or config_entry.entry_id
        self._last_reboot: datetime | None = None
        self._current_firmware: str | None = None
        self._firewall_degraded_logged = False

    def _resolve_last_reboot(self, uptime_seconds: int | None) -> datetime | None:
        """Compute a drift-tolerant UTC boot timestamp so DB only writes on reboot."""
        if uptime_seconds is None:
            return None
        candidate = (dt_util.utcnow() - timedelta(seconds=uptime_seconds)).replace(
            microsecond=0
        )
        if (
            self._last_reboot is None
            or abs((candidate - self._last_reboot).total_seconds())
            > BOOT_TIME_DRIFT_TOLERANCE.total_seconds()
        ):
            self._last_reboot = candidate
        return self._last_reboot

    @override
    async def _async_update_data(self) -> BgwCoordinatorData:
        """Fetch the latest status pages from the gateway."""
        try:
            snapshot = await self.client.async_collect()
        except BgwConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except BgwError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_response",
            ) from err

        if "firewall" in snapshot.failed_pages:
            if not self._firewall_degraded_logged:
                LOGGER.warning(
                    "BGW firewall status page unavailable (%s); continuing with degraded snapshot",
                    snapshot.failed_pages["firewall"],
                )
                self._firewall_degraded_logged = True
        elif self._firewall_degraded_logged:
            LOGGER.info("BGW firewall status page recovered")
            self._firewall_degraded_logged = False

        firmware = snapshot.gateway.firmware
        if self._current_firmware is not None and firmware != self._current_firmware:
            device_registry = dr.async_get(self.hass)
            if hasattr(device_registry, "async_get_device_by_identifier"):
                device_entry = device_registry.async_get_device_by_identifier(
                    (DOMAIN, self.device_identifier),
                    self.config_entry.entry_id,
                )
            else:  # pragma: no cover - compatibility with pre-2026 HA releases
                device_entry = device_registry.async_get_device(
                    identifiers={(DOMAIN, self.device_identifier)}
                )
            if device_entry is not None:
                device_registry.async_update_device(
                    device_entry.id,
                    sw_version=firmware,
                )
        self._current_firmware = firmware

        return BgwCoordinatorData(
            snapshot=snapshot,
            last_reboot=self._resolve_last_reboot(snapshot.gateway.uptime_seconds),
        )
