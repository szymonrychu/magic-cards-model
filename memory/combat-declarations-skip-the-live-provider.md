---
name: combat-declarations-skip-the-live-provider
description: ask_attackers/ask_blockers deliberately never consult DecisionScript.provider - wiring one up stalls every live game's combat for a full decision timeout
metadata:
  type: project
---

Found and fixed 2026-09-07, during T5 review. A first pass at
`machines/decisions.py::_ask_declaration` made `ask_attackers`/`ask_blockers`
consult `script.provider` the same way every other asker here does. That looks
like closing a real gap (a live seat previously had no way to answer either
combat declaration through this module at all), but it is a regression against
the running service: the api's `MailboxProvider.decide`
(`magic_cards_model_api.decisions`) publishes the question and *blocks the
calling thread* for up to `timeout_seconds` regardless of kind, while the api's
own `ANSWERABLE_KINDS` deliberately excludes `DECLARE_ATTACKERS`/
`DECLARE_BLOCKERS` - a live seat has no transport to answer either kind through
`POST /decide`. The api drives combat through `Game.advance()`, which calls
exactly this code. Net effect if the provider is consulted: every live game's
combat stalls for the full timeout at declare-attackers, and again per
defending player at declare-blockers, publishing an unanswerable
`pending_decision` and writing a decision-timeout audit record each time.

`_ask_declaration` now consults scripted answers, then the replay tape, then a
pause (`pause_when_unanswered`), then `default_answer` - the same order every
other asker uses, **minus the provider step**. Wiring a live seat to these two
declarations is paired work with widening the api's `ANSWERABLE_KINDS` and
giving the mailbox a real combat transport; it belongs to the phase that does
that, not to this module alone. Before touching `_ask_declaration` again, read
its own docstring and `magic_cards_model_api.decisions.ANSWERABLE_KINDS`'s.
