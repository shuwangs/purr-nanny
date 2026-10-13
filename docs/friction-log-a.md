# A friction log

2026-10-12: Started from plan-only repository. Official FAQ contradicts the plan's assumption that hackathon participants can gain Alexa toolkit access; frontend fallback is explicitly allowed. Evidence in access-validation.md. Direct voice/rendering validation remains open.

Dependency install initially failed under restricted network DNS; the reviewed network escalation succeeded. Official MCP SDK v1.30.0 installed in project virtualenv, retaining <2 version bound. Platform tests call the SDK over ASGI HTTP; they do not prove remote connectivity.

SNS standard publish lacks an end-to-end exactly-once SMS guarantee. Durable reservation avoids normal retry duplicates; timeout/crash can leave failed/queued records requiring reconciliation. No automatic retry is claimed.

First increment verification: eight platform tests pass. HTTP checks use B's RulesBackend and read C's generated resources through MCP; warnings survive even when the notification ledger fails. Package wheels build and include server/storage plus UI CSS/JS. pip check passes. Shared full suite last run had one C-owned renderer fixture mismatch (15 passed, 1 failed before the additional notification-failure case). C handoff records the exact failure. Production OAuth, shared cloud notification storage, actual SNS and remote hosting remain unfinished.

Final local integration update: C resolved the renderer assertion; full shared suite independently verified by A at 20 passed on 2026-10-12. Earlier failure entries above are historical. README now links preview, acceptance, architecture and delivery checklist. External validation limits remain open.

Conversation-agent increment: official MCP client performs authenticated Streamable HTTP discovery/calls; Bedrock Converse adapter implemented but model ID is not configured in this environment. Durable household-scoped session/turn journal reuses saved prepared keys after response loss or retryable internal MCP errors. Follow-up uses server-owned pending event reference. Development cookie login and C-compatible API/static routes are complete. Provider and tool failures preserve structured health warnings. Full suite: 74 passed. C browser integration used a scripted model plus real HTTP MCP; no paid/live model or genuine Alexa connection is claimed. UI history restoration after full page reload remains a C integration item; canonical history API is available.
