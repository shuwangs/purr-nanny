# QA fixes — 2026-10-12

The PM's confirmed duplicate notification bug is repaired. An emergency litter observation followed by a feeding record keeps the warning visible but publishes once. Alert deduplication uses household, rule and canonical evidence, with transactional claims to prevent concurrent sends. A distinct dangerous observation can produce a new alert. Aggregate rules use the sorted set of evidence IDs; a changed evidence set is a distinct alert when the recorded event participates in that evidence.

Notification recovery distinguishes confirmed rejection (`failed`, retryable) from ambiguous provider outcomes (`uncertain`). Retrying the original recording request reattempts only confirmed rejections. Missing MessageId, timeouts and generic exceptions are uncertain and never blindly retried. Existing failed ledger entries default to non-retryable because their original outcome may have been ambiguous. The schema migration preserves existing rows. UI wording covers uncertain outcomes.

For a queued entry left by a crashed process or an uncertain/legacy failure, stop the service and reconcile provider evidence before recovery. Use the local operator API `Notifications(path).reconcile(household, alert_id, rule, outcome=..., message_id=...)`: `sent` requires a verified provider message ID; `rejected` means definite non-acceptance and permits retry of the original request; `uncertain` preserves the hold. Do not reconcile an active worker's send. Reconciliation is not exposed to tool callers. SNS acceptance still does not establish delivery or reading. No scheduled retry worker or shared cloud notification ledger is implemented.

`list_cats` returns only the authenticated household's profiles, including duplicate names as separate IDs. SQLite and the reference backend support existing profiles. DynamoDB writes a household catalog entry atomically with profile creation/rename and pages its discovery query. Existing DynamoDB profiles from before this change require catalog backfill before enabling discovery; production DynamoDB startup remains unwired.

Health and care detail schemas now document event-specific fields and reject unrelated fields, unknown keys and incorrect value types at both the HTTP and repository boundaries. Explicit null remains unknown; omitted details do not erase earlier answers.

## Live local client

Start the server using README instructions. In a second terminal set `CAT_NANNY_CLIENT_TOKEN` to a configured development token, then run:

```sh
.venv/bin/python -m demo.live_client
```

The client initializes a real Streamable HTTP MCP session, discovers tools and lists household cats. Commands use `TOOL JSON`. `schemas` shows discoverable input schemas; `quit` exits. Example sequence (replace CAT_ID and EVENT_ID with returned IDs):

```text
add_cat {"name":"Miso","idempotency_key":"create-miso"}
list_cats
log_health_event {"cat_id":"CAT_ID","event_type":"vomiting","idempotency_key":"observe-miso","details":{}}
log_health_event {"cat_id":"CAT_ID","event_id":"EVENT_ID","event_type":"vomiting","idempotency_key":"clarify-miso","details":{"blood":false,"lethargy":false,"after_meal":true}}
get_today {"cat_id":"CAT_ID"}
get_patterns {"cat_id":"CAT_ID","days":7}
log_care_event {"cat_id":"CAT_ID","event_type":"feeding","idempotency_key":"feed-miso","reporter":"Alex","details":{"food":"wet food"}}
get_vet_summary {"cat_id":"CAT_ID","days":7}
```

Warnings print before follow-up questions. Answers use the original event ID and a fresh key. Repeat identical key/input to retry. This command-line client provides live local recording and clarification; the browser rendering preview remains a fixed fixture. Alexa voice integration remains unverified.

## Evidence and remaining gaps

Regression tests in `tests/test_qa_regressions.py` cover the PM reproduction, independent dangerous events, concurrent evidence deduplication, restart/recovery, confirmed rejection retries, household cat discovery, strict detail validation and preservation of unknown values. The actual MCP SDK exercises all five story categories through HTTP against the in-process ASGI service with SQLite and an SNS stub. This proves local protocol behavior, not a remote deployment or real SMS delivery.

Production OAuth/startup, shared notification storage, live DynamoDB concurrency/restart verification, Alexa rendering, veterinary review, public release/video/submission artifacts and remote latency checks remain open. No cloud resources were created and no real notification was sent. Gates G0/G2/G3 remain open.

