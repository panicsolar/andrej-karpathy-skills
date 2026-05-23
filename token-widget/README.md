# Realtime token widget

A tiny browser widget that shows token usage for your current Claude Code
session, updated once per second.

## Run it

```sh
python token-widget/widget.py
```

Open <http://localhost:8765/> in a browser. Resize/pop the window into a
small corner of your screen.

The script:

1. Looks under `~/.claude/projects/` for the most recently modified
   session JSONL (Claude Code writes one per session).
2. Tallies tokens from every assistant turn it finds.
3. Serves an HTML page that polls `/usage` every second.

## What it shows

- **Context window** — `input + cache_creation + cache_read` from the
  latest assistant turn, as a percentage of the limit. This is the
  "how full is the context right now" number.
- **Context tokens** — same in absolute numbers.
- **Output / Input (cumulative)** — summed across every assistant turn
  in the session.
- **Cache read / Cache create** — cumulative cache hits and writes.
- **Messages** — assistant turn count.

## Context-window limit

Defaults to 200,000 tokens. Override via query string for 1M-context
models:

<http://localhost:8765/?limit=1000000>

## Notes

- Zero dependencies — uses only the Python 3 standard library.
- Bound to `127.0.0.1` only.
- The transcript is the source of truth, so the widget reflects what
  Claude Code has already written to disk. There's typically a small lag
  (sub-second) between a turn finishing and the JSONL flushing.
