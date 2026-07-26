"""Helpers for pfSense device registration."""

from __future__ import annotations

from collections.abc import Iterable


def get_gateway_device_unique_id(
    config_entry_unique_id: str | None,
    current_unique_id: str | None,
    cached_unique_id: str | None = None,
) -> str | None:
    """Return the stable unique ID to use for the pfSense gateway device."""
    if cached_unique_id:
        return cached_unique_id
    if current_unique_id:
        return current_unique_id
    return config_entry_unique_id


def get_existing_gateway_device_unique_id(
    devices: Iterable,
    config_entry_id: str,
    domain: str,
    entity_device_ids: set[str],
    current_unique_id: str | None = None,
    config_entry_unique_id: str | None = None,
) -> str | None:
    """Return the best existing gateway device ID for a config entry."""
    selected_unique_id = None
    selected_score = None

    for device in devices:
        if config_entry_id not in device.config_entries:
            continue
        if device.via_device_id is not None:
            continue

        gateway_unique_ids = sorted(
            identifier[1]
            for identifier in device.identifiers
            if identifier[0] == domain
        )
        if not gateway_unique_ids:
            continue

        device_score = (
            not getattr(device, "disabled", False),
            device.id in entity_device_ids,
            current_unique_id in gateway_unique_ids if current_unique_id else False,
            (
                config_entry_unique_id in gateway_unique_ids
                if config_entry_unique_id
                else False
            ),
        )
        device_unique_id = gateway_unique_ids[0]
        if current_unique_id in gateway_unique_ids:
            device_unique_id = current_unique_id
        elif config_entry_unique_id in gateway_unique_ids:
            device_unique_id = config_entry_unique_id

        if selected_score is None or device_score > selected_score:
            selected_score = device_score
            selected_unique_id = device_unique_id

    return selected_unique_id


def get_child_device_mac_address(
    device,
    config_entry_id: str,
    mac_connection_key: str = "mac",
) -> str | None:
    """Return the MAC address for a removable child device."""
    if device.via_device_id is None:
        return None
    if config_entry_id not in device.config_entries:
        return None

    for connection_type, connection_value in device.connections:
        if connection_type == mac_connection_key:
            return connection_value.lower()

    return None


def remove_device_mac_address_from_lists(
    mac_address: str,
    configured_mac_addresses: list[str],
    tracked_mac_addresses: list[str],
) -> tuple[list[str], list[str]]:
    """Remove a MAC address from configured and tracked MAC address lists."""
    normalized_mac_address = mac_address.lower()
    return (
        [
            configured_mac_address
            for configured_mac_address in configured_mac_addresses
            if configured_mac_address.lower() != normalized_mac_address
        ],
        [
            tracked_mac_address
            for tracked_mac_address in tracked_mac_addresses
            if tracked_mac_address.lower() != normalized_mac_address
        ],
    )


def get_removable_duplicate_gateway_device_ids(
    devices: Iterable,
    config_entry_id: str,
    domain: str,
    gateway_device_unique_id: str | None,
    entity_device_ids: set[str],
    require_no_entities: bool = True,
) -> list[str]:
    """Return duplicate gateway device IDs that can be safely removed."""
    if not gateway_device_unique_id:
        return []

    gateway_identifier = (domain, gateway_device_unique_id)
    devices = list(devices)
    device_ids_with_children = {
        device.via_device_id for device in devices if device.via_device_id
    }
    duplicate_device_ids = []

    for device in devices:
        if gateway_identifier in device.identifiers:
            continue
        if not any(identifier[0] == domain for identifier in device.identifiers):
            continue
        if require_no_entities and device.id in entity_device_ids:
            continue
        if device.id in device_ids_with_children:
            continue
        if device.config_entries != {config_entry_id}:
            continue
        duplicate_device_ids.append(device.id)

    return duplicate_device_ids


def get_removable_duplicate_gateway_entity_ids(
    devices: Iterable,
    entities: Iterable,
    config_entry_id: str,
    domain: str,
    gateway_device_unique_id: str | None,
    duplicate_entity_disabler,
) -> list[str]:
    """Return stale duplicate-gateway entity IDs that can be safely removed."""
    entities = list(entities)
    duplicate_device_ids = set(
        get_removable_duplicate_gateway_device_ids(
            devices,
            config_entry_id,
            domain,
            gateway_device_unique_id,
            {entity.device_id for entity in entities if entity.device_id},
            require_no_entities=False,
        )
    )
    removable_entity_ids = []

    for duplicate_device_id in duplicate_device_ids:
        device_entities = [
            entity for entity in entities if entity.device_id == duplicate_device_id
        ]
        if not device_entities:
            continue
        if not all(
            entity.disabled_by == duplicate_entity_disabler for entity in device_entities
        ):
            continue
        removable_entity_ids.extend(entity.entity_id for entity in device_entities)

    return removable_entity_ids
