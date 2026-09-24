"""Boast, and Baron Helmut Zemo's boast: exile black cards with enough black
mana symbols, copy them, cast up to three of the copies for free.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 702.142a** - "Boast - [Cost]: [Effect]" means "[Cost]: [Effect].
  Activate only if this creature attacked this turn and only once each turn."
- **CR 107.4e** - "A hybrid mana symbol is also a colored mana symbol" and "is
  all of its component colors", so Divinity of Pride's {W/B} symbols are black
  mana symbols, and Beseech the Queen's monocolored {2/B} ones are too.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully": fourteen black symbols do not pay a
  fifteen-symbol cost.
- **CR 707.12** - "An effect that instructs a player to cast a copy of an
  object (and not just copy a spell) follows the rules for casting spells,
  except that the copy is created in the same zone the object is in" - exile,
  here - "and then cast while another spell or ability is resolving".
- **CR 707.12a** - "An effect that creates multiple copies and says a player
  'may cast' those objects allows that player to choose individually, for
  each of those objects, whether or not to cast it."
- **CR 707.10a** - "If a copy of a card is in any zone other than the stack or
  the battlefield, it ceases to exist" - a copy not cast is gone.
- **CR 112.2a** - the owner of such a copy "is the player who is instructed
  to create it and given permission to cast it".

Boast is proven on two Kaldheim printings besides Zemo, found with a Scryfall
full-text search for "Boast" on 2026-09-24, both legal in Modern and Pioneer
and in no deck under `magic-cards-model-api/decks/`: Axgard Braggart ("Boast
- {1}{W}: Untap this creature. Put a +1/+1 counter on it.") and Duskwielder
("Boast - {1}: Target opponent loses 1 life and you gain 1 life.").

The symbol-threshold exile cost and the "copy those exiled cards, cast up to
N of the copies" effect are printed on Zemo alone among legal cards (the same
search, "mana symbols among their mana costs" and "of the copies"); per the
campaign's rule for a single-printing template both readers are written
against the template's variable parts (colour, threshold, count) rather than
the sentence, and recorded in MEMORY.md.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Boast itself (CR 702.142a), on Kaldheim printings
# --------------------------------------------------------------------------


def _braggart_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"] * 3,
            battlefield=["Axgard Braggart", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob", life=40, library=["Island"] * 3)
        .build()
    )
    return scenario


def test_boast_cannot_be_activated_before_the_creature_attacks():
    scenario = _braggart_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    braggart = scenario.creature("Axgard Braggart", "alice")

    reason = scenario.why_cannot_activate(braggart, 0)

    assert reason is not None and "702.142a" in reason


def test_boast_can_be_activated_once_the_creature_has_attacked():
    scenario = _braggart_board()
    braggart = scenario.creature("Axgard Braggart", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(braggart)

    scenario.activate(braggart, auto=True)
    scenario.resolve_top()

    assert braggart.tapped is False
    assert braggart.counter_count(Counter.PLUS_ONE) == 1


def test_boast_is_only_once_each_turn():
    scenario = _braggart_board()
    braggart = scenario.creature("Axgard Braggart", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(braggart)
    scenario.activate(braggart, auto=True)
    scenario.resolve_top()

    reason = scenario.why_cannot_activate(braggart, 0)

    assert reason is not None and "already been activated" in reason


def test_a_creature_that_did_not_attack_cannot_boast_even_if_another_did():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Axgard Braggart", "Grizzly Bears", "Plains", "Plains"],
        )
        .player("bob", life=40)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))

    assert scenario.why_cannot_activate(scenario.creature("Axgard Braggart", "alice"), 0)


def test_boast_resets_on_the_next_turn():
    """Attacking is per turn: next turn, without attacking again, no boast."""
    scenario = _braggart_board()
    braggart = scenario.creature("Axgard Braggart", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(braggart)
    while scenario.game.active_player.username != "bob":
        if not scenario.game.stack_is_empty:
            scenario.pass_until_resolved()
        scenario.advance()
    while scenario.game.active_player.username != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.why_cannot_activate(braggart, 0) is not None


def test_proof_duskwielder_boasts_a_drain():
    scenario = (
        Scenario().player("alice", battlefield=["Duskwielder", "Swamp"]).player("bob").build()
    )
    duskwielder = scenario.creature("Duskwielder", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(duskwielder)

    scenario.activate(duskwielder, auto=True, targets=["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


# --------------------------------------------------------------------------
# Baron Helmut Zemo's boast
# --------------------------------------------------------------------------

#: 4 + 4 + 5 + 3 = 16 black mana symbols: Griselbrand's {B}{B}{B}{B} twice,
#: Divinity of Pride's five {W/B} (CR 107.4e), Beseech the Queen's three {2/B}.
_SIXTEEN = ["Griselbrand", "Griselbrand", "Divinity of Pride", "Beseech the Queen"]


def _zemo_board(graveyard: list[str], hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"] * 6,
            graveyard=graveyard,
            hand=hand or [],
            battlefield=["Baron Helmut Zemo", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", life=40, library=["Island"] * 6)
        .build()
    )
    zemo = scenario.creature("Baron Helmut Zemo", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(zemo)
    return scenario, zemo


def _graveyard(scenario, *names: str):
    cards = []
    pool = list(scenario.player("alice").graveyard)
    for name in names:
        card = next(state for state in pool if state.card.name == name)
        pool.remove(card)
        cards.append(card)
    return cards


def test_zemo_cannot_boast_before_attacking():
    scenario = (
        Scenario()
        .player("alice", graveyard=_SIXTEEN, battlefield=["Baron Helmut Zemo"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    reason = scenario.why_cannot_activate(scenario.creature("Baron Helmut Zemo", "alice"), 0)

    assert reason is not None and "702.142a" in reason


def test_zemo_copies_the_exiled_cards_and_casts_up_to_three_for_free():
    scenario, zemo = _zemo_board(_SIXTEEN)
    exiled = _graveyard(scenario, *_SIXTEEN)
    scenario.will_take_the_may(True, times=None)

    scenario.activate(zemo, exiling=exiled)
    scenario.resolve_top()

    # The originals stay in exile; three copies were cast, and are spells on
    # the stack now (CR 707.12), owned by alice (CR 112.2a).
    assert all(card.zone is Zone.EXILE for card in exiled)
    copies = [spell for spell in scenario.game.stack if getattr(spell, "is_copy", False)]
    assert len(copies) == 3
    assert all(copy.owner == "alice" for copy in copies)
    # CR 707.10a: the fourth copy, never cast, ceased to exist.
    assert [state for state in scenario.game.exile if state.is_copy] == []
    # No mana was spent: every Swamp is still untapped.
    swamps = [state for state in scenario.game.battlefield if state.card.name == "Swamp"]
    assert swamps and not any(swamp.tapped for swamp in swamps)


def test_the_copies_are_chosen_individually():
    """CR 707.12a: declining one copy does not decline the rest."""
    scenario, zemo = _zemo_board(_SIXTEEN)
    exiled = _graveyard(scenario, *_SIXTEEN)
    scenario.will_take_the_may(False)
    scenario.will_take_the_may(True, times=None)

    scenario.activate(zemo, exiling=exiled)
    scenario.resolve_top()

    copies = [spell for spell in scenario.game.stack if getattr(spell, "is_copy", False)]
    assert len(copies) == 3
    assert "Griselbrand" in [copy.card.name for copy in copies]


def test_declining_every_copy_casts_nothing_and_leaves_no_copy_behind():
    scenario, zemo = _zemo_board(_SIXTEEN)
    exiled = _graveyard(scenario, *_SIXTEEN)
    scenario.will_take_the_may(False, times=None)

    scenario.activate(zemo, exiling=exiled)
    scenario.resolve_top()

    assert scenario.game.stack_is_empty
    assert [state for state in scenario.game.exile if state.is_copy] == []
    assert all(card.zone is Zone.EXILE for card in exiled)


def test_casting_the_copies_is_not_casting_from_hand():
    """Zemo's own "Whenever you cast a black spell from your hand" does not
    see a copy cast from exile: no connive, the library is untouched."""
    scenario, zemo = _zemo_board(_SIXTEEN)
    exiled = _graveyard(scenario, *_SIXTEEN)
    scenario.will_take_the_may(True, times=None)
    library = len(scenario.player("alice").library)

    scenario.activate(zemo, exiling=exiled)
    scenario.resolve_top()

    assert scenario.pending_triggers == []
    assert len(scenario.player("alice").library) == library


def test_fewer_than_fifteen_black_symbols_cannot_pay():
    """CR 118.3: 4 + 4 + 5 = 13 black symbols is not fifteen."""
    scenario, zemo = _zemo_board(["Griselbrand", "Griselbrand", "Divinity of Pride"])
    exiled = _graveyard(scenario, "Griselbrand", "Griselbrand", "Divinity of Pride")

    with pytest.raises(ValueError, match="118.3"):
        scenario.activate(zemo, exiling=exiled)

    assert all(card.zone is Zone.GRAVEYARD for card in exiled)


def test_a_nonblack_card_cannot_be_exiled_for_the_cost():
    """ "Exile any number of *black* cards": a Lightning Bolt adds nothing and
    cannot be chosen at all."""
    scenario, zemo = _zemo_board([*_SIXTEEN, "Lightning Bolt"])
    exiled = _graveyard(scenario, *_SIXTEEN, "Lightning Bolt")

    with pytest.raises(ValueError):
        scenario.activate(zemo, exiling=exiled)

    assert all(card.zone is Zone.GRAVEYARD for card in exiled)


def test_zemo_boasts_only_once_each_turn():
    scenario, zemo = _zemo_board([*_SIXTEEN, *_SIXTEEN])
    first = _graveyard(scenario, *_SIXTEEN)
    scenario.will_take_the_may(False, times=None)
    scenario.activate(zemo, exiling=first)
    scenario.resolve_top()

    assert scenario.why_cannot_activate(zemo, 0) is not None
