"""Official MCP Streamable HTTP client; authorization is forwarded server-side only."""
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import httpx
from datetime import timedelta


class MCPGateway:
    def __init__(self, url, client_factory=None):
        parts = urlsplit(url)
        if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Configure a canonical MCP URL without credentials or query parameters')
        if parts.scheme == 'http' and parts.hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('Non-loopback MCP connections require HTTPS')
        self.url, self.client_factory = url, client_factory

    @asynccontextmanager
    async def connect(self, bearer):
        factory = self.client_factory or httpx.AsyncClient
        async with factory(headers={'Authorization':f'Bearer {bearer}'},timeout=20,follow_redirects=False) as http:
            async with streamable_http_client(self.url, http_client=http) as (read,write,_):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as session:
                    await session.initialize()
                    yield session

    async def tools(self, bearer):
        async with self.connect(bearer) as session:
            result = await session.list_tools()
            return [dict(name=tool.name,description=tool.description or '',inputSchema=tool.inputSchema) for tool in result.tools]

    async def call(self, bearer, name, arguments):
        async with self.connect(bearer) as session:
            result = await session.call_tool(name,arguments)
            data = result.structuredContent
            if data is None:
                import json
                data = next((json.loads(block.text) for block in result.content if getattr(block,'type',None)=='text'), {})
            return dict(name=name,is_error=bool(result.isError),structuredContent=data)
