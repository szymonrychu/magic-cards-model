# Project memory

Standing conventions and corrections, recorded as they came up. One memory
per file in `memory/`, indexed here. New memories go in this directory and
this index - not into any per-user directory - so the project stays the single
home of its own memory.

- [No mocks, scenario tests only](memory/no-mocks-scenario-tests.md) — every test uses real Scryfall cards through the Scenario harness; mocks are banned
- [Never recall MTG rules from memory](memory/never-recall-mtg-rules-from-memory.md) — every rule and CR number must be verified with knowledge_search; training data is wrong
- [magic-cards-model is a rules engine](memory/magic-cards-model-engine-goal.md) — the target is playable PvP MTG, not a card database
- [Subagents on the cheaper model](memory/subagents-on-cheaper-model.md) — pass model: "sonnet" on every Agent dispatch unless told otherwise
- [Engine fixes land in the engine](memory/engine-fixes-in-engine-only.md) — no API/frontend workarounds for rules gaps; only the most correct engine implementation
- [User examples become test cases](memory/user-examples-become-testcases.md) — every play-testing example the user reports is converted to a scenario test
- [Restart the API server after fixes](memory/restart-api-server-after-fixes.md) — uvicorn caches code at boot; kill by port (lsof -ti :8000), and verify the serving process predates no fix
- [Silent-default dispatch tables](memory/silent-default-dispatch-tables.md) — every defect class the loop has found is a lookup that defaults instead of refusing; fail closed and shout on a miss
- [Effect registry is the dominant gap](memory/effect-registry-is-the-dominant-gap.md) — most cards resolve and do nothing; the measured survey, per-deck dead-card counts, and the ranked order of work
- [Verify agent findings against the engine](memory/verify-agent-findings-against-the-engine.md) — adjudicators and reviewers each produce confident wrong claims; reproduce before acting
- [Harness deadlock defaulted every decision](memory/harness-deadlock-defaulted-every-decision.md) — 18 decisions per game timed out unanswered; re-check past "engine did nothing" reports
- [Autonomous playtest loop](memory/autonomous-playtest-loop.md) — play, report, confirm with opus, fix globally with sonnet, repeat until three clean games per deck pair
- [No commits: git checkout destroys work](memory/no-commits-git-checkout-destroys-work.md) — this repo has zero commits, so git restore/checkout/stash overwrite with an ancient index blob; recover from ~/.claude/file-history
- [Agent playtest launch](memory/agent-playtest-launch.md) — two AI players as Agent-tool subagents driving seat_cli.py: sonnet, one-session prompts, no curl (seat hides the opponent's hand), vet their reports against the CR
- [Combat declarations skip the live provider](memory/combat-declarations-skip-the-live-provider.md) — ask_attackers/ask_blockers must never consult DecisionScript.provider until the api's ANSWERABLE_KINDS and mailbox transport grow to match, or every live game's combat stalls for a full decision timeout
