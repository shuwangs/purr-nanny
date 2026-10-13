from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from server.contracts import MODELS
from server.identity import Identity
from storage.backend import RulesBackend
from storage.repository import SQLiteRepository

NOW = datetime(2026, 10, 12, 23, tzinfo=timezone.utc)
PLAN = [dict(meal_id='breakfast', label='Breakfast', time='08:00'), dict(meal_id='dinner', label='Dinner', time='18:00')]


def setup(tmp_path, **profile):
    backend = RulesBackend(SQLiteRepository(tmp_path / 'feeding.db'))
    principal = Identity('home', 'America/Chicago')
    def call(tool, args, now=NOW):
        parsed = MODELS[tool].model_validate(args).model_dump(mode='json', exclude_none=True)
        return backend.execute(tool, parsed, principal, now)
    cat = call('add_cat', dict(name='Mochi', idempotency_key='create-cat', **profile))['cat']['cat_id']
    return call, cat


def feed(cat, key, meal_id=None, **values):
    details = dict(food='wet food', amount='40 g')
    if meal_id is not None:
        details['meal_id'] = meal_id
    return dict(cat_id=cat, idempotency_key=key, event_type='feeding', details=details, **values)


def test_normal_multiple_meals_and_retry_are_distinct(tmp_path):
    call, cat = setup(tmp_path, meals_per_day=2, meal_schedule=PLAN)
    breakfast = feed(cat, 'breakfast-key', 'breakfast', reporter='Alex', occurred_at='2026-10-12T13:00:00Z')
    first = call('log_care_event', breakfast)
    assert not first['care_notes']
    assert call('log_care_event', breakfast)['event_id'] == first['event_id']
    dinner = call('log_care_event', feed(cat, 'dinner-key', 'dinner', reporter='Shu'))
    assert not dinner['care_notes']
    today = call('get_today', {'cat_id': cat})
    assert len(today['events']) == today['feeding_summary']['count'] == 2
    assert [(r['meal_label'], r['reporter'], r['amount']) for r in today['feeding_summary']['records']] == [('Breakfast', 'Alex', '40 g'), ('Dinner', 'Shu', '40 g')]
    assert not today['care_notes']


def test_same_meal_warns_without_blocking_and_followup_is_not_new_feeding(tmp_path):
    call, cat = setup(tmp_path, meals_per_day=2, meal_schedule=PLAN)
    first = call('log_care_event', feed(cat, 'first-meal', 'breakfast'))
    second = call('log_care_event', feed(cat, 'second-meal', 'breakfast', reporter='Alex'))
    assert second['logged']
    assert len(second['care_notes']) == 1
    assert second['care_notes'][0]['meal_label'] == 'Breakfast'
    assert 'confirm' in second['care_notes'][0]['message']
    corrected = call('log_care_event', feed(cat, 'correct-meal', 'dinner', event_id=second['event_id']))
    assert corrected['event_id'] == second['event_id']
    assert not corrected['care_notes']
    assert len(call('get_today', {'cat_id': cat})['events']) == 2
    assert first['event_id'] != second['event_id']


@pytest.mark.parametrize('profile', [{}, {'meals_per_day': 2}])
def test_no_schedule_only_reports_facts(tmp_path, profile):
    call, cat = setup(tmp_path, **profile)
    for i in range(3):
        result = call('log_care_event', feed(cat, f'feeding-{i}', 'breakfast'))
        assert not result['care_notes']
    today = call('get_today', {'cat_id': cat})
    assert today['feeding_summary']['count'] == 3
    assert today['feeding_summary']['plan_status'] == 'not_configured'
    assert not today['care_notes']


def test_plan_update_unknown_meal_and_local_day(tmp_path):
    call, cat = setup(tmp_path)
    updated = call('update_cat', dict(cat_id=cat, meals_per_day=2, meal_schedule=PLAN))
    assert updated['cat']['name'] == 'Mochi'
    assert updated['cat']['meal_schedule'] == PLAN
    missing = call('log_care_event', feed(cat, 'missing-meal'))
    assert missing['logged'] and missing['follow_up'][0]['field'] == 'meal_id'
    assert not missing['care_notes']
    # 04:59Z is previous household date; 05:00Z is today's midnight.
    call('log_care_event', feed(cat, 'yesterday-meal', 'breakfast', occurred_at='2026-10-12T04:59:00Z'))
    today_meal = call('log_care_event', feed(cat, 'today-meal', 'breakfast', occurred_at='2026-10-12T05:00:00Z'))
    assert not today_meal['care_notes']
    assert call('get_today', {'cat_id': cat})['feeding_summary']['count'] == 2
    renamed = call('update_cat', dict(cat_id=cat, name='Miso'))
    assert renamed['cat']['meal_schedule'] == PLAN
    call('update_cat', dict(cat_id=cat, meal_schedule=[]))
    assert call('get_today', {'cat_id': cat})['feeding_summary']['plan_status'] == 'not_configured'


@pytest.mark.parametrize('profile', [dict(meals_per_day=True), dict(meals_per_day=2, meal_schedule=PLAN[:1]), dict(meal_schedule=[PLAN[0], PLAN[0]]), dict(meal_schedule=[{**PLAN[0], 'time':'25:00'}])])
def test_invalid_plan_is_rejected(profile):
    with pytest.raises(ValidationError):
        MODELS['add_cat'].model_validate(dict(name='Mochi', idempotency_key='create-cat', **profile))


def test_dynamodb_profile_patch_preserves_plan():
    import json
    from storage.dynamodb import DynamoDBRepository
    existing = dict(cat_id='cat', name='Mochi', meals_per_day=2, meal_schedule=PLAN)
    class Client:
        def transact_write_items(self, **kwargs):
            self.actions = kwargs['TransactItems']
    client = Client()
    class Table:
        name = 'table'
        class meta:
            pass
        def get_item(self, **kwargs):
            return {'Item': {'body': json.dumps(existing), 'version': 3}}
    table = Table()
    table.meta.client = client
    result = DynamoDBRepository(table).mutate('home', 'update_cat', {'cat_id':'cat', 'name':'Miso'}, NOW)
    assert result['meal_schedule'] == PLAN
    assert result['name'] == 'Miso'
    assert client.actions[0]['Put']['ConditionExpression'] == '#v = :v'
    assert json.loads(client.actions[1]['Put']['Item']['body']) == result
