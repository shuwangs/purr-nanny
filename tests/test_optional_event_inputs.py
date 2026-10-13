from datetime import datetime, timezone
import json
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient
from server.app import build_app
from server.contracts import MODELS
from server.identity import BearerMapping
from storage.backend import RulesBackend
from storage.repository import SQLiteRepository

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)
TOKEN = 't' * 40


@pytest.mark.parametrize('tool,event_type', [('log_health_event', 'vomiting'), ('log_care_event', 'feeding')])
def test_optional_fields_through_mcp(tmp_path, tool, event_type):
    app = build_app(backend=RulesBackend(SQLiteRepository(tmp_path / 'db')), mapping=BearerMapping({TOKEN: {'household_id':'home','timezone':'America/Chicago'}}), clock=lambda: NOW)
    with TestClient(app) as client:
        headers = {'Authorization':f'Bearer {TOKEN}', 'Accept':'application/json, text/event-stream'}
        def rpc(name, args):
            response = client.post('/mcp/', headers=headers, json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
            assert response.status_code == 200
            return response.json()['result']
        initialized = client.post('/mcp/', headers=headers, json={'jsonrpc':'2.0','id':0,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
        headers['MCP-Protocol-Version'] = initialized.json()['result']['protocolVersion']
        cat = rpc('add_cat', {'name':'Mochi','idempotency_key':'create-cat'})['structuredContent']['cat']['cat_id']
        base = dict(cat_id=cat, event_type=event_type, idempotency_key='blank-input')
        original = None
        # All empty forms normalize to the same retry request and event ID.
        for extras in [{}, {'occurred_at':None,'event_id':None}, {'occurred_at':'','event_id':''}, {'occurred_at':' \t\n','event_id':' \t\n'}]:
            result = rpc(tool, {**base, **extras})
            assert not result['isError']
            event = result['structuredContent']['event']
            assert event['occurred_at'] == NOW.isoformat()
            assert event['time_defaulted']
            original = original or event['event_id']
            assert event['event_id'] == original
        valid = rpc(tool, {**base,'idempotency_key':'valid-time','event_id':'', 'occurred_at':'2026-10-12T08:00:00-05:00'})['structuredContent']['event']
        assert valid['occurred_at'] == '2026-10-12T13:00:00+00:00'
        assert not valid['time_defaulted'] and valid['event_id'] != original
        for bad in ['not-a-date','2026-10-12T08:00:00']:
            result = rpc(tool, {**base,'idempotency_key':'invalid-time','occurred_at':bad})
            assert result['isError']
            error = result['structuredContent']['error']
            assert error['code'] == 'invalid_time'
            assert 'ISO 8601' in error['message'] and 'timezone' in error['message']
        # Empty occurrence on a follow-up preserves the original event's occurrence.
        updated = rpc(tool, {**base,'idempotency_key':'followup-key','event_id':valid['event_id'],'occurred_at':'  '})['structuredContent']['event']
        assert updated['occurred_at'] == valid['occurred_at']
        assert len(rpc('get_today', {'cat_id':cat})['structuredContent']['events']) == 2


def test_schema_accepts_blank_optional_time():
    import jsonschema
    schema = MODELS['log_health_event'].model_json_schema()
    for value in ['', '  ', None, '2026-10-12T18:00:00Z']:
        jsonschema.validate({'cat_id':'cat','idempotency_key':'event-key','event_type':'vomiting','occurred_at':value,'event_id':''}, schema, format_checker=jsonschema.FormatChecker())
