"""Provider boundary. Tests inject a scripted model; live default is configured Bedrock."""
from dataclasses import dataclass, field
import anyio


@dataclass
class ModelReply:
    text: str = ''
    calls: list[dict] = field(default_factory=list)
    provider_output: list[dict] = field(default_factory=list)


class ModelUnavailable(Exception):
    pass


class BedrockModel:
    def __init__(self, client, model_id):
        self.client, self.model_id = client, model_id

    async def complete(self, messages, tools, system):
        def invoke():
            return self.client.converse(modelId=self.model_id, system=[{'text':system}],messages=messages,
                toolConfig={'tools':[{'toolSpec':{'name':tool['name'],'description':tool['description'],'inputSchema':{'json':tool['inputSchema']}}} for tool in tools]},
                inferenceConfig={'maxTokens':1200,'temperature':0})
        try:
            result = await anyio.to_thread.run_sync(invoke)
            blocks = result['output']['message']['content']
            if result.get('stopReason') not in ('end_turn','tool_use','stop_sequence'):
                raise ModelUnavailable('Model did not finish its response')
            return ModelReply(text='\n'.join(block['text'] for block in blocks if 'text' in block),
                calls=[dict(id=block['toolUse']['toolUseId'],name=block['toolUse']['name'],arguments=block['toolUse']['input']) for block in blocks if 'toolUse' in block])
        except ModelUnavailable:
            raise
        except Exception:
            raise ModelUnavailable('Model provider unavailable; retry the same message') from None


class UnconfiguredModel:
    async def complete(self, messages, tools, system):
        raise ModelUnavailable('Configure OpenAI API access or Bedrock to enable natural-language chat')
