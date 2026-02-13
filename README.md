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
- Monthly Data
  - Month
  - Status
  - Unit Consumption
  - Bill Amount (NPR)
  - Payable Amount (NPR)
  - Rebate Amount (NPR)

## Installation

### Using HACS

1. Install this integration using HACS by adding this custom repo as integration `https://github.com/arunpdl/hass-nea-usage` to HACS

2. Restart Home Assistant

### Manual Installation

1. Install this integration by creating a `custom_components` directory in your Home Assistant configuration directory, if it does not already exist. Then, copy the `nea_electricity_usage` directory from this repository to the `custom_components` directory.

2. (Optional) Copy `www/electricity-usage-card.js` to `www` directory in your Home Assistant configuration directory. Make sure to load this file as resource under Home Assistant Settings. This file is required to display the custom chart card. This step is optional and any other chart libraries can be used to display the data.

```yaml
lovelace:
resources:
  - url: /local/electricity-usage-chart.js?v=2
    type: module
```

3. Restart Home Assistant

## Configuration

Once the component has been installed, you need to configure it using the web interface in order to make it work.

1. Go to "Settings->Devices & Services".
2. Click "+ Add Integration".
3. Search for "NEA Electricity Usage".
4. Enter your NEA Username and Password. This can be obtained by registering in the NEA app on [Android](https://play.google.com/store/apps/details?id=com.nepalelectricityauthority.nea&hl=en) or [iOS](https://apps.apple.com/np/app/nea-official/id1639332704).
   ![alt text](images/sign-in.png)
5. Select your meter from the list of meters.
   ![alt text](images/select-meter.png)

## Examples

### Card Configuration

- Display a card with basic meter information

```yaml
type: entities
entities:
  - entity: sensor.meter_name_meter_owner
    name: Owner Name
  - entity: sensor.consumer_id_meter_owner
    name: Consumer ID
  - entity: sensor.sc_number_meter_owner
    name: SC Number
  - entity: sensor.total_bill_amount_meter_owner
    name: Total Bill Due
  - entity: sensor.monthly_data_meter_owner
    name: Units Consumed
title: Electricity Consumption
```

- Display monthly data in a chart (needs custom card)

```yaml
type: custom:electricity-usage-chart
entity: sensor.monthly_data_meter_owner
title: Monthly Electricity Usage
```

## API Information

The data displayed in this integration is fetched from the NEA API. The API is not officially documented and is subject to change. The endpoints were discovered by reverse engineering the NEA app. The API is not guaranteed to work in the future.
