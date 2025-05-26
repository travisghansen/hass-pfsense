import logging

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.service import entity_service_call
import voluptuous as vol

from .const import (
    DOMAIN,
    SERVICE_CLOSE_NOTICE,
    SERVICE_EXEC_COMMAND,
    SERVICE_EXEC_PHP,
    SERVICE_FILE_NOTICE,
    SERVICE_KILL_STATES,
    SERVICE_RESET_STATE_TABLE,
    SERVICE_RESTART_SERVICE,
    SERVICE_SEND_WOL,
    SERVICE_SET_DEFAULT_GATEWAY,
    SERVICE_START_SERVICE,
    SERVICE_STOP_SERVICE,
    SERVICE_SYSTEM_HALT,
    SERVICE_SYSTEM_REBOOT,
)

_LOGGER = logging.getLogger(__name__)

_data = set()


def async_get_entities(hass: HomeAssistant) -> dict[str, Entity]:
    """Get entities for a domain."""
    entities: dict[str, Entity] = {}
    for platform in async_get_platforms(hass, DOMAIN):
        entities.update(platform.entities)
    return entities


class ServiceRegistrar:
    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize with hass object."""
        self.hass = hass

    @callback
    def async_register(self):
        # services do not need to be reloaded for every config_entry
        if "loaded" in _data:
            return

        _data.add("loaded")

        # Setup services
        async def _async_send_service(call: ServiceCall):
            await entity_service_call(
                self.hass, async_get_entities(self.hass), f"service_{call.service}", call
            )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_CLOSE_NOTICE,
            schema=cv.make_entity_service_schema(
                {
                    vol.Optional("id", default="all"): vol.Any(
                        cv.positive_int, cv.string
                    ),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_FILE_NOTICE,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("id"): vol.Any(cv.string),
                    vol.Required("notice"): vol.Any(cv.string),
                    vol.Optional("category", default="HASS"): vol.Any(cv.string),
                    vol.Optional("url", default=""): vol.Any(cv.string),
                    vol.Optional("priority", default=1): cv.positive_int,
                    vol.Optional("local_only", default=False): cv.boolean,
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_START_SERVICE,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("service_name"): vol.Any(cv.string),
                    vol.Optional("service"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_STOP_SERVICE,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("service_name"): vol.Any(cv.string),
                    vol.Optional("service"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_RESTART_SERVICE,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("service_name"): vol.Any(cv.string),
                    vol.Optional("only_if_running"): vol.Any(
                        cv.positive_int, cv.string, cv.boolean
                    ),
                    vol.Optional("service"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_RESET_STATE_TABLE,
            schema={},
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_KILL_STATES,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("source"): vol.Any(cv.string),
                    vol.Optional("destination"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_SYSTEM_HALT,
            schema=cv.make_entity_service_schema({}),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_SYSTEM_REBOOT,
            schema=cv.make_entity_service_schema({}),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_SEND_WOL,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("interface"): vol.Any(cv.string),
                    vol.Required("mac"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_SET_DEFAULT_GATEWAY,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("gateway"): vol.Any(cv.string),
                    vol.Required("ip_version"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_EXEC_COMMAND,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("command"): vol.Any(cv.string),
                    vol.Optional("background"): cv.boolean,
                }
            ),
            service_func=_async_send_service,
        )

        self.hass.services.async_register(
            domain=DOMAIN,
            service=SERVICE_EXEC_PHP,
            schema=cv.make_entity_service_schema(
                {
                    vol.Required("script"): vol.Any(cv.string),
                }
            ),
            service_func=_async_send_service,
        )
