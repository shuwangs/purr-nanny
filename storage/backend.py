from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from cat_health_signals import follow_up, red_flags, patterns, vet_summary, timestamp
from server.backend import DomainError
from server.mcp.contracts import envelope
from .repository import StorageError
from cat_health_signals.feeding import feeding_summary


class RulesBackend:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, tool, args, principal, now):
        result = self._execute(tool, args, principal, now)
        result['display_timezone'] = principal.timezone
        if 'window' in result:
            result['window']['timezone'] = principal.timezone
        return result

    def _execute(self, tool, args, principal, now):
        now = timestamp(now).astimezone(timezone.utc)
        household = principal.household_id
        try:
            if tool == 'list_cats':
                return envelope(cats=self.repository.list_cats(household))
            if tool in ('add_cat', 'update_cat', 'log_health_event', 'log_care_event'):
                body = self.repository.mutate(household, tool, args, now)
                if tool in ('add_cat', 'update_cat'):
                    return envelope(logged=True, cat=body)
                events = self.repository.list_events(household, args['cat_id'])
                cat = self.repository.get_cat(household, args['cat_id'])
                summary = feeding_summary(cat, events, now, principal.timezone,
                    local_date=timestamp(body['occurred_at']).astimezone(ZoneInfo(principal.timezone)).date())
                notes = [note for note in summary['care_notes'] if body['event_id'] in note['evidence']] if body['event_type'] == 'feeding' else []
                questions = follow_up(body)
                if body['event_type'] == 'feeding' and cat.get('meal_schedule') and body.get('details', {}).get('meal_id') not in {slot['meal_id'] for slot in cat['meal_schedule']}:
                    questions = [dict(field='meal_id', question='Which planned meal was this feeding for?')]
                return envelope(feeding_summary=summary, care_notes=notes, logged=True, event_id=body['event_id'], event=body, follow_up=questions, red_flags=red_flags(events, now), analysis_status='evaluated', includes_sample_data=any(e['source'] == 'seed' for e in events))
            cat = self.repository.get_cat(household, args['cat_id'])
            events = self.repository.list_events(household, args['cat_id'])
            days = args.get('days', 7)
            flags = red_flags(events, now)
            flag_ids = {event_id for flag in flags for event_id in flag['evidence']}
            flags_include_seed = any(e['source'] == 'seed' and e['event_id'] in flag_ids for e in events)
            if tool == 'get_today':
                zone = ZoneInfo(principal.timezone)
                local_start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
                start, end = local_start.astimezone(timezone.utc), (local_start+timedelta(days=1)).astimezone(timezone.utc)
                selected = [e for e in events if start <= timestamp(e['occurred_at']) < end and timestamp(e['occurred_at']) <= now]
                feeding = feeding_summary(cat, events, now, principal.timezone)
                return envelope(feeding_summary=feeding, care_notes=feeding['care_notes'], cat=cat, events=selected, window=dict(start=start.isoformat(), end=end.isoformat(), timezone=principal.timezone), red_flags=red_flags(events, now), includes_sample_data=flags_include_seed or any(e['source'] == 'seed' for e in selected), analysis_status='evaluated')
            if tool == 'get_patterns':
                result = patterns(events, now, days)
                return envelope(patterns=result, red_flags=red_flags(events, now), window=result[0]['window'], includes_sample_data=flags_include_seed or any(e['source'] == 'seed' and e['event_id'] in result[0]['evidence'] for e in events), analysis_status='evaluated')
            if tool == 'get_vet_summary':
                return envelope(**vet_summary(cat, events, now, days), analysis_status='evaluated')
            raise DomainError('unsupported_tool', 'Unsupported tool')
        except StorageError as error:
            raise DomainError(error.code, str(error)) from error
