import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.routing import Mount

from server.backend import DomainError, ReferenceBackend
from server.contracts import MODELS, DESCRIPTIONS, envelope
from server.identity import AuthMiddleware, BearerMapping, identity
from server.notifications import Notifications
from apps.resources import RESOURCES, MIME_TYPE, resource_html

log = logging.getLogger("cat_nanny.platform")


def build_app(*, backend, mapping, notifications=None, clock=None, allowed_hosts=None, allowed_origins=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    mcp = Server("cat-nanny", version="0.1.0", instructions="Check analysis_status. If unavailable, no health assessment was performed. Present red_flags before follow-up questions. Sent notifications mean provider acceptance, not recipient delivery or read receipt.")

    @mcp.list_resources()
    async def list_resources():
        return [types.Resource(uri=uri, name=name, mimeType=MIME_TYPE)
                for name, uri in RESOURCES.items()]

    @mcp.read_resource()
    async def read_resource(uri):
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        return [ReadResourceContents(content=resource_html(str(uri)), mime_type=MIME_TYPE)]

    @mcp.list_tools()
    async def list_tools():
        return [types.Tool(name=name, description=DESCRIPTIONS[name], inputSchema=model.model_json_schema(),
                           **({"_meta": {"ui": {"resourceUri": RESOURCES[name]}}} if name in RESOURCES else {}),
                           annotations=types.ToolAnnotations(readOnlyHint=(name.startswith("get_") or name == "list_cats"), destructiveHint=False, idempotentHint=True, openWorldHint=name.startswith("log_")))
                for name, model in MODELS.items()]

    @mcp.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        request_id, start = str(uuid.uuid4()), time.monotonic()
        code = "ok"
        try:
            if name not in MODELS:
                raise DomainError("unknown_tool", "Unknown tool")
            try:
                args = MODELS[name].model_validate(arguments).model_dump(mode="json", exclude_none=True)
            except ValidationError as error:
                if any(issue['loc'] == ('occurred_at',) for issue in error.errors()):
                    raise DomainError("invalid_time", "occurred_at must be an ISO 8601 date-time with a timezone, for example 2026-10-12T13:00:00-05:00. Leave it blank to use the recording time.") from None
                raise DomainError("invalid_arguments", "Arguments do not match the tool schema") from None
            principal = identity.get()
            result = await anyio.to_thread.run_sync(backend.execute, name, args, principal, clock())
            result["display_timezone"] = principal.timezone
            if result.get("analysis_status") == "evaluated":
                result.setdefault("limitations", []).append("Prototype health rules have not been reviewed by a veterinarian; this is not a diagnosis.")
            flags = result.get("red_flags", [])
            flags.sort(key=lambda f: {"emergency": 0, "urgent": 1, "warning": 2}.get(f.get("level"), 2))
            if notifications and name.startswith("log_"):
                try:
                    result["notification_status"] = await anyio.to_thread.run_sync(notifications.send, principal.household_id, result.get("event_id"), flags)
                except Exception:
                    # Notification ledger/provider failure must never hide a health warning.
                    result["notification_status"] = {"state": "failed"}
            return result
        except DomainError as error:
            code, message = error.code, error.message
        except Exception:
            code, message = "internal_error", "Request failed; retry with the same idempotency key"
        finally:
            # No bearer tokens, household identifiers, event details, or contact info.
            log.info(json.dumps({"request_id": request_id, "tool": name if name in MODELS else "unknown", "code": code, "duration_ms": round((time.monotonic() - start) * 1000)}))
        result = envelope(error={"code": code, "message": message, "request_id": request_id})
        return types.CallToolResult(isError=True, structuredContent=result, content=[types.TextContent(type="text", text=json.dumps(result))])

    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts or ["127.0.0.1:*", "localhost:*", "testserver"],
        allowed_origins=allowed_origins or ["http://127.0.0.1:*", "http://localhost:*", "http://testserver"])
    manager = StreamableHTTPSessionManager(mcp, stateless=True, json_response=True, security_settings=security,
                                           max_request_body_size=65536)

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    class Endpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    app = Starlette(routes=[Mount("/mcp", app=Endpoint())], lifespan=lifespan)
    app.add_middleware(AuthMiddleware, mapping=mapping)
    return app


def create_app():
    if os.getenv("CAT_NANNY_MODE", "local") != "local":
        raise RuntimeError("Production mode requires an OAuth verifier and B's production backend")
    path = os.getenv("CAT_NANNY_DB", "cat_nanny.sqlite3")
    mapping = BearerMapping(json.loads(os.environ.get("CAT_NANNY_TOKEN_MAP", "{}")))
    topics = json.loads(os.getenv("CAT_NANNY_SNS_TOPICS", "{}"))
    sns = None
    if topics:
        import boto3
        from botocore.config import Config
        # Disable automatic retries: SNS standard topics do not provide SMS exactly-once delivery.
        sns = boto3.client("sns", config=Config(retries={"total_max_attempts": 1}, connect_timeout=2, read_timeout=3))
    from storage.backend import RulesBackend
    from storage.repository import SQLiteRepository
    return build_app(backend=RulesBackend(SQLiteRepository(path)), mapping=mapping,
                     notifications=Notifications(path, sns=sns, topics=topics),
                     allowed_hosts=json.loads(os.getenv("CAT_NANNY_ALLOWED_HOSTS", '["127.0.0.1:*", "localhost:*"]')),
                     allowed_origins=json.loads(os.getenv("CAT_NANNY_ALLOWED_ORIGINS", '["http://127.0.0.1:*", "http://localhost:*"]')))
