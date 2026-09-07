"""Outside the game, and the ability that reaches into it: Karn, the Great Creator.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file, and Karn's text with `resolve_cards`.

- **CR 400.11a** - "Cards in a player's sideboard are outside the game. See
  rule 100.4." Outside the game is **not a zone**: CR 400.1 numbers seven zones
  and none of them is this. `models/zone.py` carries that distinction, and
  `Zone.SIDEBOARD` is storage for the objects rather than an eighth zone.
- **CR 100.4** - a sideboard is "a group of additional cards the player may use
  to modify their deck between games of a match"; CR 100.4a caps it at fifteen
  in constructed and spans the four-copy limit across deck and sideboard.
- **CR 400.11c** - "Cards outside the game can't be affected by spells or
  abilities, except for characteristic-defining abilities printed on them ...
  and spells and abilities that allow those cards to be brought into the game."
- **CR 108.3b** - "Some spells and abilities allow a player to take cards **they
  own** from outside the game and bring them into the game", and the owner of a
  sideboard card is "the player who started the game with it in their sideboard".
- **CR 400.11b** - a card brought in this way "remain[s] in the game until the
  game ends, their owner leaves the game, or a rule or effect removes them from
  the game, whichever comes first".
- **CR 701.20a / 701.20b** - "To reveal a card, show that card to all players
  for a brief time", and "Revealing a card doesn't cause it to leave the zone
  it's in."
- **CR 406.3 / 406.3a** - exiled cards are face up by default and may be
  examined by any player at any time; a card exiled face down "can't be examined
  by any player except when instructions allow it" and "has no characteristics".
- **CR 602.5** - "A player can't begin to activate an ability that's prohibited
  from being activated", which is where Karn's static ability is felt.
- **CR 611.1 / 611.3 / 611.3a / 611.3b** - a continuous effect may "affect ...
  the rules of the game"; a static ability generates one; it is not locked in;
  it applies while its source is on the battlefield.
- **CR 606.4 / 606.6 / 704.5i** - the loyalty cost is paid on activation, a
  negative cost needs the counters to be there, and a planeswalker at 0 loyalty
  is put into its owner's graveyard.
- **CR 113.7a** - an ability on the stack resolves even though its source has
  left the battlefield.
- **CR 608.2d** - the "you may" and the choice are made as the ability resolves,
  and no illegal option may be chosen.

Karn, the Great Creator (`resolve_cards`, {4}, loyalty 5):

    Activated abilities of artifacts your opponents control can't be activated.
    +1: Until your next turn, up to one target noncreature artifact becomes an
        artifact creature with power and toughness each equal to its mana value.
    −2: You may reveal an artifact card you own from outside the game or choose
        a face-up artifact card you own in exile. Put that card into your hand.

The `+1`'s layer arithmetic has its own file (`test_type_changing_and_pt_setting_
effects.py`); it appears here once, so that all three of Karn's abilities are
covered somewhere as one working card.

The decklist used for the deck-legality case is Reironaldu's "eldrazi ramp",
second place in the Modern challenge at mtgtop8 deck 884028, played 2026-08-27 -
the same registered list `test_mulligans.py` pulled with `statistics_decks` and
verified Modern-legal, reused rather than re-derived.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Match, Player, Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario
from tests.scenarios.test_mulligans import eldrazi_ramp

KARN_MINUS_TWO = 1
"""Karn's second activated ability. `+1` is index 0."""


def _karn_board(
    *,
    sideboard: list[str] | None = None,
    exile: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
    bob_exile: list[str] | None = None,
    bob_sideboard: list[str] | None = None,
    alice_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"] * 5,
            battlefield=["Karn, the Great Creator", *(alice_battlefield or [])],
            sideboard=sideboard,
            exile=exile,
        )
        .player(
            "bob",
            library=["Mountain"] * 5,
            battlefield=bob_battlefield,
            exile=bob_exile,
            sideboard=bob_sideboard,
        )
        .build()
    )


def _main_phase(scenario: Scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD)


# -- the minus two, the happy path ----------------------------------------


