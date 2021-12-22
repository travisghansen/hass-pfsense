"""The pfSense component."""
from __future__ import annotations

from typing import Final

from homeassistant.components.sensor import (
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_TIMESTAMP,
    STATE_CLASS_MEASUREMENT,
    SensorEntityDescription,
)
from homeassistant.const import (
    DATA_BYTES,
    FREQUENCY_HERTZ,
    PERCENTAGE,
    TEMP_CELSIUS,
    TIME_SECONDS,
)

DEFAULT_USERNAME = "admin"
DOMAIN = "pfsense"

UNDO_UPDATE_LISTENER = "undo_update_listener"

PLATFORMS = ["sensor", "switch", "device_tracker", "binary_sensor"]
LOADED_PLATFORMS = "loaded_platforms"

PFSENSE_CLIENT = "pfsense_client"
COORDINATOR = "coordinator"
DEVICE_TRACKER_COORDINATOR = "device_tracker_coordinator"
SHOULD_RELOAD = "should_reload"
TRACKED_MACS = "tracked_macs"
DEFAULT_SCAN_INTERVAL = 30
CONF_TLS_INSECURE = "tls_insecure"
DEFAULT_TLS_INSECURE = False
DEFAULT_VERIFY_SSL = True

CONF_DEVICE_TRACKER_ENABLED = "device_tracker_enabled"
DEFAULT_DEVICE_TRACKER_ENABLED = False

CONF_DEVICE_TRACKER_SCAN_INTERVAL = "device_tracker_scan_interval"
DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL = 150

CONF_DEVICE_TRACKER_CONSIDER_HOME = "device_tracker_consider_home"
DEFAULT_DEVICE_TRACKER_CONSIDER_HOME = 0

CONF_DEVICES = "devices"

COUNT = "count"

# pulled from upnp component
BYTES_RECEIVED = "bytes_received"
BYTES_SENT = "bytes_sent"
PACKETS_RECEIVED = "packets_received"
PACKETS_SENT = "packets_sent"
DATA_PACKETS = "packets"
DATA_RATE_PACKETS_PER_SECOND = f"{DATA_PACKETS}/{TIME_SECONDS}"

ICON_MEMORY = "mdi:memory"

SENSOR_TYPES: Final[dict[str, SensorEntityDescription]] = {
    # pfstate
    "telemetry.pfstate.used": SensorEntityDescription(
        key="telemetry.pfstate.used",
        name="pf State Table Used",
        native_unit_of_measurement=COUNT,
        icon="mdi:table-network",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.pfstate.total": SensorEntityDescription(
        key="telemetry.pfstate.total",
        name="pf State Table Total",
        native_unit_of_measurement=COUNT,
        icon="mdi:table-network",
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.pfstate.used_percent": SensorEntityDescription(
        key="telemetry.pfstate.used_percent",
        name="pf State Table Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:table-network",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # mbuf
    "telemetry.mbuf.used": SensorEntityDescription(
        key="telemetry.mbuf.used",
        name="Memory Buffers Used",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.mbuf.total": SensorEntityDescription(
        key="telemetry.mbuf.total",
        name="Memory Buffers Total",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.mbuf.used_percent": SensorEntityDescription(
        key="telemetry.mbuf.used_percent",
        name="Memory Buffers Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # memory with state_class due to being less static
    "telemetry.memory.usermem": SensorEntityDescription(
        key="telemetry.memory.usermem",
        name="Memory Usermem",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.memory.swap_reserved": SensorEntityDescription(
        key="telemetry.memory.swap_reserved",
        name="Memory Swap Reserved",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # memory without state_class due to being generally static
    "telemetry.memory.physmem": SensorEntityDescription(
        key="telemetry.memory.physmem",
        name="Memory Physmem",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.memory.realmem": SensorEntityDescription(
        key="telemetry.memory.realmem",
        name="Memory Realmem",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.memory.swap_total": SensorEntityDescription(
        key="telemetry.memory.swap_total",
        name="Memory Swap Total",
        native_unit_of_measurement=DATA_BYTES,
        icon=ICON_MEMORY,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # memory percentages
    "telemetry.memory.swap_used_percent": SensorEntityDescription(
        key="telemetry.memory.swap_used_percent",
        name="Memory Swap Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.memory.used_percent": SensorEntityDescription(
        key="telemetry.memory.used_percent",
        name="Memory Used Percentage",
        native_unit_of_measurement=PERCENTAGE,
        icon=ICON_MEMORY,
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # cpu
    "telemetry.cpu.used_percent": SensorEntityDescription(
        key="telemetry.cpu.used_percent",
        name="CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:speedometer-medium",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.frequency.current": SensorEntityDescription(
        key="telemetry.cpu.frequency.current",
        name="CPU Frequency Current",
        native_unit_of_measurement=FREQUENCY_HERTZ,
        icon="mdi:speedometer-medium",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.frequency.max": SensorEntityDescription(
        key="telemetry.cpu.frequency.max",
        name="CPU Frequency Max",
        native_unit_of_measurement=FREQUENCY_HERTZ,
        icon="mdi:speedometer",
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.count": SensorEntityDescription(
        key="telemetry.cpu.count",
        name="CPU Count",
        native_unit_of_measurement=COUNT,
        icon="mdi:speedometer-medium",
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.load_average.one_minute": SensorEntityDescription(
        key="telemetry.cpu.load_average.one_minute",
        name="CPU Load Average One Minute",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:speedometer-slow",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.load_average.five_minute": SensorEntityDescription(
        key="telemetry.cpu.load_average.five_minute",
        name="CPU Load Average Five Minute",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:speedometer-slow",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.cpu.load_average.fifteen_minute": SensorEntityDescription(
        key="telemetry.cpu.load_average.fifteen_minute",
        name="CPU Load Average Fifteen Minute",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:speedometer-slow",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # system
    "telemetry.system.temp": SensorEntityDescription(
        key="telemetry.system.temp",
        name="System Temperature",
        native_unit_of_measurement=TEMP_CELSIUS,
        device_class=DEVICE_CLASS_TEMPERATURE,
        icon="mdi:thermometer",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "telemetry.system.boottime": SensorEntityDescription(
        key="telemetry.system.boottime",
        name="System Boottime",
        native_unit_of_measurement=TIME_SECONDS,
        device_class=DEVICE_CLASS_TIMESTAMP,
        icon="mdi:clock-outline",
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    # dhcp
    "dhcp_stats.leases.total": SensorEntityDescription(
        key="dhcp_stats.leases.total",
        name="DHCP Leases Total",
        native_unit_of_measurement="clients",
        icon="mdi:ip-network-outline",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "dhcp_stats.leases.online": SensorEntityDescription(
        key="dhcp_stats.leases.online",
        name="DHCP Leases Online",
        native_unit_of_measurement="clients",
        icon="mdi:ip-network-outline",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    "dhcp_stats.leases.offline": SensorEntityDescription(
        key="dhcp_stats.leases.offline",
        name="DHCP Leases Offline",
        native_unit_of_measurement="clients",
        icon="mdi:ip-network-outline",
        state_class=STATE_CLASS_MEASUREMENT,
        # entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
}

SERVICE_CLOSE_NOTICE = "close_notice"
SERVICE_FILE_NOTICE = "file_notice"
SERVICE_START_SERVICE = "start_service"
SERVICE_STOP_SERVICE = "stop_service"
SERVICE_RESTART_SERVICE = "restart_service"
SERVICE_SYSTEM_HALT = "system_halt"
SERVICE_SYSTEM_REBOOT = "system_reboot"
SERVICE_SEND_WOL = "send_wol"
