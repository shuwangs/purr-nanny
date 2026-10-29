# Chat and Echo display

`web/chat/chat.html`, `chat.css`, and `chat.js` provide the browser UI served by `server.chat_app`.

Desktop: an Echo-style screen and household selectors occupy the left panel; conversation, safety guidance, follow-up prompts, and composer occupy the right. On narrow screens the display stacks above chat.

Today and veterinary tool results load into a sandboxed frame on the Echo screen. Only the latest card is shown. Frame messages require a matching source window and initialization handshake; switching views clears old frame registrations and timers. Card failure leaves the chat reply available. New conversation and cat changes clear the display and visible messages, while saved care data remains intact.

Login uses the separate chat password. MCP and model credentials stay on the server. Retries reuse the request ID to avoid duplicate writes. Health warnings appear before ordinary reply text and follow-up prompts. Recorder selection is self-declared attribution, not individual authentication.

Run both services as described in README. `tests/chat_ui.cjs` checks login, retries, safety ordering, display-card routing, handshake, and reset. `tests/ui_renderer.cjs` checks the card renderer. These checks use mocked browser objects and do not establish visual correctness or live model access.
