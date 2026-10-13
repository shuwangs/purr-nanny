"""Persistent local integration fixture, not B's production storage or health rules."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo
from server.contracts import envelope
from server.identity import Identity


class Backend(Protocol):
    def execute(self, tool: str, args: dict, principal: Identity, now: datetime) -> dict: ...


class DomainError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class ReferenceBackend:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS cats(household TEXT, id TEXT, name TEXT, PRIMARY KEY(household,id));
            CREATE TABLE IF NOT EXISTS events(household TEXT, cat TEXT, id TEXT, body TEXT, PRIMARY KEY(household,id));
            CREATE TABLE IF NOT EXISTS retries(household TEXT, key TEXT, request TEXT, result TEXT, PRIMARY KEY(household,key));
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def execute(self, tool, args, principal, now):
        if now.utcoffset() is None:
            raise ValueError("Reference time must include timezone")
        now = now.astimezone(timezone.utc)
        household = principal.household_id
        request = json.dumps([tool, args], sort_keys=True)
        key = args.get("idempotency_key")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if key:
                existing = db.execute("SELECT request,result FROM retries WHERE household=? AND key=?", (household, key)).fetchone()
                if existing:
                    if existing[0] != request:
                        raise DomainError("idempotency_conflict", "Use a new key for changed input")
                    return json.loads(existing[1])
            if tool == "list_cats":
                cats = [{"cat_id": row[0], "name": row[1]} for row in db.execute("SELECT id,name FROM cats WHERE household=? ORDER BY name,id", (household,))]
                result = envelope(cats=cats)
            elif tool == "add_cat":
                cat_id = str(uuid.uuid4())
                db.execute("INSERT INTO cats VALUES(?,?,?)", (household, cat_id, args["name"]))
                result = envelope(cat={"cat_id": cat_id, "name": args["name"]}, logged=True)
            else:
                cat = db.execute("SELECT name FROM cats WHERE household=? AND id=?", (household, args["cat_id"])).fetchone()
                if not cat:
                    raise DomainError("not_found", "Cat not found in this household")
                if tool == "update_cat":
                    db.execute("UPDATE cats SET name=? WHERE household=? AND id=?", (args["name"], household, args["cat_id"]))
                    result = envelope(logged=True, cat={"cat_id": args["cat_id"], "name": args["name"]})
                elif tool.startswith("log_"):
                    result = self.log(db, household, tool, args, now)
                else:
                    result = self.query(db, household, tool, args, principal, now)
            if key:
                db.execute("INSERT INTO retries VALUES(?,?,?,?)", (household, key, request, json.dumps(result)))
            return result

    def log(self, db, household, tool, args, now):
        event_id = args.get("event_id") or str(uuid.uuid4())
        old = db.execute("SELECT cat,body FROM events WHERE household=? AND id=?", (household, event_id)).fetchone()
        if args.get("event_id") and not old:
            raise DomainError("not_found", "Event not found in this household")
        if old and (old[0] != args["cat_id"] or json.loads(old[1])["kind"] != tool or json.loads(old[1])["event_type"] != args["event_type"]):
            raise DomainError("event_conflict", "Follow-up must use the same cat and event type")
        body = json.loads(old[1]) if old else {"event_id": event_id, "kind": tool, "recorded_at": now.isoformat(), "details": {}}
        for field in ("cat_id", "event_type", "reporter"):
            if args.get(field) is not None:
                body[field] = args[field]
        if not old:
            body["source"] = args["source"]
        elif body["source"] != args["source"]:
            raise DomainError("event_conflict", "Follow-up must preserve the event source")
        if args.get("occurred_at"):
            occurred = datetime.fromisoformat(args["occurred_at"]).astimezone(timezone.utc)
            if occurred > now:
                raise DomainError("invalid_time", "Occurrence time cannot be in the future")
            body["occurred_at"], body["time_defaulted"] = occurred.isoformat(), False
        elif not old:
            body["occurred_at"], body["time_defaulted"] = now.isoformat(), True
        body["details"].update(args["details"])
        from storage.attribution import apply_attribution
        apply_attribution(body,args,now)
        body["updated_at"] = now.isoformat()
        db.execute("INSERT OR REPLACE INTO events VALUES(?,?,?,?)", (household, args["cat_id"], event_id, json.dumps(body)))
        return envelope(logged=True, event_id=event_id, event=body,
                        analysis_status="unavailable", limitations=["Reference backend does not evaluate health signals; B's rules adapter is required."])

    def query(self, db, household, tool, args, principal, now):
        zone = ZoneInfo(principal.timezone)
        if tool == "get_today":
            start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end = (start.astimezone(zone) + timedelta(days=1)).astimezone(timezone.utc)
        else:
            start, end = now - timedelta(days=args["days"]), now
        events = [json.loads(row[0]) for row in db.execute("SELECT body FROM events WHERE household=? AND cat=?", (household, args["cat_id"]))]
        events = sorted([e for e in events if start <= datetime.fromisoformat(e["occurred_at"]) < end and datetime.fromisoformat(e["occurred_at"]) <= now], key=lambda e: (e["occurred_at"], e["event_id"]))
        return envelope(events=events, window={"start": start.isoformat(), "end": end.isoformat(), "timezone": principal.timezone},
                        includes_sample_data=any(e["source"] == "seed" for e in events),
                        analysis_status="unavailable", limitations=["Patterns and clinical summary await B's rules adapter."])
