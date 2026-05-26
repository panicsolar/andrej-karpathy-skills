#!/usr/bin/env python3
"""Realtime token-usage widget for Claude Code sessions.

Run it:  python widget.py
Open:    http://localhost:8765/

The script picks the most recently modified session transcript under
~/.claude/projects/ (Claude Code writes one JSONL per session there) and
serves a small HTML page that polls live token totals once per second.
"""
from __future__ import annotations

import http.server
import json
import socketserver
from pathlib import Path
from urllib.parse import urlparse

PROJECTS_DIR = Path.home() / ".claude" / "projects"
PORT = 8765


def find_latest_session() -> Path | None:
    if not PROJECTS_DIR.is_dir():
        return None
    jsonls = list(PROJECTS_DIR.rglob("*.jsonl"))
    if not jsonls:
        return None
    return max(jsonls, key=lambda p: p.stat().st_mtime)


def parse_usage(path: Path) -> dict:
    totals = {
        "input": 0,
        "output": 0,
        "cache_creation": 0,
        "cache_read": 0,
        "context_window": 0,
        "messages": 0,
        "model": "",
        "session": path.stem,
    }
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message") or {}
            usage = msg.get("usage")
            if not usage:
                continue
            inp = usage.get("input_tokens", 0) or 0
            out = usage.get("output_tokens", 0) or 0
            cc = usage.get("cache_creation_input_tokens", 0) or 0
            cr = usage.get("cache_read_input_tokens", 0) or 0
            totals["messages"] += 1
            totals["input"] += inp
            totals["output"] += out
            totals["cache_creation"] += cc
            totals["cache_read"] += cr
            totals["context_window"] = inp + cc + cr
            if msg.get("model"):
                totals["model"] = msg["model"]
    return totals


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Claude tokens</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { color-scheme: dark; }
  html, body { margin: 0; }
  body {
    font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #141414;
    color: #e6e6e6;
    padding: 18px 20px;
    min-width: 280px;
  }
  h1 {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #888;
    margin: 0 0 14px;
    font-weight: 600;
  }
  .row { display: flex; justify-content: space-between; padding: 5px 0; }
  .row .label { color: #888; }
  .row .value { font-variant-numeric: tabular-nums; }
  .big { font-size: 22px; font-weight: 600; letter-spacing: -0.01em; }
  .bar {
    height: 6px;
    background: #262626;
    border-radius: 3px;
    overflow: hidden;
    margin: 6px 0 14px;
  }
  .bar > div {
    height: 100%;
    width: 0;
    background: linear-gradient(90deg, #f59e0b, #ea580c);
    transition: width 0.4s ease;
  }
  .pct { color: #f59e0b; }
  .pct.warn { color: #ef4444; }
  .meta {
    color: #555;
    font-size: 11px;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid #262626;
    font-variant-numeric: tabular-nums;
  }
  .dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #22c55e;
    margin-right: 6px;
    vertical-align: middle;
  }
  .dot.stale { background: #6b7280; }
  .dot.err { background: #ef4444; }
</style>
</head>
<body>
  <h1>Claude Code &middot; live tokens</h1>
  <div class="row">
    <span class="label">Context window</span>
    <span class="value big pct" id="ctx-pct">&mdash;</span>
  </div>
  <div class="bar"><div id="ctx-bar"></div></div>
  <div class="row"><span class="label">Context tokens</span><span class="value" id="ctx-tokens">&mdash;</span></div>
  <div class="row"><span class="label">Output (cumulative)</span><span class="value" id="output">&mdash;</span></div>
  <div class="row"><span class="label">Input (cumulative)</span><span class="value" id="input">&mdash;</span></div>
  <div class="row"><span class="label">Cache read</span><span class="value" id="cache-read">&mdash;</span></div>
  <div class="row"><span class="label">Cache create</span><span class="value" id="cache-create">&mdash;</span></div>
  <div class="row"><span class="label">Messages</span><span class="value" id="messages">&mdash;</span></div>
  <div class="meta"><span class="dot" id="dot"></span><span id="meta">connecting&hellip;</span></div>

<script>
  const params = new URLSearchParams(location.search);
  const LIMIT = Math.max(1, parseInt(params.get('limit') || '200000', 10));
  const fmt = n => Number(n || 0).toLocaleString();
  let lastMtime = 0;

  async function tick() {
    const dot = document.getElementById('dot');
    const meta = document.getElementById('meta');
    try {
      const r = await fetch('/usage', { cache: 'no-store' });
      const d = await r.json();
      if (d.error) {
        dot.className = 'dot err';
        meta.textContent = d.error;
        return;
      }
      const ctx = d.context_window || 0;
      const pct = (ctx / LIMIT) * 100;
      const pctEl = document.getElementById('ctx-pct');
      pctEl.textContent = pct.toFixed(1) + '%';
      pctEl.classList.toggle('warn', pct >= 80);
      document.getElementById('ctx-bar').style.width = Math.min(100, pct) + '%';
      document.getElementById('ctx-tokens').textContent = fmt(ctx) + ' / ' + fmt(LIMIT);
      document.getElementById('output').textContent = fmt(d.output);
      document.getElementById('input').textContent = fmt(d.input);
      document.getElementById('cache-read').textContent = fmt(d.cache_read);
      document.getElementById('cache-create').textContent = fmt(d.cache_creation);
      document.getElementById('messages').textContent = fmt(d.messages);
      const fresh = d.mtime > lastMtime;
      lastMtime = d.mtime;
      dot.className = 'dot' + (fresh ? '' : ' stale');
      const sid = (d.session || '').slice(0, 8);
      meta.textContent = (d.model || 'unknown model') + ' · ' + sid;
    } catch (e) {
      dot.className = 'dot err';
      meta.textContent = 'disconnected';
    }
  }
  tick();
  setInterval(tick, 1000);
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/usage":
            session = find_latest_session()
            if session is None:
                payload = {"error": f"no session JSONL found under {PROJECTS_DIR}"}
            else:
                payload = parse_usage(session)
                payload["mtime"] = session.stat().st_mtime
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
            return
        self._send(404, b"not found", "text/plain")


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    print(f"token widget: http://localhost:{PORT}/")
    if not PROJECTS_DIR.is_dir():
        print(f"warning: {PROJECTS_DIR} does not exist yet")
    with ThreadingServer(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
