"""Feeding coordination is separate from request deduplication and health signals."""
from zoneinfo import ZoneInfo
from . import timestamp


def feeding_summary(cat, events, now, household_timezone, *, local_date=None):
    now = timestamp(now)
    zone = ZoneInfo(household_timezone)
    date = local_date or now.astimezone(zone).date()
    slots = {slot['meal_id']: slot for slot in cat.get('meal_schedule') or []}
    selected = list({event['event_id']: event for event in events
        if event['event_type'] == 'feeding' and timestamp(event['occurred_at']) <= now
        and timestamp(event['occurred_at']).astimezone(zone).date() == date}.values())
    selected.sort(key=lambda event: (timestamp(event['occurred_at']), event['event_id']))
    records = [dict(event_id=event['event_id'], occurred_at=event['occurred_at'], reporter=event.get('reporter'),performed_by=event.get('performed_by'),recorded_by=event.get('recorded_by'),
                    food=event.get('details', {}).get('food'), amount=event.get('details', {}).get('amount'),
                    meal_label=slots.get(event.get('details', {}).get('meal_id'), {}).get('label')) for event in selected]
    notes = []
    for meal_id, slot in slots.items():
        group = [event for event in selected if event.get('details', {}).get('meal_id') == meal_id]
        if len(group) >= 2:
            notes.append(dict(code='possible_duplicate_meal', meal_id=meal_id, meal_label=slot['label'],
                evidence=[event['event_id'] for event in group],
                message=f"{slot['label']} already has a feeding record. Please confirm whether an additional feeding took place. All observations have been saved."))
    return dict(count=len(records), local_date=date.isoformat(), timezone=household_timezone,
                plan_status='configured' if slots else 'not_configured', records=records, care_notes=notes)
