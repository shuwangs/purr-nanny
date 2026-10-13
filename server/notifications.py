"""Durable alert ledger. Retry only confirmed rejection; reconcile uncertain sends."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager


class Notifications:
    def __init__(self, path, sns=None, topics=None):
        self.path, self.sns, self.topics = str(path), sns, topics or {}
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS notifications(
                household TEXT, event TEXT, rule TEXT, state TEXT, message_id TEXT,
                PRIMARY KEY(household,event,rule))''')
            if "retryable" not in {row[1] for row in db.execute("PRAGMA table_info(notifications)")}:
                db.execute("ALTER TABLE notifications ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def alert_key(event_id, flag):
        evidence = sorted(set(flag.get('evidence') or [event_id]))
        return evidence[0] if len(evidence) == 1 else 'alert:' + hashlib.sha256(json.dumps(evidence).encode()).hexdigest()

    def reconcile(self, household, alert_id, rule, *, outcome, message_id=None):
        """Operator-only: resolve an interrupted/ambiguous send after checking provider evidence.

        Use rejected only when the provider definitely did not accept the message.
        This operation is intentionally not exposed as an MCP tool.
        """
        if outcome not in ('sent', 'rejected', 'uncertain') or (outcome == 'sent' and not message_id):
            raise ValueError('A valid provider outcome and message ID for sent are required')
        state = 'failed' if outcome == 'rejected' else outcome
        with self.connect() as db:
            changed = db.execute("UPDATE notifications SET state=?,message_id=?,retryable=? WHERE household=? AND event=? AND rule=? AND state IN ('queued','uncertain','failed')",
                (state, message_id, int(outcome == "rejected"), household, alert_id, rule)).rowcount
        return bool(changed)

    def send(self, household, event_id, flags):
        if not flags or not event_id or not self.sns or household not in self.topics:
            return {'state': 'disabled'}
        results = []
        for flag in flags:
            if flag.get('level') == 'warning':
                continue  # Next-visit advice is displayed, not sent as an urgent SMS.
            # Historical warnings remain visible, but an unrelated record must not send them.
            if flag.get('evidence') and event_id not in flag['evidence']:
                continue
            rule = flag['rule_id']
            alert_id = self.alert_key(event_id, flag)
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                inserted = db.execute("INSERT OR IGNORE INTO notifications(household,event,rule,state,message_id) VALUES(?,?,?,'queued',NULL)", (household, alert_id, rule)).rowcount
                claimed = inserted or db.execute("UPDATE notifications SET state='queued' WHERE household=? AND event=? AND rule=? AND state='failed' AND retryable=1", (household, alert_id, rule)).rowcount
                row = db.execute('SELECT state,message_id FROM notifications WHERE household=? AND event=? AND rule=?', (household, alert_id, rule)).fetchone()
            if claimed:
                try:
                    response = self.sns.publish(TopicArn=self.topics[household], Message='Purr Nanny recorded a health warning. Review the record and its veterinary guidance.')
                    message_id = response.get('MessageId')
                    state = 'sent' if message_id else 'uncertain'
                except Exception as error:
                    # A transport exception does not prove rejection: the provider may have accepted.
                    status = getattr(error, 'response', {}).get('ResponseMetadata', {}).get('HTTPStatusCode')
                    state = 'failed' if isinstance(status, int) and 400 <= status < 500 and status != 408 and getattr(error, 'response', {}).get('Error', {}).get('Code') not in ('RequestTimeout', 'RequestTimeoutException') else 'uncertain'
                    message_id = None
                with self.connect() as db:
                    db.execute('UPDATE notifications SET state=?,message_id=?,retryable=? WHERE household=? AND event=? AND rule=?', (state, message_id, int(state == "failed"), household, alert_id, rule))
                row = state, message_id
            results.append({'rule_id': rule, 'alert_id': alert_id, 'state': row[0], 'message_id': row[1]})
        state = next((s for s in ('uncertain', 'failed', 'queued', 'sent') if any(r['state'] == s for r in results)), 'disabled')
        return {'state': state, 'rules': results}
