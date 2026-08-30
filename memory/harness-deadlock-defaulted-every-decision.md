---
name: harness-deadlock-defaulted-every-decision
description: A lock deadlock in the playtest harness silently defaulted ~18 decisions per game, so past "the engine did nothing" reports are suspect and must be re-checked
metadata:
  type: project
---

Found 2026-08-30, game 15. The playtest harness held `store.locked(game_id)`
across a blocking decision wait, so a seat that had been handed a pending
decision **could not answer it**.

The path: a `pass-priority` request resolves a spell inside one locked HTTP
request, raises a decision for the *other* player, and parks in
`GameDecisionProvider.decide` for 60s still holding the lock. The other player
wakes correctly within ~0.2s (`compute_wake_reason` is fine), but `run_action`
then calls `available_actions`, which `dry_run`-POSTs a cast for every card in
hand, and `action_cast` takes the same lock. The tool call cannot return until
the decision times out; the player answers instantly and is told "no pending
decision for you". `POST /decide` recorded nothing to the audit log, so the log
looked like a player who never answered.

**Scale: 18 timeouts in ONE game** - `choose_cards` 9, `choose_targets` 6,
`pay_life` 2, `may` 1, across both players. A fetchland's "may find Urza's Power
Plant while searching your library" defaulted to *no*; shockland "pay 2 life"
prompts defaulted. Essentially every meaningful decision in every playtest so far
was answered by the timeout, not the player.

**Therefore: re-check past reports before trusting them.** Any earlier finding of
the shape "the ability resolved and did nothing" may have been this deadlock
rather than an engine defect - and conversely, some real defects were masked by
boards that never reached the interesting state. The Solitude and Karn defects
were confirmed independently from `changed: false` log lines and stand; findings
that rest only on an agent's narration do not.

**Two lessons that generalise:**

1. **A wrong CR citation in a log line manufactured a false bug report.** The
   timeout logger hardcoded `CR 608.2d` for every decision kind. 608.2d
   explicitly excludes choices "already made as part of ... putting the spell or
   ability on the stack", so it is exactly the wrong rule for a trigger's
   targets (that is CR 603.3d / 601.2c, which the engine cites correctly). A
   player read the log, concluded the engine chose targets at the wrong time,
   and reported it. The engine was right; the log lied. The project's
   look-every-number-up rule applies to log lines and prose, not only to code.

2. **A docstring asserting an invariant is not evidence.** `seatkit.py` carried a
   comment headed "Why this cannot deadlock" that proved the poll loop takes no
   lock - and the very next statement after the loop took it. Read the code
   after the block the comment is defending.

**Log fidelity, fixed alongside:** dry-run probes were audited identically to
real plays - 956 of 2410 entries in one game were probe refusals ("not an
instant and has no flash"). When reading a game log, discount these.

Related: [[verify-agent-findings-against-the-engine]],
[[silent-default-dispatch-tables]], [[autonomous-playtest-loop]].
