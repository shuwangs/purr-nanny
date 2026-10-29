import unittest
import tempfile
from datetime import datetime, timezone, timedelta
from storage import SQLiteRepository, StorageError
from cat_health_signals import red_flags, patterns, follow_up

NOW = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = SQLiteRepository(self.tmp.name+'/events.db')
        self.cat = self.repo.mutate('home', 'add_cat', dict(name='Miso', idempotency_key='create-cat'), NOW)['cat_id']

    def tearDown(self):
        self.tmp.cleanup()

    def log(self, key='event-key', **values):
        args = dict(cat_id=self.cat, event_type='vomiting', details={}, source='seed', idempotency_key=key)
        args.update(values)
        return self.repo.mutate('home', 'log_health_event', args, NOW)

    def test_retry_and_followup(self):
        first = self.log()
        self.assertEqual(first, self.log())
        updated = self.log('follow-up', event_id=first['event_id'], details={'blood': True})
        self.assertEqual(first['recorded_at'], updated['recorded_at'])
        self.assertEqual(len(self.repo.list_events('home', self.cat)), 1)
        self.assertEqual(red_flags([updated], NOW)[0]['rule_id'], 'vomiting_concerning_signs')
        self.assertNotIn('blood', [q['field'] for q in follow_up(updated)])
        with self.assertRaises(StorageError):
            self.log(details={'blood': False})

    def test_isolation_restart_and_same_timestamp(self):
        self.log('one-event')
        self.log('two-event')
        restarted = SQLiteRepository(self.repo.path)
        self.assertEqual(len(restarted.list_events('home', self.cat)), 2)
        with self.assertRaises(StorageError):
            restarted.list_events('other', self.cat)

    def test_times(self):
        with self.assertRaises(StorageError):
            self.log(occurred_at=(NOW+timedelta(seconds=1)).isoformat())
        with self.assertRaises(ValueError):
            patterns([], datetime(2026, 10, 12))
        event = self.log(occurred_at=(NOW-timedelta(days=7)).isoformat())
        self.assertEqual(patterns([event], NOW)[0]['sample_size'], 1)
        self.assertEqual(patterns([event], NOW+timedelta(microseconds=1))[0]['sample_size'], 0)

    def test_unknown_is_not_false_and_emergency_priority(self):
        vomit = self.log(details={'blood': True})
        litter = {**vomit, 'event_id': 'litter', 'event_type': 'litter', 'details': {'straining': True, 'urine_output': 'none'}}
        self.assertEqual(red_flags([vomit, litter], NOW)[0]['level'], 'emergency')
        unknown = {**litter, 'details': {'straining': True}}
        self.assertEqual(red_flags([unknown], NOW), [])
        self.assertEqual(follow_up(unknown)[0]['field'], 'urine_output')
        self.assertEqual(patterns([vomit], NOW)[1]['status'], 'insufficient_data')

    def test_weight_and_food_windows(self):
        events = []
        for i, kg in enumerate([5, 4.8]):
            events.append(dict(event_id=str(i), event_type='weight', occurred_at=(NOW-timedelta(days=6-i)).isoformat(), details={'weight_kg': kg}))
        self.assertAlmostEqual(patterns(events, NOW)[2]['change_kg'], -.2)
        change = dict(event_id='food', event_type='food_change', occurred_at=(NOW-timedelta(days=4)).isoformat(), details={})
        self.assertEqual(patterns(events+[change], NOW, 8)[3]['denominator'], 4)


if __name__ == '__main__':
    unittest.main()

class BackendTests(unittest.TestCase):
    def test_dst_today_and_malformed_details(self):
        from storage.backend import RulesBackend
        from server.identity import Identity
        from server.backend import DomainError
        with tempfile.TemporaryDirectory() as folder:
            backend = RulesBackend(SQLiteRepository(folder+'/data.db'))
            principal = Identity('home', 'America/Chicago')
            now = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
            cat_id = backend.execute('add_cat', dict(name='Miso', idempotency_key='create-cat'), principal, now)['cat']['cat_id']
            args = dict(cat_id=cat_id, event_type='vomiting', idempotency_key='bad-detail', details={'blood': 'false'})
            with self.assertRaises(DomainError) as error:
                backend.execute('log_health_event', args, principal, now)
            self.assertEqual(error.exception.code, 'invalid_details')
            args.update(idempotency_key='good-detail', details={'blood': None})
            backend.execute('log_health_event', args, principal, now)
            today = backend.execute('get_today', {'cat_id': cat_id}, principal, now)
            window = today['window']
            self.assertEqual((datetime.fromisoformat(window['end'])-datetime.fromisoformat(window['start'])).total_seconds(), 25*3600)
            self.assertEqual(len(today['events']), 1)
            self.assertFalse(today['includes_sample_data'])

    def test_seed_warning_outside_today_is_labeled(self):
        from storage.backend import RulesBackend
        from server.identity import Identity
        with tempfile.TemporaryDirectory() as folder:
            backend = RulesBackend(SQLiteRepository(folder+'/data.db'))
            principal = Identity('home', 'America/Chicago')
            cat_id = backend.execute('add_cat', dict(name='Miso', idempotency_key='create-cat'), principal, NOW)['cat']['cat_id']
            backend.execute('log_health_event', dict(cat_id=cat_id, event_type='vomiting', idempotency_key='seed-danger', source='seed', occurred_at=(NOW-timedelta(days=2)).isoformat(), details={'blood': True}), principal, NOW)
            result = backend.execute('get_today', {'cat_id': cat_id}, principal, NOW)
            self.assertEqual(result['events'], [])
            self.assertTrue(result['red_flags'])
            self.assertTrue(result['includes_sample_data'])
            self.assertTrue(backend.execute('get_patterns', {'cat_id': cat_id, 'days': 1}, principal, NOW)['includes_sample_data'])
