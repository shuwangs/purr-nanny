"""Deterministic observations; no diagnosis, network, or implicit clock."""
from datetime import datetime, timedelta
from collections import Counter
from decimal import Decimal
from math import isfinite

__version__ = '0.1.0'


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if result.utcoffset() is None:
        raise ValueError('Timestamp must include timezone')
    return result


QUESTIONS = {
    'vomiting': {'blood': 'Was there blood in the vomit?', 'lethargy': 'Is your cat unusually weak or lethargic?', 'after_meal': 'Did this happen within two hours after eating?'},
    'appetite': {'eating': 'Is your cat eating normally, less, or nothing?', 'duration_hours': 'How many hours has this been happening?'},
    'litter': {'straining': 'Is your cat straining to urinate?', 'urine_output': 'Is urine output normal, little, or none?'},
    'energy': {'level': 'Is energy normal, reduced, or severely reduced?'},
    'food_change': {'food': 'What food did your cat switch to?', 'previous_food': 'What food was your cat eating before the change?'},
    'weight': {'weight_kg': 'What is the measured weight in kilograms?'},
}


def follow_up(event):
    return [{'field': field, 'question': question} for field, question in QUESTIONS.get(event['event_type'], {}).items()
            if event.get('details', {}).get(field) is None]


def weight_measurements(events, now, days):
    now = timestamp(now)
    distinct = {e['event_id']: e for e in events if e['event_type'] == 'weight'
                and now - timedelta(days=days) <= timestamp(e['occurred_at']) <= now
                and isinstance(e.get('details', {}).get('weight_kg'), (int, float))
                and not isinstance(e['details']['weight_kg'], bool)
                and isfinite(e['details']['weight_kg']) and e['details']['weight_kg'] > 0}
    return sorted(distinct.values(), key=lambda e: (timestamp(e['occurred_at']), e['event_id']))


def weight_delta(weights):
    if len(weights) < 2 or timestamp(weights[-1]['occurred_at']) <= timestamp(weights[0]['occurred_at']):
        return None, None
    baseline = Decimal(str(weights[0]['details']['weight_kg']))
    change = Decimal(str(weights[-1]['details']['weight_kg'])) - baseline
    return change, change / baseline * 100


def red_flags(events, now):
    now = timestamp(now)
    flags = []
    recent = [e for e in events if now - timedelta(days=7) <= timestamp(e['occurred_at']) <= now]
    def add(rule, level, evidence, message):
        flags.append(dict(rule_id=rule, level=level, evidence=[e['event_id'] for e in evidence], recommended_wording=message))
    for e in recent:
        d = e.get('details', {})
        if e['event_type'] == 'litter' and d.get('straining') is True and d.get('urine_output') in ('little', 'none'):
            add('urinary_obstruction_signs', 'emergency', [e], 'Straining with little or no urine can be an emergency. Seek immediate veterinary attention.')
        if e['event_type'] == 'vomiting' and (d.get('blood') is True or d.get('lethargy') is True):
            add('vomiting_concerning_signs', 'urgent', [e], 'Vomiting with blood or lethargy was reported. Please call your vet today.')
        if e['event_type'] == 'appetite' and d.get('eating') == 'nothing' and isinstance(d.get('duration_hours'), (int, float)) and d['duration_hours'] >= 24:
            add('not_eating_24h', 'urgent', [e], 'Your cat has reportedly not eaten for at least a day. Contact a veterinarian promptly.')
    # Distinct observations only: a follow-up/retry must not inflate episode counts.
    vomits = list({e['event_id']: e for e in events
                   if e['event_type'] == 'vomiting' and timestamp(e['occurred_at']) <= now}.values())
    day = [e for e in vomits if now - timedelta(hours=24) <= timestamp(e['occurred_at']) <= now]
    if len(day) >= 3:
        add('frequent_vomiting_24h', 'urgent', day,
            'At least three vomiting observations were recorded in 24 hours. Please call your vet today.')
    current = [e for e in vomits if now - timedelta(days=30) < timestamp(e['occurred_at']) <= now]
    previous = [e for e in vomits if now - timedelta(days=60) < timestamp(e['occurred_at']) <= now - timedelta(days=30)]
    # A zero baseline cannot establish a doubling; do not invent a ratio.
    if len(current) >= 3 and len(previous) > 0 and len(current) >= 2 * len(previous):
        add('vomiting_frequency_doubled', 'warning', previous + current,
            f'{len(current)} vomiting observations were recorded in the last 30 days, compared with {len(previous)} in the preceding 30 days. This is worth mentioning at your next veterinary visit; recorded frequency does not establish a cause.')
    weights = weight_measurements(events, now, 30)
    change, percentage = weight_delta(weights)
    if percentage is not None and percentage <= Decimal('-5'):
        add('weight_loss_30d', 'warning', [weights[0], weights[-1]],
            f'Recorded weight decreased by {abs(percentage):.1f}% within 30 days. This is worth mentioning at your next veterinary visit.')
    return sorted(flags, key=lambda f: ({'emergency': 0, 'urgent': 1, 'warning': 2}[f['level']], f['rule_id']))


