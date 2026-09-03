"""Shared helpers for talking to the NEA API."""
import logging
import ssl

import aiohttp

from .const import LOGIN_URL, CLIENT_ID

_LOGGER = logging.getLogger(__name__)

# NEA's server uses a certificate that can't be verified against standard
# CA bundles. Used for all NEA API calls.
NEA_SSL_CONTEXT = ssl.create_default_context()
NEA_SSL_CONTEXT.check_hostname = False
NEA_SSL_CONTEXT.verify_mode = ssl.CERT_NONE


async def fetch_access_token(
    session: aiohttp.ClientSession, username: str, password: str, client_secret: str
) -> str | None:
    """Log in to the NEA API and return a fresh access token, or None on failure.

    Shared by the config flow (initial login) and the update coordinator
    (silent re-login when a token expires) so there's one place that knows
    how to talk to NEA's auth endpoint.
    """
    payload = {
        "username": username,
        "password": password,
        "client_id": CLIENT_ID,
        "client_secret": client_secret,
        "grant_type": "password",
    }

    try:
        async with session.post(
            LOGIN_URL, json=payload, timeout=30, ssl=NEA_SSL_CONTEXT
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("access_token")
            if response.status == 401:
                _LOGGER.error("Invalid NEA credentials")
            else:
                _LOGGER.error("Failed to fetch access token: %s", response.status)
            return None
    except aiohttp.ClientError as err:
        _LOGGER.error("Error fetching access token: %s", err)
        return None
