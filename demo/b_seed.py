"""Run from repository root with the rules package installed."""
from datetime import datetime, timezone
from storage.backend import RulesBackend
from storage import SQLiteRepository
from server.identity import Identity


def seed(repository, now=datetime(2026, 10, 12, 18, tzinfo=timezone.utc)):
    backend = RulesBackend(repository)
    principal = Identity('demo-household', 'America/Chicago')
    cat = backend.execute('add_cat', {'name': 'Miso', 'idempotency_key': 'demo-miso-v1'}, principal, now)['cat']['cat_id']
    for key, event_type, details in [('feeding', 'feeding', {'food': 'wet food'}), ('vomiting', 'vomiting', {'blood': False, 'lethargy': False, 'after_meal': True})]:
        backend.execute('log_care_event' if key == 'feeding' else 'log_health_event', dict(cat_id=cat, idempotency_key='demo-'+key+'-v1', event_type=event_type, source='seed', details=details), principal, now)
    return {name: backend.execute(name, {'cat_id': cat, 'days': 7}, principal, now) for name in ('get_today', 'get_patterns', 'get_vet_summary')}


if __name__ == '__main__':
    import json, tempfile
    with tempfile.TemporaryDirectory() as folder:
        print(json.dumps(seed(SQLiteRepository(folder+'/demo.db')), indent=2))
