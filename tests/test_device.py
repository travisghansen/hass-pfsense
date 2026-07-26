"""Tests for pfSense device registration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "pfsense" / "device.py"
)
SPEC = importlib.util.spec_from_file_location("pfsense_device", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

get_gateway_device_unique_id = MODULE.get_gateway_device_unique_id
get_existing_gateway_device_unique_id = MODULE.get_existing_gateway_device_unique_id
get_child_device_mac_address = MODULE.get_child_device_mac_address
remove_device_mac_address_from_lists = MODULE.remove_device_mac_address_from_lists
get_removable_duplicate_gateway_device_ids = (
    MODULE.get_removable_duplicate_gateway_device_ids
)
get_removable_duplicate_gateway_entity_ids = (
    MODULE.get_removable_duplicate_gateway_entity_ids
)


class GetGatewayDeviceUniqueIdTests(unittest.TestCase):
    """Cover stable gateway device ID selection."""

    def test_prefers_cached_unique_id(self) -> None:
        """Keep using the cached gateway ID once it is known."""
        self.assertEqual(
            get_gateway_device_unique_id(
                "entry-device-id",
                None,
                "firewall-device-id",
            ),
            "firewall-device-id",
        )

    def test_uses_current_unique_id_when_no_cache(self) -> None:
        """Use the live pfSense ID when no cached value exists yet."""
        self.assertEqual(
            get_gateway_device_unique_id(
                "entry-device-id",
                "firewall-device-id",
            ),
            "firewall-device-id",
        )

    def test_falls_back_to_config_entry_unique_id(self) -> None:
        """Use the config entry ID if pfSense does not report one."""
        self.assertEqual(
            get_gateway_device_unique_id("entry-device-id", None),
            "entry-device-id",
        )


@dataclass
class MockDevice:
    """Minimal device-registry entry for helper tests."""

    id: str
    identifiers: set[tuple[str, str]]
    connections: set[tuple[str, str]] = field(default_factory=set)
    config_entries: set[str] = field(default_factory=set)
    via_device_id: str | None = None
    disabled_by: str | None = None

    @property
    def disabled(self) -> bool:
        """Return whether the mock device is disabled."""
        return self.disabled_by is not None


@dataclass
class MockEntity:
    """Minimal entity-registry entry for helper tests."""

    entity_id: str
    unique_id: str
    device_id: str | None = None
    disabled_by: str | None = None


class ChildDeviceRemovalHelperTests(unittest.TestCase):
    """Cover child-device deletion helpers."""

    def test_get_child_device_mac_address_returns_mac_for_child_device(self) -> None:
        """Child devices expose their MAC address for UI deletion."""
        self.assertEqual(
            get_child_device_mac_address(
                MockDevice(
                    id="tracker",
                    identifiers=set(),
                    connections={("mac", "AA:BB:CC:DD:EE:FF")},
                    config_entries={"entry-id"},
                    via_device_id="gateway",
                ),
                "entry-id",
            ),
            "aa:bb:cc:dd:ee:ff",
        )

    def test_get_child_device_mac_address_ignores_gateway_devices(self) -> None:
        """Gateway devices are not removable through the child-device flow."""
        self.assertIsNone(
            get_child_device_mac_address(
                MockDevice(
                    id="gateway",
                    identifiers={("pfsense", "gateway-id")},
                    connections={("mac", "AA:BB:CC:DD:EE:FF")},
                    config_entries={"entry-id"},
                ),
                "entry-id",
            )
        )

    def test_remove_device_mac_address_from_lists_is_case_insensitive(self) -> None:
        """Removing a child device drops its MAC from both config lists."""
        self.assertEqual(
            remove_device_mac_address_from_lists(
                "aa:bb:cc:dd:ee:ff",
                ["11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"],
                ["aa:bb:cc:dd:ee:ff", "77:88:99:AA:BB:CC"],
            ),
            (
                ["11:22:33:44:55:66"],
                ["77:88:99:AA:BB:CC"],
            ),
        )


class GetExistingGatewayDeviceUniqueIdTests(unittest.TestCase):
    """Cover stable reuse of existing gateway devices."""

    def test_prefers_existing_gateway_device_with_entities(self) -> None:
        """Keep using the existing entity-backed gateway device on upgrade."""
        devices = [
            MockDevice(
                id="legacy",
                identifiers={("pfsense", "entry-device-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="current",
                identifiers={("pfsense", "firewall-device-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_existing_gateway_device_unique_id(
                devices,
                "entry-id",
                "pfsense",
                {"legacy"},
                current_unique_id="firewall-device-id",
                config_entry_unique_id="entry-device-id",
            ),
            "entry-device-id",
        )

    def test_prefers_current_gateway_identifier_when_it_already_exists(self) -> None:
        """Reuse the current pfSense device ID when it is already registered."""
        devices = [
            MockDevice(
                id="legacy",
                identifiers={("pfsense", "entry-device-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="current",
                identifiers={("pfsense", "firewall-device-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_existing_gateway_device_unique_id(
                devices,
                "entry-id",
                "pfsense",
                {"current"},
                current_unique_id="firewall-device-id",
                config_entry_unique_id="entry-device-id",
            ),
            "firewall-device-id",
        )

    def test_prefers_enabled_gateway_over_disabled_entity_backed_gateway(self) -> None:
        """Avoid attaching new entities to a disabled duplicate gateway device."""
        devices = [
            MockDevice(
                id="legacy",
                identifiers={("pfsense", "entry-device-id")},
                config_entries={"entry-id"},
                disabled_by="user",
            ),
            MockDevice(
                id="current",
                identifiers={("pfsense", "firewall-device-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_existing_gateway_device_unique_id(
                devices,
                "entry-id",
                "pfsense",
                {"legacy"},
                current_unique_id="firewall-device-id",
                config_entry_unique_id="entry-device-id",
            ),
            "firewall-device-id",
        )

    def test_ignores_child_devices(self) -> None:
        """Child devices must not be considered gateway-device candidates."""
        devices = [
            MockDevice(
                id="tracker",
                identifiers={("pfsense", "child-id")},
                config_entries={"entry-id"},
                via_device_id="gateway",
            )
        ]

        self.assertIsNone(
            get_existing_gateway_device_unique_id(
                devices,
                "entry-id",
                "pfsense",
                set(),
                current_unique_id="firewall-device-id",
                config_entry_unique_id="entry-device-id",
            )
        )


class GetRemovableDuplicateGatewayDeviceIdsTests(unittest.TestCase):
    """Cover duplicate gateway cleanup selection."""

    def test_returns_orphaned_duplicate_gateway(self) -> None:
        """Remove older gateway devices once nothing references them."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_device_ids(
                devices,
                "entry-id",
                "pfsense",
                "gateway-id",
                {"canonical"},
            ),
            ["duplicate"],
        )

    def test_skips_duplicate_gateway_with_entities(self) -> None:
        """Keep duplicates that still own entity-registry entries."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_device_ids(
                devices,
                "entry-id",
                "pfsense",
                "gateway-id",
                {"canonical", "duplicate"},
            ),
            [],
        )

    def test_allows_manual_removal_of_duplicate_gateway_with_entities(self) -> None:
        """Manual duplicate deletion can ignore stale entity attachments."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
            ),
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_device_ids(
                devices,
                "entry-id",
                "pfsense",
                "gateway-id",
                {"canonical", "duplicate"},
                require_no_entities=False,
            ),
            ["duplicate"],
        )