def test_an_artifact_card_from_outside_the_game_goes_to_your_hand():
    """Karn's `−2`, all the way through: a sideboard card ends up in hand.

    CR 400.11a puts the sideboard outside the game, CR 400.11c makes this one
    of the very few abilities allowed to touch it, and CR 400.11b keeps the
    card in the game once it arrives. The reveal is CR 701.20a.
    """
    scenario = _karn_board(sideboard=["Grafdigger's Cage", "Lightning Bolt"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")
    (cage,) = [state for state in alice.outside_the_game if state.name == "Grafdigger's Cage"]

    scenario.will_choose_cards(cage, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    assert karn.loyalty == 3, "CR 606.4: the −2 is paid on activation"
    scenario.pass_until_resolved()

    assert cage.zone is Zone.HAND
    assert cage in alice.hand
    assert [state.name for state in alice.outside_the_game] == ["Lightning Bolt"]


def test_the_reveal_shows_the_one_card_and_not_the_rest_of_the_sideboard():
    """CR 701.20a shows "that card", not the group it came from.

    The sideboard is hidden (nobody may look at it) and outside the game
    (CR 400.11c), so the single reveal is the whole of what becomes public.
    Anything downstream deciding what an opponent may see reads `Game.reveals`,
    and it holds exactly one entry naming exactly one card.
    """
    scenario = _karn_board(sideboard=["Grafdigger's Cage", "Torpor Orb", "Trinisphere"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")
    (orb,) = [state for state in alice.outside_the_game if state.name == "Torpor Orb"]

    scenario.will_choose_cards(orb, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert len(scenario.game.reveals) == 1
    (reveal,) = scenario.game.reveals
    assert reveal.card_name == "Torpor Orb"
    assert reveal.revealed_by == "alice"
    assert reveal.zone is Zone.SIDEBOARD, "CR 701.20b: it was shown where it sat"
    assert reveal.source == "Karn, the Great Creator"
    revealed = {entry.card_id for entry in scenario.game.reveals}
    assert not any(state.id in revealed for state in alice.outside_the_game), (
        "the two cards left outside the game were never shown"
    )


def test_a_face_up_artifact_you_own_in_exile_needs_no_reveal():
    """The other half of the same paragraph: "or choose a face-up artifact card
    you own in exile".

    CR 406.3 already makes a face-up exiled card one that "may be examined by
    any player at any time", so there is nothing to reveal - the card is
    chosen, not revealed, and Karn's text says exactly that.
    """
    scenario = _karn_board(exile=["Ensnaring Bridge"])
    karn = _main_phase(scenario)
    bridge = scenario.find("Ensnaring Bridge", Zone.EXILE)

    scenario.will_choose_cards(bridge, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert bridge.zone is Zone.HAND
    assert bridge in scenario.player("alice").hand
    assert scenario.game.reveals == [], "CR 406.3: a face-up exiled card is already public"


# -- nothing to fetch, and declining --------------------------------------


def test_with_nothing_legal_to_fetch_the_ability_asks_nothing():
    """A sideboard of nonartifacts offers no candidate at all.

    CR 608.2d: "The player can't choose an option that's illegal or
    impossible." There is no candidate, so no question is put and the ability
    resolves having done nothing - the loyalty is still spent, because CR 606.4
    paid it on activation, long before this.
    """
    scenario = _karn_board(sideboard=["Lightning Bolt", "Shock"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert len(alice.outside_the_game) == 2, "nothing left the sideboard"
    assert alice.hand == []
    assert scenario.game.reveals == []
    assert not any(
        question.source == "Karn, the Great Creator" for question in scenario.questions_asked()
    ), "with no legal candidate there is nothing to ask"
    assert karn.loyalty == 3


def test_declining_the_may_leaves_the_card_outside_the_game():
    """ "You may reveal" - CR 608.2d's plain optional, and declining is legal."""
    scenario = _karn_board(sideboard=["Grafdigger's Cage"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")

    scenario.will_take_the_may(False, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert [state.name for state in alice.outside_the_game] == ["Grafdigger's Cage"]
    assert alice.hand == []
    assert scenario.game.reveals == []


# -- you own, not you control (CR 108.3b) ---------------------------------


def test_an_opponents_face_up_artifact_in_exile_cannot_be_chosen():
    """Exile is a shared, public zone: bob's exiled artifact is right there and
    is still not alice's to take.

    CR 108.3b's gate is ownership, and CR 108.3 fixes an owner for the whole
    game. `CardState.owner` is what the engine filters on - deliberately not
    `controller`, which is a different question with a different answer.
    """
    scenario = _karn_board(bob_exile=["Ensnaring Bridge"])
    karn = _main_phase(scenario)
    bridge = scenario.find("Ensnaring Bridge", Zone.EXILE)
    assert bridge.owner == "bob"

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert bridge.zone is Zone.EXILE
    assert scenario.player("alice").hand == []
    assert not any(
        question.source == "Karn, the Great Creator" for question in scenario.questions_asked()
    )


def test_an_artifact_in_an_opponents_sideboard_cannot_be_chosen():
    """The same rule on the outside-the-game side, and the direct refusal.

    `Player.bring_into_the_game` raises rather than shrugging: a fetch that
    quietly found nothing is exactly the failure this subsystem exists to
    prevent.
    """
    scenario = _karn_board(bob_sideboard=["Grafdigger's Cage"])
    karn = _main_phase(scenario)
    alice = scenario.player("alice")
    (cage,) = scenario.player("bob").outside_the_game

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()
    assert cage.zone is Zone.SIDEBOARD
    assert alice.hand == []

    with pytest.raises(ValueError, match="CR 108.3b"):
        alice.bring_into_the_game(cage)


def test_a_card_already_in_the_game_cannot_be_brought_in_from_outside_it():
    """CR 400.11a is the boundary: a card in hand is not outside the game."""
    scenario = _karn_board()
    _main_phase(scenario)
    alice = scenario.player("alice")
    scenario.draw(1)
    (mountain,) = alice.hand

    with pytest.raises(ValueError, match="CR 400.11a"):
        alice.bring_into_the_game(mountain)


def test_a_sideboard_card_stamped_for_another_player_is_not_yours_to_fetch():
    """`Player.add` only fills in a *blank* owner (CR 108.3), so a sideboard
    can hold an object somebody else owns. `owned_outside_the_game` filters on
    the owner rather than on whose sideboard it sits in."""
    scenario = _karn_board(sideboard=["Grafdigger's Cage"])
    _main_phase(scenario)
    alice = scenario.player("alice")
    (cage,) = alice.outside_the_game
    cage.owner = "bob"

    assert alice.outside_the_game == [cage]
    assert alice.owned_outside_the_game() == []
    with pytest.raises(ValueError, match="CR 108.3b"):
        alice.bring_into_the_game(cage)


# -- face-down exile is not face-up exile (CR 406.3) ----------------------


def test_a_face_down_exiled_artifact_cannot_be_chosen():
    """CR 406.3: a card "exiled face down" can't be examined by any player, and
    CR 406.3a says it "has no characteristics" - so it is not a face-up
    artifact card, and asking whether it is an artifact has no answer to give.
    """
    scenario = _karn_board(exile=["Ensnaring Bridge"])
    karn = _main_phase(scenario)
    bridge = scenario.find("Ensnaring Bridge", Zone.EXILE)
    bridge.turn_face_down()
    assert bridge.face_down

    assert scenario.game.face_up_cards_in_exile("alice") == []

    scenario.activate(karn, index=KARN_MINUS_TWO)
    scenario.pass_until_resolved()

    assert bridge.zone is Zone.EXILE
    assert scenario.player("alice").hand == []


# -- the static ability (CR 602.5, CR 611.1) ------------------------------


def test_an_opponents_artifact_ability_cannot_be_activated():
    """ "Activated abilities of artifacts your opponents control can't be
    activated." Bob's Sol Ring keeps its `{T}: Add {C}{C}` and may not use it.

    CR 602.5 is where the prohibition lands, and CR 605.1a's mana abilities are
    *not* spared: Karn's sentence has no "unless they're mana abilities" tail.
    """
    scenario = _karn_board(bob_battlefield=["Sol Ring"])
    _main_phase(scenario)
    sol_ring = scenario.creature("Sol Ring", "bob")

    assert scenario.why_cannot_activate(sol_ring, username="bob") == (
        "Sol Ring's activated abilities can't be activated: "
        "Karn, the Great Creator says so (CR 602.5, CR 611.1)"
    )
    with pytest.raises(ValueError, match="CR 602.5"):
        scenario.activate(sol_ring, username="bob")


def test_your_own_artifact_ability_is_untouched():
    """ "your opponents control" - the "your" is Karn's controller's.

    This is the assertion a single-player test cannot make, and the wrong
    version of this layer effect passes every test that does not make it.
    """
    scenario = _karn_board(alice_battlefield=["Sol Ring"], bob_battlefield=["Sol Ring"])
    _main_phase(scenario)
    alice_sol_ring = scenario.creature("Sol Ring", "alice")
    bob_sol_ring = scenario.creature("Sol Ring", "bob")

    assert scenario.why_cannot_activate(alice_sol_ring, username="alice") is None
    assert scenario.why_cannot_activate(bob_sol_ring, username="bob") is not None


def test_an_opponents_nonartifact_ability_is_untouched():
    """The quality is "artifacts". Bob's Basking Rootwalla is a Lizard."""
    scenario = _karn_board(bob_battlefield=["Basking Rootwalla"])
    _main_phase(scenario)
    rootwalla = scenario.creature("Basking Rootwalla", "bob")

    assert scenario.why_cannot_activate(rootwalla, username="bob") is None


def test_the_prohibition_stops_when_karn_leaves_the_battlefield():
    """CR 604.2 and CR 611.3b: the effect is active "as long as the permanent
    with the ability remains on the battlefield"."""
    scenario = _karn_board(bob_battlefield=["Sol Ring"])
    karn = _main_phase(scenario)
    sol_ring = scenario.creature("Sol Ring", "bob")
    assert scenario.why_cannot_activate(sol_ring, username="bob") is not None

    scenario.game.destroy(karn)
    assert karn.zone is Zone.GRAVEYARD

    assert scenario.why_cannot_activate(sol_ring, username="bob") is None


def test_a_symmetric_prohibition_catches_its_own_controller():
    """Collector Ouphe: "Activated abilities of artifacts can't be activated."

    No "your opponents control" clause, so CR 611.3b applies it to every
    artifact on the battlefield - its controller's Sol Ring included. The
    contrast with Karn is the point: one sentence names a controller and the
    other does not, and the engine has to tell them apart rather than assuming
    every prohibition is one-sided.
    """
    scenario = _karn_board(
        alice_battlefield=["Collector Ouphe", "Sol Ring"], bob_battlefield=["Sol Ring"]
    )
    _main_phase(scenario)

    assert scenario.why_cannot_activate(
        scenario.creature("Sol Ring", "alice"), username="alice"
    ) == (
        "Sol Ring's activated abilities can't be activated: "
        "Collector Ouphe says so (CR 602.5, CR 611.1)"
    )
    assert scenario.why_cannot_activate(scenario.creature("Sol Ring", "bob"), username="bob")


# -- the plus one, so all three abilities are covered ---------------------


def test_the_plus_one_animates_a_noncreature_artifact():
    """`+1: Until your next turn, up to one target noncreature artifact becomes
    an artifact creature with power and toughness each equal to its mana value.`

    The layer arithmetic (CR 613.1d, 613.4b, 613.6) is `test_type_changing_and_
    pt_setting_effects.py`'s subject; this is the one assertion that Karn's
    three abilities all work on the same card.
    """
    scenario = _karn_board(alice_battlefield=["Ensnaring Bridge"])
    karn = _main_phase(scenario)
    bridge = scenario.creature("Ensnaring Bridge", "alice")

    scenario.activate(karn, targets=[bridge])
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(bridge).is_creature
    assert scenario.game.power_of(bridge) == 3, "Ensnaring Bridge's mana value"
    assert karn.loyalty == 6


# -- loyalty (CR 606.4, 606.6, 704.5i, 113.7a) ----------------------------


def test_the_minus_two_is_refused_once_the_loyalty_is_too_low():
    """CR 606.6: "A loyalty ability with a negative loyalty cost ... can't be
    activated unless the permanent has at least that many loyalty counters on
    it." Karn at 1 is a Karn that cannot `−2`."""
    scenario = _karn_board(sideboard=["Grafdigger's Cage"])
    karn = _main_phase(scenario)
    karn.remove_counters(Counter.LOYALTY, 4)  # staged, the way a library is rigged
    assert karn.loyalty == 1

    assert scenario.why_cannot_activate(karn, index=KARN_MINUS_TWO) == (
        "Karn, the Great Creator has 1 loyalty, not the 2 its −2 cost removes (CR 606.6)"
    )
    with pytest.raises(ValueError, match="CR 606.6"):
        scenario.activate(karn, index=KARN_MINUS_TWO)


def test_karn_dying_to_his_own_cost_still_puts_the_card_in_your_hand():
    """Karn staged at 2 loyalty: the `−2` pays him to 0.

    CR 606.4 makes the counter change the cost, paid on activation; CR 704.5i
    then puts a planeswalker at 0 loyalty into its owner's graveyard as soon as
    state-based actions are checked - which is before his own ability resolves.
    CR 113.7a is what lets the ability resolve anyway, and the fetch still
    happens, because the ability's controller is on the ability, not on a
    permanent that has to still be there.
    """
    scenario = _karn_board(sideboard=["Trinisphere"])
    karn = _main_phase(scenario)
    karn.remove_counters(Counter.LOYALTY, 3)
    assert karn.loyalty == 2
    alice = scenario.player("alice")
    (trinisphere,) = alice.outside_the_game

    scenario.will_choose_cards(trinisphere, username="alice")
    scenario.activate(karn, index=KARN_MINUS_TWO)

    assert karn.zone is Zone.GRAVEYARD, "CR 704.5i, checked as priority comes back"

    scenario.pass_until_resolved()
    assert trinisphere.zone is Zone.HAND, "CR 113.7a: the ability resolved without its source"
    assert len(scenario.game.reveals) == 1


# -- deck legality is a decklist question, not a zone question ------------


def test_fetching_from_the_sideboard_does_not_change_what_deck_legality_counts():
    """CR 100.2a and CR 100.4a are checked against the registered decklist.

    `Deck.check_legality` counts the `Deck` - sixty cards, fifteen sideboard,
    four copies across both - and a card physically leaving a player's
    sideboard mid-game is not an edit to that list. The card is now in the
    game (CR 400.11b) and the decklist says exactly what it said before, which
    is what makes the fetch legal to run at all rather than a deck-construction
    violation halfway through a game.
    """
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed="outside-the-game",
    )
    registered: Deck = series.register_deck("alice", eldrazi_ramp())
    series.register_deck("bob", eldrazi_ramp())
    game = series.start_game()
    alice = game.player("alice")

    before_mainboard = dict(registered.mainboard)
    before_sideboard = dict(registered.sideboard)
    assert len(alice.outside_the_game) == registered.sideboard_size == 15

    (cage, *_) = alice.owned_outside_the_game(lambda state: state.name == "Grafdigger's Cage")
    # `Player.bring_into_the_game` mints the moved card's own
    # `zone_change_stamp` with no `Game` method's `_id_allocator_scope`
    # open around it here.
    with game._id_allocator_scope():  # noqa: SLF001
        alice.bring_into_the_game(cage)

    assert cage.zone is Zone.HAND
    assert len(alice.outside_the_game) == 14, "the physical sideboard is one card lighter"
    assert registered.mainboard == before_mainboard
    assert registered.sideboard == before_sideboard
    assert series.decks["alice"].check_legality(card) is registered, "still a legal list"


def test_a_card_brought_into_one_game_is_outside_the_game_again_in_the_next():
    """CR 400.11b: brought-in cards "remain in the game until the game ends".

    The game ending is the bound, and `Match._fresh` honours it without a
    special case - the next game reloads the registered decklist, so the
    fifteen-card sideboard is whole again.
    """
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed="outside-the-game",
    )
    series.register_deck("alice", eldrazi_ramp())
    series.register_deck("bob", eldrazi_ramp())
    first = series.start_game()
    alice = first.player("alice")
    (orb, *_) = alice.owned_outside_the_game(lambda state: state.name == "Torpor Orb")
    # `Player.bring_into_the_game` mints the moved card's own
    # `zone_change_stamp` with no `Game` method's `_id_allocator_scope`
    # open around it here.
    with first._id_allocator_scope():  # noqa: SLF001
        alice.bring_into_the_game(orb)
    assert len(alice.outside_the_game) == 14

    first.concede("bob")
    assert first.is_over

    second = series.start_game()
    assert len(second.player("alice").outside_the_game) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in second.player("alice").outside_the_game)
