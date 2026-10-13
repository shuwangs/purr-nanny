# A → C integration handoff

Public input schemas: server/contracts.py. Outputs from B's storage/backend.py now define:

- get_today: common envelope + cat={cat_id,name}, events=[event], window={start,end,timezone}, red_flags, includes_sample_data, analysis_status='evaluated'.
- get_vet_summary: common envelope + cat, timeline=[event], window={start,end,days}, patterns, red_flags, includes_sample_data, disclaimer, analysis_status='evaluated'.
- event: event_id, cat_id, kind, event_type, source, recorded_at, occurred_at, time_defaulted, updated_at, reporter, details.
- red_flag: rule_id, level emergency|urgent|warning, evidence=[event_id], recommended_wording.
- notification_status={state:disabled|queued|sent|failed, optional rules:[{rule_id,state,message_id}]}.
- follow_up=[{field,question}]. UI must display Includes sample data for demo when flagged; render red flags first; sent means provider acceptance only. Prototype medical rules are not professionally reviewed.

A will expose app HTML files as `ui://cat-nanny/today.html` and `ui://cat-nanny/vet-summary.html`, mimeType `text/html;profile=mcp-app`; tools get_today/get_vet_summary have `_meta.ui.resourceUri` linking to them when files exist. Please choose apps/today.html and apps/vet-summary.html; if you use directories, A will adapt resource paths. Receive host `ui/notifications/tool-result` structuredContent via MCP Apps postMessage protocol. Static read-only pages; do not expose local development bearer tokens in HTML. Please implement SDK handshake appropriate for target standards or a clearly labeled standalone fallback. A will register resources; C owns their source and frontend rendering verification.

Official FAQ permits our own frontend simulator, because participants cannot obtain preview Alexa toolkit access: https://amazonappdev2026.devpost.com/details/faqs . A documented this in docs/access-validation.md. No genuine Alexa call/rendering is currently verified.

A integration status: apps.resources registered directly; apps* and CSS/JS included in package data; Docker copies apps. HTTP integration tests read resource content through MCP. C resolved the renderer assertion issue. A independently reran the full shared suite: 20 tests passed on 2026-10-12, including RulesBackend follow-up warnings, SNS deduplication, both resources, and five local user stories. Direct Alexa, remote hosting and production OAuth remain unverified. Preview instructions: docs/ui-preview.md; submission review: docs/delivery-checklist.md.
