# Platform contract v1.0

Machine-readable schemas: `server/mcp/contracts.py`; discover the same schemas through `tools/list`. Unknown top-level fields are rejected. Every tool uses a trusted server identity; `household_id` and timezone cannot be supplied as tool arguments. Reporter is descriptive, optional, and never establishes permissions.

| Tool | Required input | Optional input |
| --- | --- | --- |
| list_cats | — | — |
| add_cat | name, idempotency_key | — |
| update_cat | cat_id, name | — |
| log_health_event | cat_id, event_type, idempotency_key | event_id, occurred_at, reporter, details, source |
| log_care_event | cat_id, event_type, idempotency_key | event_id, occurred_at, reporter, details, source |
| get_today | cat_id | — |
| get_patterns | cat_id | days (1–90, default 7) |
| get_vet_summary | cat_id | days (1–90, default 7) |

Health types: vomiting, appetite, litter, energy, weight. Care types: feeding, water, litter_cleaning, medication, food_change. Cat names are 1–80 characters. Idempotency keys are 8–128 characters, scoped to the household across mutations. Repeat the exact key/input on network retries. A changed request with the same key returns idempotency_conflict. Follow-up answers use the existing event_id, matching cat/type/source, and a new key. Only supplied details change; missing facts remain unknown. Creating and correcting records preserves original recorded_at; updated_at tracks the correction.

occurred_at is an ISO 8601 date-time with an offset (Z accepted), normalized to UTC. Omission on initial recording defaults to explicit service time and sets time_defaulted=true. Future occurrence is rejected. Today uses household-local midnight including DST; rolling windows are durations ending at explicit reference time. RulesBackend includes observations exactly at reference time. Source is user (default) or seed; results containing seed data expose includes_sample_data=true. Consumers must display “Includes sample data for demo”.

All successful results contain schema_version, event_id (nullable), logged, follow_up, red_flags, patterns, notification_status. Additional cat/event/events/window/timeline fields are tool-specific. A result with analysis_status=unavailable means no health assessment was performed; empty red_flags in that case does not mean no danger.

Red flags: rule_id, level (emergency, urgent, warning), evidence (event IDs), recommended_wording. Order emergency before urgent before warning. Deliver recommended wording before ordinary follow-up questions. Follow-ups: field, question. Patterns include status, time window, sample size, denominator, evidence; insufficient_data forbids asserted association. Summary is a factual timeline, never a diagnosis.

Notification state: disabled, queued, sent, failed, uncertain. sent means SNS accepted a message ID, not delivered or read. State is deduplicated by trusted household/rule/canonical evidence identity. Historical warnings remain in results but unrelated records do not trigger sends. Confirmed provider rejection is retryable on the same request; legacy failures, queued entries and uncertain outcomes need operator reconciliation; SNS ambiguous timeouts are not automatically retried because duplicate SMS cannot be ruled out. The SQLite ledger must persist between restarts and is suitable for one local instance; a cloud deployment needs shared durable conditional-write storage. SNS topic configuration is server-side; tool callers cannot supply a recipient.

Tool errors use MCP isError=true plus the standard envelope and error={code,message,request_id}. Codes include invalid_arguments, unknown_tool, not_found, event_conflict, idempotency_conflict, invalid_time, internal_error. Internal provider details and input values are not exposed. Transport authentication failures are HTTP 401 without WWW-Authenticate, matching Amazon's currently documented requirement. Tokens and household/event/contact details are omitted from platform logs.

Event detail fields are event-specific, nullable and optional. Unknown or unrelated keys and coerced booleans/numbers are rejected at transport and repository boundaries. Tool discovery exposes conditional schemas for each event type.

| Event type | Detail fields |
| --- | --- |
| vomiting | blood, lethargy, after_meal (booleans) |
| appetite | eating (normal/less/nothing), duration_hours (finite nonnegative number) |
| litter | straining (boolean), urine_output (normal/little/none) |
| energy | level (normal/reduced/severely_reduced) |
| weight | weight_kg (finite positive number) |
| feeding | food, amount (text) |
| water | amount (text) |
| litter_cleaning | notes (text) |
| medication | name, dose (text; recorded observations only) |
| food_change | food, previous_food (text) |

List cats before selecting a cat_id. Duplicate names return separate profiles; the client must ask which cat rather than guessing. An empty household returns an empty list.

Readable views use display_timezone (trusted household timezone), also included in query window metadata. UTC ISO timestamps and internal rule/event IDs remain in structured data; HTML resources convert times and replace identifiers with human-readable signal and observation labels. warning-level signals mean next-visit discussion and do not send SNS notifications.

## Feeding plans and household coordination

Profiles support optional meals_per_day (integer 1–12) and meal_schedule=[{meal_id,label,time?}]. IDs must be unique; time is HH:MM in household local time. If both schedule and meals_per_day are provided, slot count must agree. update_cat supports partial changes and preserves other fields. Set meal_schedule=[] to remove a schedule. Existing profiles need no migration; no plan is assumed.

Example update_cat:
```json
{"cat_id":"CAT_ID","meals_per_day":2,"meal_schedule":[{"meal_id":"breakfast","label":"Breakfast","time":"08:00"},{"meal_id":"dinner","label":"Dinner","time":"18:00"}]}
```
Feeding details additionally support meal_id, referencing a configured slot. Scheduled times are descriptive; the service never guesses the meal from proximity to a time. With a plan but missing/unrecognized meal_id, the feeding is saved and a clarification is returned. meals_per_day alone is not a schedule and does not support same-meal judgment.

get_today includes feeding_summary={count,local_date,timezone,plan_status,records,care_notes}. Every record supplies occurred_at, reporter, food, amount and a meal_label when matched to the configured plan. No schedule means plan_status=not_configured, with facts only. Unknown portions/reporters remain unknown. Counts are counts of distinct recorded events, not an inferred amount consumed.

care_notes is separate from clinical red_flags and never triggers SNS. Two distinct feeding events for the same configured meal_id on the same household-local date produce possible_duplicate_meal, with evidence IDs and a gentle confirmation message. The event is already saved (logged=true); this is not a refusal or overfeeding diagnosis. Breakfast and dinner are separate slots. Different local dates are separate meals. Backdated logs are checked against their occurrence date. Corrections update the same event and can resolve the note. Exact retries keep the original event ID and do not add records. Reusing a request key for different input still returns idempotency_conflict.

Optional event input normalization: for both logging tools, omitted/null/empty/whitespace-only occurred_at and event_id are treated as unfilled before validation and idempotency comparison. A new event uses the explicit current service time and a new event ID. An existing event's follow-up preserves its occurrence time when no correction is supplied. Nonempty invalid or timezone-free timestamps return invalid_time with an ISO 8601 example; valid aware timestamps are normalized to UTC. Empty input forms share the same retry semantics.
