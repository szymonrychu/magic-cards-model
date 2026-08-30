---
name: restart-api-server-after-fixes
description: The uvicorn server caches code at boot - remind the user to restart after every fix wave
metadata:
  type: project
---

The API server (uvicorn in magic-cards-model-api) imports the engine and the
API code at boot; edits on disk do not reach a running process. Twice the user
tested against a server still running pre-fix code and reported bugs that were
already fixed (the mana-pool write-back, the auto-tap-all-lands behavior) -
each time cost a debugging round.

**Why:** the user runs their own `mise run` server in a terminal and keeps it
running across fix waves. `pkill -f uvicorn` also does not reliably match the
process (`uv run uvicorn ...` shows as `python3.1`); kill by port instead - but
**it must be `lsof -ti :8000 -sTCP:LISTEN | xargs kill`**.

**Without `-sTCP:LISTEN` the kill takes the MCP server down with the API.**
`lsof -ti :8000` matches every process holding a socket on that port, which
includes CLIENTS with an established connection - and the `mtg` MCP server holds
exactly such a connection. On 2026-08-30 the MCP server (which had just been
reconnected) died the instant the API was restarted for a new game; nothing in
`mcp.py` calls `sys.exit`, and the process was simply killed by the restart
command itself. This is the long-standing "MCP stays gone after a restart"
symptom, and the cause was the restart command, not the server.

**The same trap applies to the `mtg` MCP server, and is worse.** It is spawned
once when the Claude Code session starts and caches `magic_cards_model_api.mcp`
at that moment - so every later edit to `mcp.py`, `seat_cli.py`, `visibility.py`
or the schemas is invisible to it for the rest of the session. On 2026-08-29 a
`my_state` call through the MCP tool errored against a live game while the
identical call through `seat_cli` worked, because `mcp.py` had been rewritten
twice since boot (uid threading, then the `decide` tool). Unlike uvicorn there is
no port to kill: the fix is reconnecting the MCP server (or restarting the
session), which only the user can do. Subagents inherit the session's MCP
servers, so a stale server is stale for every agent dispatched.

**How to apply:** after any wave of engine or API fixes lands, tell the user to
restart (`lsof -ti :8000 | xargs kill; cd ~/Documents/magic-cards-model-api &&
mise run`) and hard-refresh the page. When reproducing a user-reported bug
live, first confirm the serving process started after the last code change -
check `lsof -nP -iTCP:8000 -sTCP:LISTEN` against the file mtimes - before
believing the report.
