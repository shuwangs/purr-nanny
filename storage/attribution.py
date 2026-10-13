"""Separate the person doing care from the person entering an observation."""
def apply_attribution(body, args, now):
    if args.get('performed_by') is not None:
        body['performed_by'] = args['performed_by']
    if args.get('recorded_by') is not None:
        person = args['recorded_by']
        body.setdefault('first_recorded_by',person)
        body['recorded_by'] = person
        body.setdefault('entry_history',[]).append(dict(recorded_by=person,recorded_at=now.isoformat()))
