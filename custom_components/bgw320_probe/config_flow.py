"""Config flow for the BGW320 Probe integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, override
from urllib.parse import urlparse

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    import probatio as vol
else:
    try:
        import probatio as vol
    except ModuleNotFoundError:  # pragma: no cover - pre-2026 HA fallback
        import voluptuous as vol

from .api import (
    BgwConnectionError,
    BgwGatewayClient,
    BgwInvalidUrlError,
    BgwParseError,
    BgwSnapshot,
    normalize_gateway_url,
)
from .const import DEFAULT_TIMEOUT, DEFAULT_URL, DEFAULT_VERIFY_SSL, DOMAIN, LOGGER


def _derive_unique_id(snapshot: BgwSnapshot, normalized_url: str) -> str:
    """Derive a hardware-stable unique ID from validated MAC, serial, or host:port."""
    if snapshot.gateway.mac_address:
        return snapshot.gateway.mac_address
    if snapshot.gateway.serial_number:
        return snapshot.gateway.serial_number.lower()
    netloc = urlparse(normalized_url).netloc or normalized_url
    return netloc.lower()


class BgwProbeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle UI configuration and reconfiguration for BGW320 Probe."""

    VERSION = 1

    async def _async_validate_input(
        self, user_input: Mapping[str, Any]
    ) -> tuple[str, bool, BgwSnapshot]:
        """Validate the gateway URL and perform a live status probe."""
        normalized_url = normalize_gateway_url(str(user_input[CONF_URL]))
        verify_ssl = bool(user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        client = BgwGatewayClient(
            base_url=normalized_url,
            session=session,
            timeout=DEFAULT_TIMEOUT,
        )
        snapshot = await client.async_collect()
        return normalized_url, verify_ssl, snapshot

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        default_url = DEFAULT_URL
        default_verify_ssl = DEFAULT_VERIFY_SSL

        if self.source == SOURCE_RECONFIGURE:
            reconfigure_entry = self._get_reconfigure_entry()
            default_url = reconfigure_entry.data.get(CONF_URL, DEFAULT_URL)
            default_verify_ssl = reconfigure_entry.data.get(
                CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL
            )

        if user_input is not None:
            default_url = str(user_input.get(CONF_URL, default_url))
            default_verify_ssl = bool(
                user_input.get(CONF_VERIFY_SSL, default_verify_ssl)
            )
            try:
                normalized_url, verify_ssl, snapshot = await self._async_validate_input(
                    user_input
                )
            except BgwInvalidUrlError:
                errors[CONF_URL] = "invalid_url"
            except BgwConnectionError:
                errors["base"] = "cannot_connect"
            except BgwParseError:
                errors["base"] = "invalid_response"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error validating BGW gateway")
                errors["base"] = "unknown"
            else:
                unique_id = _derive_unique_id(snapshot, normalized_url)
                await self.async_set_unique_id(unique_id, raise_on_progress=False)

                if self.source == SOURCE_RECONFIGURE:
                    reconfigure_entry = self._get_reconfigure_entry()
                    if reconfigure_entry.unique_id is not None:
                        self._abort_if_unique_id_mismatch(reason="unique_id_mismatch")
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data_updates={
                            CONF_URL: normalized_url,
                            CONF_VERIFY_SSL: verify_ssl,
                        },
                    )

                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=snapshot.gateway.model,
                    data={
                        CONF_URL: normalized_url,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                )

        step_id = "reconfigure" if self.source == SOURCE_RECONFIGURE else "user"
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=default_url): str,
                    vol.Required(CONF_VERIFY_SSL, default=default_verify_ssl): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of gateway URL or TLS verification."""
        return await self.async_step_user(user_input)
