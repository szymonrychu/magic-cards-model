---
name: announcement-is-atomic
description: Why Casting validates every refusal before it mutates anything - CR 601.2a moves the card to the stack only after why_cannot_cast_a_land/why_cannot_cast_now/why_cannot_cast_restriction have all cleared, so an illegal cast is refused with a reason instead of half-applied
metadata:
  type: project
---

**2026-09-07.** `machines/casting.py`'s `Casting.model_post_init` is the whole
announcement in one call. Verified in-session with `mise run rules:find`:

- **CR 305.1**: "A player who has priority may play a land card from their
  hand during a main phase of their turn when the stack is empty... Since the
  land doesn't go on the stack, it is never a spell, and players can't respond
  to it with instants or activated abilities." `why_cannot_cast_a_land` checks
  this first, before anything else, because a land was never a spell to begin
  with - there is nothing for CR 601.2a's own opening sentence ("To propose the
  casting of a spell...") to be about.
- **CR 601.2a**: "To propose the casting of a spell, a player first moves that
  card (or that copy of a card) from where it is to the stack." This is the
  mutation - `_move_to_the_stack` - and `model_post_init` runs it last, only
  after `why_cannot_cast_a_land`, `why_cannot_cast_now` (CR 117.1a's timing)
  and `why_cannot_cast_restriction` have all raised nothing.

Each of the three checks raises `ValueError` on refusal; `model_post_init` lets
that propagate straight out of the constructor before `_move_to_the_stack` is
ever reached, so an illegal cast never puts the card on the stack at all - the
refusal text is the only effect. This matters because CR 601.2a's move is
itself an identity-changing event (CR 400.7: the object on the stack is a new
object), and undoing it once it has happened is a real rewind, not a no-op:
`Casting._refusing`/`.cancel` exist precisely to reverse it for a refusal that
surfaces *after* the move (a bad target, an unpayable cost), per CR 601.6 ("the
casting of the spell is illegal and the game returns to the moment before the
casting of that spell was proposed") and CR 733.1's mechanics for undoing it
(both verified with `mise run rules:find` in this session). Front-loading the
three checks that can be known before the move ever happens means the common
refusal path - a land in the wrong phase, a card whose type can't be cast at
all - never needs `cancel()` in the first place, and never produces a
transiently-wrong game state for anything to observe.

The concrete gap this ordering closed: without `why_cannot_cast_a_land` running
first, `why_cannot_cast_now`'s CR 117.1a timing check passed a land straight
through (a land in the active player's main phase with an empty stack
satisfies `Game.can_cast_sorcery` exactly like a real spell would), and `Game.
cast` would then refuse deep inside cost determination with a CR 118.6
"unpayable cost" message - which is a lie for a land, since a land's blank
mana-cost corner is not the kind of unpayable cost an alternative cost like
Suspend could ever make payable. `why_cannot_cast_a_land` refuses it honestly,
at the source, instead.

Related: [[legal-actions-enumeration]].
