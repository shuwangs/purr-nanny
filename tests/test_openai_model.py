import asyncio
import json
import httpx
import pytest
from server.models.openai import OpenAIModel, response_input
from server.models import ModelUnavailable


def test_openai_round_trip_tool_and_reply():
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers['authorization'] == 'Bearer test-only-key'
        assert payload['store'] is False
        assert 'test-only-key' not in request.content.decode()
        if len(requests) == 1:
            assert payload['tools'][0]['strict'] is False
            return httpx.Response(200, json={'status':'completed','output':[
                {'type':'reasoning','id':'r1','summary':[], 'encrypted_content':'opaque'},
                {'type':'function_call','id':'f1','call_id':'c1','name':'get_today','arguments':'{"cat_id":"cat1"}'}]})
        assert payload['input'][1]['type'] == 'reasoning'
        assert payload['input'][-1]['call_id'] == 'c1'
        assert 'feeding' in payload['input'][-1]['output']
        return httpx.Response(200, json={'status':'completed','output':[
            {'type':'message','role':'assistant','content':[{'type':'output_text','text':'One feeding recorded.'}]}]})
    async def run():
        model = OpenAIModel('test-only-key','test-model',httpx.MockTransport(handler))
        messages = [{'role':'user','content':[{'text':'Today?'}]}]
        tools = [{'name':'get_today','description':'Query','inputSchema':{'type':'object'}}]
        reply = await model.complete(messages,tools,'Instructions')
        assert reply.calls[0]['arguments'] == {'cat_id':'cat1'}
        messages.extend([
            {'role':'assistant','content':[], 'provider_output':reply.provider_output},
            {'role':'user','content':[{'toolResult':{'toolUseId':'c1','content':[{'json':{'events':[{'event_type':'feeding'}]}}]}}]}])
        assert (await model.complete(messages,tools,'Instructions')).text == 'One feeding recorded.'
    asyncio.run(run())


@pytest.mark.parametrize('status',[401,429,500])
def test_provider_failure_does_not_leak_response(status):
    model = OpenAIModel('secret','test',httpx.MockTransport(lambda r:httpx.Response(status,text='private provider details')))
    with pytest.raises(ModelUnavailable) as error:
        asyncio.run(model.complete([],[],'Instructions'))
    assert 'private provider details' not in str(error.value)
    assert 'secret' not in str(error.value)


def test_existing_transcript_conversion():
    items = response_input([
        {'role':'assistant','content':[{'toolUse':{'toolUseId':'a','name':'get_today','input':{'cat_id':'cat'}}}]},
        {'role':'user','content':[{'toolResult':{'toolUseId':'a','content':[{'json':{'events':[]}}]}}]}])
    assert [i['type'] for i in items] == ['function_call','function_call_output']
    assert items[0]['call_id'] == items[1]['call_id']
