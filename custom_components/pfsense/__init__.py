"""Support for pfSense."""
from __future__ import annotations

import copy
from datetime import timedelta
import logging
import math
import re
import time
from typing import Callable

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get_registry
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_DEVICE_TRACKER_ENABLED,
    CONF_DEVICE_TRACKER_SCAN_INTERVAL,
    CONF_TLS_INSECURE,
    COORDINATOR,
    DEFAULT_DEVICE_TRACKER_ENABLED,
    DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TLS_INSECURE,
    DEFAULT_VERIFY_SSL,
    DEVICE_TRACKER_COORDINATOR,
    DOMAIN,
    LOADED_PLATFORMS,
    PFSENSE_CLIENT,
    PLATFORMS,
    SHOULD_RELOAD,
    UNDO_UPDATE_LISTENER,
)
from .pypfsense import Client as pfSenseClient
from .services import ServiceRegistrar

_LOGGER = logging.getLogger(__name__)


def dict_get(data: dict, path: str, default=None):
    pathList = re.split(r"\.", path, flags=re.IGNORECASE)
    result = data
    for key in pathList:
        try:
            key = int(key) if key.isnumeric() else key
            result = result[key]
        except:
            result = default
            break

    return result


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    if hass.data[DOMAIN][entry.entry_id].get(SHOULD_RELOAD, True):
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
    else:
        hass.data[DOMAIN][entry.entry_id][SHOULD_RELOAD] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up pfSense from a config entry."""
    config = entry.data
    options = entry.options

    url = config[CONF_URL]
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    device_tracker_enabled = options.get(
        CONF_DEVICE_TRACKER_ENABLED, DEFAULT_DEVICE_TRACKER_ENABLED
    )
    client = pfSenseClient(url, username, password, {"verify_ssl": verify_ssl})
    data = PfSenseData(client, entry)

    async def async_update_data():
        """Fetch data from pfSense."""
        async with async_timeout.timeout(10):
            await hass.async_add_executor_job(lambda: data.update())

            if not data.state:
                raise UpdateFailed(f"Error fetching {entry.title} pfSense state")

            return data.state

    scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{entry.title} pfSense state",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    platforms = PLATFORMS.copy()
    device_tracker_coordinator = None
    if not device_tracker_enabled:
        platforms.remove("device_tracker")
    else:
        device_tracker_data = PfSenseData(client, entry)
        device_tracker_scan_interval = options.get(
            CONF_DEVICE_TRACKER_SCAN_INTERVAL, DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL
        )

        async def async_update_device_tracker_data():
            """Fetch data from pfSense."""
            async with async_timeout.timeout(10):
                await hass.async_add_executor_job(
                    lambda: device_tracker_data.update({"scope": "device_tracker"})
                )

                if not device_tracker_data.state:
                    raise UpdateFailed(f"Error fetching {entry.title} pfSense state")

                return device_tracker_data.state

        device_tracker_coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"{entry.title} pfSense device tracker state",
            update_method=async_update_device_tracker_data,
            update_interval=timedelta(seconds=device_tracker_scan_interval),
        )

    undo_listener = entry.add_update_listener(_async_update_listener)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        DEVICE_TRACKER_COORDINATOR: device_tracker_coordinator,
        PFSENSE_CLIENT: client,
        UNDO_UPDATE_LISTENER: [undo_listener],
        LOADED_PLATFORMS: platforms,
    }

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    if device_tracker_enabled:
        # Fetch initial data so we have data when entities subscribe
        await device_tracker_coordinator.async_config_entry_first_refresh()

    hass.config_entries.async_setup_platforms(entry, platforms)

    service_registar = ServiceRegistrar(hass)
    service_registar.async_register()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = hass.data[DOMAIN][entry.entry_id][LOADED_PLATFORMS]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    for listener in hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]:
        listener()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    version = config_entry.version

    _LOGGER.debug("Migrating from version %s", version)

    # 1 -> 2: tls_insecure to verify_ssl
    if version == 1:
        version = config_entry.version = 2
        tls_insecure = config_entry.data.get(CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE)
        data = dict(config_entry.data)

        # remove tls_insecure
        if CONF_TLS_INSECURE in data.keys():
            del data[CONF_TLS_INSECURE]

        # add verify_ssl
        if CONF_VERIFY_SSL not in data.keys():
            data[CONF_VERIFY_SSL] = not tls_insecure

        hass.config_entries.async_update_entry(
            config_entry,
            data=data,
        )

        _LOGGER.info("Migration to version %s successful", version)

    return True


class PfSenseData:
    def __init__(self, client: pfSenseClient, config_entry: ConfigEntry):
        """Initialize the data object."""
        self._client = client
        self._config_entry = config_entry
        self._state = {}

    @property
    def state(self):
        return self._state

    def _log_timing(func):
        def inner(*args, **kwargs):
            begin = time.time()
            response = func(*args, **kwargs)
            end = time.time()
            elapsed = round((end - begin), 3)
            _LOGGER.debug(f"execution time: PfSenseData.{func.__name__} {elapsed}")

            return response

        return inner

    @_log_timing
    def _get_system_info(self):
        return self._client.get_system_info()

    @_log_timing
    def _get_firmware_update_info(self):
        try:
            return self._client.get_firmware_update_info()
        except BaseException as err:
            # can take some time to refresh data
            # will catch it the next cycle likely
            if "timed out" in str(err):
                return None
            raise err

    @_log_timing
    def _get_telemetry(self):
        return self._client.get_telemetry()

    @_log_timing
    def _get_host_firmware_version(self):
        return self._client.get_host_firmware_version()

    @_log_timing
    def _get_config(self):
        return self._client.get_config()

    @_log_timing
    def _get_interfaces(self):
        return self._client.get_interfaces()

    @_log_timing
    def _get_services(self):
        return self._client.get_services()

    @_log_timing
    def _get_carp_interfaces(self):
        return self._client.get_carp_interfaces()

    @_log_timing
    def _get_carp_status(self):
        return self._client.get_carp_status()

    @_log_timing
    def _get_dhcp_leases(self):
        return self._client.get_dhcp_leases()

    @_log_timing
    def _are_notices_pending(self):
        return self._client.are_notices_pending()

    @_log_timing
    def _get_notices(self):
        return self._client.get_notices()

    @_log_timing
    def _get_arp_table(self):
        return self._client.get_arp_table(True)

    def update(self, opts={}):
        """Fetch the latest state from pfSense."""
        current_time = time.time()

        # copy the old data to have around
        previous_state = copy.deepcopy(self._state)
        if "previous_state" in previous_state.keys():
            del previous_state["previous_state"]

        self._state["system_info"] = self._get_system_info()
        self._state["host_firmware_version"] = self._get_host_firmware_version()
        self._state["update_time"] = current_time
        self._state["previous_state"] = previous_state

        if "scope" in opts.keys() and opts["scope"] == "device_tracker":
            self._state["arp_table"] = self._get_arp_table()
        else:
            self._state["firmware_update_info"] = self._get_firmware_update_info()
            self._state["telemetry"] = self._get_telemetry()
            self._state["config"] = self._get_config()
            self._state["interfaces"] = self._get_interfaces()
            self._state["services"] = self._get_services()
            self._state["carp_interfaces"] = self._get_carp_interfaces()
            self._state["carp_status"] = self._get_carp_status()
            self._state["dhcp_leases"] = self._get_dhcp_leases()
            self._state["dhcp_stats"] = {}
            self._state["notices"] = {}
            self._state["notices"][
                "pending_notices_present"
            ] = self._are_notices_pending()
            self._state["notices"]["pending_notices"] = self._get_notices()

            lease_stats = {"total": 0, "online": 0, "offline": 0}
            for lease in self._state["dhcp_leases"]:
                if "act" in lease.keys() and lease["act"] == "expired":
                    continue

                lease_stats["total"] += 1
                if "online" in lease.keys():
                    if lease["online"] == "online":
                        lease_stats["online"] += 1
                    if lease["online"] == "offline":
                        lease_stats["offline"] += 1

            self._state["dhcp_stats"]["leases"] = lease_stats

            # calcule pps and kbps
            scan_interval = self._config_entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            )
            update_time = dict_get(self._state, "update_time")
            previous_update_time = dict_get(self._state, "previous_state.update_time")

            if previous_update_time is not None:
                elapsed_time = update_time - previous_update_time

                # calculate CPU Usage based on ticks
                # /usr/local/www/widgets/widgets/system_information.widget.php
                previous_cpu = dict_get(self._state, "previous_state.telemetry.cpu")
                if previous_cpu is not None:
                    current_cpu = dict_get(self._state, "telemetry.cpu")
                    if (
                        dict_get(previous_cpu, "ticks.total")
                        <= dict_get(current_cpu, "ticks.total")
                    ) and (
                        dict_get(previous_cpu, "ticks.idle")
                        <= dict_get(current_cpu, "ticks.idle")
                    ):
                        total_change = dict_get(current_cpu, "ticks.total") - dict_get(
                            previous_cpu, "ticks.total"
                        )
                        idle_change = dict_get(current_cpu, "ticks.idle") - dict_get(
                            previous_cpu, "ticks.idle"
                        )
                        cpu_used_percent = math.floor(
                            ((total_change - idle_change) / total_change) * 100
                        )
                        self._state["telemetry"]["cpu"][
                            "used_percent"
                        ] = cpu_used_percent

                for interface_name in dict_get(
                    self._state, "telemetry.interfaces", {}
                ).keys():
                    interface = dict_get(
                        self._state, f"telemetry.interfaces.{interface_name}"
                    )
                    previous_interface = dict_get(
                        self._state,
                        f"previous_state.telemetry.interfaces.{interface_name}",
                    )
                    if previous_interface is None:
                        break

                    for property in [
                        "inbytes",
                        "outbytes",
                        "inbytespass",
                        "outbytespass",
                        "inbytesblock",
                        "outbytesblock",
                        "inpkts",
                        "outpkts",
                        "inpktspass",
                        "outpktspass",
                        "inpktsblock",
                        "outpktsblock",
                    ]:

                        current_parent_value = interface[property]
                        previous_parent_value = previous_interface[property]
                        change = abs(current_parent_value - previous_parent_value)
                        rate = change / elapsed_time

                        value = 0
                        if "pkts" in property:
                            label = "packets_per_second"
                            value = rate
                        if "bytes" in property:
                            label = "kilobytes_per_second"
                            # 1 Byte = 8 bits
                            # 1 byte is equal to 0.001 kilobytes
                            KBs = rate / 1000
                            # Kbs = KBs * 8
                            value = KBs

                        new_property = f"{property}_{label}"
                        interface[new_property] = int(round(value, 0))

                        continue

                        # TODO: this logic is not perfect but probably 'good enough'
                        # to make this perfect the stats should probably be their own
                        # coordinator
                        #
                        # put this here to prevent over-agressive calculations when
                        # data is refreshed due to switches being triggered etc
                        #
                        # theoretically if switches are going on/off rapidly the value
                        # would never get updated as the code currently is
                        if elapsed_time >= scan_interval:
                            interface[new_property] = int(round(value, 0))
                        else:
                            previous_value = dict_get(previous_interface, new_property)
                            if previous_value is None:
                                previous_value = value
                            interface[new_property] = int(round(previous_value, 0))

                for server_name in dict_get(
                    self._state, "telemetry.openvpn.servers", {}
                ).keys():
                    if (
                        server_name
                        not in dict_get(
                            self._state, "telemetry.openvpn.servers", {}
                        ).keys()
                    ):
                        continue

                    if (
                        server_name
                        not in dict_get(
                            self._state, "previous_state.telemetry.openvpn.servers", {}
                        ).keys()
                    ):
                        continue

                    server = self._state["telemetry"]["openvpn"]["servers"][server_name]
                    previous_server = self._state["previous_state"]["telemetry"][
                        "openvpn"
                    ]["servers"][server_name]

                    for property in [
                        "total_bytes_recv",
                        "total_bytes_sent",
                    ]:

                        current_parent_value = server[property]
                        previous_parent_value = previous_server[property]
                        change = abs(current_parent_value - previous_parent_value)
                        rate = change / elapsed_time

                        value = 0
                        if "pkts" in property:
                            label = "packets_per_second"
                            value = rate
                        if "bytes" in property:
                            label = "kilobytes_per_second"
                            # 1 Byte = 8 bits
                            # 1 byte is equal to 0.001 kilobytes
                            KBs = rate / 1000
                            # Kbs = KBs * 8
                            value = KBs

                        new_property = f"{property}_{label}"
                        server[new_property] = int(round(value, 0))


class CoordinatorEntityManager:
    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
        process_entities_callback: Callable,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.process_entities_callback = process_entities_callback
        self.async_add_entities = async_add_entities
        hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER].append(
            coordinator.async_add_listener(self.process_entities)
        )
        self.entity_unique_ids = set()
        self.entities = {}

    @callback
    def process_entities(self):
        entities = self.process_entities_callback(self.hass, self.config_entry)
        i_entity_unqiue_ids = set()
        for entity in entities:
            unique_id = entity.unique_id
            if unique_id is None:
                raise Exception("unique_id is missing from entity")
            i_entity_unqiue_ids.add(unique_id)
            if unique_id not in self.entity_unique_ids:
                self.async_add_entities([entity])
                self.entity_unique_ids.add(unique_id)
                self.entities[unique_id] = entity
                # print(f"{unique_id} registered")
            else:
                # print(f"{unique_id} already registered")
                pass

        # check for missing entities
        for entity_unique_id in self.entity_unique_ids:
            if entity_unique_id not in i_entity_unqiue_ids:
                pass
                # print("should remove entity: " + str(self.entities[entity_unique_id].entry_id))
                # print("candidate to remove entity: " + str(entity_unique_id))
                # self.async_remove_entity(self.entities[entity_unique_id])
                # self.entity_unique_ids.remove(entity_unique_id)
                # del self.entities[entity_unique_id]

    async def async_remove_entity(self, entity):
        registry = await async_get_registry(self.hass)
        if entity.entity_id in registry.entities:
            registry.async_remove(entity.entity_id)


class PfSenseEntity(CoordinatorEntity, RestoreEntity):
    """base entity for pfSense"""

    @property
    def device_info(self):
        """Device info for the firewall."""
        state = self.coordinator.data
        model = state["host_firmware_version"]["platform"]
        manufacturer = "netgate"
        firmware = state["host_firmware_version"]["firmware"]["version"]

        device_info = {
            "identifiers": {(DOMAIN, self.pfsense_device_unique_id)},
            "name": self.pfsense_device_name,
            "configuration_url": self.config_entry.data.get("url", None),
        }

        device_info["model"] = model
        device_info["manufacturer"] = manufacturer
        device_info["sw_version"] = firmware

        return device_info

    @property
    def pfsense_device_name(self):
        if self.config_entry.title and len(self.config_entry.title) > 0:
            return self.config_entry.title
        return "{}.{}".format(
            self._get_pfsense_state_value("system_info.hostname"),
            self._get_pfsense_state_value("system_info.domain"),
        )

    @property
    def pfsense_device_unique_id(self):
        return self._get_pfsense_state_value("system_info.netgate_device_id")

    def _get_pfsense_state_value(self, path, default=None):
        state = self.coordinator.data
        value = dict_get(state, path, default)

        return value

    def _get_pfsense_client(self) -> pfSenseClient:
        return self.hass.data[DOMAIN][self.config_entry.entry_id][PFSENSE_CLIENT]

    def service_close_notice(self, id: int | str | None = None):
        client = self._get_pfsense_client()
        client.close_notice(id)

    def service_file_notice(self, **kwargs):
        client = self._get_pfsense_client()
        client.file_notice(**kwargs)

    def service_start_service(self, service_name: str):
        client = self._get_pfsense_client()
        client.start_service(service_name)

    def service_stop_service(self, service_name: str):
        client = self._get_pfsense_client()
        client.stop_service(service_name)

    def service_restart_service(self, service_name: str, only_if_running: bool = False):
        client = self._get_pfsense_client()
        if only_if_running:
            client.restart_service_if_running(service_name)
        else:
            client.restart_service(service_name)

    def service_system_halt(self):
        client = self._get_pfsense_client()
        client.system_halt()

    def service_system_reboot(self):
        client = self._get_pfsense_client()
        client.system_reboot()

    def service_send_wol(self, interface: str, mac: str):
        client = self._get_pfsense_client()
        client.send_wol(interface, mac)
