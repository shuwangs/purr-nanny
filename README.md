# Purr Nanny platform

A's first implementation: eight MCP tool schemas, authenticated Streamable HTTP transport, trusted household identity, durable local records, and an optional SNS notification adapter. B's rules/storage are integrated through the `Backend.execute` interface. No cloud resources have been created and no real Alexa+ connection has been verified.

## Run locally

For reusable local configuration, copy `.env.example` to `.env` and edit your own
values. `.env` is ignored by Git; share `.env.example`, not credentials or local
databases. Configure AWS credentials through an authorized AWS profile separately.
Each teammate has their own local database unless explicitly configured otherwise.

```sh
cp .env.example .env
.venv/bin/pip install -e './packages/cat-health-signals' -e '.[test]'
# Terminal 1: MCP backend
.venv/bin/uvicorn server.app:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
# Terminal 2: web chat
.venv/bin/uvicorn server.chat_app:create_app --factory --env-file .env --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/` and sign in using your configured chat password.
Natural-language responses require the AWS region, credentials and Bedrock model
configuration. Existing exported environment variables take precedence over `.env`;
use fresh terminals or unset conflicting variables when switching configurations.

Python 3.11+:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]' -e packages/cat-health-signals
export CAT_NANNY_TOKEN_MAP='{"replace-with-a-random-token-at-least-32-characters":{"household_id":"demo","timezone":"America/Chicago"}}'
.venv/bin/uvicorn server.app:create_app --factory --host 127.0.0.1 --port 8000
```

Connect an MCP client to `http://127.0.0.1:8000/mcp/` with `Authorization: Bearer <configured token>`. Clients must accept `application/json, text/event-stream`. The SDK provides initialization, tool discovery, and structured tool results. Bearer mapping is for local development; it does not implement OAuth account linking.

```sh
.venv/bin/python -m pytest -q
```

See [contracts](docs/contracts.md), [deployment notes](docs/deployment.md), and [access validation](docs/access-validation.md). Medical rules have not been professionally reviewed. The reference fixture reports analysis unavailable; the rules backend exposes explicit provisional-rule limitations.

See [local UI preview](docs/ui-preview.md) for both read-only views, [five-story acceptance](docs/acceptance.md), [architecture](docs/architecture.md), and [delivery checklist](docs/delivery-checklist.md). The preview exercises the resource bridge and structured backend results; live Alexa and remote deployment remain unverified. Node.js is required for UI renderer tests.

For an interactive client using actual MCP HTTP calls, start the server above, set `CAT_NANNY_CLIENT_TOKEN` to one configured token, and run `.venv/bin/python -m demo.live_client`. See [live client and QA fixes](docs/qa-fixes.md) for examples, recovery steps, evidence and remaining release gaps.

## Natural-language chat agent

### OpenAI without AWS

In your private `.env`, set:

```dotenv
CAT_NANNY_CHAT_MODE=openai
OPENAI_API_KEY=your-private-api-key
CAT_NANNY_OPENAI_MODEL=gpt-4.1-mini
```

Replace the existing demo mode line rather than adding duplicate settings.
Restart the chat service with `--env-file .env` on port 8001; keep MCP on 8000.
Start a new conversation and select a cat. The page shows `OpenAI` as its mode.
The server calls the Responses API and executes requested functions through the
existing authenticated MCP gateway. API keys remain server-side. Cat data stays
in SQLite, but conversation context and tool results are sent to OpenAI for
inference. `store=false` disables application-state storage of Responses; this
does not promise zero provider retention. API billing is separate from ChatGPT
subscriptions. No AWS account is required for this mode.

Adapter tests use mocked HTTP and cover tool-call/result conversion, encrypted
reasoning preservation and provider errors. Live inference requires your own
valid API key and available API credit; it has not been verified by those tests.

### Local demo without AWS

Set `CAT_NANNY_CHAT_MODE=demo` in `.env`, then restart the chat service using
`--env-file .env`. The page labels this as a fixed-rule demo, not an AI model.
Select a cat and try `今天有哪些记录？`, `最近30天兽医摘要`, or `猫刚吐了`.
Answer follow-ups with explicit phrases such as `没血`, `精神正常`, `饭后`.
This adapter supports a small vocabulary and calls the real MCP backend;
observations are persisted as user records in the local database. Use a separate
demo database or cat for practice. It does not call AWS or send model requests.
Remove the setting to return to the configured Bedrock adapter. Other care-write
intents and arbitrary natural-language interpretation are not implemented by this
demo planner.

A's chat service calls the existing MCP endpoint through the official MCP client, with durable per-household conversations and message/tool journals. C's web interface is served by the chat service. Keep the MCP server running on port 8000; in another terminal with the same CAT_NANNY_TOKEN_MAP:

```sh
export CAT_NANNY_MCP_URL='http://127.0.0.1:8000/mcp/'
export CAT_NANNY_CHAT_DB='cat_nanny_chat.sqlite3'
export CAT_NANNY_CHAT_MCP_TOKEN='ONE_SERVER_TOKEN_FROM_CAT_NANNY_TOKEN_MAP'
export CAT_NANNY_CHAT_PASSWORD='A_SEPARATE_PRIVATE_CHAT_LOGIN_PASSWORD'
export CAT_NANNY_CHAT_RECORDERS='["Shu","Alex","Yuan"]'
export AWS_DEFAULT_REGION='YOUR_AUTHORIZED_AWS_REGION'
export CAT_NANNY_BEDROCK_MODEL_ID='YOUR_TOOL_CAPABLE_MODEL_OR_INFERENCE_PROFILE_ID'
.venv/bin/uvicorn server.chat_app:create_app --factory --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`. Sign in with the separate chat password; the server sets an HttpOnly local cookie and keeps the MCP bearer out of chat/model payloads. Configure AWS access through the normal boto3 credential chain. No model credentials belong in the HTML or browser storage. Without a model ID the UI/API explains that model access is not configured; it does not simulate a real model response.

[Chat API and recovery contract](docs/chat-api.md) describes the browser aliases, canonical session endpoints and retry behavior. [Model/agent notes](docs/conversation-agent.md) cover configuration and verification limits. Development cookie login and SQLite state remain local-only; production OAuth, shared durable sessions and live provider/AWS validation are still open.


Select **Current recorder** before adding or supplementing observations. The configured household names default to Shu, Alex and Yuan (`CAT_NANNY_CHAT_RECORDERS`). This selection identifies the person entering the record; it is independent of **Care performed by**, which requires an explicit statement such as “Alex fed 40 g of wet food.” Queries show the entire household regardless of the current recorder. Local name selection is self-declared attribution, not individual account authentication.
