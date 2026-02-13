import voluptuous as vol
import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
from .const import DOMAIN, LOGIN_URL, CLIENT_ID, CLIENT_SECRET
import logging

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

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Fetch the access token
            client_secret = user_input.get("client_secret", CLIENT_SECRET)
            access_token = await self._fetch_access_token(
                user_input["username"], user_input["password"], client_secret
            )

            if access_token:
                # Fetch the list of meters after getting the access token
                meters = await self._fetch_meters(access_token)

                if meters:
                    # Store the access token and meter choices in instance variables
                    self._access_token = access_token
                    self._username = user_input["username"]
                    self._password = user_input["password"]
                    self._client_secret = client_secret
                    self._meter_choices = {
                        meter["meterId"]: f"{meter['consumerName']} - {meter['scNum']}"
                        for meter in meters
                    }

                    # Move to the next step where the user selects a meter
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
            _LOGGER.debug(f"Access token: {self._access_token}")
            
            if meter_id:
                data_url = f"https://app.nea.org.np/api/v1/meters/{meter_id}/details"
                # Create the entry using the stored access token
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

    async def _fetch_access_token(self, username, password, client_secret=CLIENT_SECRET):
        """Fetch the access token using username and password."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        payload = {
            "username": username,
            "password": password,
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "grant_type": "password",
        }
        
        try:
            async with session.post(
                LOGIN_URL,
                json=payload,
                timeout=30
            ) as response:
                _LOGGER.debug(f"Login response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(f"Access token response data: {data}")
                    return data.get("access_token")
                elif response.status == 401:
                    _LOGGER.error("Invalid credentials provided.")
                    return None
                else:
                    _LOGGER.error(f"Failed to fetch access token: {response.status}")
                    return None
        except aiohttp.ClientConnectionError as e:
            _LOGGER.error(f"Connection error fetching access token: {e}")
            return None
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Error fetching access token: {e}")
            return None

    async def _fetch_meters(self, access_token):
        """Fetch the list of meters using the access token."""
        session = aiohttp_client.async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with session.get(
                "https://app.nea.org.np/api/v1/meters/my-meters",
                headers=headers,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", [])
                else:
                    _LOGGER.error(f"Failed to fetch meters: {response.status}")
                    return None
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Error fetching meters: {e}")
            return None