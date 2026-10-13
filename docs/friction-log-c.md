# C friction log

| Date | Observation | Impact / action | Status |
|---|---|---|---|
| 2026-10-12 | Shared directory initially contains plan; A/B are editing concurrently; directory has no Git repository | Explicit file ownership communicated through existing chats; do not overwrite A/B files | Coordinated |
| 2026-10-12 | Veterinary output uses timeline while today uses events | Renderer accepts agreed query-specific fields; regression assertion checks veterinary rows | Fixed locally |
| 2026-10-12 | Provider sent state can be mistaken for SMS delivery | View explicitly says acceptance, with delivery/read unconfirmed | Implemented |
| 2026-10-12 | Empty flags from unavailable backend could imply health clearance | View shows analysis unavailable warning independent of flag list | Implemented |
| 2026-10-12 | Live Alexa access, actual UI host rendering, deployment and clinical review have no verified evidence | Acceptance and delivery gates left pending; narration must identify simulator | Open external validation |
| 2026-10-12 | UI test fake DOM empty text expectation was incorrect | Corrected assertion; no product behavior change | Fixed |

Local browser rendering now verified via the simulated host; real Alexa remains unverified. Screenshot: c-preview.png. The localhost preview listener required sandbox escalation and was allowed; no cloud resource or third-party upload was created.

## Web chat increment

- 2026-10-12: A's durable session API and C's simple chat API were reconciled through documented compatibility aliases. A serves the existing card resources at /apps/* and the chat assets at /chat-assets/*.
- Network uncertainty: failed sends preserve a client message UUID, conversation and cat selection. Retries do not create a second user bubble; server-side tool journaling owns write deduplication.
- Mobile layout: replaced a fixed guessed sidebar height with a flex layout so the composer remains visible; kept an explicit accessible cat-selector label when its visual label is hidden.
- Long card scroll: position new replies at their beginning so priority signals remain visible above the embedded card.
- Reauthentication: retain pending/current conversation ID when bootstrap returns a new session, avoiding loss of the pending follow-up context.
- Browser proof used a scripted model with real authenticated HTTP MCP calls; live provider/voice behavior remains unverified.

- Credential correction: the initial local login entered an MCP bearer in the browser. User clarified that the MCP token must stay server-side; C replaced the token input with a distinct chat-password input and asked A to map the password session to a configured backend token. Historical token-login QA is not evidence for the new path.
- Safety ordering correction: previously the prompt box followed model prose. Structured warning cards now precede prose and questions, tested against a reply with no warnings.
