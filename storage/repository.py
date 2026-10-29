"""Transactional local repository, with household-scoped keys and immutable retry results."""
from storage.attribution import apply_attribution
import json
from contextlib import contextmanager
import sqlite3
import uuid
from datetime import timezone
from cat_health_signals import timestamp


class StorageError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class SQLiteRepository:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS b_cats(household TEXT, id TEXT, body TEXT, PRIMARY KEY(household,id));
CREATE TABLE IF NOT EXISTS b_events(household TEXT, cat TEXT, id TEXT, body TEXT, PRIMARY KEY(household,cat,id));
CREATE TABLE IF NOT EXISTS b_retries(household TEXT, key TEXT, request TEXT, result TEXT, PRIMARY KEY(household,key));''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list_cats(self, household):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM b_cats WHERE household=? ORDER BY id', (household,)).fetchall()
        return sorted([json.loads(row[0]) for row in rows], key=lambda cat: (cat['name'].casefold(), cat['cat_id']))

    def get_cat(self, household, cat_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM b_cats WHERE household=? AND id=?', (household, cat_id)).fetchone()
        if not row:
            raise StorageError('not_found', 'Cat not found in this household')
        return json.loads(row[0])

    def list_events(self, household, cat_id):
        self.get_cat(household, cat_id)
        with self.connect() as db:
            rows = db.execute('SELECT body FROM b_events WHERE household=? AND cat=?', (household, cat_id)).fetchall()
        return sorted([json.loads(r[0]) for r in rows], key=lambda e: (timestamp(e['occurred_at']), e['event_id']))

    def mutate(self, household, tool, args, now):
        from .validation import validate_details
        from server.mcp.contracts import profile_changes
        if tool.startswith('log_'):
            validate_details(args['event_type'], args.get('details', {}))
        now = timestamp(now).astimezone(timezone.utc)
        request = json.dumps([tool, args], sort_keys=True)
        key = args.get('idempotency_key')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT request,result FROM b_retries WHERE household=? AND key=?', (household, key)).fetchone()
                if old:
                    if old[0] != request:
                        raise StorageError('idempotency_conflict', 'Retry key already used for different input')
                    return json.loads(old[1])
            if tool == 'add_cat':
                body = dict(cat_id=str(uuid.uuid4()), **profile_changes(args))
                db.execute('INSERT INTO b_cats VALUES(?,?,?)', (household, body['cat_id'], json.dumps(body)))
            else:
                existing_cat = self.get_cat(household, args['cat_id'])
                if tool == 'update_cat':
                    body = dict(cat_id=args['cat_id'], **profile_changes(args, existing_cat))
                    db.execute('UPDATE b_cats SET body=? WHERE household=? AND id=?', (json.dumps(body), household, args['cat_id']))
                else:
                    event_id = args.get('event_id') or str(uuid.uuid4())
                    row = db.execute('SELECT body FROM b_events WHERE household=? AND cat=? AND id=?', (household, args['cat_id'], event_id)).fetchone()
                    if args.get('event_id') and not row:
                        raise StorageError('not_found', 'Event not found for this cat and household')
                    body = json.loads(row[0]) if row else dict(event_id=event_id, cat_id=args['cat_id'], kind=tool, event_type=args['event_type'], source=args.get('source', 'user'), recorded_at=now.isoformat(), occurred_at=now.isoformat(), time_defaulted=True, details={}, reporter=None)
                    if body['event_type'] != args['event_type'] or body['kind'] != tool or body['source'] != args.get('source', 'user'):
                        raise StorageError('event_conflict', 'Follow-up must preserve type, kind and source')
                    if args.get('occurred_at'):
                        occurred = timestamp(args['occurred_at']).astimezone(timezone.utc)
                        if occurred > now:
                            raise StorageError('invalid_time', 'Occurrence cannot be in the future')
                        body.update(occurred_at=occurred.isoformat(), time_defaulted=False)
                    body['details'].update(args.get('details', {}))
                    if args.get('reporter') is not None:
                        body['reporter'] = args['reporter']
                    apply_attribution(body,args,now)
                    body['updated_at'] = now.isoformat()
                    db.execute('INSERT OR REPLACE INTO b_events VALUES(?,?,?,?)', (household, args['cat_id'], event_id, json.dumps(body)))
            if key:
                db.execute('INSERT INTO b_retries VALUES(?,?,?,?)', (household, key, request, json.dumps(body)))
            return body
