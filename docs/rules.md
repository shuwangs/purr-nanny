# Data and health rules

`storage.backend.RulesBackend` uses `SQLiteRepository` for household-scoped cat profiles and events. Follow-up updates preserve event identity; retries reuse saved mutation results. Occurrence and recording timestamps are separate, unknown details stay unknown, and future occurrence times are rejected.

## Details and rules

Recognized boolean details: blood, lethargy, after_meal, straining. Values are boolean or null. Numeric details: duration_hours (nonnegative finite), weight_kg (positive finite). Eating: normal/less/nothing. Urine output: normal/little/none. Energy level: normal/reduced/severely_reduced. Repository rejects malformed recognized values. Extra factual details are retained. `after_meal=true` explicitly means within two hours, as asked by follow-up; no temporal relationship is invented from nearby feeding records.

Rules use an explicit aware reference time and a seven-day inclusive window:

- urinary_obstruction_signs: straining=true with urine_output=little/none → emergency, seek immediate veterinary attention.
- vomiting_concerning_signs: vomiting with blood=true or lethargy=true → urgent, prompt veterinary evaluation.
- frequent_vomiting_24h: at least three distinct vomiting observations in the inclusive rolling 24-hour window → urgent, call the vet today. Two observations in seven days alone do not trigger an urgent signal.
- vomiting_frequency_doubled: at least three observations in the last 30 days and at least twice the positive preceding-30-day count → warning, mention at the next veterinary visit. A zero prior count cannot establish a doubling and does not trigger this rule. Adjacent windows do not overlap: (now−30d, now] versus (now−60d, now−30d]. Warning-level signals are displayed without SMS. Counts represent recorded observations, not guaranteed logging coverage.
- not_eating_24h: eating=nothing and duration_hours>=24 → urgent, prompt veterinary contact.

Evidence contains event IDs. Emergency sorts before urgent. Safety results are evaluated before ordinary missing-detail questions; unknown details never count as false. The initial set intentionally does not assess every danger. Empty red_flags is not a declaration of safety. Veterinary review remains pending.

Source rationale: [Cornell vomiting](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/vomiting), [Cornell urinary disease](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-lower-urinary-tract-disease), [Cornell hairballs](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/danger-hairballs). The conservative 24-hour appetite trigger and two-hour meal association are project choices, not validated clinical thresholds.

## Statistics and queries

Lookback queries include start and reference now (so records logged at the injected now participate); future records are excluded. Today uses household-local midnight to next midnight, end-exclusive, further filtered <=now; DST boundaries use ZoneInfo. Every pattern includes a window, sample size, denominator and evidence. Frequency denominator is requested calendar days, not verified logging coverage. Meal proportion requires three observations with explicit boolean after_meal; otherwise insufficient_data. Weight change requires two positive measurements at distinct times. Food comparison requires exactly one change, equal windows of at least three days on each side, capped at seven days. Increased means after_count>=3 and after_count>=2*before_count. This descriptive threshold does not establish causation. Missing observations can bias every statistic.

Summary is a structured factual timeline with sample labeling; it contains no generated diagnosis. The independent Apache-2.0 package is installable locally; separate public repo/registry release and real de-identified data collection remain pending.

## Weight warnings

Weight design correction (2026-10-12): weight_loss_30d compares the earliest and latest distinct-time positive finite weight measurements in [reference_now−30 days, reference_now]. A decrease of at least 5% from the earliest measurement produces warning-level next-visit guidance, using those two event IDs as evidence. Missing measurements, same-time-only measurements, zero/invalid values, and future measurements cannot trigger it. Comparisons use decimal arithmetic on recorded numeric values and unrounded percentages; UI rounding never changes the threshold. This remains a provisional project rule, not clinically reviewed guidance.

Weight patterns additionally expose change_percent alongside change_kg. The UI displays kilograms to at most three decimals and percentages to one decimal, including units; e.g. 4.2→3.9 is -0.3 kg and -7.1%. The 30-day warning is evaluated independently of a user-selected shorter summary window, so prior evidence can lie outside the visible timeline. warning-level reminders do not send SNS messages.
