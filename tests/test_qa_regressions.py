from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from server.contracts import MODELS
from server.identity import Identity
from server.notifications import Notifications
from storage.backend import RulesBackend
from storage.repository import SQLiteRepository, StorageError

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)

class SNS:
    def __init__(self): self.calls = 0
    def publish(self, **kwargs):
        self.calls += 1
        return {'MessageId': str(self.calls)}


def test_pm_historical_alert_reproduction(tmp_path):
    backend = RulesBackend(SQLiteRepository(tmp_path/'db'))
    home = Identity('home', 'America/Chicago')
    cat = backend.execute('add_cat', dict(name='Miso', idempotency_key='create-cat'), home, NOW)['cat']['cat_id']
    sns = SNS()
    notifications = Notifications(tmp_path/'db', sns, {'home': 'test'})
    def record(tool, kind, key, details):
        result = backend.execute(tool, dict(cat_id=cat, event_type=kind, idempotency_key=key, details=details), home, NOW)
        notifications.send('home', result['event_id'], result['red_flags'])
        return result
    danger = record('log_health_event', 'litter', 'danger-event', {'straining': True, 'urine_output': 'none'})
    feeding = record('log_care_event', 'feeding', 'feeding-event', {})
    assert feeding['red_flags'] == danger['red_flags']
    assert sns.calls == 1
    notifications.send('home', 'another-event', danger['red_flags'])
    assert sns.calls == 1
    # A separate event triggering the same rule still deserves an alert.
    record('log_health_event', 'litter', 'second-danger', {'straining': True, 'urine_output': 'none'})
    assert sns.calls == 2


def test_alert_evidence_identity_and_concurrency(tmp_path):
    sns = SNS()
    notices = Notifications(tmp_path/'db', sns, {'home': 'test'})
    flags = [{'rule_id': 'aggregate', 'evidence': ['one', 'two']}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda event: notices.send('home', event, flags), ['one', 'two']*4))
    assert sns.calls == 1
    notices.send('home', 'two', [{'rule_id': 'aggregate', 'evidence': ['two', 'one']}])
    assert sns.calls == 1


def test_notification_recovery_and_legacy_failure(tmp_path):
    class TimeoutSNS(SNS):
        def publish(self, **kwargs):
            self.calls += 1
            raise TimeoutError()
    sns = TimeoutSNS()
    path = tmp_path/'db'
    notices = Notifications(path, sns, {'home': 'test'})
    flags = [{'rule_id': 'rule', 'evidence': ['event']}]
    assert notices.send('home', 'event', flags)['state'] == 'uncertain'
    restarted = Notifications(path, sns, {'home': 'test'})
    assert restarted.send('home', 'event', flags)['state'] == 'uncertain'
    assert sns.calls == 1
    assert restarted.reconcile('home', 'event', 'rule', outcome='rejected')
    restarted.sns = SNS()
    assert restarted.send('home', 'event', flags)['state'] == 'sent'
    assert restarted.sns.calls == 1
    with restarted.connect() as db:
        db.execute("INSERT INTO notifications(household,event,rule,state) VALUES('home','old','rule','failed')")
        db.execute("INSERT INTO notifications(household,event,rule,state) VALUES('home','crash','rule','queued')")
    assert restarted.send('home', 'old', [{'rule_id': 'rule'}])['state'] == 'failed'
    assert restarted.send('home', 'crash', [{'rule_id': 'rule'}])['state'] == 'queued'
    assert restarted.reconcile('home', 'crash', 'rule', outcome='sent', message_id='verified')
    assert restarted.send('home', 'crash', [{'rule_id': 'rule'}])['state'] == 'sent'
    assert restarted.sns.calls == 1


