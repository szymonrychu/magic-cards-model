---
name: nontoken-substring-guard-inverted-triggers
description: "nontoken" contains "token" as a substring, so a plain-substring token guard in condition_matches inverted every "nontoken X enters" trigger; word-boundary alone stops the false match but does not enforce the restriction
metadata:
  type: project
---

2026-09-08. `machines/triggers.condition_matches`'s ENTERS_THE_BATTLEFIELD
branch had `if "token" in lowered: ...` guarding a check that the entering
permanent *be* a token (written for Caretaker's Talent's "one or more tokens
you control enter"). `"nontoken"` contains `"token"` as a substring, so the
same guard matched Weapons Manufacturing's "a nontoken artifact you control
enters" and Miirym, Sentinel Wyrm's "another nontoken Dragon you control
enters" too - and since the guard *demands* a token, it was exactly inverted:
both cards fired only on the one class of permanent their own printed text
excludes, and never fired on the class they actually cover.

`scripts/sweep_pool.py` did not catch it: it never calls `condition_matches`,
only checks whether the event parsed and the effect returned non-`None`, so
Weapons Manufacturing scored two `handled` clauses while doing nothing at all
in a real game. A trigger whose event parses but whose condition can never
(or always-wrongly) match is invisible to that sweep - see the "sweeper's
blind spot" section of `docs/2026-09-08-trigger-findings.md` for the two
distinct escaping shapes.

Fix: check `"nontoken"` first (`\bnontoken\b`, enforcing NOT a token) before
falling back to a bare `\btoken\b` word-boundary check (enforcing IS a token).
A word-boundary test alone on `"token"` stops the false substring match but
does **not** enforce the nontoken restriction - Miirym would still loop on
her own token Dragons, since nothing then required the entering permanent to
NOT be one. The same restriction on `IS_SACRIFICED` (Ashling, the Limitless's
"you sacrifice a nontoken Elemental") had no substring collision to trip on,
because nothing in that branch read "nontoken" - or any token/nontoken
distinction - at all; it needed the check added fresh, not un-inverted.

A second, independent trap in the same defect chain: fixing the condition
alone ships a burn spell. Weapons Manufacturing's effect had no
`TRIGGER_EFFECTS` row and no token-with-quoted-ability parser, so
`trigger_effect_for` fell through to `parse_mixed_effect`, whose damage regex
(`_DAMAGE_TARGET_RE`, unanchored `.*` under `fullmatch`) read *inside* the
token's own quoted granted ability and matched "deals 2 damage to any
target" there - a working, wrong effect, not a `None` that would have made
the bug visible. `machines/targeting.py`'s `profile_for_text` had the
identical blind spot: scanning raw ability text for `"target"` mentions with
no quoted-span stripping counted the granted ability's own "target creature"
as the *outer* ability's targeting requirement too (caught live by
`tests/scenarios/test_parsed_layer_effects.py`'s Tower Above test, which had
baked the wrong two-target announcement in as expected behaviour). Any
regex or scanner that reads a card's raw oracle text for a keyword `_TARGET_
WORD`/`deals ... damage`/etc. has to treat a quoted span as opaque - it is
CR 111.3's stated text of a *different* object, not the printed ability's own
words - or it will misread a granted ability's text as its own.
