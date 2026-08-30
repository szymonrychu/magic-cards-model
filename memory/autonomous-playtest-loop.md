---
name: autonomous-playtest-loop
description: The self-driving playtest loop - two agents play, reports stop the game, an opus agent confirms the rule, a sonnet agent fixes it globally, repeat
metadata:
  type: project
---

Standing assignment (given 2026-08-29): run an autonomous loop that plays real
decks against each other through the API and drives every defect it finds to a
global engine fix. Target: three consecutive clean games per deck pair.

Deck pairs: urzatron vs blink, creatures toolbox vs boros energy, and eldrazi
ramp vs living end - now run as three CONCURRENT matchups per iteration rather
than one pair at a time. Decklists come from `statistics_decks` (real
tournament lists, never `statistics_archetypes` core_cards).

**The loop:**
1. Boot the server: `uv run python -m magic_cards_model_api.serve --deck
   alice=decks/X.txt --deck bob=decks/Y.txt --seed N --port 8000`, log to
   `/tmp/game-server.log`. Seat uids print in the boot block.
2. Dispatch two subagents (sonnet or haiku), one seat uid each, driving
   `seat_cli.py`. They play to win, competitively, not just legally.
3. A player who believes the engine is wrong calls `seat_cli report` - which
   lands in the audit log as action `report_problem` with a full snapshot. The
   report must carry what happened plus the ruling (looked up with
   spellslinger), and NO code suggestions.
4. `scripts/watch_reports.py` polls `/api/games/{id}/log` for `report_problem`
   and returns on the first one. On a report: stop the game, dispatch an OPUS
   agent (fable if genuinely hard) to re-check the rule against the CR, then a
   SONNET agent to write scenario tests and fix it. Review both with subagents.
5. A game that finishes clean still gets reviewed - a HAIKU agent summarizes the
   log and the issues it spots feed the same loop.

**Three matchups run CONCURRENTLY per iteration** (2026-08-30), not one. The
server holds several games at once - `store` already keys by `game_id`; it was
only `serve.py` that booted a single game. Arm one watcher per game and treat a
report from any of them as the stop signal for that game only; the others keep
playing. Three games per iteration means three times the defect surface per unit
of wall-clock, which is the point.

**Role assignment (fixed by the user):**
- playing: **haiku** (switched from sonnet 2026-08-30 - players are the most
  numerous and least demanding role, and there are now six of them at a time)
- implementation and review: sonnet
- game-log summary: haiku
- rule investigation and problem confirmation: opus, fable when very complicated

**Never idle while a game runs** (added 2026-08-30 by the user: "work on known
gaps while players are busy"). A game takes tens of minutes of agent wall-clock;
that window is for the known-gap backlog, not for watching. **Dispatch gap work
in worktrees** (`isolation: "worktree"`), one per agent - the owner's standing
instruction as of 2026-08-30. Two agents editing one tree is how a review agent
came to run `git checkout` over another agent's uncommitted work. The running
server is pinned to the code it booted with, so parallel edits never reach the
live game; merge and restart only between games.

Standing backlog, in order: the `REPLACEMENTS` registry conversion (last of the
three name-keyed registries), mana-spent/kicker tracking (5 abilities fail
closed), copy effects, then the alternative-cost keywords Cascade/Cycling/Evoke/
Rebound that Living End needs.

**Fixes must be global.** A fix targets the mechanic, not the card - it should
correct ~95% of cards sharing it. Per-card special-casing is only for cards
whose rules are genuinely unique. Prefer parsing behaviour out of oracle text
over name-keyed registries (see the two registries in CLAUDE.md).

Related: [[agent-playtest-launch]], [[never-recall-mtg-rules-from-memory]],
[[no-mocks-scenario-tests]], [[engine-fixes-in-engine-only]],
[[restart-api-server-after-fixes]], [[user-examples-become-testcases]].
