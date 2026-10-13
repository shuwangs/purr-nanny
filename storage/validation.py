from pydantic import ValidationError
from server.event_details import validate
from .repository import StorageError


def validate_details(event_type, details):
    try:
        validate(event_type, details)
    except (ValidationError, ValueError):
        raise StorageError('invalid_details', 'Details do not match the event type schema') from None
