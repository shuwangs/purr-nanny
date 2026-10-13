"""Local development bearer mapping. Production OAuth verifier must replace this."""
import hashlib
import hmac
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    household_id: str
    timezone: str


identity: ContextVar[Identity] = ContextVar("household_identity")


class BearerMapping:
    def __init__(self, entries: dict):
        from zoneinfo import ZoneInfo
        self.entries = []
        for token, config in entries.items():
            if len(token) < 32:
                raise ValueError("Development bearer tokens must have at least 32 characters")
            ZoneInfo(config["timezone"])
            self.entries.append((hashlib.sha256(token.encode()).digest(), Identity(**config)))
        if not self.entries:
            raise ValueError("Configure CAT_NANNY_TOKEN_MAP; anonymous access is disabled")

    def resolve(self, authorization: str) -> Identity | None:
        if not authorization.startswith("Bearer "):
            return None
        digest = hashlib.sha256(authorization[7:].encode()).digest()
        for expected, principal in self.entries:
            if hmac.compare_digest(digest, expected):
                return principal
        return None


class AuthMiddleware:
    def __init__(self, app, mapping):
        self.app, self.mapping = app, mapping

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        headers = dict(scope["headers"])
        principal = self.mapping.resolve(headers.get(b"authorization", b"").decode("utf-8", errors="replace"))
        if principal is None:
            return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        context = identity.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            identity.reset(context)
