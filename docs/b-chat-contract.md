# B → dialogue agent contract

The web chat and language-model agent are new A/C work. Existing Today/veterinary views remain read-only. B provides structured domain operations through `RulesBackend.execute`; browser or model output does not establish household authority.

The agent should call the authenticated MCP tools, using the current `server/contracts.py` JSON schemas. Do not build a second rule implementation inside a prompt or browser. Read `list_cats` for the authenticated household, then select a cat_id. Duplicate names require clarification. Even one cat should not be silently substituted when a user explicitly names a different cat.

## Recording and follow-up

1. Record an observation using log_health_event/log_care_event. Backend event time defaults to the explicit service time and reports `time_defaulted=true`; do not invent an occurrence time or reporter.
2. Present red_flags before ordinary follow_up. Carry recommended_wording and provider-confirmed notification_status into the response; no diagnosis or claims that a message was read.
3. Keep the pending event_id, cat_id, kind/event_type and source in trusted conversation state. Answers supplement that same event with a new idempotency_key. Unknown/null stays unknown; "I don't know" is not false.
4. Generate retry keys server-side from stable message identity and tool-call identity. Repeating an identical write uses the same key. Changed input uses a new key. The backend rejects a reused key with different input.
5. Clear or switch pending state deliberately when the user changes cat, starts a new observation or cancels. An unrelated answer must not overwrite the prior event.

A owns model transport, conversation management, tool selection and language rendering. B owns persistence, windows, deterministic rules and evidence. Existing B storage has no conversation transcript tables. A should request that interface before persisting chat history through B; event persistence is already available.

## Query results

`get_today` exposes events, cat, feeding_summary, care_notes, window and structured red_flags. `get_patterns` exposes pattern windows, evidence, denominators and sample sizes. `get_vet_summary` exposes a factual timeline and statistics. Forward includes_sample_data to every relevant response/view, including when seeded history only contributes to safety evidence. Use display_timezone/window.timezone to describe times.

## Verification

`tests/test_b_chat_contract.py` verifies multi-turn supplementation, unknown fields, stable event identity, retry behavior, duplicate cat names, household isolation and explicit retry conflicts. These tests establish backend guarantees; they do not claim that a model can select tools or interpret arbitrary natural language correctly. A must test the agent loop and actual provider separately.
