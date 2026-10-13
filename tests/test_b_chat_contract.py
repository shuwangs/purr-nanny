"""Backend guarantees the dialogue agent can rely on, without mocking an LLM."""
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
import pytest
from server.backend import DomainError
from server.identity import Identity
from storage import SQLiteRepository
from storage.backend import RulesBackend

NOW = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)


@pytest.fixture
def domain():
    with TemporaryDirectory() as folder:
        repository = SQLiteRepository(folder+'/chat-contract.db')
        yield RulesBackend(repository), Identity('chat-home', 'America/Chicago')


def test_dialogue_followup_preserves_event_and_retry(domain):
    backend, identity = domain
    cat = backend.execute('add_cat', {'name': 'Miso', 'idempotency_key': 'chat-add-miso'}, identity, NOW)['cat']
    initial = dict(cat_id=cat['cat_id'], event_type='vomiting', details={}, idempotency_key='chat-turn-1-call-1')
    first = backend.execute('log_health_event', initial, identity, NOW)
    assert 'blood' in {q['field'] for q in first['follow_up']}
    assert first['event']['details'].get('blood') is None
    supplement = {**initial, 'event_id': first['event_id'], 'idempotency_key': 'chat-turn-2-call-1', 'details': {'blood': True}}
    answer = backend.execute('log_health_event', supplement, identity, NOW)
    assert answer['event_id'] == first['event_id']
    assert answer['red_flags']
    assert 'blood' not in {q['field'] for q in answer['follow_up']}
    retry = backend.execute('log_health_event', supplement, identity, NOW)
    assert retry['event'] == answer['event']
    today = backend.execute('get_today', {'cat_id': cat['cat_id']}, identity, NOW)
    assert len(today['events']) == 1


def test_duplicate_names_require_agent_clarification(domain):
    backend, identity = domain
    for key in ('chat-cat-one', 'chat-cat-two'):
        backend.execute('add_cat', {'name': 'Miso', 'idempotency_key': key}, identity, NOW)
    cats = backend.execute('list_cats', {}, identity, NOW)['cats']
    assert len(cats) == 2
    assert cats[0]['cat_id'] != cats[1]['cat_id']
    assert backend.execute('list_cats', {}, Identity('other-home', 'America/Chicago'), NOW)['cats'] == []
    with pytest.raises(DomainError) as error:
        backend.execute('get_today', {'cat_id': cats[0]['cat_id']}, Identity('other-home', 'America/Chicago'), NOW)
    assert error.value.code == 'not_found'


def test_agent_retry_key_conflict_is_explicit(domain):
    backend, identity = domain
    cat = backend.execute('add_cat', {'name': 'Miso', 'idempotency_key': 'chat-create'}, identity, NOW)['cat']
    args = dict(cat_id=cat['cat_id'], event_type='appetite', details={'eating': 'nothing'}, idempotency_key='chat-one-call')
    first = backend.execute('log_health_event', args, identity, NOW)
    assert 'duration_hours' in {q['field'] for q in first['follow_up']}
    with pytest.raises(DomainError) as error:
        backend.execute('log_health_event', {**args, 'details': {'eating': 'normal'}}, identity, NOW)
    assert error.value.code == 'idempotency_conflict'
