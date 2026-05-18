"""Support for pfSense (GOUDEN BUILD - Cache & Veilig)."""

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
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.storage import Store

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

# --- SMART CACHE LOGIC ---
STORAGE_VERSION = 1


async def async_save_cache(hass: HomeAssistant, entry_id: str, data: dict):
    """Save state to local cache."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_cache")
    try:
        await store.async_save(data)
    except Exception as e:
        _LOGGER.error(f"Failed to save pfSense cache: {e}")


async def async_load_cache(hass: HomeAssistant, entry_id: str):
    """Load state from local cache."""
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_cache")
    try:
        return await store.async_load()
    except Exception as e:
        _LOGGER.error(f"Failed to load pfSense cache: {e}")
        return None


# -------------------------


def dict_get(data: dict, path: str, default=None):
    pathList = re.split(r"\.", path, flags=re.IGNORECASE)
    result = data
    for key in pathList:
        try:
            key = int(key) if key.isnumeric() else key
            result = result[key]
        except Exception:
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
    data = PfSenseData(client, entry, hass)
    scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    async def async_update_data():
        """Fetch data from pfSense."""
        try:
            async with async_timeout.timeout(scan_interval - 1):
                # Volledig asynchroon en veilig via de achtergrond thread!
                new_state = await hass.async_add_executor_job(data.update)
                if not new_state:
                    raise UpdateFailed("Geen data ontvangen van pfSense")

                # Sla op in de Smart Cache!
                await async_save_cache(hass, entry.entry_id, new_state)
                return new_state

        except Exception as err:
            _LOGGER.warning(
                f"Fout bij ophalen pfSense: {err}. We proberen de cache te laden..."
            )
            cached_data = await async_load_cache(hass, entry.entry_id)
            if cached_data:
                data._state = cached_data  # Zet de interne state terug
                return cached_data
            raise UpdateFailed(f"Fout en geen cache beschikbaar: {err}")

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
        device_tracker_data = PfSenseData(client, entry, hass)
        device_tracker_scan_interval = options.get(
            CONF_DEVICE_TRACKER_SCAN_INTERVAL, DEFAULT_DEVICE_TRACKER_SCAN_INTERVAL
        )

        async def async_update_device_tracker_data():
            """Fetch data from pfSense."""
            try:
                async with async_timeout.timeout(device_tracker_scan_interval - 1):
                    new_dt_state = await hass.async_add_executor_job(
                        lambda: device_tracker_data.update({"scope": "device_tracker"})
                    )
                    if not new_dt_state:
                        raise UpdateFailed("Geen device tracker data ontvangen")
                    return new_dt_state
            except Exception as err:
                _LOGGER.warning(f"Device tracker update faalde: {err}")
                if device_tracker_data._state:
                    return device_tracker_data._state
                raise UpdateFailed(err)

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

    await coordinator.async_config_entry_first_refresh()
    if device_tracker_enabled:
        await device_tracker_coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

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
    if version == 1:
        version = config_entry.version = 2
        tls_insecure = config_entry.data.get(CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE)
        data = dict(config_entry.data)
        if CONF_TLS_INSECURE in data.keys():
            del data[CONF_TLS_INSECURE]
        if CONF_VERIFY_SSL not in data.keys():
            data[CONF_VERIFY_SSL] = not tls_insecure
        hass.config_entries.async_update_entry(config_entry, data=data)
    return True


class PfSenseData:
    def __init__(
        self, client: pfSenseClient, config_entry: ConfigEntry, hass: HomeAssistant
    ):
        """Initialize the data object."""
        self._client = client
        self._config_entry = config_entry
        self._hass = hass
        self._state = {}
        self._firmware_update_info = None

    @property
    def state(self):
        return self._state

    def update(self, opts={}):
        """Fetch the latest state from pfSense. Draait synchroon in executor."""
        new_state = {}

        try:
            current_time = time.time()
            previous_state = copy.deepcopy(self._state)
            if "previous_state" in previous_state.keys():
                del previous_state["previous_state"]

            new_state["update_time"] = current_time
            new_state["previous_state"] = previous_state

            new_state["system_info"] = self._client.get_system_info()
            new_state["host_firmware_version"] = (
                self._client.get_host_firmware_version()
            )

            if "scope" in opts.keys() and opts["scope"] == "device_tracker":
                try:
                    new_state["arp_table"] = self._client.get_arp_table(True)
                except BaseException as err:
                    _LOGGER.error(f"failed to retrieve arp table {err=}, {type(err)=}")
            else:
                try:
                    self._firmware_update_info = self._client.get_firmware_update_info()
                except Exception:
                    pass  # Timeout of fout, we pakken hem volgende keer

                # Haal de telemetrie op (inclusief onze nieuwe WAN IP en pfBlockerNG data!)
                telemetry_data = self._client.get_telemetry()

                new_state["firmware_update_info"] = self._firmware_update_info
                new_state["telemetry"] = telemetry_data
                new_state["config"] = self._client.get_config()
                new_state["interfaces"] = self._client.get_interfaces()
                new_state["services"] = self._client.get_services()
                new_state["carp_interfaces"] = self._client.get_carp_interfaces()
                new_state["carp_status"] = self._client.get_carp_status()
                new_state["dhcp_leases"] = self._client.get_dhcp_leases(False)
                new_state["dhcp_stats"] = {}
                new_state["notices"] = {
                    "pending_notices_present": self._client.are_notices_pending(),
                    "pending_notices": self._client.get_notices(),
                }

                # Zorg dat de specifieke keys plat in de telemetry dictionary komen te staan voor de sensoren
                new_state["telemetry"]["wan_ip"] = telemetry_data.get("wan_ip")
                new_state["telemetry"]["pfblockerng"] = telemetry_data.get(
                    "pfblockerng"
                )

                lease_stats = {"total": 0, "online": 0, "idle_offline": 0}
                for lease in new_state["dhcp_leases"]:
                    if "act" in lease.keys() and lease["act"] == "expired":
                        continue
                    lease_stats["total"] += 1
                    if "online" in lease.keys():
                        if lease["online"] in ["active", "active/online", "online"]:
                            lease_stats["online"] += 1
                        if lease["online"] in ["offline", "idle/offline", "idle"]:
                            lease_stats["idle_offline"] += 1
                new_state["dhcp_stats"]["leases"] = lease_stats

                # Bereken PPS en KBPS
                scan_interval = self._config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
                update_time = dict_get(new_state, "update_time")
                previous_update_time = dict_get(new_state, "previous_state.update_time")

                if previous_update_time is not None:
                    elapsed_time = update_time - previous_update_time

                    previous_cpu = dict_get(new_state, "previous_state.telemetry.cpu")
                    if previous_cpu is not None:
                        current_cpu = dict_get(new_state, "telemetry.cpu")
                        if (
                            dict_get(previous_cpu, "ticks.total")
                            <= dict_get(current_cpu, "ticks.total")
                        ) and (
                            dict_get(previous_cpu, "ticks.idle")
                            <= dict_get(current_cpu, "ticks.idle")
                        ):
                            total_change = dict_get(
                                current_cpu, "ticks.total"
                            ) - dict_get(previous_cpu, "ticks.total")
                            idle_change = dict_get(
                                current_cpu, "ticks.idle"
                            ) - dict_get(previous_cpu, "ticks.idle")
                            if total_change > 0:
                                new_state["telemetry"]["cpu"]["used_percent"] = (
                                    math.floor(
                                        ((total_change - idle_change) / total_change)
                                        * 100
                                    )
                                )
                            else:
                                new_state["telemetry"]["cpu"]["used_percent"] = (
                                    dict_get(
                                        previous_state, "telemetry.cpu.used_percent"
                                    )
                                )

                    for interface_name in dict_get(
                        new_state, "telemetry.interfaces", {}
                    ).keys():
                        interface = dict_get(
                            new_state, f"telemetry.interfaces.{interface_name}"
                        )
                        previous_interface = dict_get(
                            new_state,
                            f"previous_state.telemetry.interfaces.{interface_name}",
                        )
                        if previous_interface is None:
                            break

                        for prop in [
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
                            change = abs(interface[prop] - previous_interface[prop])
                            rate = change / elapsed_time if elapsed_time > 0 else 0

                            if "pkts" in prop:
                                label = "packets_per_second"
                                value = rate
                            if "bytes" in prop:
                                label = "kilobytes_per_second"
                                value = rate / 1000

                            new_property = f"{prop}_{label}"
                            if elapsed_time >= scan_interval:
                                interface[new_property] = int(round(value, 0))
                            else:
                                previous_value = dict_get(
                                    previous_interface, new_property
                                )
                                interface[new_property] = int(
                                    round(
                                        previous_value
                                        if previous_value is not None
                                        else value,
                                        0,
                                    )
                                )

                    for server_name in dict_get(
                        new_state, "telemetry.openvpn.servers", {}
                    ).keys():
                        if (
                            server_name
                            not in dict_get(
                                new_state,
                                "previous_state.telemetry.openvpn.servers",
                                {},
                            ).keys()
                        ):
                            continue

                        server = new_state["telemetry"]["openvpn"]["servers"][
                            server_name
                        ]
                        previous_server = new_state["previous_state"]["telemetry"][
                            "openvpn"
                        ]["servers"][server_name]

                        for prop in ["total_bytes_recv", "total_bytes_sent"]:
                            change = abs(server[prop] - previous_server[prop])
                            rate = change / elapsed_time if elapsed_time > 0 else 0
                            new_property = f"{prop}_kilobytes_per_second"
                            server[new_property] = int(round(rate / 1000, 0))

        except BaseException as err:
            self._state = new_state
            raise err

        self._state = new_state
        return new_state


class CoordinatorEntityManager:
    """GOUDEN BUILD: Slimme Entity Manager voorkomt duplicaten!"""

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

        # Registreer de listener netjes zonder duplicaten te riskeren
        self.hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER].append(
            coordinator.async_add_listener(self.process_entities)
        )
        self.entity_unique_ids = set()

    @callback
    def process_entities(self):
        entities = self.process_entities_callback(self.hass, self.config_entry)
        new_entities = []

        for entity in entities:
            if entity.unique_id not in self.entity_unique_ids:
                new_entities.append(entity)
                self.entity_unique_ids.add(entity.unique_id)

        if new_entities:
            self.async_add_entities(new_entities)


class PfSenseEntity(CoordinatorEntity, RestoreEntity):
    """base entity for pfSense"""

    @property
    def coordinator_context(self):
        return None

    @property
    def device_info(self):
        state = self.coordinator.data
        if not state or "host_firmware_version" not in state:
            return None

        return {
            "identifiers": {(DOMAIN, self.pfsense_device_unique_id)},
            "name": self.pfsense_device_name,
            "configuration_url": self.config_entry.data.get("url", None),
            "model": state["host_firmware_version"]["platform"],
            "manufacturer": "netgate",
            "sw_version": state["host_firmware_version"]["firmware"]["version"],
        }

    @property
    def pfsense_device_name(self):
        if self.config_entry.title:
            return self.config_entry.title
        return f"{self._get_pfsense_state_value('system_info.hostname')}.{self._get_pfsense_state_value('system_info.domain')}"

    @property
    def pfsense_device_unique_id(self):
        return self._get_pfsense_state_value("system_info.netgate_device_id")

    def _get_pfsense_state_value(self, path, default=None):
        return dict_get(self.coordinator.data, path, default)

    def _get_pfsense_client(self) -> pfSenseClient:
        return self.hass.data[DOMAIN][self.config_entry.entry_id][PFSENSE_CLIENT]

    def service_close_notice(self, id: int | str | None = None):
        self._get_pfsense_client().close_notice(id)

    def service_file_notice(self, **kwargs):
        self._get_pfsense_client().file_notice(**kwargs)

    def service_start_service(
        self, service_name: str, service: dict | str | None = None
    ):
        self._get_pfsense_client().start_service(service_name, service)

    def service_stop_service(
        self, service_name: str, service: dict | str | None = None
    ):
        self._get_pfsense_client().stop_service(service_name, service)

    def service_restart_service(
        self,
        service_name: str,
        only_if_running: int | str | None | bool = False,
        service: dict | str | None = None,
    ):
        client = self._get_pfsense_client()
        if str(only_if_running).lower() in ["true", "1"]:
            client.restart_service_if_running(service_name, service)
        else:
            client.restart_service(service_name, service)

    def service_reset_state_table(self):
        self._get_pfsense_client().reset_state_table()

    def service_kill_states(self, source: str, destination: str = None):
        self._get_pfsense_client().kill_states(source, destination)

    def service_system_halt(self):
        self._get_pfsense_client().system_halt()

    def service_system_reboot(self):
        self._get_pfsense_client().system_reboot()

    def service_send_wol(self, interface: str, mac: str):
        self._get_pfsense_client().send_wol(interface, mac)

    def service_set_default_gateway(self, gateway: str, ip_version: str):
        self._get_pfsense_client().set_default_gateway(gateway, ip_version)

    def service_exec_php(self, script: str):
        self._get_pfsense_client()._exec_php(script)

    def service_exec_command(self, command: str, background: bool = False):
        self._get_pfsense_client()._exec_command(command, background)
