# Chat and Echo display

`web/chat/chat.html`, `chat.css`, and `chat.js` provide the browser UI served by `server.chat_app`.

Desktop: an Echo-style screen and household selectors occupy the left panel; conversation, safety guidance, follow-up prompts, and composer occupy the right. On narrow screens the display stacks above chat.

Today and veterinary tool results load into a sandboxed frame on the Echo screen. Only the latest card is shown. Frame messages require a matching source window and initialization handshake; switching views clears old frame registrations and timers. Card failure leaves the chat reply available. New conversation and cat changes clear the display and visible messages, while saved care data remains intact.

Login uses the separate chat password. MCP and model credentials stay on the server. Retries reuse the request ID to avoid duplicate writes. Health warnings appear before ordinary reply text and follow-up prompts. Recorder selection is self-declared attribution, not individual authentication.

Run both services as described in README. `tests/chat_ui.cjs` checks login, retries, safety ordering, display-card routing, handshake, and reset. `tests/ui_renderer.cjs` checks the card renderer. These checks use mocked browser objects and do not establish visual correctness or live model access.

## Voice input and synchronized display

The composer offers English (US) and Mandarin speech recognition through the browser's `SpeechRecognition` / `webkitSpeechRecognition` API. It requires browser support, microphone permission, and a secure context (HTTPS or localhost). Browser speech recognition may use an external browser-provider service and need internet access; this is not Alexa integration or guaranteed offline recognition. Unsupported browsers retain text input. No additional model API is called for transcription by this application.

Click Start voice input, speak, then stop. Interim words appear on the left screen, while only finalized words enter the draft. Existing typed text is preserved. Review/edit the transcript and press Send to submit; recognition never submits automatically. Select the language that matches your speech. Model/demo language-understanding limits still apply after transcription.

The left screen mirrors the current submitted message, request status, latest assistant reply, prioritized health warnings, and follow-up prompt. The latest successful Today/vet card appears below the reply. Every new reply clears stale cards, including replies without a card; retries and failures show the same status on both sides. Changing cats or starting a conversation clears both views.

Recognition requests up to five alternative transcripts. When supplied by the browser, alternatives can be selected explicitly without sending. Experimental contextual pet-name hints are not sent: a browser can expose that API while its speech service rejects it, preventing dictation entirely. Service failures show a specific error and preserve the draft. For English feeding phrases, a conservative suggestion can correct a close pet-name spelling and an “are fed” / “eye fed” opening. Suggestions preserve the rest of the transcript, require user selection, and never write records. Editing a draft updates the left display and clears stale suggestions. No speech model was retrained or added; pronunciation tolerance remains limited by the browser provider.
