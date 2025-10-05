"""Config flow for Marstek Local API integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import dhcp
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import MarstekAPIError, MarstekUDPClient
from .const import CONF_PORT, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    api = MarstekUDPClient(hass, data.get(CONF_HOST), data[CONF_PORT])

    try:
        await api.connect()

        # Try to get device info
        device_info = await api.get_device_info()

        if not device_info:
            raise CannotConnect("Failed to get device information")

        # Return info that you want to store in the config entry.
        return {
            "title": f"{device_info.get('device', 'Marstek Device')} ({device_info.get('wifi_mac', 'Unknown')})",
            "device": device_info.get("device"),
            "firmware": device_info.get("ver"),
            "mac": device_info.get("wifi_mac"),
        }

    except MarstekAPIError as err:
        _LOGGER.error("Error connecting to Marstek device: %s", err)
        raise CannotConnect from err
    finally:
        await api.disconnect()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Marstek Local API."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Start discovery
        return await self.async_step_discovery()

    async def async_step_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle discovery of devices."""
        errors = {}

        if user_input is None:
            # Perform discovery
            api = MarstekUDPClient(self.hass, port=DEFAULT_PORT)
            try:
                await api.connect()
                self._discovered_devices = await api.discover_devices()
                await api.disconnect()

                if not self._discovered_devices:
                    # No devices found, offer manual entry
                    return await self.async_step_manual()

                # Build list of discovered devices
                devices_list = {
                    device["mac"]: f"{device['name']} ({device['ip']})"
                    for device in self._discovered_devices
                }

                # Add manual entry option
                devices_list["manual"] = "Manual IP entry"

                return self.async_show_form(
                    step_id="discovery",
                    data_schema=vol.Schema(
                        {
                            vol.Required("device"): vol.In(devices_list),
                        }
                    ),
                    errors=errors,
                )

            except Exception as err:
                _LOGGER.error("Discovery failed: %s", err)
                await api.disconnect()
                return await self.async_step_manual()

        # User selected a device
        selected = user_input["device"]

        if selected == "manual":
            return await self.async_step_manual()

        # Find selected device
        device = next(
            (d for d in self._discovered_devices if d["mac"] == selected), None
        )

        if not device:
            errors["base"] = "device_not_found"
            return self.async_show_form(step_id="discovery", errors=errors)

        # Check if already configured
        await self.async_set_unique_id(device["mac"])
        self._abort_if_unique_id_configured()

        # Create entry
        return self.async_create_entry(
            title=f"{device['name']} ({device['ip']})",
            data={
                CONF_HOST: device["ip"],
                CONF_PORT: DEFAULT_PORT,
                "mac": device["mac"],
                "device": device["name"],
                "firmware": device["firmware"],
            },
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual IP entry."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Check if already configured
                await self.async_set_unique_id(info["mac"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        "mac": info["mac"],
                        "device": info["device"],
                        "firmware": info["firmware"],
                    },
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: dhcp.DhcpServiceInfo
    ) -> FlowResult:
        """Handle DHCP discovery."""
        # Extract info from DHCP discovery
        host = discovery_info.ip
        mac = discovery_info.macaddress

        # Validate the device
        try:
            info = await validate_input(
                self.hass,
                {CONF_HOST: host, CONF_PORT: DEFAULT_PORT}
            )

            # Check if already configured
            await self.async_set_unique_id(info["mac"])
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

            # Store discovery info for confirmation
            self.context["title_placeholders"] = {"name": info["title"]}
            self.context["device_info"] = {
                CONF_HOST: host,
                CONF_PORT: DEFAULT_PORT,
                "mac": info["mac"],
                "device": info["device"],
                "firmware": info["firmware"],
            }

            return await self.async_step_discovery_confirm()

        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during DHCP discovery")
            return self.async_abort(reason="unknown")

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            device_info = self.context["device_info"]
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data=device_info,
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders=self.context.get("title_placeholders"),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Marstek Local API."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self.config_entry.options.get(
                            "scan_interval", DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
