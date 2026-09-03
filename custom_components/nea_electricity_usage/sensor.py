from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers import aiohttp_client
from homeassistant.util import slugify
from datetime import timedelta
import logging
import aiohttp

from .api import fetch_access_token
from .nepali_calendar import bs_month_to_gregorian_start
from .const import (
    DOMAIN,
    CLIENT_SECRET,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

NEPALI_MONTHS_ORDER = [
    "Baisakh", "Jestha", "Ashad", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"
]

# Sentinel distinguishing "got a 401" from "no data" in the request layer,
# so the coordinator knows when it's worth trying to re-authenticate.
_UNAUTHORIZED = object()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the electricity usage sensors from a config entry."""
    coordinator = ElectricityUsageCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(f"Error during initial refresh: {err}")
        raise

    entities = []
    if coordinator.data:
        meter_name = coordinator.data.get("meter_name", "unknown")

        entities.extend([
            ElectricityTotalBillSensor(coordinator, meter_name),
            ElectricityTotalDuesSensor(coordinator, meter_name),
            ElectricityMeterNameSensor(coordinator, meter_name),
            ElectricityConsumerIDSensor(coordinator, meter_name),
            ElectricityScNumSensor(coordinator, meter_name),
            ElectricityMonthlyDataSensor(coordinator, meter_name),
            ElectricityMonthlyBillSensor(coordinator, meter_name),
        ])

    async_add_entities(entities, True)

class ElectricityUsageCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching electricity usage data.

    Re-authenticates automatically (using the username/password saved at
    setup time) when NEA's access token expires, instead of leaving every
    entity permanently unavailable after the first 401.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the coordinator."""
        scan_hours = entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=scan_hours),
        )
        self.entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self):
        """Fetch data from API, transparently re-logging in once if the token expired."""
        result = await self._request(self.entry.data["access_token"])

        if result is _UNAUTHORIZED:
            _LOGGER.info("NEA access token expired, logging in again")
            new_token = await fetch_access_token(
                self._session,
                self.entry.data["username"],
                self.entry.data["password"],
                self.entry.data.get("client_secret") or CLIENT_SECRET,
            )
            if not new_token:
                # Stored username/password no longer work - this needs a human,
                # so surface it as a reauth prompt instead of silently failing forever.
                raise ConfigEntryAuthFailed("Re-authentication with NEA failed")

            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "access_token": new_token}
            )
            result = await self._request(new_token)
            if result is _UNAUTHORIZED:
                raise ConfigEntryAuthFailed("NEA rejected refreshed credentials")

        if result is None:
            raise UpdateFailed("No data received from NEA")

        self._update_statistics(result)
        return result

    def _update_statistics(self, data: dict) -> None:
        """Backfill long-term statistics from NEA's own monthly history.

        NEA's API already returns a year or so of past months in a single
        response - rather than waiting for that trend to slowly accumulate
        via ordinary polling, push it straight into HA's statistics store
        so a native `statistics-graph` card can chart it immediately, with
        no custom card and no extra dependency. Re-running this on every
        poll just upserts the same months, so it stays correct even if NEA
        revises a past figure.
        """
        if "recorder" not in self.hass.config.components:
            return  # recorder disabled - nothing to backfill into

        from homeassistant.components.recorder.statistics import (
            async_add_external_statistics,
        )

        meter_name = data.get("meter_name", "unknown")
        meter_slug = slugify(meter_name)
        fields = {
            "consumed_units": ("Consumed Units", "kWh"),
            "bill_amount": ("Bill Amount", "NPR"),
        }

        for field, (label, unit) in fields.items():
            points = []
            for item in data.get("meter_analytics", []):
                start = bs_month_to_gregorian_start(item["month"])
                value = item.get(field)
                if start is None or value is None:
                    continue
                points.append({"start": start, "mean": value, "min": value, "max": value})

            if not points:
                continue

            metadata = {
                "has_mean": True,
                "has_sum": False,
                "name": f"{meter_name} {label}",
                "source": DOMAIN,
                "statistic_id": f"{DOMAIN}:{meter_slug}_{field}",
                "unit_of_measurement": unit,
            }
            async_add_external_statistics(self.hass, metadata, points)

    async def _request(self, access_token: str):
        """Make one authenticated request. Returns _UNAUTHORIZED, None, or processed data."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            async with self._session.get(
                self.entry.data["data_url"],
                headers=headers,
                timeout=30,
                ssl=False
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get('data'):
                        _LOGGER.error("No data received from API")
                        return None
                    return self._process_data(data['data'])
                elif response.status == 401:
                    return _UNAUTHORIZED
                else:
                    _LOGGER.error(f"Failed to fetch data: {response.status}")
                    return None
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error fetching data: {err}")
            return None

    def _process_data(self, data):
        """Process the raw data into the format we need."""
        try:
            processed_data = {
                "meter_name": data.get("meterName", "Unknown"),
                "consumer_id": data.get("consumerId", "Unknown"),
                "sc_num": data.get("scNum", "Unknown"),
                "total_bill_amount": float(data.get("totalBillAmount", 0)),
                "total_dues_amount": float(data.get("totalDuesAmount", 0)),
                "meter_analytics": []
            }

            for item in data.get("meterAnalytics", []):
                try:
                    processed_item = {
                        "month": item.get("month", "Unknown"),
                        "status": item.get("status", "Unknown"),
                        "consumed_units": float(item.get("consumedUnits", 0)),
                        "bill_amount": float(item.get("billAmt", 0)),
                        "payable_amount": float(item.get("payableAmount", 0)),
                        "rebate_amount": float(item.get("billAmt", 0)) - float(item.get("payableAmount", 0))
                    }
                    processed_data["meter_analytics"].append(processed_item)
                except (ValueError, TypeError) as err:
                    _LOGGER.error(f"Error processing meter analytics item: {err}")
                    continue

            if processed_data["meter_analytics"]:
                processed_data["meter_analytics"].sort(key=lambda x: (
                    int(x["month"].split('/')[1]) if '/' in x["month"] else 0,
                    NEPALI_MONTHS_ORDER.index(x["month"].split('/')[0]) if '/' in x["month"] else 0
                ))

            return processed_data
        except Exception as err:
            _LOGGER.error(f"Error processing data: {err}")
            return None

class BaseElectricitySensor(CoordinatorEntity, SensorEntity):
    """Base class for electricity sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ElectricityUsageCoordinator, meter_name: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._meter_name = meter_name

    @property
    def device_info(self):
        """Return device information.

        The device's own name already carries the meter/consumer name, so
        (with has_entity_name=True) HA prefixes every entity's short name
        with it automatically - no need to repeat the meter name inside
        each entity's own name too.
        """
        return {
            "identifiers": {(DOMAIN, self._meter_name)},
            "name": self._meter_name,
            "manufacturer": "NEA",
            "model": "Smart Meter",
        }