## Design threshold and readable UI correction

2026-10-12: User confirmed the vomiting design conditions. Removed the seven-day/two-observation urgent trigger. Urgent vomiting rules now cover blood, lethargy, and at least three distinct observations within the inclusive rolling 24-hour window. “3 次以上” is interpreted as >=3. Monthly frequency is warning-level: at least three in the last 30 days, at least twice a positive preceding-30-day count. Zero prior count does not establish a doubling. Warning-level guidance is displayed for the next visit and does not send SMS. Existing emergency and appetite rules are outside this vomiting correction; no claim that all other design features are complete. Thresholds remain provisional project requirements, not validated clinical guidance.

Monthly comparisons use adjacent nonoverlapping windows and deduplicate event IDs. Vet summaries evaluate warnings using the full history, including comparison evidence outside the displayed timeline, and preserve seed labeling for that evidence.

Backend results now provide trusted display_timezone and window timezone. UTC ISO strings and IDs remain in structured results for interoperability; user views format all dates in household time, including daylight-saving changes, and display signal names plus observation descriptions instead of rule IDs/event UUIDs. Missing household timezone in an older result falls back to device local time; invalid dates display Time unknown. Boolean observations show Yes/No.

Verification: 41 tests pass. tests/test_design_thresholds.py covers urgent and warning thresholds, window boundaries, future/duplicate observations, summary comparison evidence and SMS suppression. Node renderer tests cover CDT/CST, localized timestamps and hidden identifiers. Both pages visually checked in the local MCP Apps preview. Screenshot: docs/qa-readable-preview.png. Restart a running service to load changed Python rules, then rerun the query/reopen the App resource to replace cached results and HTML.

## Meal-aware feeding coordination

Implemented optional profile plans and explicit feeding meal_id. Normal multiple meals are independent records. Same configured meal on the same household-local date produces a confirmation note, without blocking the save or sending a health SMS. Without a schedule (including meals_per_day only), the service reports count/time/reporter/food/amount and does not judge excess feeding. Unknown meal selection is saved with a follow-up question; scheduled times do not imply automatic slot assignment.

Verification: tests/test_feeding_plan.py covers exact request retries, breakfast/dinner, a second record for the same meal, correcting the existing event, no plan, count-only plan, unknown meal, partial profile updates, local midnight, invalid schedules, and DynamoDB versioned profile/catalog preservation. UI renderer assertions cover two meals with names/times/amounts and separate confirmation wording. These are local/stub tests; live DynamoDB remains unverified.

## Inspector blank event fields

Optional occurred_at/event_id inputs are normalized before Pydantic validation and retry-key comparison. Missing, null, empty and whitespace-only values behave identically. New events default to explicit service time; blank event_id creates a new event. A valid supplied time is retained after UTC normalization; a nonempty malformed or timezone-free time returns a clear invalid_time message with a format example. Blank occurrence on an existing-event follow-up preserves its original time. Tests exercise both logging tools through MCP HTTP, all blank forms with the same retry key, valid offsets, malformed values, follow-up preservation and discoverable schema acceptance. Full suite: 54 passed.

## Weight-loss reminder and number formatting

Added weight_loss_30d: at least 5% decrease between earliest/latest distinct-time valid weights within the inclusive rolling 30-day window → warning, mention at next veterinary visit. 4.2 kg to 3.9 kg produces the reminder. It is shown by recording, today/pattern queries and vet summaries; it does not send SMS. Decimal comparison prevents binary-floating-point noise at the exact 5% boundary. UI renders -0.30000000000000027 as -0.3 kg and change_percent as -7.1%.

Full suite: 61 passed. Weight regression tests cover above/below/exact threshold, 30-day boundary, future and invalid data, insufficient/distinct-time samples, actual RulesBackend summary/query output and warning SMS suppression. Renderer tests cover localized units and absence of floating-point tails. Restart the running backend and reopen the resource after rerunning the query to see the updated rule and formatting.
