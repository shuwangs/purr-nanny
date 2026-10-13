# cat-health-signals

A pure Python package for deterministic feline observation statistics and conservative safety signals. No AWS, Alexa, model, network, or implicit system clock dependencies. Apache-2.0. Not veterinary diagnosis; rules have not received veterinary review.

Install from the project root:

```sh
python -m pip install ./packages/cat-health-signals
```

```python
from datetime import datetime, timezone
from cat_health_signals import patterns, red_flags
now = datetime(2026, 10, 12, 18, tzinfo=timezone.utc)
events = [{"event_id": "example", "event_type": "vomiting",
           "occurred_at": now.isoformat(), "source": "seed",
           "details": {"blood": True}}]
print(red_flags(events, now))
print(patterns(events, now, days=7))
```

All timestamps must include a timezone. Events must belong to one cat; the caller enforces authorization and isolation. Missing details stay unknown. `follow_up(event)`, `red_flags(events, now)`, `patterns(events, now, days=7)`, and `vet_summary(cat, events, now, days=7)` return JSON-compatible structures. Frequency counts observations, not inferred episode totals. Historical logging does not prove complete coverage.

Rules and thresholds: see the parent project's `docs/rules.md`. Public repository creation and registry release remain pending.
