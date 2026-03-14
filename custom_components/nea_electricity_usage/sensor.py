from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.helpers import aiohttp_client, json
from datetime import timedelta
import logging
import aiohttp

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

NEPALI_MONTHS_ORDER = [
    "Baisakh", "Jestha", "Ashad", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the electricity usage sensors from a config entry."""
    access_token = entry.data["access_token"]
    data_url = entry.data["data_url"]
    coordinator = ElectricityUsageCoordinator(hass, access_token, data_url)
    
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
        ])

    async_add_entities(entities, True)

class ElectricityUsageCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching electricity usage data."""

    def __init__(self, hass: HomeAssistant, access_token: str, data_url: str):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._access_token = access_token
        self._data_url = data_url
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self):
        """Fetch data from API."""
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            async with self._session.get(
                self._data_url, 
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
                    _LOGGER.error("Authentication failed - token might be expired")
                    return None
                else:
                    _LOGGER.error(f"Failed to fetch data: {response.status}")
                    return None
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Error fetching data: {err}")
            return None
        except Exception as err:
            _LOGGER.error(f"Unexpected error: {err}")
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

    def __init__(self, coordinator: ElectricityUsageCoordinator, meter_name: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._meter_name = meter_name

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._meter_name)},
            "name": f"Electricity Meter {self._meter_name}",
            "manufacturer": "NEA",
            "model": "Smart Meter",
        }

class ElectricityTotalBillSensor(BaseElectricitySensor):
    """Sensor for total bill amount."""

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_total_bill_amount"
        self._attr_name = f"Total Bill Amount {meter_name}"
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

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_total_dues_amount"
        self._attr_name = f"Total Dues Amount {meter_name}"
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

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_meter_name"
        self._attr_name = f"Meter Name {meter_name}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("meter_name")
        return None

class ElectricityConsumerIDSensor(BaseElectricitySensor):
    """Sensor for consumer ID."""

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_consumer_id"
        self._attr_name = f"Consumer ID {meter_name}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("consumer_id")
        return None

class ElectricityScNumSensor(BaseElectricitySensor):
    """Sensor for SC number."""

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_sc_num"
        self._attr_name = f"SC Number {meter_name}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("sc_num")
        return None

class ElectricityMonthlyDataSensor(BaseElectricitySensor):
    """Sensor for monthly analytics data."""

    def __init__(self, coordinator, meter_name):
        super().__init__(coordinator, meter_name)
        self._attr_unique_id = f"{DOMAIN}_{meter_name}_monthly_data"
        self._attr_name = f"Monthly Data {meter_name}"

    @property
    def native_value(self):
        """Return the current month's data."""
        if self.coordinator.data and self.coordinator.data.get("meter_analytics"):
            # Return the most recent month's consumed units
            return self.coordinator.data["meter_analytics"][0]["consumed_units"]
        return None

    @property
    def extra_state_attributes(self):
        """Return the monthly analytics data as attributes."""
        if self.coordinator.data:
            return {
                "monthly_data": self.coordinator.data.get("meter_analytics", [])
            }
        return {}

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return "kWh"