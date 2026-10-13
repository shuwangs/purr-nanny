"""Cross-module local story acceptance. Does not claim Alexa or cloud verification."""
from datetime import datetime, timezone
import pytest
from storage import SQLiteRepository
from storage.backend import RulesBackend
from server.backend import DomainError
from server.contracts import MODELS
from server.identity import Identity
from server.notifications import Notifications

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)


def test_five_stories_with_real_backend(tmp_path):
    backend = RulesBackend(SQLiteRepository(tmp_path / 'stories.db'))
    family = Identity('demo-family', 'America/Chicago')
    other = Identity('other-family', 'America/Chicago')
    def call(tool, args, principal=family):
        args = MODELS[tool].model_validate(args).model_dump(mode='json', exclude_none=True)
        return backend.execute(tool, args, principal, NOW)
    cat = call('add_cat', {'name':'Miso', 'idempotency_key':'create-miso'})['cat']['cat_id']
    args = dict(cat_id=cat, idempotency_key='observation-1', event_type='vomiting', source='seed', details={})
    first = call('log_health_event', args)
    assert first['follow_up']
    update = {**args, 'event_id':first['event_id'], 'idempotency_key':'clarify-event', 'details':{'blood':False, 'lethargy':False, 'after_meal':True}}
    corrected = call('log_health_event', update)
    assert corrected['event_id'] == first['event_id']
    assert call('log_health_event', update)['event_id'] == first['event_id']
    today = call('get_today', {'cat_id':cat})
    assert len(today['events']) == 1
    stats = call('get_patterns', {'cat_id':cat, 'days':7})['patterns']
    meals = next(p for p in stats if p['pattern_id']=='vomiting_after_meal')
    assert meals['status']=='insufficient_data' and meals['sample_size']==1
    assert meals['denominator']==1 and first['event_id'] in meals['evidence']
    urgent = call('log_health_event', dict(cat_id=cat,idempotency_key='urgent-sample',event_type='litter',source='seed',details={'straining':True,'urine_output':'none'}))
    assert urgent['red_flags'][0]['level']=='emergency'
    # Stub acceptance and failure; no actual SMS is sent.
    class SNS:
        calls = 0
        def publish(self, **kwargs):
            self.calls += 1
            return {'MessageId':'stub-accepted'}
    sns = SNS()
    notifications = Notifications(tmp_path / 'notifications.db', sns=sns, topics={'demo-family':'stub-topic'})
    assert notifications.send(family.household_id, urgent['event_id'], urgent['red_flags'])['state']=='sent'
    notifications.send(family.household_id, urgent['event_id'], urgent['red_flags'])
    assert sns.calls==1
    class FailedSNS:
        def publish(self, **kwargs): raise RuntimeError('Simulated provider failure')
    failed = Notifications(tmp_path / 'failure.db', sns=FailedSNS(),topics={'demo-family':'stub-topic'})
    assert failed.send(family.household_id,urgent['event_id'],urgent['red_flags'])['state']=='uncertain'
    care = call('log_care_event',dict(cat_id=cat,idempotency_key='family-feeding',event_type='feeding',source='seed',reporter='Alex',details={'food':'wet food'}))
    assert any(e['event_id']==care['event_id'] and e['reporter']=='Alex' for e in call('get_today',{'cat_id':cat},Identity('demo-family','America/Chicago'))['events'])
    with pytest.raises(DomainError): call('get_today', {'cat_id':cat}, other)
    today = call('get_today', {'cat_id':cat})
    summary = call('get_vet_summary', {'cat_id':cat,'days':7})
    assert [e['event_id'] for e in summary['timeline']]==[e['event_id'] for e in today['events']]
    assert summary['patterns']==call('get_patterns', {'cat_id':cat,'days':7})['patterns']
    assert summary['display_timezone'] == 'America/Chicago'
    assert summary['window']['timezone'] == 'America/Chicago'
    assert today['display_timezone'] == 'America/Chicago'
    assert summary['includes_sample_data'] and 'not a diagnosis' in summary['disclaimer']
