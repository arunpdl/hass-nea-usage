DOMAIN = "nea_electricity_usage"
LOGIN_URL = "https://app.nea.org.np/api/v1/auth/login"
CLIENT_ID = "1"
CLIENT_SECRET = "xQ8yr3Oe2jrvR0X6UZ8Okr2CSyJij2AgcWVrvT6QsTgpnW4HEqbWIwI436cPzVK6"

CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"
# NEA billing data changes at most monthly - polling every 5 minutes (the old
# default) only wastes calls against a reverse-engineered API. Configurable
# via the integration's Options.
DEFAULT_SCAN_INTERVAL_HOURS = 6
