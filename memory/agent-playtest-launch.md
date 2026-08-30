---
name: agent-playtest-launch
description: How to launch the two AI players against each other - Agent-tool subagents driving seat_cli, model, prompts, and vetting their reports
metadata:
  type: project
---

The dogfood playtest (magic-cards-model-api) runs two AI players against each
other on a game server booted with `uv run python -m magic_cards_model_api.serve
--deck alice=decks/X.txt --deck bob=decks/Y.txt --seed N`.

**Why:** the user switched from haiku to sonnet (2026-08-28) and from separate
`claude` CLI processes to Agent-tool subagents ("run subagents through tool,
not through command"). **Players drive the `mtg` MCP tools directly** (2026-08-30). The mtg server is a
session-level entry in the project `.mcp.json`, not per-player, and every tool
takes `player_uid` as its first argument - so subagents inherit it from this
session and each one is confined to its own seat by the uid in its prompt.
Tools: `my_state`, `wait_for_priority`, `cast`, `play_land`, `activate`,
`declare_attackers`, `declare_blockers`, `pass_priority`, `advance`,
`resolve_top`, `set_step`, `decide`, `game_log`, `report_problem`. They block
until the seat has something to do, so one tool call is one whole turn of
waiting - agents do not poll.

`src/magic_cards_model_api/seat_cli.py` remains as the Bash-shaped fallback for
the same seat API (`state`, `wait`, `cast`, `play-land`, `activate`,
`attackers`, `blockers`, `pass`, `advance`, `resolve`, `log`, `report`). Use it
only when the MCP server is disconnected; prefer MCP.

**The trap that kept agents off MCP for eleven games was mine, not the tool's:**
after the original blockers were fixed I kept copying the previous game's
seat_cli prompt. Re-read this memory when writing a player prompt.

**How to apply:**
- Each player is dispatched with a SECRET SEAT UID (minted at game creation,
  printed by `serve` in the boot block: "seat uids"). Every mtg MCP tool and
  every `seat_cli` invocation takes the uid first; an unknown uid can neither
  act nor see anything, and uids never appear in state views. Read the uids
  off the server console (/tmp/game-server.log) and put one in each agent's
  prompt - never both.
- Launch two general-purpose subagents (model sonnet), one per seat, in one
  message. The prompt must give the uid, the exact command template, the
  command vocabulary, the turn protocol (double-pass rolls the game on by
  itself; advance only for untap/cleanup), the no-curl rule (the seat hides
  the opponent's hand - direct API calls would leak it), and "ONE session,
  play the whole game now, no deferring".
- Subagents have spellslinger (knowledge_search, resolve_cards, card_search) -
  instruct them to look rules and card text up before claiming a problem.
- Reports land in three places: the game log (`report` command, POST
  /api/games/{id}/report, carries a full snapshot), players/<p>/problems.md,
  and players/<p>/game-summary.md at the end.
- Kill and relaunch freely mid-game: the game lives on the server; fresh
  subagents resume from state. Restarting the server starts a FRESH game
  (in-memory store).
- Vet every reported problem against the CR before calling it real: the first
  eight reports contained zero real engine defects - all were the agent not
  knowing card text or corner rules (CR 103.8a first-draw skip, CR 508.8
  empty-combat skip, lands that enter tapped). Related:
  [[never-recall-mtg-rules-from-memory]], [[subagents-on-cheaper-model]].

## Haiku players quit early (2026-08-30)

The owner switched players from sonnet to haiku. The first haiku player stopped
mid-game at turn 2 and wrote a summary instead of playing, inventing a reason
("the format limits text" - there is no such limit). It also burned its first
turn using `advance` to walk through its own main phase.

So a haiku player prompt needs two things a sonnet prompt did not:

1. **An explicit stop condition and an explicit ban on stopping otherwise** -
   play until `state` shows a `winner`, or until a report is filed. Say plainly
   that stopping because the game "is proceeding well" or because it feels long
   is not allowed, and that a partially played game is worthless.
2. **`advance` is ONLY for untap and cleanup**, stated as a rule rather than a
   convention - haiku reaches for it to move through its own main phase.

Relaunching mid-game is free: the game lives on the server, and a fresh agent
reads the board with `state` and carries on. Prefer that over restarting a game.

Also: with several games on one server, **`--game` is required on every command**.
`seatkit` defaults to `games[0]`, so seats in the second and third games are
rejected with "that uid is no seat in this game" unless pinned. Resolving the
game from the uid instead is queued work.