def test_confirmed_rejection_can_retry(tmp_path):
    from botocore.exceptions import ClientError
    class Rejected(SNS):
        def publish(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ClientError({'Error': {'Code': 'Throttled'}, 'ResponseMetadata': {'HTTPStatusCode': 429}}, 'Publish')
            return {'MessageId': 'accepted'}
    sns = Rejected()
    notices = Notifications(tmp_path/'db', sns, {'home': 'test'})
    assert notices.send('home', 'event', [{'rule_id': 'rule'}])['state'] == 'failed'
    assert notices.send('home', 'event', [{'rule_id': 'rule'}])['state'] == 'sent'
    assert sns.calls == 2


def test_discovery_is_scoped_and_preserves_ambiguous_names(tmp_path):
    repo = SQLiteRepository(tmp_path/'db')
    for home, key in [('a', 'first-cat'), ('a', 'second-cat'), ('b', 'other-cat')]:
        repo.mutate(home, 'add_cat', dict(name='Miso', idempotency_key=key), NOW)
    backend = RulesBackend(SQLiteRepository(tmp_path/'db'))
    cats = backend.execute('list_cats', {}, Identity('a', 'America/Chicago'), NOW)['cats']
    assert len(cats) == 2 and len({cat['cat_id'] for cat in cats}) == 2
    assert backend.execute('list_cats', {}, Identity('empty', 'America/Chicago'), NOW)['cats'] == []


@pytest.mark.parametrize('kind,details', [
    ('vomiting', {'weight_kg': 5}), ('feeding', {'blood': True}),
    ('vomiting', {'blood': 'false'}), ('appetite', {'duration_hours': True}),
    ('weight', {'weight_kg': float('nan')}), ('energy', {'level': 'sleepy'}),
    ('litter', {'unknown': None}), ('weight', {'weight_kg': 0}),
])
def test_details_rejected_at_transport_and_storage(tmp_path, kind, details):
    tool = 'log_care_event' if kind == 'feeding' else 'log_health_event'
    args = dict(cat_id='cat', idempotency_key='event-key', event_type=kind, details=details)
    with pytest.raises(ValidationError): MODELS[tool].model_validate(args)
    with pytest.raises(StorageError) as error: SQLiteRepository(tmp_path/'db').mutate('home', tool, args, NOW)
    assert error.value.code == 'invalid_details'


def test_schema_and_explicit_unknown_preserved():
    schema = MODELS['log_health_event'].model_json_schema()
    vomiting = next(part['then']['properties']['details'] for part in schema['allOf'] if part['if']['properties']['event_type']['const'] == 'vomiting')
    assert vomiting['additionalProperties'] is False
    assert set(vomiting['properties']) == {'blood', 'lethargy', 'after_meal'}
    args = MODELS['log_health_event'].model_validate(dict(cat_id='cat', idempotency_key='event-key', event_type='vomiting', details={'blood': None}))
    assert args.model_dump(exclude_none=True)['details'] == {'blood': None}


def test_all_stories_through_sdk_http_client(tmp_path):
    import anyio
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from server.app import build_app
    from server.identity import BearerMapping
    sns = SNS()
    token, other_token = 'a'*40, 'b'*40
    app = build_app(backend=RulesBackend(SQLiteRepository(tmp_path/'db')),
        mapping=BearerMapping({token: {'household_id': 'home', 'timezone': 'America/Chicago'},
                               other_token: {'household_id': 'other', 'timezone': 'America/Chicago'}}),
        notifications=Notifications(tmp_path/'db', sns, {'home': 'test'}), clock=lambda: NOW)
    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers={'Authorization': 'Bearer '+token}) as http:
                async with streamable_http_client('http://testserver/mcp/', http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        async def call(name, args):
                            result = await session.call_tool(name, args)
                            assert not result.isError, result
                            return result.structuredContent
                        cat = (await call('add_cat', {'name': 'Miso', 'idempotency_key': 'create-cat'}))['cat']['cat_id']
                        assert (await call('list_cats', {}))['cats'][0]['cat_id'] == cat
                        observation = dict(cat_id=cat, event_type='vomiting', idempotency_key='record-event', details={})
                        first = await call('log_health_event', observation)
                        assert first['follow_up']
                        supplement = {**observation, 'event_id': first['event_id'], 'idempotency_key': 'answer-event', 'details': {'blood': True}}
                        warning = await call('log_health_event', supplement)
                        assert warning['red_flags'][0]['level'] == 'urgent'
                        assert warning['notification_status']['state'] == 'sent'
                        await call('log_health_event', supplement)
                        assert sns.calls == 1
                        feeding = await call('log_care_event', dict(cat_id=cat, event_type='feeding', idempotency_key='feed-event', reporter='Alex', details={'food': 'wet food'}))
                        assert feeding['notification_status']['state'] == 'disabled'
                        assert sns.calls == 1
                        today = await call('get_today', {'cat_id': cat})
                        assert len(today['events']) == 2
                        assert today['events'][1]['reporter'] == 'Alex' or today['events'][0]['reporter'] == 'Alex'
                        stats = await call('get_patterns', {'cat_id': cat})
                        assert stats['patterns'][1]['status'] == 'insufficient_data'
                        summary = await call('get_vet_summary', {'cat_id': cat})
                        assert {event['event_id'] for event in summary['timeline']} == {event['event_id'] for event in today['events']}
                        invalid = await session.call_tool('log_health_event', {**observation, 'details': {'typo': True}})
                        assert invalid.isError and invalid.structuredContent['error']['code'] == 'invalid_arguments'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers={'Authorization': 'Bearer '+other_token}) as http:
                async with streamable_http_client('http://testserver/mcp/', http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        assert (await session.call_tool('list_cats', {})).structuredContent['cats'] == []
                        assert (await session.call_tool('get_today', {'cat_id': cat})).isError
    anyio.run(exercise)


def test_dynamodb_discovery_pagination_and_atomic_catalog():
    import json
    from storage.dynamodb import DynamoDBRepository, partition
    class Table:
        name = 'test'
        def __init__(self):
            self.calls = []
            self.actions = None
            self.meta = type('Meta', (), {'client': self})()
        def get_item(self, **kwargs): return {}
        def transact_write_items(self, **kwargs): self.actions = kwargs['TransactItems']
        def query(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs['ExpressionAttributeValues'][':pk'] == partition('home', '__cats__')
            page = {'Items': [{'body': json.dumps(dict(cat_id=str(len(self.calls)), name='Miso'))}]}
            if len(self.calls) == 1: page['LastEvaluatedKey'] = {'PK': 'catalog', 'SK': 'CAT#one'}
            else: assert kwargs['ExclusiveStartKey']['SK'] == 'CAT#one'
            return page
    table = Table()
    repo = DynamoDBRepository(table)
    cat = repo.mutate('home', 'add_cat', dict(name='Miso', idempotency_key='create-cat'), NOW)
    catalog = table.actions[1]['Put']['Item']
    assert catalog['PK'] == partition('home', '__cats__')
    assert catalog['SK'] == 'CAT#'+cat['cat_id']
    assert json.loads(catalog['body']) == cat
    assert len(repo.list_cats('home')) == 2