class ElectricityTotalBillSensor(BaseElectricitySensor):
    """Sensor for total bill amount."""

    _attr_name = "Total Bill Amount"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_total_bill_amount"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "NPR"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("total_bill_amount")
        return None

class ElectricityTotalDuesSensor(BaseElectricitySensor):
    """Sensor for total dues amount."""

    _attr_name = "Total Dues Amount"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_total_dues_amount"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "NPR"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("total_dues_amount")
        return None

class ElectricityMeterNameSensor(BaseElectricitySensor):
    """Sensor for meter name."""

    _attr_name = "Meter Name"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_meter_name"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("meter_name")
        return None

class ElectricityConsumerIDSensor(BaseElectricitySensor):
    """Sensor for consumer ID."""

    _attr_name = "Consumer ID"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_consumer_id"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("consumer_id")
        return None

class ElectricityScNumSensor(BaseElectricitySensor):
    """Sensor for SC number."""

    _attr_name = "SC Number"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_sc_num"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("sc_num")
        return None

class ElectricityMonthlyDataSensor(BaseElectricitySensor):
    """Sensor for the current month's consumption.

    The full per-month history is still available as the `monthly_data`
    attribute for anyone who wants it (automations, templates, the old
    custom card), but the sensor's own state/state_class are now set up
    so HA's native long-term statistics track it too - point this at a
    built-in `statistics-graph` card and you get a real trend chart with
    no custom card or extra dependency required.
    """

    _attr_name = "Current Month Usage"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_monthly_data"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "kWh"

    @property
    def native_value(self):
        """Return the current month's consumed units.

        meter_analytics is sorted oldest-first, so the latest month is the
        last entry, not the first - using [0] here was a bug (it reported
        the oldest month in the response despite the sensor's name).
        """
        if self.coordinator.data and self.coordinator.data.get("meter_analytics"):
            return self.coordinator.data["meter_analytics"][-1]["consumed_units"]
        return None

    @property
    def extra_state_attributes(self):
        """Return the full monthly analytics history as attributes."""
        if self.coordinator.data:
            return {
                "monthly_data": self.coordinator.data.get("meter_analytics", [])
            }
        return {}

class ElectricityMonthlyBillSensor(BaseElectricitySensor):
    """Sensor for the current month's bill amount.

    Mirrors ElectricityMonthlyDataSensor (consumed units) but for cost -
    exists mainly so usage and cost each have a real entity with their own
    state_class, letting a dual-axis chart card (e.g. apexcharts-card's
    documented `statistics:` series option) plot both together the same
    way its own multi-y-axis examples do, rather than needing one of them
    to be an external-only statistic.
    """

    _attr_name = "Current Month Bill"

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_monthly_bill"
        # MONETARY device_class only validates against state_class TOTAL, not
        # MEASUREMENT (matches ElectricityTotalBillSensor's pairing below).
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = "NPR"

    @property
    def native_value(self):
        """Return the current month's bill amount (meter_analytics is oldest-first)."""
        if self.coordinator.data and self.coordinator.data.get("meter_analytics"):
            return self.coordinator.data["meter_analytics"][-1]["bill_amount"]
        return None
