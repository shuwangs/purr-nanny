# Phase 0 access findings — 2026-10-12

Official sources checked:

- [Hackathon rules](https://amazonappdev2026.devpost.com/rules): deadline October 23, 2026 12:00 PDT = 14:00 America/Chicago. Alexa+ track accepts self-hosted MCP with at least spec 2025-11-25 over Streamable HTTP, or a simulated Alexa+ experience. Repository must execute required technology at runtime. Video should be under three minutes, publicly visible on YouTube/Vimeo. Full eligibility and submission requirements still need C's review.
- [Official FAQ](https://amazonappdev2026.devpost.com/details/faqs): gated Alexa+ SDK, toolkit, CLI and simulator are preview partner-only; hackathon participants cannot apply for access. It expressly allows a self-hosted MCP server demonstrated in our own frontend. Direct Alexa tests require pre-existing partner access; that access has not been established here.
- [Alexa+ quickstart](https://www.developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html): remote URL, Streamable HTTP, OAuth 2.1 authorization code + S256 PKCE, resource parameter, protected-resource and authorization-server metadata. No WWW-Authenticate header on 401. Requires sub-500ms query round trip. None of remote OAuth, latency, rendering, or Alexa voice behavior is verified by local tests.
- [Authentication](https://www.developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-authentication.html): service client-credentials and user linking are distinct tiers. An M2M token must never be mapped to a user's household automatically.
- [Official SDK v1 branch](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x): supported maintenance line; bounded <2 to retain the 2025-era transport used by Amazon's guide. Installed and tested mcp 1.30.0.

G0 remains open: local MCP recording works; no remote hosting, partner-account call, ten voice-expression tests, or target UI rendering has been verified. The permitted frontend fallback is confirmed, but its implementation belongs to C. Do not describe local bearer mapping as account linking or a passing G0.
