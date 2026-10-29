# homematic_exporter

> Fork of [sfudeus/homematic_exporter](https://github.com/sfudeus/homematic_exporter) with radio interface metrics (duty cycle), per-type channel restriction (`channels_only`) and a fix for duplicate enum series. Image: `ghcr.io/fbrnc/homematic_exporter`.

A simple tool to export data from [Homematic](https://www.homematic.com/) devices for consumption by [Prometheus](https://prometheus.io/), written in Python 3.

`homematic_exporter` will listen on a freely definable port and emit data in prometheus format which is periodically fetched via XML-RPC from CCU3. The fetching period is configurable, too.

`homematic_exporter` was originally written for HomematicIP, but was verified to work with the BidCoS-RF devices as well (specifically HM-CC-RT-DN and HM-WDS40-TH-I-2, thanks to @NilsGriebner), just the respective port needs to be used (`2010` for HomematicIP and `2001` for BidCoS-RF)

## Usage

The exporter can be run in different modes:

* with `--dump_devices`, only the device list will be dumped and the script terminates (used for debugging purposes)
* with `--dump_parameters <deviceAddress>`, the parameters of a single device are dumped and the script terminates (used for debugging purposes)
* with `--dump_device_names`, all device/channel names recognized from the CCU are dumped
* without special arguments (only `ccu_host` is mandatory) data is continuously gathered and exposed via HTTP on the port defined by `--port <port>`

```bash

usage: exporter.py [-h] --ccu_host CCU_HOST [--ccu_port CCU_PORT] [--ccu_user CCU_USER] [--ccu_pass CCU_PASS] [--interval INTERVAL]
                   [--namereload NAMERELOAD] [--port PORT] [--config_file CONFIG_FILE] [--debug] [--dump_devices] [--dump_parameters DUMP_PARAMETERS]
                   [--dump_device_names]
optional arguments:
  -h, --help            show this help message and exit
  --ccu_host CCU_HOST   The hostname of the ccu instance
  --ccu_port CCU_PORT   The port for the xmlrpc service (2001 for BidcosRF, 2010 for HmIP)
  --ccu_user CCU_USER   The username for the CCU (if authentication is enabled)
  --ccu_pass CCU_PASS   The password for the CCU (if authentication is enabled)
  --interval INTERVAL   The interval between two gathering runs in seconds
  --namereload NAMERELOAD
                        After how many intervals the device names are reloaded
  --port PORT           The port where to expose the exporter
  --config_file CONFIG_FILE
                        A config file with e.g. supported types and device name mappings
  --debug
  --dump_devices        Do not start exporter, just dump device list
  --dump_parameters DUMP_PARAMETERS
                        Do not start exporter, just dump device parameters of given device
  --dump_device_names   Do not start exporter, just dump device names
```

Can be used via docker as well.

```bash

> $ docker run --rm sfudeus/homematic_exporter --help
usage: homematic_exporter [-h] --ccu_host CCU_HOST [--ccu_port CCU_PORT] [--ccu_user CCU_USER] [--ccu_pass CCU_PASS] [--interval INTERVAL]
                          [--namereload NAMERELOAD] [--port PORT] [--config_file CONFIG_FILE] [--debug] [--dump_devices]
                          [--dump_parameters DUMP_PARAMETERS] [--dump_device_names]

options:
  -h, --help            show this help message and exit
  --ccu_host CCU_HOST   The hostname of the ccu instance
  --ccu_port CCU_PORT   The port for the xmlrpc service (2001 for BidcosRF, 2010 for HmIP)
  --ccu_user CCU_USER   The username for the CCU (if authentication is enabled)
  --ccu_pass CCU_PASS   The password for the CCU (if authentication is enabled)
  --interval INTERVAL   The interval between two gathering runs in seconds
  --namereload NAMERELOAD
                        After how many intervals the device names are reloaded
  --port PORT           The port where to expose the exporter
  --config_file CONFIG_FILE
                        A config file with e.g. supported types and device name mappings
  --debug
  --dump_devices        Do not start exporter, just dump device list
  --dump_parameters DUMP_PARAMETERS
                        Do not start exporter, just dump device parameters of given device
  --dump_device_names   Do not start exporter, just dump device names
```

All CLI arguments with uppercase arguments can set those via environment variables as well.


## Metrics

Metrics are all prefixed with `homematic_`, the remaining name is based on the parameter name within the device descriptor.
All metrics are equipped with labels for the `ccu` instance, the device address, device type and parent device type.
In addition a device mapping can be added via `--config_file`. Device addresses can be mapped to custom names which are then usable as labels in e.g. Grafana.
If no mappings are in the config file, the names from the CCU user interface are used and exposed as label `mapped_name`.

Unused entries of an enum value list (empty strings in the CCU, e.g. for `ERROR` of `HM-Sec-SCo`) are exported with their index as state name, so every state is a distinct series.

### Radio interface metrics

On every run the exporter also calls `listBidcosInterfaces` and exports per radio interface (labels `ccu`, `interface`, `interface_type`):

* `homematic_interface_duty_cycle`: duty cycle in percent. In the 868 MHz band a sender may only transmit 1 % of each hour; at about 98 % the CCU stops sending, buttons get no acknowledgement and commands are lost.
* `homematic_interface_connected`: 1 if the interface is connected.

The call is answered by the CCU itself without radio traffic. It works on both ports (2001 and 2010).

### Restricting channels

For some BidCos-RF actors (e.g. `HM-LC-Sw4-PCB`, `HM-LC-Bl1PBU-FM`, `HM-LC-Sw1-Pl-DN-R1`, `HM-ES-PMSw1-Pl-DN-R1`) reading the status channels is not answered from the CCU cache but triggers a radio request on every run. With several of them this can use up a large part of the duty cycle. `channels_only` in the config file limits the channels read per parent device type; all other channels of that type are skipped. Types not listed are read completely.

```json
"channels_only": {
  "HM-LC-Sw4-PCB": [0],
  "HM-LC-Bl1PBU-FM": [0]
}
```

Channel `0` (MAINTENANCE) contains `UNREACH`, `CONFIG_PENDING`, `LOWBAT` and the RSSI values.

## CCU configuration

The CCU needs to be configured to be able to fetch data.

* For the general functionality, the XML-RPC interface (port 2001, 2010) must be accessible\
(`Settings -> Control panel -> Configure firewall -> XML-RPC API`)
* For retrieving device names from the CCU, the Script API (port 8181) has to be enabled\
(`Settings -> Control panel -> Configure firewall -> Script API`)\
By providing a device mapping configuration, no access to the Script API is required.

`Restricted access` is sufficient if the exporter is running on a host whitelisted for restricted access\
`(Settings -> Control panel -> Configure firewall -> IP addresses for restricted access)`.\
Otherwise you'd need `Full access`.

It is highly advisable to enable authentication\
(`Settings -> Control panel -> Security -> Authentication`).
Credentials are provided via `--ccu_user` and `--ccu_pass`.

## Restrictions

Only a configurable list of device types is supported so far (since I could only test those). Currently these are:

* the weather station (`HmIP-SWO-PL`)
* the temperature and humidity sensor (with and without display) (`HmIP-STH`, `HmIP-STHD`)
* the pluggable switch/meter (`HMIP-PSM`)
* the flush-mount switch/meter (`HmIP-FSM`)
* the water sensor (`HmIP-SWD`)
* window and door contact (`HMIP-SWDO`), thanks to @kremers
* BidCoS-RF radiator thermostat (`HM-CC-RT-DN`), thanks to @NilsGriebner
* BidCoS-RF temperature and humidity sensor (`HM-WDS40-TH-I-2`), thanks to @NilsGriebner

See the list `DEFAULT_SUPPORTED_TYPES` in `exporter.py` for the default list, which has been used at least once successfully by a user.

If you want support for more devices, you can easily extend them via config file or wait for me to implement that. You can support that by [donating](https://www.amazon.de/hz/wishlist/ls/342DL52U9EX2U?ref_=wl_share) the intended device :-).
Feel free to open issues for unsupported items.

## Build

This fork builds `ghcr.io/fbrnc/homematic_exporter` (linux/amd64, linux/arm64) via GitHub Actions on every push to `master` and on tags `v*`. Tests: `pytest`.

For multi-architecture builds (x86, arm, arm64), e.g. use `docker buildx build --platform linux/amd64,linux/arm/v7,linux/arm64 -t sfudeus/homematic_exporter:latest .` or use `build.sh`.

You can usually find an up-to-date image for amd64, arm and arm64 at sfudeus/homematic_exporter:latest in [docker hub](https://hub.docker.com/r/sfudeus/homematic_exporter). Additionally, they are tagged with their build date to have a stable reference.
