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
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.device_identifier: str = config_entry.unique_id or config_entry.entry_id
        self._last_reboot: datetime | None = None
        self._last_uptime: int | None = None
        self._last_firmware: str | None = None
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
            or (self._last_uptime is not None and uptime_seconds < self._last_uptime)
            or abs(candidate - self._last_reboot) > BOOT_TIME_DRIFT_TOLERANCE
        ):
            self._last_reboot = candidate
        self._last_uptime = uptime_seconds
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

        if fw_err := snapshot.failed_pages.get("firewall"):
            if not self._firewall_degraded_logged:
                LOGGER.warning(
                    "BGW firewall status page unavailable (%s); continuing with degraded snapshot",
                    fw_err,
                )
                self._firewall_degraded_logged = True
        elif self._firewall_degraded_logged:
            LOGGER.info("BGW firewall status page recovered")
            self._firewall_degraded_logged = False

        if firmware := snapshot.gateway.firmware:
            if self.data is not None and firmware != self._last_firmware:
                reg = dr.async_get(self.hass)
                ident = (DOMAIN, self.device_identifier)
                device = (
                    reg.async_get_device_by_identifier(ident, self.config_entry.entry_id)
                    if hasattr(reg, "async_get_device_by_identifier")
                    else reg.async_get_device(identifiers={ident})
                )
                if device is not None:
                    reg.async_update_device(device.id, sw_version=firmware)
            self._last_firmware = firmware

        return BgwCoordinatorData(
            snapshot=snapshot,
            last_reboot=self._resolve_last_reboot(snapshot.gateway.uptime_seconds),
        )
