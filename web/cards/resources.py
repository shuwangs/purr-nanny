"""Self-contained MCP App resources; no network assets or browser-side storage."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESOURCES = {
    "get_today": "ui://cat-nanny/today.html",
    "get_vet_summary": "ui://cat-nanny/vet-summary.html",
}
MIME_TYPE = "text/html;profile=mcp-app"


def resource_html(uri: str) -> str:
    if uri not in RESOURCES.values():
        raise ValueError("Unknown UI resource")
    view = "today" if uri == RESOURCES["get_today"] else "vet-summary"
    title = "Today’s care" if view == "today" else "Veterinary summary"
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Purr Nanny</title>'
            f'<style>{(ROOT / "style.css").read_text()}</style></head><body data-view="{view}">'
            f'<main><header><p class="eyebrow">PURR NANNY / SHARED CARE</p><h1>{title}</h1></header>'
            '<div id="result" role="status" aria-live="polite"><p>Waiting for the server result…</p></div>'
            '<footer>Read-only · Health observations remain facts, not diagnoses.</footer></main>'
            f'<script>{(ROOT / "view.js").read_text()}</script></body></html>')
