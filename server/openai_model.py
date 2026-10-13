"""Responses API adapter; MCP tools still run through the local gateway."""
import json
import httpx
from server.models import ModelReply, ModelUnavailable


def response_input(messages):
    items = []
    for message in messages:
        if message.get('provider_output'):
            items.extend(message['provider_output'])
            continue
        for block in message['content']:
            if 'text' in block:
                items.append({'role': message['role'], 'content': block['text']})
            elif 'toolUse' in block:
                call = block['toolUse']
                items.append({'type': 'function_call', 'call_id': call['toolUseId'],
                              'name': call['name'], 'arguments': json.dumps(call['input'], ensure_ascii=False)})
            elif 'toolResult' in block:
                result = block['toolResult']
                items.append({'type': 'function_call_output', 'call_id': result['toolUseId'],
                              'output': json.dumps(result['content'], ensure_ascii=False)})
    return items


class OpenAIModel:
    def __init__(self, api_key, model_id, transport=None):
        if not api_key or not model_id:
            raise ValueError('Set OPENAI_API_KEY and CAT_NANNY_OPENAI_MODEL')
        self.api_key, self.model_id, self.transport = api_key, model_id, transport

    async def complete(self, messages, tools, system):
        payload = dict(model=self.model_id, instructions=system, input=response_input(messages),
                       store=False, include=['reasoning.encrypted_content'], max_output_tokens=2400,
                       tools=[dict(type='function', name=t['name'], description=t['description'],
                                   parameters=t['inputSchema'], strict=False) for t in tools])
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport, follow_redirects=False) as client:
                response = await client.post('https://api.openai.com/v1/responses', json=payload,
                                             headers={'Authorization': 'Bearer ' + self.api_key})
            if response.status_code == 401:
                raise ModelUnavailable('OpenAI API key is invalid; check server configuration.')
            if response.status_code == 429:
                raise ModelUnavailable('OpenAI quota or rate limit reached; check API billing and limits, then retry the same message.')
            response.raise_for_status()
            data = response.json()
            if data.get('status') != 'completed':
                raise ModelUnavailable('OpenAI response did not complete; retry the same message.')
            output = data['output']
            calls = [dict(id=b['call_id'], name=b['name'], arguments=json.loads(b['arguments']))
                     for b in output if b['type'] == 'function_call']
            if any(not isinstance(c['arguments'], dict) for c in calls):
                raise ValueError('Invalid tool arguments')
            text = '\n'.join(c['text'] for b in output if b['type'] == 'message'
                             for c in b['content'] if c['type'] == 'output_text')
            return ModelReply(text=text, calls=calls, provider_output=output)
        except ModelUnavailable:
            raise
        except Exception:
            raise ModelUnavailable('OpenAI request failed; check model access and connectivity, then retry the same message.') from None
