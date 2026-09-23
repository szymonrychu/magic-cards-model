"""Scenario: G2a's plain "if <condition>" clause reader (no "instead"
anywhere), on `Game.condition_holds`, ordered after the "instead if" reader
in `tests/scenarios/test_instead_if_condition.py`.

Two real printings prove the leading word order - the condition first, as
its own clause once `_CLAUSE_SEPARATOR` has already cut the sentence apart at
its period:

- Giant's Ire: "Giant's Ire deals 4 damage to target player or planeswalker.
  If you control a Giant, draw a card." - the damage is unconditional; only
  the draw is gated.
- Peppersmoke: "Target creature gets -1/-1 until end of turn. If you control
  a Faerie, draw a card." - the same shape, gated on an unrelated condition
  (Faeries, not Giants), the proof this reader is not fitted to either card.

Two more cards prove the reader fails closed rather than silently:

- Cling to Dust's own "If it was a creature card, ..." names the card this
  same clause just exiled ("it") - an anaphoric reference `Game.condition_
  holds` does not read (it answers board-state conditions, never "the object
  a clause just moved"). `condition_is_readable`'s regex-only gate refuses
  the parse outright, so the card keeps the `AnaphoricClauseNotice` verdict
  it already had, rather than a new reader silently treating an unread
  condition as false.
- Fatal Push's own "Destroy target creature if it has mana value 2 or less."
  is a *target restriction*, not a top-level conditional instruction -
  `machines/targeting.py`'s `profile_for_text` already reads the trailing
  "if it has mana value N or less" as part of the target phrase itself, so
  `_parse_targeted_clause` (tried first in every per-clause dispatch chain)
  consumes the whole clause before this reader - tried last - ever sees it.
  Its own dedicated Revolt reader (`_parse_revolt_destroy_or_exile_clause`,
  a whole-text reader tried well before any per-clause dispatch) keeps its
  current parser winner.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written."
- **CR 608.2b** - "A target that's no longer in the zone it was in when it
  was targeted is illegal."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import AnaphoricClauseNotice
from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# ---------------------------------------------------------------------------
# Giant's Ire - leading "If <condition>, <consequence>." as its own clause,
# after an unconditional damage clause.
# ---------------------------------------------------------------------------


def _giants_ire_board(alice_extra_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Giant's Ire"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"] + alice_extra_battlefield,
            library=["Opt"],
        )
        .player("bob")
    )


def test_giants_ire_deals_4_damage_and_draws_nothing_without_a_giant():
    scenario = _giants_ire_board([]).build()
    _to_main(scenario)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    life_before = bob.life
    hand_before = len(alice.hand)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Giant's Ire", *sources, targets=["bob"])

    assert bob.life == life_before - 4
    # The spell itself left the hand and nothing replaced it.
    assert len(alice.hand) == hand_before - 1


def test_giants_ire_deals_4_damage_and_draws_a_card_with_a_giant():
    """Bonecrusher Giant (a real Giant creature, off the pool) satisfies the
    condition - the damage is identical either way; only the draw changes."""
    scenario = _giants_ire_board(["Bonecrusher Giant"]).build()
    _to_main(scenario)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    life_before = bob.life
    hand_before = len(alice.hand)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Giant's Ire", *sources, targets=["bob"])

    assert bob.life == life_before - 4
    # The spell left, and a card came back - net unchanged.
    assert len(alice.hand) == hand_before


# ---------------------------------------------------------------------------
# Peppersmoke - the same leading shape, a different condition (Faeries, not
# Giants) and a different unconditional half (a pump, not damage).
# ---------------------------------------------------------------------------


def _peppersmoke_board(alice_extra_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Peppersmoke"],
            battlefield=["Swamp"] + alice_extra_battlefield,
            library=["Opt"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_peppersmoke_always_shrinks_the_target_but_draws_nothing_without_a_faerie():
    scenario = _peppersmoke_board([]).build()
    _to_main(scenario)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)
    bears = scenario.creature("Grizzly Bears", "bob")
    before = scenario.game.characteristics_of(bears).power_toughness

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Peppersmoke", swamp, targets=[bears])

    after = scenario.game.characteristics_of(bears).power_toughness
    assert after == (before[0] - 1, before[1] - 1)
    assert len(alice.hand) == hand_before - 1


def test_peppersmoke_draws_a_card_with_a_faerie():
    scenario = _peppersmoke_board(["Faerie Vandal"]).build()
    _to_main(scenario)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)
    bears = scenario.creature("Grizzly Bears", "bob")
    before = scenario.game.characteristics_of(bears).power_toughness

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Peppersmoke", swamp, targets=[bears])

    after = scenario.game.characteristics_of(bears).power_toughness
    assert after == (before[0] - 1, before[1] - 1)
    assert len(alice.hand) == hand_before


# ---------------------------------------------------------------------------
# Cling to Dust - an "if" this engine genuinely cannot read (an anaphoric
# reference to the object the clause itself just moved, not a board
# condition) stays a notice, not a new, silently-wrong "handled".
# ---------------------------------------------------------------------------


def test_cling_to_dust_unreadable_condition_stays_a_notice_not_silently_run():
    scenario = (
        Scenario()
        .player("alice", hand=["Cling to Dust"], battlefield=["Swamp"], graveyard=["Opt"])
        .player("bob")
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Cling to Dust", swamp, targets=[opt])

    # CR 608.2c: no notion of running half an effect - the exile and the
    # unread "if" are one instruction, so the whole thing fails closed and
    # Opt never leaves the graveyard.
    assert opt.zone is Zone.GRAVEYARD
    assert alice.life == life_before
    assert len(alice.hand) == hand_before - 1
    notices = scenario.game.anaphoric_clause_notices
    assert len(notices) == 1
    assert isinstance(notices[0], AnaphoricClauseNotice)


# ---------------------------------------------------------------------------
# Fatal Push - a target-restriction "if" keeps its own dedicated Revolt
# reader; this reader never sees it.
# ---------------------------------------------------------------------------


def test_fatal_push_still_destroys_a_cheap_creature_with_no_revolt():
    scenario = (
        Scenario()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Fatal Push", swamp, targets=[mystic])

    assert mystic.zone is Zone.GRAVEYARD
