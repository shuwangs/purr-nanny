"""Shared backend interface and domain errors."""
from datetime import datetime
from typing import Protocol
from server.identity import Identity


class Backend(Protocol):
    def execute(self, tool: str, args: dict, principal: Identity, now: datetime) -> dict: ...


class DomainError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)
