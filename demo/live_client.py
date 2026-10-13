"""Interactive MCP client for the local simulator route; uses real HTTP calls."""
import argparse
import asyncio
import json
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def display(result):
    body = result.structuredContent or {}
    for flag in body.get('red_flags', []):
        print(f"{flag['level'].upper()}: {flag['recommended_wording']}")
    if body.get('includes_sample_data'):
        print('Includes sample data for demo')
    for question in body.get('follow_up', []):
        print(f"Follow-up ({question['field']}): {question['question']}")
    print(json.dumps(body or result.model_dump(mode='json'), indent=2))


async def run(url, token):
    if not token:
        raise ValueError('Set CAT_NANNY_CLIENT_TOKEN to a configured development token')
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer '+token}, timeout=30) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print('Purr Nanny local MCP client. Prototype rules; not a diagnosis.')
                print('Enter TOOL JSON, schemas, or quit. Use list_cats to select a cat_id.')
                print('Tools: '+', '.join(tool.name for tool in tools.tools))
                display(await session.call_tool('list_cats', {}))
                while True:
                    try:
                        line = await asyncio.to_thread(input, '> ')
                    except EOFError:
                        break
                    if line.strip() == 'quit':
                        break
                    if line.strip() == 'schemas':
                        print(json.dumps({tool.name: tool.inputSchema for tool in tools.tools}, indent=2))
                        continue
                    if not line.strip():
                        continue
                    name, _, raw = line.strip().partition(' ')
                    try:
                        arguments = json.loads(raw or '{}')
                        if not isinstance(arguments, dict):
                            raise ValueError('Arguments must be a JSON object')
                    except ValueError as error:
                        print(str(error))
                        continue
                    display(await session.call_tool(name, arguments))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000/mcp/')
    args = parser.parse_args()
    asyncio.run(run(args.url, os.environ.get('CAT_NANNY_CLIENT_TOKEN', '')))
