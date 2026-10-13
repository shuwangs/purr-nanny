"""Durable household-scoped turn journal; never stores bearer tokens."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from server.backend import DomainError


class Conversations:
    def __init__(self, path, lease_seconds=300):
        self.path, self.lease_seconds = str(path), lease_seconds
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS chat_sessions(household TEXT,id TEXT,history TEXT,pending TEXT,selected_cat TEXT,running TEXT,owner TEXT,lease REAL,PRIMARY KEY(household,id));
            CREATE TABLE IF NOT EXISTS chat_request_sessions(household TEXT,message TEXT,session TEXT,PRIMARY KEY(household,message));
            CREATE TABLE IF NOT EXISTS chat_turns(household TEXT,session TEXT,message TEXT,input TEXT,state TEXT,response TEXT,PRIMARY KEY(household,session,message));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, household):
        session = str(uuid.uuid4())
        with self.db() as db:
            db.execute('INSERT INTO chat_sessions VALUES(?,?,?, ?,NULL,NULL,NULL,0)', (household, session, '[]', 'null'))
        return session

    def session_for_message(self, household, message):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT session FROM chat_request_sessions WHERE household=? AND message=?', (household,message)).fetchone()
            if row:
                return row[0]
            session = str(uuid.uuid4())
            db.execute('INSERT INTO chat_sessions VALUES(?,?,?, ?,NULL,NULL,NULL,0)', (household,session,'[]','null'))
            db.execute('INSERT INTO chat_request_sessions VALUES(?,?,?)', (household,message,session))
            return session

    def get(self, household, session):
        with self.db() as db:
            row = db.execute('SELECT history,pending,selected_cat,running FROM chat_sessions WHERE household=? AND id=?', (household,session)).fetchone()
            if row is None:
                raise DomainError('not_found', 'Conversation not found')
            turns = db.execute('SELECT message,input,response FROM chat_turns WHERE household=? AND session=? ORDER BY rowid', (household,session)).fetchall()
        messages, results = [], []
        for message, request, response in turns:
            messages.append(dict(message_id=message,role='user',text=json.loads(request)['text']))
            if response:
                result = json.loads(response)
                messages.append(dict(message_id=message,role='assistant',text=result['reply'],status=result['status']))
                results = result['tool_results']
        pending = json.loads(row[1])
        queue = pending if isinstance(pending,list) else ([pending] if pending else [])
        return dict(schema_version='1.0',conversation_id=session,messages=messages,pending_follow_up=queue[0] if queue else None,pending_follow_ups=queue,selected_cat=row[2],tool_results=results,running_message_id=row[3])

    def begin(self, household, session, message, text, selected_cat=None, recorded_by=None):
        request_values = dict(text=text,cat_id=selected_cat)
        if recorded_by is not None:
            request_values['recorded_by'] = recorded_by
        request = json.dumps(request_values,sort_keys=True)
        owner = str(uuid.uuid4())
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT history,pending,selected_cat,running,lease FROM chat_sessions WHERE household=? AND id=?', (household,session)).fetchone()
            if row is None:
                raise DomainError('not_found','Conversation not found')
            turn = db.execute('SELECT input,state,response FROM chat_turns WHERE household=? AND session=? AND message=?', (household,session,message)).fetchone()
            if turn and turn[0] != request:
                raise DomainError('message_conflict','This message ID was already used for different input')
            if turn and turn[2]:
                return None, None, json.loads(turn[2])
            if row[3] and (row[3] != message or row[4] > time.time()):
                raise DomainError('conversation_busy','Retry the running message with the same message ID after it finishes or its lease expires')
            if turn:
                state = json.loads(turn[1])
            else:
                pending = json.loads(row[1])
                queue = pending if isinstance(pending,list) else ([pending] if pending else [])
                state = dict(transcript=json.loads(row[0])+[dict(role='user',content=[dict(text=text)])],
                             pending=queue[0] if queue else None,pending_queue=queue[1:],selected_cat=selected_cat or row[2],tool_results=[],round=0,steps=0,plan=None)
                db.execute('INSERT INTO chat_turns VALUES(?,?,?,?,?,NULL)', (household,session,message,request,json.dumps(state)))
            db.execute('UPDATE chat_sessions SET running=?,owner=?,lease=? WHERE household=? AND id=?', (message,owner,time.time()+self.lease_seconds,household,session))
        return owner,state,None

    def save(self, household, session, message, owner, state, response=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            claim = db.execute('SELECT owner FROM chat_sessions WHERE household=? AND id=?', (household,session)).fetchone()
            if not claim or claim[0] != owner:
                raise DomainError('conversation_busy','Conversation lease was replaced')
            db.execute('UPDATE chat_turns SET state=?,response=? WHERE household=? AND session=? AND message=?', (json.dumps(state),json.dumps(response) if response else None,household,session,message))
            if response:
                db.execute('UPDATE chat_sessions SET history=?,pending=?,selected_cat=?,running=NULL,owner=NULL,lease=0 WHERE household=? AND id=?', (json.dumps(state['transcript']),json.dumps(([state['pending']] if state['pending'] else [])+state.get('pending_queue',[])),state['selected_cat'],household,session))
            else:
                db.execute('UPDATE chat_sessions SET lease=? WHERE household=? AND id=?', (time.time()+self.lease_seconds,household,session))

    def release(self, household, session, owner):
        # Keep the journal; retrying the same message resumes the saved plan.
        with self.db() as db:
            db.execute('UPDATE chat_sessions SET lease=0 WHERE household=? AND id=? AND owner=?', (household,session,owner))
