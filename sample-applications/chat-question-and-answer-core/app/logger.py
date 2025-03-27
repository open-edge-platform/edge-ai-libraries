import structlog
from .config import Settings

config = Settings()


def add_service_name(_, __, event_dict):
    """
    Adds custom processors to add the service name to the event dictionary.

    Args:
        _ (Any): Placeholder for the first argument, not used.
        __ (Any): Placeholder for the second argument, not used.
        event_dict (dict): The event dictionary to which the service name will be added.

    Returns:
        dict: The updated event dictionary with the service name added.
    """

    event_dict["service_name"] = config.APP_DISPLAY_NAME
    return event_dict


# Configure structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        add_service_name,
        structlog.processors.JSONRenderer(),
    ]
)

# Create logger
logger = structlog.get_logger()
