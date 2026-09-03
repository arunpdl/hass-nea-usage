# hass-nea-usage

A [Home Assistant](https://www.home-assistant.io/) custom integration to display electricity usage for [Nepal Electricity Authority](https://nea.org.np/) consumers

## Features

![Meter info](images/feature-info.png)
![Usage info](images/feature-usage.png)

- Display meter owner information
- Display monthly unit consumption, bill amount and rebate amount
- Display total bill due amount

## Entities

- Consumer ID
- Meter Name
- SC Number
- Total Bill Amount (NPR)
- Total Bill Due (NPR)
- Current Month Usage (kWh) - state tracked as a normal HA statistic (see
  [Charting usage over time](#charting-usage-over-time)), plus the full
  per-month history as a `monthly_data` attribute:
  - Month
  - Status
  - Unit Consumption
  - Bill Amount (NPR)
  - Payable Amount (NPR)
  - Rebate Amount (NPR)

Entity names no longer repeat the meter name (e.g. `Total Bill Amount`
instead of `Total Bill Amount <meter name>`) - each meter is its own HA
device, and the device name (your consumer/meter name) is what
distinguishes entities across multiple meters.

## Installation

### Using HACS

1. Install this integration using HACS by adding this custom repo as integration `https://github.com/arunpdl/hass-nea-usage` to HACS

2. Restart Home Assistant

### Manual Installation

1. Install this integration by creating a `custom_components` directory in your Home Assistant configuration directory, if it does not already exist. Then, copy the `nea_electricity_usage` directory from this repository to the `custom_components` directory.

2. Restart Home Assistant

## Configuration

Once the component has been installed, you need to configure it using the web interface in order to make it work.

1. Go to "Settings->Devices & Services".
2. Click "+ Add Integration".
3. Search for "NEA Electricity Usage".
4. Enter your NEA Username and Password. This can be obtained by registering in the NEA app on [Android](https://play.google.com/store/apps/details?id=com.nepalelectricityauthority.nea&hl=en) or [iOS](https://apps.apple.com/np/app/nea-official/id1639332704).
   ![alt text](images/sign-in.png)
5. Select your meter from the list of meters.
   ![alt text](images/select-meter.png)

Re-authentication is automatic: if NEA's access token expires, the
integration silently logs back in with the username/password you entered
above. If NEA later rejects those saved credentials outright (e.g. you
changed your password), Home Assistant will prompt you to re-enter them via
its normal repair/reauth flow instead of leaving every entity unavailable.

### Options

Click "Configure" on the integration to change how often it polls NEA
(default: every 6 hours - NEA billing data changes at most monthly, so
there's little reason to poll more often than that, but it's adjustable
from 1 to 72 hours).

## Examples

### Card Configuration

- Display a card with basic meter information

```yaml
type: entities
entities:
  - entity: sensor.meter_name
    name: Owner Name
  - entity: sensor.consumer_id
    name: Consumer ID
  - entity: sensor.sc_number
    name: SC Number
  - entity: sensor.total_bill_amount
    name: Total Bill Due
  - entity: sensor.current_month_usage
    name: Units Consumed
title: Electricity Consumption
```

(Use whatever entity IDs your own install actually assigned - check
Settings → Devices & Services → NEA Electricity Usage → your meter's device.)

### Charting usage over time

`Current Month Usage` is a normal HA sensor with a `state_class`, so it
works with the built-in statistics/history cards for *future* months as
they're polled - no custom card or extra dependency required:

```yaml
type: statistics-graph
title: Monthly Electricity Usage
entities:
  - sensor.current_month_usage
stat_types:
  - mean
```

NEA's API already hands back a year or so of *past* months in one response
though, so you don't have to wait for that history to build up: every poll
also backfills each month's Consumed Units and Bill Amount straight into
HA's own long-term statistics, under `nea_electricity_usage:<meter>_consumed_units`
and `nea_electricity_usage:<meter>_bill_amount`. Point a `statistics-graph`
card at those directly (a plain string is a valid `entities` entry - see the
[card's docs](https://www.home-assistant.io/dashboards/statistics-graph/)) to
get the full historical trend immediately, self-maintaining as new months
arrive:

```yaml
type: statistics-graph
title: Monthly Usage & Cost
entities:
  - nea_electricity_usage:sirjana_paudel_consumed_units
  - nea_electricity_usage:sirjana_paudel_bill_amount
stat_types:
  - mean
```

(Replace `sirjana_paudel` with your own meter name, slugified - check
Developer Tools → Statistics in HA to find the exact ID.) Because NEA
reports months in the Nepali (Bikram Sambat) calendar, each month is placed
on the chart's real time axis using an approximate BS→Gregorian conversion
(month-level accuracy, +/- roughly two weeks - see `nepali_calendar.py`),
not an exact day-for-day mapping.

If you want the raw month-by-month breakdown NEA returns (bill amount,
rebate, status, ...) rather than just the chartable numbers, it's available
as the `monthly_data` attribute on the `Current Month Usage` sensor - handy
for a `markdown` card or a template.

## API Information

The data displayed in this integration is fetched from the NEA API. The API is not officially documented and is subject to change. The endpoints were discovered by reverse engineering the NEA app. The API is not guaranteed to work in the future.
