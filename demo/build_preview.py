"""Build a labelled, offline MCP Apps host from real local rules-backend results.
Run: .venv/bin/python -m demo.build_preview --output /tmp/cat-nanny-preview
"""
import argparse
import json
import tempfile
from pathlib import Path
from apps.resources import RESOURCES, resource_html
from demo.b_seed import seed
from storage import SQLiteRepository


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        results = seed(SQLiteRepository(Path(folder) / 'preview.db'))
    for tool, uri in RESOURCES.items():
        (output / uri.rsplit('/', 1)[-1]).write_text(resource_html(uri))
    (output / 'results.json').write_text(json.dumps(results, indent=2))
    host = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Purr Nanny local simulator</title><style>
body{font-family:system-ui;margin:0;background:#edf0e8;color:#24352c}header{padding:18px 24px;background:#213f32;color:white}h1{font-size:24px;margin:0}p{line-height:1.5}nav{display:flex;gap:12px;padding:16px 24px}button{font:inherit;padding:10px 16px;cursor:pointer;border:1px solid #869b87;border-radius:8px}button[aria-pressed=true]{background:#213f32;color:white}iframe{width:100%;height:1100px;border:0}#status{padding:0 24px}</style></head><body>
<header><h1>Purr Nanny · local simulator</h1><p>Simulated MCP Apps host · fixed sample data · not a live Alexa connection</p></header>
<nav aria-label="Choose view"><button data-tool="get_today" aria-pressed="true">Today</button><button data-tool="get_vet_summary" aria-pressed="false">Veterinary summary</button></nav><p id="status" role="status">Loading local backend results…</p><iframe title="Cat care result" sandbox="allow-scripts" src="today.html"></iframe>
<script>
const frame = document.querySelector('iframe'); let tool = 'get_today', ready = false, results;
function deliver(){ if(ready && results){frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-input',params:{arguments:{}}},'*');frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{structuredContent:results[tool]}},'*');document.getElementById('status').textContent='Showing actual local rules-backend output; reference time 2026-10-12 18:00 UTC.';}}
window.addEventListener('message',event=>{if(event.source!==frame.contentWindow || event.data?.jsonrpc!=='2.0')return;const msg=event.data;if(msg.method==='ui/initialize')frame.contentWindow.postMessage({jsonrpc:'2.0',id:msg.id,result:{protocolVersion:'2026-01-26',hostInfo:{name:'Local simulator',version:'0.1.0'},hostCapabilities:{},hostContext:{}}},'*');if(msg.method==='ui/notifications/initialized'){ready=true;deliver();}});
fetch('results.json').then(r=>{if(!r.ok)throw Error('Unable to load results');return r.json();}).then(data=>{results=data;deliver();}).catch(()=>document.getElementById('status').textContent='Unable to load results. Serve this folder with a local HTTP server.');
for(const button of document.querySelectorAll('button'))button.addEventListener('click',()=>{ready=false;tool=button.dataset.tool;for(const item of document.querySelectorAll('button'))item.setAttribute('aria-pressed',String(item===button));frame.src=tool==='get_today'?'today.html':'vet-summary.html';});
</script></body></html>'''
    (output / 'index.html').write_text(host)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='/tmp/cat-nanny-preview')
    print(build(parser.parse_args().output) / 'index.html')
