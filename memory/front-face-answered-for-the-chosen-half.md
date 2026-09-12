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
say only that half's characteristics exist once it is on the stack.

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
`Casting.face_timing_refusals` for whichever face the caller names later. The
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
