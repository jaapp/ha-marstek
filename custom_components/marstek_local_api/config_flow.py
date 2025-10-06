"""Config flow for Marstek Local API integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import dhcp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import MarstekAPIError, MarstekUDPClient
from .const import CONF_PORT, DATA_COORDINATOR, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any], use_ephemeral_port: bool = False) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    use_ephemeral_port: Deprecated parameter, kept for compatibility
    """
    # Always bind to device port (reuse_port allows multiple instances)
    target_port = data.get(CONF_PORT, DEFAULT_PORT)
    api = MarstekUDPClient(hass, data.get(CONF_HOST), target_port, remote_port=target_port)

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
            # Temporarily disconnect existing integration clients to avoid port conflicts
            paused_clients = []
            for entry in self._async_current_entries():
                if DOMAIN in self.hass.data and entry.entry_id in self.hass.data[DOMAIN]:
                    coordinator = self.hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
                    if coordinator:
                        # Handle both single-device and multi-device coordinators
                        if hasattr(coordinator, 'device_coordinators'):
                            # Multi-device coordinator
                            _LOGGER.debug("Pausing multi-device coordinator %s during discovery", entry.title)
                            for device_coordinator in coordinator.device_coordinators.values():
                                if device_coordinator.api:
                                    await device_coordinator.api.disconnect()
                                    paused_clients.append(device_coordinator.api)
                        elif hasattr(coordinator, 'api') and coordinator.api:
                            # Single-device coordinator
                            _LOGGER.debug("Pausing API client for %s during discovery", entry.title)
                            await coordinator.api.disconnect()
                            paused_clients.append(coordinator.api)

            # Wait a bit for disconnections to complete and sockets to close
            import asyncio
            await asyncio.sleep(1)

            # Bind to same port as device (required by Marstek protocol)
            api = MarstekUDPClient(self.hass, port=DEFAULT_PORT, remote_port=DEFAULT_PORT)
            try:
                await api.connect()
                self._discovered_devices = await api.discover_devices()
                await api.disconnect()

                _LOGGER.info("Discovered %d device(s): %s", len(self._discovered_devices), self._discovered_devices)
            except Exception as err:
                _LOGGER.error("Discovery failed: %s", err, exc_info=True)
                try:
                    await api.disconnect()
                except Exception:
                    pass  # Ignore disconnect errors
                return await self.async_step_manual()
            finally:
                # Wait a bit before resuming to ensure discovery socket is fully closed
                await asyncio.sleep(1)

                # Resume paused clients
                for client in paused_clients:
                    try:
                        _LOGGER.debug("Resuming paused API client for host %s", client.host)
                        await client.connect()
                    except Exception as err:
                        _LOGGER.warning("Failed to resume client for host %s: %s", client.host, err)

            if not self._discovered_devices:
                # No devices found, offer manual entry
                return await self.async_step_manual()

            # Build list of discovered devices
            devices_list = {}

            # Add "All devices" option if multiple devices found
            if len(self._discovered_devices) > 1:
                devices_list["__all__"] = f"All devices ({len(self._discovered_devices)} batteries)"

            for device in self._discovered_devices:
                mac = device["mac"]
                # Show all devices, the abort happens when user selects one already configured
                devices_list[mac] = f"{device['name']} ({device['ip']})"
                _LOGGER.debug("Adding device to list: %s (%s) MAC: %s", device['name'], device['ip'], mac)

            _LOGGER.info("Built device list with %d device(s)", len(devices_list))

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

        # User selected a device
        selected = user_input["device"]

        if selected == "manual":
            return await self.async_step_manual()

        # Check if user selected "All devices"
        if selected == "__all__":
            # Create multi-device entry
            # Use a synthetic unique ID based on all MACs
            all_macs = sorted([d["mac"] for d in self._discovered_devices])
            unique_id = "_".join(all_macs)

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Marstek System ({len(self._discovered_devices)} batteries)",
                data={
                    "devices": [
                        {
                            CONF_HOST: d["ip"],
                            CONF_PORT: DEFAULT_PORT,
                            "mac": d["mac"],
                            "device": d["name"],
                            "firmware": d["firmware"],
                        }
                        for d in self._discovered_devices
                    ],
                },
            )

        # Find selected device (single device mode)
        device = next(
            (d for d in self._discovered_devices if d["mac"] == selected), None
        )

        if not device:
            errors["base"] = "device_not_found"
            return self.async_show_form(step_id="discovery", errors=errors)

        # Check if already configured
        await self.async_set_unique_id(device["mac"])
        self._abort_if_unique_id_configured()

        # Create entry for single device
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

        # Validate the device using ephemeral port to avoid conflicts
        try:
            info = await validate_input(
                self.hass,
                {CONF_HOST: host, CONF_PORT: DEFAULT_PORT},
                use_ephemeral_port=True
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
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Marstek Local API."""

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
