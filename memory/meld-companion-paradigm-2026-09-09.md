---
name: meld-companion-paradigm-2026-09-09
description: Three deferred keyword mechanics closed together (meld's merged-object subsystem, companion's deck-legality parser, paradigm's unbounded delayed trigger) - what each needed and one real near-miss caught before shipping
metadata:
  type: project
---

**2026-09-09.** Meld (CR 701.42/712), Companion (CR 702.139) and Paradigm
(CR 702.192) all landed in one wave, closing a gap the "Transforming a
permanent" wave and a keyword-actions wave had each separately deferred.

**Meld reuses transform's `up_face` idiom rather than growing a parallel
merged-object type.** `CardState.meld_result: Card | None`, read by `up_face`
before the land-face/`transformed` branches, gives a melded permanent the
combined back face's characteristics through the exact same properties
transform already feeds - `Card` mirrors every field `up_face` callers read,
so handing one back works with zero changes to `types`/`subtypes`/`power`/
`toughness`/`name`/`oracle_text`. One property still needed its own branch:
`keywords` fell through to `self.card.keywords` whenever `self.card.
card_faces` was empty, which is true for every meld card (they use
`all_parts`, not `card_faces`), so a melded permanent kept reporting its own
half's printed keywords ("Meld") instead of the combined face's ("Trample",
"Haste") until that branch was added explicitly - caught by a scenario test
asserting on the melded permanent's keyword set, not by inspection.

**The partner card is lifted off `Game.battlefield` entirely, into
`Game.melded_pairs: dict[UUID, CardState]`, rather than teaching every
battlefield-enumerating call site (combat, `legal_actions`, every
state-based action) that a melded pair is one permanent.** This is the
opposite choice from the "computed characteristics" wave's own 68-site sweep
for a narrower problem - here, zero existing call sites needed to change.
The trap this shape has: `Game.meld`'s own formation step exiles both cards
first (CR 712.4a's own instruction), and the partner's `exile_permanent`
call left it sitting in `Game.exile` even after it was also stored in
`melded_pairs` - a real bug (the partner appeared twice: once as itself in
exile, once again inside the melded pair) caught by
`test_a_melded_permanent_exiled_puts_both_cards_in_exile` failing with one
extra "Hanweir Garrison" in the list. Fixed with an explicit
`Game._take_out_of_every_zone(partner)` before storing it, mirroring the
"ids only, one true home" discipline `models/action.py` already documents
for `Action`/`Player.companion_id`.

**Companion's condition parser shipped a real near-miss, caught before this
landed rather than after.** The first draft of the mana-value-parity and
deck-size readers assumed plausible-sounding templates ("Each nonland card
in your starting deck has an even mana value.", "Your starting deck contains
at least 40 cards.") without checking them against a real printing first -
exactly the "training data is wrong" trap this repo's own CLAUDE.md warns
about for CR numbers, just for card text instead. `resolve_cards` on Gyruda,
Obosh, Yorion and Keruga found the real wording is structurally different
("Your starting deck contains only cards with even mana values.", "...at
least twenty cards more than the minimum deck size.") - a deck-wide "contains
only" shape, and a size threshold *relative to the format's own minimum*,
neither of which the assumed regexes matched at all. Rewritten before
shipping, with the corrected wording checked in the same session; the two
verified-first shapes (Kaheera, Lurrus - resolved from their actual fixture
JSON before any regex was written) needed no changes. Lesson: "card text is
the same [as CR numbers]: verify with resolve_cards, never from memory" -
CLAUDE.md already says this, and this is the wave that found the training
data actually was wrong.

**Paradigm's "first time this game" needed no counter at all.** The delayed
trigger it creates has `remaining=None` ("for the rest of the game"), so the
trigger's own presence in `Game.delayed_triggers.triggers` (matched by
`(controller, source_name)` on `ParadigmCopyAndCast`) already answers "has a
spell with this name resolved before" - a second resolution just finds the
existing trigger and creates no second one, which is what stops copies
handed out per turn from doubling. The one deliberate simplification: a
declined free copy is removed immediately rather than through a general
"a copy in a zone other than the stack ceases to exist" state-based action
(CR 704.5e/707.10a, still not built) - sound only because nothing gives
another player a priority window between the copy's creation and the
"cast it or not" choice, both inside the one delayed trigger's own
resolution.