def patterns(events, now, days=7):
    now = timestamp(now)
    if not 1 <= days <= 90:
        raise ValueError('days must be between 1 and 90')
    start = now - timedelta(days=days)
    selected = sorted([e for e in events if start <= timestamp(e['occurred_at']) <= now], key=lambda e: (timestamp(e['occurred_at']), e['event_id']))
    window = {'start': start.isoformat(), 'end': now.isoformat(), 'days': days}
    vomits = [e for e in selected if e['event_type'] == 'vomiting']
    known = [e for e in vomits if isinstance(e.get('details', {}).get('after_meal'), bool)]
    output = [dict(pattern_id='frequency', status='observed' if selected else 'insufficient_data', window=window, counts=dict(Counter(e['event_type'] for e in selected)), denominator=days, denominator_unit='calendar_days', sample_size=len(selected), evidence=[e['event_id'] for e in selected]),
              dict(pattern_id='vomiting_after_meal', status='observed' if len(known) >= 3 else 'insufficient_data', window=window, numerator=sum(e['details']['after_meal'] for e in known), denominator=len(known), sample_size=len(known), evidence=[e['event_id'] for e in known])]
    weights = weight_measurements(events, now, days)
    change, percentage = weight_delta(weights)
    output.append(dict(pattern_id='weight_trend', status='observed' if change is not None else 'insufficient_data',
                       window=window, sample_size=len(weights), denominator=len(weights),
                       change_kg=float(change) if change is not None else None,
                       change_percent=float(percentage) if percentage is not None else None,
                       evidence=[e['event_id'] for e in weights]))
    changes = [e for e in selected if e['event_type'] == 'food_change']
    comparison = dict(pattern_id='food_change_comparison', status='insufficient_data', window=window, sample_size=0, denominator=0, evidence=[])
    if len(changes) == 1:
        change = timestamp(changes[0]['occurred_at'])
        span = min(timedelta(days=7), change-start, now-change)
        if span >= timedelta(days=3):
            before = [e for e in vomits if change-span <= timestamp(e['occurred_at']) < change]
            after = [e for e in vomits if change <= timestamp(e['occurred_at']) <= change+span]
            comparison.update(status='observed', before_count=len(before), after_count=len(after), denominator=span.total_seconds()/86400, denominator_unit='days_per_side', sample_size=len(before)+len(after), increased=len(after) >= max(3, 2*len(before)), evidence=[changes[0]['event_id']]+[e['event_id'] for e in before+after], limitation='Recorded observations only; incomplete logging can bias comparisons. No causal inference.')
    output.append(comparison)
    return output


def vet_summary(cat, events, now, days=7):
    stats = patterns(events, now, days)
    ids = set(stats[0]['evidence'])
    timeline = sorted([e for e in events if e['event_id'] in ids], key=lambda e: (timestamp(e['occurred_at']), e['event_id']))
    flags = red_flags(events, now)
    evidence_ids = {event_id for flag in flags for event_id in flag['evidence']}
    return dict(cat=cat, window=stats[0]['window'], timeline=timeline, patterns=stats,
                red_flags=flags, includes_sample_data=any(e.get('source') == 'seed' for e in events if e['event_id'] in ids | evidence_ids),
                disclaimer='Factual observations for veterinary review; not a diagnosis.')
