# A deployment handoff

The local app runs with uvicorn. Default mode is local and binding in README is loopback. Any CAT_NANNY_MODE other than local fails closed. Static development bearer mapping must be replaced by validated OAuth access tokens before real Alexa account linking. Validate issuer, audience/resource, expiry and scopes; map authenticated user subject to household server-side, separately from M2M discovery credentials. Publish PRM and OAuth metadata using the chosen authorization provider; no fake metadata is supplied here.

Environment:

| Name | Meaning |
| --- | --- |
| CAT_NANNY_MODE | local only until production verifier/backend are configured |
| CAT_NANNY_TOKEN_MAP | secret JSON mapping development bearer tokens to household_id/timezone |
| CAT_NANNY_DB | persistent local SQLite path; default cat_nanny.sqlite3 |
| CAT_NANNY_ALLOWED_HOSTS | JSON host allowlist, including optional port patterns |
| CAT_NANNY_ALLOWED_ORIGINS | JSON origin allowlist; absence of Origin supports server clients |
| CAT_NANNY_SNS_TOPICS | optional JSON household→SNS topic ARN; absent disables sends |
| AWS_DEFAULT_REGION | boto3 region for optional SNS |

infra/Dockerfile packages the local development app, with a /data volume for persistent state. Do not use ephemeral container disk for event/idempotency/notification records. Do not run multiple replicas with the local SQLite ledger. A cloud instance needs B's DynamoDB repository plus shared durable notification deduplication and a production token verifier. Secrets belong in managed secrets storage, not Docker build args or source control. TLS/reverse-proxy host allowlists must use the actual endpoint name.

Choose AWS hosting only after checking the protocol in that environment. A long-running ASGI container is the current reference; no unverified Lambda adapter is included. AgentCore remains a candidate, not a demonstrated deployment. Required live checks: initialize/tools/list/log/follow-up/read over remote HTTP, OAuth flows, cross-household denial, query latency, SNS sandbox recipient permission/opt-in and failure handling, persistence after restart. No deployment, SMS charges, subscriptions or public endpoint have been created.

SNS adapter calls boto3.publish against configured topics, with SDK retry count limited to one. Permission example is infra/sns-policy.example.json. Replace its placeholders and restrict to existing authorized topics. Returned MessageId indicates acceptance only. Adapter tests use a fake client; actual AWS connectivity and SMS delivery are unverified.
