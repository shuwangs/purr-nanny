from datetime import datetime, timedelta, timezone
import pytest
from cat_health_signals import red_flags, vet_summary
from server.notifications import Notifications

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)


def vomit(event_id, age, **details):
    return dict(event_id=event_id, event_type='vomiting', occurred_at=(NOW-age).isoformat(), details=details, source='user')


def rule_ids(events, now=NOW):
    return {flag['rule_id'] for flag in red_flags(events, now)}


@pytest.mark.parametrize('details', [{'blood': True}, {'lethargy': True}])
def test_concerning_signs_need_today_contact(details):
    flags = red_flags([vomit('one', timedelta(), **details)], NOW)
    assert len(flags) == 1
    assert flags[0]['rule_id'] == 'vomiting_concerning_signs'
    assert flags[0]['level'] == 'urgent'


def test_24h_threshold_and_boundaries():
    two = [vomit('one', timedelta()), vomit('two', timedelta(hours=1))]
    assert not rule_ids(two)
    three = two + [vomit('three', timedelta(hours=24))]
    assert rule_ids(three) == {'frequent_vomiting_24h'}
    assert not rule_ids(three, NOW + timedelta(microseconds=1))
    assert not rule_ids(two + [two[0]])  # Same event cannot count twice.
    assert not rule_ids(two + [vomit('older', timedelta(days=2))])
    assert not rule_ids(two + [vomit('future', -timedelta(seconds=1))])


def test_30_day_threshold_and_nonoverlapping_windows():
    previous = [vomit('old-1', timedelta(days=30)), vomit('old-2', timedelta(days=40))]
    current = [vomit(f'new-{i}', timedelta(days=2+i)) for i in range(4)]
    assert not rule_ids(previous + current[:3])
    flag = red_flags(previous + current, NOW)[0]
    assert flag['rule_id'] == 'vomiting_frequency_doubled'
    assert flag['level'] == 'warning'
    assert len(flag['evidence']) == 6
    assert not rule_ids(current)  # No positive comparison baseline.
    assert not rule_ids(previous[:1] + current[:2])  # Fewer than three.
    assert rule_ids(previous[:1] + current[:3]) == {'vomiting_frequency_doubled'}
    # Summary uses prior-window evidence even when timeline covers only 30 days.
    summary = vet_summary({'name': 'Mochi'}, previous + current, NOW, 30)
    assert summary['red_flags'][0]['rule_id'] == 'vomiting_frequency_doubled'
    previous[1]['source'] = 'seed'
    assert vet_summary({'name': 'Mochi'}, previous + current, NOW, 7)['includes_sample_data']


def test_next_visit_warning_does_not_send_sms(tmp_path):
    class SNS:
        def publish(self, **kwargs):
            pytest.fail('Next-visit warning must not send SMS')
    notices = Notifications(tmp_path / 'notifications.db', SNS(), {'home': 'stub-topic'})
    assert notices.send('home', 'event', [{'rule_id': 'vomiting_frequency_doubled', 'level': 'warning', 'evidence': ['event']}])['state'] == 'disabled'