class GetRemovableDuplicateGatewayEntityIdsTests(unittest.TestCase):
    """Cover duplicate gateway entity cleanup selection."""

    def test_returns_device_disabled_entities_on_duplicate_gateway(self) -> None:
        """Remove stale entities that only exist due to a disabled duplicate device."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
                disabled_by="user",
            ),
        ]
        entities = [
            MockEntity(
                entity_id="sensor.pfsense_temp",
                unique_id="legacy_id_telemetry_system_temp",
                device_id="duplicate",
                disabled_by="device",
            )
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_entity_ids(
                devices,
                entities,
                "entry-id",
                "pfsense",
                "gateway-id",
                "device",
            ),
            ["sensor.pfsense_temp"],
        )

    def test_keeps_duplicate_gateway_entities_when_not_disabled_by_device(self) -> None:
        """Do not drop duplicate-gateway entities disabled for another reason."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
            ),
        ]
        entities = [
            MockEntity(
                entity_id="sensor.pfsense_temp",
                unique_id="legacy_id_telemetry_system_temp",
                device_id="duplicate",
                disabled_by="user",
            )
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_entity_ids(
                devices,
                entities,
                "entry-id",
                "pfsense",
                "gateway-id",
                "device",
            ),
            [],
        )

    def test_skips_duplicate_gateway_with_child_devices(self) -> None:
        """Keep duplicates while other devices still point at them."""
        devices = [
            MockDevice(
                id="canonical",
                identifiers={("pfsense", "gateway-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="duplicate",
                identifiers={("pfsense", "legacy-id")},
                config_entries={"entry-id"},
            ),
            MockDevice(
                id="tracker",
                identifiers=set(),
                config_entries={"entry-id"},
                via_device_id="duplicate",
            ),
        ]

        self.assertEqual(
            get_removable_duplicate_gateway_device_ids(
                devices,
                "entry-id",
                "pfsense",
                "gateway-id",
                {"canonical", "tracker"},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
