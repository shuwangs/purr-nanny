# Local view preview

Run from the project root after installing README dependencies. Node.js is required for the renderer assertions.

```sh
.venv/bin/python -m pytest -q tests/test_ui_resources.py tests/test_c_acceptance.py
.venv/bin/python -m demo.build_preview --output /tmp/cat-nanny-preview
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory /tmp/cat-nanny-preview
```

Open http://127.0.0.1:8765/ and switch between Today and Veterinary summary. The generator uses B's real local repository, rules backend and seed function in a disposable database. The browser host simulates initialization and passes the generated structured results to the same resource used by MCP. It does not connect to Alexa or send notifications, and is a resource-rendering preview rather than a full agent simulator or end-to-end MCP client.

Observed 2026-10-12: both views initialize in the Codex in-app browser; Today displays Miso, source banner, feeding/vomiting records and unknown reporter; Veterinary summary displays four pattern cards with denominators/evidence and the identical event IDs. The full service and renderer tests verify additional cases. Actual Alexa rendering and smaller-screen device testing remain pending.
