from datetime import datetime, timedelta, timezone
import pytest
from cat_health_signals import red_flags, patterns
from server.identity import Identity
from storage.backend import RulesBackend
from storage.repository import SQLiteRepository
from server.notifications import Notifications

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)


def weight(key, value, age):
    return dict(event_id=key, event_type='weight', occurred_at=(NOW-age).isoformat(), details={'weight_kg':value}, source='user')


@pytest.mark.parametrize('latest,expected', [(3.9, True), (3.99, True), (4.0, False), (4.2, False), (4.5, False)])
def test_design_threshold(latest, expected):
    events = [weight('baseline',4.2,timedelta(days=30)), weight('latest',latest,timedelta())]
    flags = red_flags(events, NOW)
    assert bool(flags) == expected
    if expected:
        assert flags[0]['rule_id'] == 'weight_loss_30d'
        assert flags[0]['level'] == 'warning'
        assert flags[0]['evidence'] == ['baseline','latest']


def test_exact_five_percent_and_window_boundaries():
    events = [weight('baseline', 4, timedelta(days=30)), weight('latest',3.8,timedelta())]
    assert red_flags(events, NOW)
    assert not red_flags(events, NOW+timedelta(microseconds=1))
    assert not red_flags(events[:1], NOW)
    assert not red_flags([weight('a',4,timedelta()), weight('b',3.8,timedelta())], NOW)
    assert not red_flags([events[0], weight('future',3.8,-timedelta(seconds=1))], NOW)
    assert not red_flags([weight('zero',0,timedelta(days=1)),events[1]], NOW)
    assert not red_flags([weight('infinite',float('inf'),timedelta(days=1)),events[1]], NOW)
    assert not red_flags([events[0],weight('near',3.800001,timedelta())], NOW)


def test_real_backend_summary_and_no_sms(tmp_path):
    backend = RulesBackend(SQLiteRepository(tmp_path/'weights.db'))
    principal = Identity('home','America/Chicago')
    cat = backend.execute('add_cat',dict(name='Mochi',idempotency_key='create-cat'),principal,NOW)['cat']['cat_id']
    for event in [weight('baseline',4.2,timedelta(days=20)),weight('latest',3.9,timedelta())]:
        backend.execute('log_health_event',dict(cat_id=cat,event_type='weight',idempotency_key=event['event_id']+'-key',details=event['details'],occurred_at=event['occurred_at']),principal,NOW)
    summary = backend.execute('get_vet_summary',dict(cat_id=cat,days=30),principal,NOW)
    metric = next(p for p in summary['patterns'] if p['pattern_id']=='weight_trend')
    assert metric['change_kg'] == -0.3
    assert metric['change_percent'] == pytest.approx(-7.142857)
    assert summary['red_flags'][0]['rule_id'] == 'weight_loss_30d'
    assert backend.execute('get_today',dict(cat_id=cat),principal,NOW)['red_flags']
    class SNS:
        def publish(self, **kwargs):
            pytest.fail('Weight next-visit reminder must not send SMS')
    assert Notifications(tmp_path/'notice.db',SNS(),{'home':'stub'}).send('home',summary['red_flags'][0]['evidence'][-1],summary['red_flags'])['state']=='disabled'
