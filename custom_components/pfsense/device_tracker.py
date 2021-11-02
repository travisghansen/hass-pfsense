"""Support for tracking for pfSense devices."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from homeassistant.components.device_tracker import SOURCE_TYPE_ROUTER
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    async_get as async_get_dev_reg,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_registry import (
    DISABLED_INTEGRATION,
    async_get as async_get_ent_reg,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import slugify
from mac_vendor_lookup import AsyncMacLookup

from . import CoordinatorEntityManager, PfSenseEntity, dict_get
from .const import (
    CONF_DEVICES,
    DEVICE_TRACKER_COORDINATOR,
    DOMAIN,
    PFSENSE_CLIENT,
    SHOULD_RELOAD,
)

_LOGGER = logging.getLogger(__name__)


def lookup_mac(mac_vendor_lookup: AsyncMacLookup, mac: str) -> str:
    mac = mac_vendor_lookup.sanitise(mac)
    if type(mac) == str:
        mac = mac.encode("utf8")
    return mac_vendor_lookup.prefixes[mac[:6]].decode("utf8")


def get_device_tracker_unique_id(mac: str, netgate_id: str):
    """Generate device_tracker unique ID."""
    return slugify(f"{netgate_id}_mac_{mac}")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: entity_platform.AddEntitiesCallback,
) -> None:
    """Set up device tracker for pfSense component."""
    mac_vendor_lookup = AsyncMacLookup()
    try:
        await mac_vendor_lookup.update_vendors()
    except:
        try:
            await mac_vendor_lookup.load_vendors()
        except:
            pass

    store = Store(hass, 1, DOMAIN)
    cache_data = await store.async_load() or {}
    ent_reg = async_get_ent_reg(hass)

    @callback
    def process_entities_callback(
        hass: HomeAssistant, config_entry: ConfigEntry
    ) -> list[PfSenseScannerEntity]:
        # options = config_entry.options
        data = hass.data[DOMAIN][config_entry.entry_id]
        coordinator = data[DEVICE_TRACKER_COORDINATOR]
        state = coordinator.data
        # seems unlikely *all* devices are intended to be monitored
        # disable by default and let users enable specific entries they care about
        enabled_default = False

        entities = []
        entries = dict_get(state, "arp_table")
        if not entries:
            return []

        whitelisted_devices = config_entry.options.get(CONF_DEVICES)
        if whitelisted_devices:
            enabled_default = True

        mac_entries = [
            entry_mac.lower()
            for entry in entries
            if (entry_mac := entry.get("mac-address"))
            and (not whitelisted_devices or entry_mac in whitelisted_devices)
        ]
        mac_entries_missing_from_arp = list(set(cache_data.keys()) - set(mac_entries))
        for entry_mac in [*mac_entries, *mac_entries_missing_from_arp]:
            if enabled_default and entry_mac not in whitelisted_devices:
                continue

            mac_vendor = None
            try:
                mac_vendor = lookup_mac(mac_vendor_lookup, entry_mac)
            except:
                pass

            if entry_mac in mac_entries_missing_from_arp:
                _LOGGER.debug(
                    (
                        "Creating an entity with the last known state for mac %s "
                        "because it's not in the ARP table"
                    ),
                    entry_mac,
                )

            entity = PfSenseScannerEntity(
                hass,
                config_entry,
                coordinator,
                enabled_default,
                entry_mac,
                mac_vendor,
                cache_data.get(entry_mac),
            )

            entities.append(entity)
            cache_data[entry_mac] = {
                "extra_state_attributes": entity._extra_state_attributes,
                "ip_address": entity._ip_address,
                "hostname": entity._hostname,
            }

            if not enabled_default:
                continue

            entity_id = ent_reg.async_get_entity_id(
                "device_tracker", DOMAIN, entity.unique_id
            )
            if (
                entity_id
                and (entity_entry := ent_reg.async_get(entity_id))
                and entity_entry.disabled_by == DISABLED_INTEGRATION
            ):
                ent_reg.async_update_entity(entity_id, disabled_by=None)
                hass.data[DOMAIN][config_entry.entry_id][SHOULD_RELOAD] = True

        return entities, cache_data

    cem = CoordinatorEntityManager(
        hass,
        hass.data[DOMAIN][config_entry.entry_id][DEVICE_TRACKER_COORDINATOR],
        config_entry,
        process_entities_callback,
        async_add_entities,
        True,
    )
    cem.process_entities()

    dev_reg = async_get_dev_reg(hass)

    async def remove_devices(event: Event) -> None:
        """Remove devices."""
        for mac in event.data["macs"]:
            _LOGGER.debug("Removing device and entity for mac %s", mac)
            device = dev_reg.async_get_device({}, {(CONNECTION_NETWORK_MAC, mac)})
            if device:
                dev_reg.async_remove_device(device.id)
            cache_data.pop(mac, None)
            await store.async_save(cache_data)

    hass.bus.async_listen(
        f"{DOMAIN}_{config_entry.entry_id}_remove_devices", remove_devices
    )


class PfSenseScannerEntity(PfSenseEntity, ScannerEntity):
    """Represent a scanned device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        enabled_default: bool,
        mac: str,
        mac_vendor: str,
        cache_data: dict[str, str] | None,
    ) -> None:
        """Set up the pfSense scanner entity."""
        self.hass = hass
        self.config_entry = config_entry
        self.coordinator = coordinator
        self._mac_address = mac
        self._mac_vendor = mac_vendor
        self._last_known_ip = None
        self._cache_data = cache_data

        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_unique_id = get_device_tracker_unique_id(
            mac, self.pfsense_device_unique_id
        )

    def _get_pfsense_arp_entry(self) -> dict[str, str]:
        state = self.coordinator.data
        for entry in state["arp_table"]:
            if entry.get("mac-address", "").lower() == self._mac_address:
                return entry

        return None

    @property
    def source_type(self) -> str:
        """Return the source type, eg gps or router, of the device."""
        return SOURCE_TYPE_ROUTER

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra state attributes."""
        if not self.is_connected and self._cache_data:
            return self._cache_data["extra_state_attributes"]

        return self._extra_state_attributes

    @property
    def _extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return extra state attributes."""
        entry = self._get_pfsense_arp_entry()
        if entry is None:
            return None

        attrs = {}
        for property in ["interface", "expires", "type"]:
            attrs[property] = entry.get(property)

        return attrs

    @property
    def ip_address(self) -> str | None:
        """Return the primary ip address of the device."""
        if not self.is_connected and self._cache_data:
            return self._cache_data["ip_address"]

        return self._ip_address

    @property
    def _ip_address(self) -> str | None:
        """Return the primary ip address of the device."""
        entry = self._get_pfsense_arp_entry()
        if entry is None:
            return None

        ip_address = entry.get("ip-address")
        if ip_address is not None and len(ip_address) > 0:
            self._last_known_ip = ip_address
        return ip_address

    @property
    def mac_address(self) -> str | None:
        """Return the mac address of the device."""
        return self._mac_address

    @property
    def hostname(self) -> str | None:
        """Return hostname of the device."""
        if not self.is_connected and self._cache_data:
            return self._cache_data["hostname"]
        return self._hostname

    @property
    def _hostname(self) -> str | None:
        """Return hostname of the device."""
        entry = self._get_pfsense_arp_entry()
        if entry is None:
            return None
        value = entry.get("hostname").strip("?")
        if len(value) > 0:
            return value
        return None

    @property
    def name(self) -> str:
        """Return the name of the device."""
        # return self.hostname or f"{self.mac_address}"
        # return self.hostname or f"{self.pfsense_device_name} {self._mac_address}"
        return self.hostname or self._mac_address

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.mac_address)},
            default_manufacturer=self._mac_vendor,
            default_name=self.name,
            via_device=(DOMAIN, self.pfsense_device_unique_id),
        )

    @property
    def icon(self) -> str:
        """Return device icon."""
        try:
            return "mdi:lan-connect" if self.is_connected else "mdi:lan-disconnect"
        except:
            return "mdi:lan-disconnect"

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        entry = self._get_pfsense_arp_entry()
        if entry is None:
            if self._last_known_ip is not None and len(self._last_known_ip) > 0:
                # force a ping to _last_known_ip to possibly recreate arp entry?
                pass

            return False
        # TODO: check "expires" here to add more honed in logic?
        # TODO: clear cache under certain scenarios?
        ip_address = entry.get("ip-address")
        if ip_address is not None and len(ip_address) > 0:
            client = self.hass.data[DOMAIN][self.config_entry.entry_id][PFSENSE_CLIENT]
            self.hass.async_add_executor_job(client.delete_arp_entry, ip_address)

        return True
