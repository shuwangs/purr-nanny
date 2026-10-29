# Purr Nanny

A local cat-care assistant: record care and health observations, answer follow-up questions, review today's activity, and prepare factual veterinary summaries.

The browser shows an Echo-style display on the left and chat on the right. Today and veterinary cards appear on the display. This is a visual simulation; no live Alexa connection has been verified. Health rules are provisional and have not been reviewed by a veterinarian.

## Run locally

Requires Python 3.11+. Node.js is also required for frontend tests.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './packages/cat-health-signals' -e '.[test]'
cp -n .env.example .env
```

Edit `.env`: uncomment `CAT_NANNY_CHAT_MODE=demo` for a fixed-phrase demo without model charges. Keep only one active chat-mode setting. The MCP token must match in `CAT_NANNY_TOKEN_MAP` and `CAT_NANNY_CHAT_MCP_TOKEN`. Use your own token and chat password; keep `.env` private.

Terminal 1 — care service:

```sh
.venv/bin/uvicorn server.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

Terminal 2 — web chat:

```sh
.venv/bin/uvicorn server.chat_app:create_app --factory --env-file .env --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001 and sign in with `CAT_NANNY_CHAT_PASSWORD`. The example password is `cat-nanny-local-chat-2026`. Select a cat and recorder before writing observations. If no cats exist, ask to add one. Demo mode understands a limited vocabulary; try `今天有哪些记录？`, `最近30天兽医摘要`, or `猫刚吐了`. It writes actual local records, so use a test cat for practice.

For natural-language AI, use one of the existing adapters:

- OpenAI: set `CAT_NANNY_CHAT_MODE=openai`, `OPENAI_API_KEY`, and `CAT_NANNY_OPENAI_MODEL` (default `gpt-4.1-mini`).
- Bedrock: omit the chat-mode setting and configure AWS credentials, region, and `CAT_NANNY_BEDROCK_MODEL_ID` for a tool-capable model.

Restart the chat service after configuration changes. Exported shell variables override `.env`. Keys stay on the server; model inference sends conversation context and tool results to the selected provider and can incur charges. Live provider access is not established by mocked tests.

## Code map

| Directory | Purpose |
| --- | --- |
| `apps/` | Chat UI, Echo display, and care-card renderer |
| `server/` | Chat agent, model adapters, authenticated MCP tools, conversations, optional SNS notifications |
| `storage/` | SQLite persistence, validation, attribution, and rules integration |
| `packages/cat-health-signals/` | Deterministic statistics, feeding summaries, and health signals |
| `tests/` | Domain, transport, agent, and frontend regression tests |
| `infra/` | MCP container and optional SNS policy example |

SQLite stores care data and conversations locally. A new conversation clears the visible chat, not saved care records. Public visitor isolation and a single-command full-app deployment are not implemented.

## Tests and references

```sh
.venv/bin/python -m pytest -q
```

See [architecture](docs/architecture.md), [tool contracts](docs/contracts.md), [chat API](docs/chat-api.md), [agent](docs/conversation-agent.md), [UI](docs/chat-ui.md), [rules](docs/rules.md), and [deployment](docs/deployment.md).
