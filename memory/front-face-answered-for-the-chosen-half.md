---
name: front-face-answered-for-the-chosen-half
description: Card.types and Card.oracle_text read the FRONT face - never use either to decide anything about the half actually being cast (CR 709.3a, CR 715.3a)
metadata:
  type: project
  date: 2026-09-12
---

**`Card.types`, `Card.oracle_text` and `targeting_profile(card)` all answer
about the printing's FRONT face, and none of them answers CR 709.3a's
question.** `Card.types` goes through `Card.front_type_line`, which splits
`type_line` on `//` and keeps the left half; `targeting_profile(card)` reads
`Card.front_oracle_text` the same way. CR 709.3a and CR 715.3a both say only
the *chosen* half is evaluated to see if a cast is legal, and CR 709.3b/715.3b
say only that half's characteristics exist once it is on the stack. CR 601.3e is the general rule both are instances of: "These alternative characteristics replace the object's characteristics for this determination."

Two defects found by probing the seat API, 2026-09-12, both established by
running the engine rather than reading it:

1. **The engine read the front face's type line to decide whether a half could
   be cast.** `why_cannot_cast_now` asked `spell.card.types`, so a split card's
   timing was decided by whichever half happened to be printed on the left.
   Measured both ways round: **Replicate**, the Sorcery half of Repudiate //
   Replicate (`Instant // Sorcery`), was announced during an **upkeep step** at
   `{1}{G}{U}` and went onto the stack - a sorcery-speed spell cast at instant
   speed, the engine playing a different game. And **Incongruity**, the Instant
   half of Incubation // Incongruity (`Sorcery // Instant`), was **refused**
   during one. The same read made Stomp, an `Instant - Adventure` printed on a
   Creature card, sorcery-speed.
2. **`Action.target_slots` and `Game.legal_targets` reported the front half's
   targeting phrase on both rows.** `Game._announcement_profile` took no face,
   so the Tear row of Wear // Tear advertised Wear's "target artifact" and the
   Incongruity row of Incubation // Incongruity advertised no target at all for
   a spell CR 601.2c refuses without one. An agent reading either row is told
   to find the wrong object.

**The ordering trap, and why the fix is shaped the way it is.** CR 709.3 and
CR 715.3 both put the choice of half *before* the card goes onto the stack, but
this engine's `Casting` drives CR 601.2 a step at a time and CR 601.2a's move
happens in `model_post_init` - so by the time a caller reaches
`cast_as_split_half`/`cast_as_adventure`, CR 307.1's "when the stack is empty"
is already false **because of this very spell**, and re-asking the timing
question there answers it wrongly for every half. A naive recheck in those
methods refused a main-phase Sorcery half. So the question is asked once, at
the proposal, for every option `castable_faces` offers, and frozen onto
`Casting.face_cast_refusals` for whichever face the caller names later. The
proposal is refused only when *every* option is refused, or a `Sorcery //
Instant` card's legal half becomes unreachable; and `cast` spends the no-face
answer at CR 601.2i, or a caller that names no half at all smuggles the front
one through.

**How to apply:**
- Never decide anything about a cast from `card.types`, `card.oracle_text` or
  `targeting_profile(card)`. Ask `types_being_cast(card, face)` /
  `face_being_cast(card, face)`, or read `CardState.types`/`.oracle_text`,
  which go through `up_face`.
- Any new question asked during announcement must be asked **per face** if it
  is asked of a card that has faces - and asked *before* CR 601.2a's move if
  its answer depends on the stack.
- Two CR rules with the same words (709.3a and 715.3a, 709.3b and 715.3b) must
  share one implementation. Scoping a fix to `Layout.SPLIT` left CR 715's
  identical rule silently unimplemented: an Adventure was announced
  against its whole printing's profile, so a targetless Stomp resolved dealing
  nothing. Make the chosen face the discriminator, not the layout.

**The third instance, found by taking the same probe one step further
(2026-09-12).** `why_cannot_cast_restriction` read `spell.card.types` too, for
CR 611.1's noncreature prohibitions, so the creature front face answered for
the Adventure half there as well: **Stomp was cast freely under Ranger-Captain
of Eos's "Your opponents can't cast noncreature spells this turn"**, and again
out of a graveyard under **Soulless Jailer's "Players can't cast noncreature
spells from graveyards or exile"**. Both measured by running the engine. This
is what made it a family rather than a pair, and it is why the answer is frozen
on one dict (`Casting.face_cast_refusals`) under CR 601.3's umbrella rather
than a per-question field: the *next* per-face question gets the mechanism for
free, and a caller cannot spend one answer and forget the other.

The zone prohibition also gave the second half of the ordering argument. CR
601.2a's move makes `spell.zone` the **stack**, so a zone prohibition asked
after the move is asked about the wrong zone - the same reason the timing
question cannot be asked there, arriving from a different direction. Anything
CR 601.3 wants to know must be asked before the move.

**How to apply, added to the list above:**
- When two questions are asked at the same point about the same thing, bundle
  them into one call (`legal_actions._why_cannot_cast_face`). Both used to sit
  above the per-face loop; fixing one and leaving the other hoisted would have
  looked like a fix and shipped the same bug.
- `machines/casting_restrictions.py` must not import `machines/casting.py` -
  the dependency runs the other way. A characteristic substitution it needs is
  passed **in** by the caller that knows the face, never re-derived there.
- Before claiming a read is safely face-blind, name the printing that would
  distinguish it. `why_cannot_cast_a_land` (CR 305.1) and
  `legal_actions._CASTABLE_TYPES` were both checked and left: no printed split
  or adventurer card has a land half, and an MDFC's land face is never named
  as a `Casting.face`. Recorded rather than silently skipped.
- An earlier version of this note claimed "no split or adventurer printing has
  flash on one half only". **Wrong** - Brazen Borrower prints Flash on its
  creature front and Petty Theft does not. Corrected by sweeping every
  `split`/`adventure` printing in the pool for the keyword rather than by
  reasoning about it. It stays unobservable only because the half without the
  keyword is an Instant anyway.
