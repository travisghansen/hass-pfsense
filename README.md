[![Build Status](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Factions-badge.atrox.dev%2Ftravisghansen%2Fhass-pfsense%2Fbadge%3Fref%3Dmain&style=for-the-badge)](https://actions-badge.atrox.dev/travisghansen/hass-pfsense/goto?ref=main)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
# hass-pfsense

Join `pfSense` with `home-assistant`!

pfSense is a free and open-source firewall and router that also features unified threat management, load balancing, multi WAN, and more.

`hass-pfsense` uses the built-in `xmlrpc` service of `pfSense` for all interactions. No special plugins or software needs to be installed to use the integration.

## core architecture enhancements (golden build)

This overhauled edition introduces native stability improvements engineered to comply with modern Home Assistant Core principles:
- **Async Execution:** Asynchronous network execution ensures that raw PHP operations and XML-RPC evaluations take place entirely within an executor thread pool, eliminating event-loop blocking issues or UI freezing.
- **Smart Local Storage Cache:** Utilizes Home Assistant's internal storage schemas to maintain state snapshots. If the router reboots or falls offline during an operating cycle, sensors leverage a reliable fallback cache rather than showing as `Unavailable`.
- **Duplicate Entity Safeguard:** Regulates individual unique ID declarations strictly, suppressing unwanted duplicate entities resulting from intermittent network timeouts.

# installation

Add the repo to your `hacs` installation as a custom repository or clone the directory manually. Once the integration is installed, be sure to restart Home Assistant and clear your browser cache.

# configuration

Configuration is managed entirely from the UI using `config_flow` semantics. Simply go to `Settings -> Devices & Services -> Add Integration` and search for `pfSense`.

## pfSense

- `System -> Advanced -> Max Processes` - set it to 5 or more.
- If using a non `admin` user account, ensure the user has the `System - HA node sync` privilege. Note that this privilege effectively gives the user complete access to the system via the `xmlrpc` feature.

## config

- `URL` - put the full URL to your `pfSense` UI (ie: `https://192.168.1.1`), supported format is `<scheme>://<ip or host>[:<port>]`.
- `Verify SSL Certificate` - determines if the SSL certificate should be verified (if using the default self-signed pfSense certificate, uncheck this option).
- `username` - the username to use for authentication (ie: `admin`).
- `password` - the password to use for authentication.
- `Firewall Name` - a custom name to be used for `entity` naming (default: uses the `pfSense` `hostname`).

## options

- `Scan Interval (seconds)` - scan interval to use for state polling (default: `30`).
- `Enable Device Tracker` - turn on the device tracker integration using the `pfSense` ARP table (default: `false`).
- `Device Tracker Scan Interval (seconds)` - scan interval to use for ARP updates (default: `150`).
- `Device Tracker Consider Home (seconds)` - seconds to wait before marking a device as away after not being seen (default: `0`).

# entities

Many `entities` are created by `hass-pfsense` for stats etc. Due to the volume of entities, some are disabled by default. If something is missing, review the disabled entities list under your pfSense device profile.

## binary_sensor

- CARP status (enabled/disabled)
- System notices pending (the bell icon indicator from the pfSense UI)
- **CPU Overload (>90%):** Diagnostic problem indicator that flags abnormal hardware consumption.
- **Memory Overload (>90%):** Diagnostic problem indicator that flags low internal runtime memory availability.

## button

- **Reboot Router:** Issues a graceful hardware restart via native Home Assistant button execution.
- **Halt Router:** Safe powerdown execution toggle.
- **Reset State Table:** Flushes active firewall translation connections instantly.

## device_tracker

In order to use the `device_tracker` integration, you must enable it in the integration options and select the **specific** devices you wish to track.

Tracking uses the `pfSense` ARP table. Each poll interval, the ARP table is checked for the entry and if present, the device is considered `Home`. Additionally, _after_ the ARP table is checked, the ARP entry is force-removed (if present) from `pfSense` by the integration. In short, your devices must communicate with `pfSense` at least once each poll interval to be considered `Home`.

## sensor

- **WAN IP Address:** Displays your external WAN interface address natively for effortless automation mapping.
- System details (name, version, temp, boottime, etc.)
- pfState details (used, max, etc.)
- CPU details (average load, frequency, etc.)
- mbuf details
- Memory details
- Filesystem usage percentage
- Interface details (status, stats, pps, kbs)
- Gateways details (status, delay, stddev, loss)
- CARP interface status
- DHCP stats (total, online, and offline clients)
- OpenVPN server stats (connected client count, bytes sent/received, kB/s sent/received)

## switch

- **pfBlockerNG AdBlocker:** Easily enable/disable adblocking features directly from your dashboard. It modifies your runtime parameters and re-triggers the filtering subsystem seamlessly.
- Filter rules - enable/disable firewall rules
- NAT port forward rules - enable/disable rules
- NAT outbound rules - enable/disable rules
- Services - start/stop services (services must be enabled on pfSense before they can be controlled)

## update

- **Firmware Updates Available:** Employs the native Home Assistant `update` schema. Tracks current vs latest system builds and handles firmware updates asynchronously without freezing backend routines.

# services

```yaml
service: pfsense.close_notice
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  # default is to clear all notices
  # id: <some id>

service: pfsense.file_notice
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  id: "hass"
  notice: "hello world"
  # category: "HASS"
  # url: ""
  # priority: 1
  # local_only: false

service: pfsense.system_halt
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present

service: pfsense.system_reboot
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present

service: pfsense.reset_state_table
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present 

service: pfsense.kill_states
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  source: "0.0.0.0/0"
  destination: "192.168.0.1/24"

service: pfsense.start_service
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  service_name: "dpinger"

service: pfsense.stop_service
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  service_name: "dpinger"

service: pfsense.restart_service
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  service_name: "dpinger"
  # only_if_running: false

service: pfsense.send_wol
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  interface: lan
  mac: "B9:7B:A6:46:B3:8B"

service: pfsense.set_default_gateway
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  gateway: GW_WAN
  ip_version: "4"

# extremely advanced, use with caution
# see EXEC_EXAMPLES.md
service: pfsense.exec_command
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  command: ping -c 1 yahoo.com

# extremely advanced, use with caution
# see EXEC_EXAMPLES.md
service: pfsense.exec_php
data:
  entity_id: binary_sensor.pfsense_localdomain_pending_notices_present
  script: |
    require_once '/etc/inc/config.inc';
    global $config;
    $interface = "lan";
    $dns = "192.168.0.1";

    if (!is_array($config["dhcpd"])) {
        $config["dhcpd"] = [];
    }
    if (!is_array($config["dhcpd"][$interface])) {
        $config["dhcpd"][$interface] = [];
    }

    $config["dhcpd"][$interface]["dnsserver"] = [];
    $config["dhcpd"][$interface]["dnsserver"][] = $dns;

    write_config("HASS - exec_php: update dhcpd dns server");

    // reload services, etc here as necessary
    $toreturn = [
        "data" => true,
    ];
