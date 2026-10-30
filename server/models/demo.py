"""Small, explicitly simulated planner; no external model or network calls."""
import json
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from server.models import ModelReply


class DemoModel:
    async def complete(self, messages, tools, system):
        context = json.loads(system.split('Trusted session context: ', 1)[1])
        blocks = messages[-1]['content']
        results = [b['toolResult'] for b in blocks if 'toolResult' in b]
        if results:
            data = results[-1]['content'][0]['json']
            if results[-1].get('status') == 'error':
                return ModelReply(text='Demo operation failed: ' + data.get('error', {}).get('message', 'Please check the input.'))
            if data.get('logged'):
                return ModelReply(text='Record saved.')
            events = data.get('events', data.get('timeline', []))
            def local_time(event):
                return datetime.fromisoformat(event['occurred_at'].replace('Z','+00:00')).astimezone(ZoneInfo(context['timezone'])).strftime('%b %d, %Y %I:%M %p %Z')
            lines = [f"{e['event_type']} · {local_time(e)} · Care performed by: {e.get('performed_by') or 'Unknown'} · Recorded by: {e.get('recorded_by') or 'Unknown'}" for e in events]
            return ModelReply(text=('Records found:\n' + '\n'.join(lines)) if lines else 'No records were found in this time window. Missing records do not mean nothing happened.')
        text = '\n'.join(b.get('text', '') for b in blocks)
        cat = context.get('selected_cat')
        mentioned = [c for c in context['cats'] if c['name'].casefold() in text.casefold()]
        if mentioned and (len(mentioned) != 1 or mentioned[0]['cat_id'] != cat):
            return ModelReply(text='Select the cat you mentioned in the sidebar before sending your message.')
        if not cat:
            return ModelReply(text='Choose a cat in the sidebar first.')
        lower = text.lower()
        feeding_words = r'喂了|喂食|\b(?:fed|feed|feeding)\b'
        feeding_query = bool(re.search(r'(?:\b(?:did|has|have|was|when|whether)\b.*\b(?:feed|fed|eaten|feeding)\b|喂过.*[吗没]|吃过.*[吗没])', lower))
        if re.search(feeding_words, lower) and not feeding_query and re.search(r"\b(?:will|going to|plan to|remind|should|don't|didn't|not|never)\b|打算|准备|提醒|没喂|没有喂", lower):
            return ModelReply(text='Is this a completed feeding? Say “I fed Coco today at 10 am” after feeding. No feeding record has been saved.')
        food_change = bool(re.search(r'换粮|换了.*(?:粮|食物)|(?:chang(?:e|ed|ing)|switch(?:ed|ing)?)\b[^.!?\n]*\b(?:food|foofd|diet)\b',lower))
        name, args = None, {'cat_id': cat}
        if re.search(r'摘要|summary|兽医', lower):
            name = 'get_vet_summary'
            match = re.search(r'(\d+)\s*(?:天|days?)', lower)
            args['days'] = int(match[1]) if match else 30
        elif feeding_query or (not food_change and re.search(r'今天|today|喂过|吃过|喂药.*吗', lower) and not re.search(r'吐|vomit|threw up|吃得少|不吃|体重|weight|公斤|kg|喂了|喂食|\b(?:fed|feed|feeding)\b', lower)):
            name = 'get_today'
        else:
            from server.agent import BOOLEAN_PHRASES, ENUM_PHRASES, supported_detail
            pending = context.get('pending_follow_up')
            event_type = 'food_change' if food_change else 'vomiting' if re.search(r'吐|vomit|threw up', lower) else 'appetite' if re.search(r'食欲|吃得少|不吃|eating', lower) else 'weight' if re.search(r'体重|weight|kg|公斤', lower) else 'feeding' if re.search(feeding_words,lower) else None
            continuing = bool(pending and event_type is None)
            if continuing:
                event_type = pending['event_type']
            if not event_type:
                return ModelReply(text='Local demo examples: today’s records, a veterinary summary for the last 30 days, my cat vomited, eating less, weight 3.9 kg, Alex fed 40 g of wet food, or my cat changed food. Answer follow-up questions with explicit phrases such as no blood, normal energy, after a meal, or 6 hours. This mode uses fixed rules and has no AI model.')
            from server.event_details import FIELDS
            details = {}
            for field in FIELDS[event_type]:
                candidates = [False, True] if field in BOOLEAN_PHRASES else list(ENUM_PHRASES[field]) if field in ENUM_PHRASES else []
                unit = {'weight_kg': r'(?:kg|公斤|千克)', 'duration_hours': r'(?:hours?|小时)'}.get(field)
                if unit:
                    match = re.search(r'(\d+(?:\.\d+)?)\s*' + unit, lower)
                    if match:
                        candidates = [float(match[1])]
                for value in candidates:
                    if supported_detail(field, value, text, text):
                        details[field] = value
            if event_type=='food_change':
                transition = re.search(r'\bfrom\s+([^.!?\n]+?)\s+to\s+([^.!?\n]+)',text,re.I)
                if transition:
                    details.update(previous_food=transition.group(1).strip(),food=transition.group(2).strip())
                else:
                    foods = [food for food in ('wet food','dry food','湿粮','干粮','罐头') if food in lower]
                    if len(foods)==1:
                        field = pending['questions'][0]['field'] if continuing and pending.get('questions') else 'food'
                        details[field] = foods[0]
            if event_type=='feeding':
                amount = re.search(r'\d+(?:\.\d+)?\s*(?:grams?|g|克)',text,re.I)
                if amount:
                    details['amount'] = amount.group()
                foods = [food for food in ('wet food','dry food','湿粮','干粮','罐头') if food in lower]
                if len(foods)==1:
                    details['food'] = foods[0]
            name = 'log_care_event' if event_type in ('feeding','food_change') else 'log_health_event'
            from server.agent import supported_performer
            performers = [person for person in context.get('recorders',[]) if supported_performer(person,text,text,context.get('recorded_by'))]
            if len(performers)==1:
                args.update(performed_by=performers[0],performed_by_evidence=text)
            if not continuing:
                time_match = re.search(r'\b(?:at\s+)?(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*[ap]\.?m\.?(?!\w)', text, re.I)
                if re.search(r'\byesterday\b|\btomorrow\b|\blast\b|\bago\b|昨天|明天|前天|\d{4}-\d{2}-\d{2}', lower):
                    args['occurred_at_evidence'] = text
                elif time_match:
                    args['occurred_at_evidence'] = time_match.group()
                elif re.search(r'\bat\s+\d|\d+\s*(?:点|时)', lower):
                    args['occurred_at_evidence'] = text
            args.update(event_type=event_type, details=details, detail_evidence={f: text for f in details}, continue_event=continuing)
        return ModelReply(calls=[{'id': uuid.uuid4().hex, 'name': name, 'arguments': args}])
