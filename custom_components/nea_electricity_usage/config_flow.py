import voluptuous as vol
import logging

import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .api import fetch_access_token, NEA_SSL_CONTEXT
from .const import (
    DOMAIN,
    CLIENT_SECRET,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class ElectricityUsageFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for electricity usage."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the flow."""
        self._access_token = None
        self._meter_choices = None
        self._username = None
        self._password = None
        self._client_secret = None
        self._reauth_entry = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ElectricityUsageOptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            client_secret = user_input.get("client_secret", CLIENT_SECRET)
            session = aiohttp_client.async_get_clientsession(self.hass)
            access_token = await fetch_access_token(
                session, user_input["username"], user_input["password"], client_secret
            )

            if access_token:
                meters = await self._fetch_meters(access_token)

                if meters:
                    self._access_token = access_token
                    self._username = user_input["username"]
                    self._password = user_input["password"]
                    self._client_secret = client_secret
                    self._meter_choices = {
                        meter["meterId"]: f"{meter['consumerName']} - {meter['scNum']}"
                        for meter in meters
                    }

                    return await self.async_step_select_meter()
                else:
                    errors["base"] = "cannot_fetch_meters"
            else:
                errors["base"] = "invalid_credentials"

        data_schema = vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Optional("client_secret"): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_select_meter(self, user_input=None):
        """Handle the step for selecting a meter."""
        errors = {}

        if user_input is not None:
            meter_id = user_input.get("meter_id")

            if meter_id:
                await self.async_set_unique_id(str(meter_id))
                self._abort_if_unique_id_configured()

                data_url = f"https://app.nea.org.np/api/v1/meters/{meter_id}/details"
                return self.async_create_entry(
                    title="Electricity Usage",
                    data={
                        "access_token": self._access_token,
                        "data_url": data_url,
                        "username": self._username,
                        "password": self._password,
                        "client_secret": self._client_secret,
                    },
                )

            errors["base"] = "no_meter_selected"

        data_schema = vol.Schema(
            {
                vol.Required("meter_id"): vol.In(self._meter_choices),
            }
        )

        return self.async_show_form(
            step_id="select_meter", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(self, entry_data):
        """Start a reauth flow when stored NEA credentials stop working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for fresh NEA credentials and update the existing entry in place."""
        errors = {}

        if user_input is not None:
            client_secret = user_input.get("client_secret", CLIENT_SECRET)
            session = aiohttp_client.async_get_clientsession(self.hass)
            access_token = await fetch_access_token(
                session, user_input["username"], user_input["password"], client_secret
            )

            if access_token:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        "access_token": access_token,
                        "username": user_input["username"],
                        "password": user_input["password"],
                        "client_secret": client_secret,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

            errors["base"] = "invalid_credentials"

        data_schema = vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Optional("client_secret"): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=data_schema, errors=errors
        )

    async def _fetch_meters(self, access_token):
        """Fetch the list of meters using the access token."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with session.get(
                "https://app.nea.org.np/api/v1/meters/my-meters",
                headers=headers,
                timeout=30,
                ssl=NEA_SSL_CONTEXT,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                else:
                    _LOGGER.error("Failed to fetch meters: %s", response.status)
                    return None
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching meters: %s", err)
            return None


class ElectricityUsageOptionsFlowHandler(config_entries.OptionsFlow):
    """Options for electricity usage - currently just the poll interval."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL_HOURS, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=72)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
