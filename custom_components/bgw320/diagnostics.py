"""Diagnostics support for the AT&T BGW320 integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import BgwConfigEntry

TO_REDACT: set[str] = {
    CONF_URL,
    "mac_address",
    "serial_number",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: BgwConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a AT&T BGW320 config entry."""
    data = entry.runtime_data.data
    payload: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "unique_id": entry.unique_id,
        },
        "snapshot": asdict(data.snapshot),
        "last_reboot": data.last_reboot.isoformat() if data.last_reboot else None,
    }
    return async_redact_data(payload, TO_REDACT)
