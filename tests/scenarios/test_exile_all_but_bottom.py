""" "When this creature enters, if it was cast, each player exiles all but
the bottom six cards of their library face down." (Doomsday Excruciator) -
`_EXILE_ALL_BUT_BOTTOM_OF_LIBRARY_RE` in `machines/effects.py`, widened from
the imperative "Exile all but the bottom card of each opponent's/target
player's library" to the "each player exiles ... of their library" subject
and the "face down" rider.

- **Doomsday Excruciator** (the listed card): every player, the caster
  included, keeps exactly their bottom six cards; everything above goes to
  exile face down.
- **Nicol Bolas, the Arisen**'s `-12` (the second printing, the back face of
  Nicol Bolas, the Ravager: not a listed card, not in any api deck): the
  same reader's targeted-player subject, face up, bottom *one*. No other
  printing legal in Modern, Pioneer or Standard carries the "each player
  exiles all but the bottom N ... face down" sentence.

Corner cases:

- CR 603.4: "if it was cast" is an intervening "if" - put onto the
  battlefield without being cast, the creature's ability does not trigger at
  all.
- CR 609.3: a library of six or fewer cards has nothing above the bottom six
  to exile, and is left alone.
- CR 406.3 / 406.3a: a card exiled face down can't be examined and has no
  characteristics.
- The bottom six are the six the library keeps, in their original order -
  the library is not shuffled.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 406.3, 406.3a, 603.4, 609.3.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

EXCRUCIATOR = "Doomsday Excruciator"
NICOL_BOLAS = "Nicol Bolas, the Ravager"

TEN = [
    "Forest",
    "Island",
    "Mountain",
    "Swamp",
    "Plains",
    "Lightning Bolt",
    "Tarmogoyf",
    "Memnite",
    "Grizzly Bears",
    "Llanowar Elves",
]


def _resolve_all(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _board(alice_library: list[str], bob_library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EXCRUCIATOR], battlefield=["Swamp"] * 6, library=alice_library)
        .player("bob", library=bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: PlayedScenario) -> None:
    scenario.cast_and_resolve(EXCRUCIATOR, *scenario.untapped_sources(*["Swamp"] * 6))
    _resolve_all(scenario)


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def test_each_player_keeps_exactly_the_bottom_six_cards():
    scenario = _board(list(TEN), list(reversed(TEN)))

    _cast(scenario)

    assert _names(scenario.player("alice").library) == TEN[-6:]
    assert _names(scenario.player("bob").library) == list(reversed(TEN))[-6:]
    exiled_alice = [c for c in scenario.game.exile if c.owner == "alice"]
    exiled_bob = [c for c in scenario.game.exile if c.owner == "bob"]
    assert sorted(c.card.name for c in exiled_alice) == sorted(TEN[:4])
    assert sorted(c.card.name for c in exiled_bob) == sorted(list(reversed(TEN))[:4])
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_the_exiled_cards_are_face_down_with_no_characteristics():
    """CR 406.3a."""
    scenario = _board(list(TEN), list(TEN))

    _cast(scenario)

    exiled = [c for c in scenario.game.exile if c.owner in ("alice", "bob")]
    assert len(exiled) == 8
    assert all(c.face_down for c in exiled)
    assert all(c.has_no_characteristics for c in exiled)


def test_a_library_of_six_or_fewer_is_left_alone():
    """CR 609.3: nothing above the bottom six to exile."""
    scenario = _board(TEN[:6], TEN[:3])

    _cast(scenario)

    assert _names(scenario.player("alice").library) == TEN[:6]
    assert _names(scenario.player("bob").library) == TEN[:3]
    assert [c for c in scenario.game.exile if c.owner in ("alice", "bob")] == []


def test_seven_cards_loses_only_the_top_one():
    scenario = _board(TEN[:7], [])

    _cast(scenario)

    assert _names(scenario.player("alice").library) == TEN[1:7]
    assert [c.card.name for c in scenario.game.exile if c.owner == "alice"] == [TEN[0]]


def test_put_onto_the_battlefield_without_casting_does_not_trigger():
    """CR 603.4: the intervening "if it was cast" is false, so the ability
    never triggers."""
    scenario = _board(list(TEN), list(TEN))

    scenario.put_onto_battlefield(EXCRUCIATOR, "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert len(scenario.player("alice").library) == 10
    assert len(scenario.player("bob").library) == 10
    assert scenario.game.exile == []


def test_the_excruciators_upkeep_draw_comes_from_the_bottom_six():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[EXCRUCIATOR], battlefield=["Swamp"] * 6, library=list(TEN))
        .player("bob", library=list(TEN))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast(scenario)
    assert _names(scenario.player("alice").library) == TEN[-6:]

    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        scenario.advance()
    _resolve_all(scenario)

    assert _names(scenario.player("alice").hand) == [TEN[4]]


# -- Nicol Bolas, the Arisen: the targeted subject, face up ------------------


def test_nicol_bolas_the_arisen_exiles_all_but_the_bottom_card_face_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[NICOL_BOLAS])
        .player("bob", library=TEN[:5])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    front = scenario.find(NICOL_BOLAS, Zone.HAND, "alice")
    nicol = scenario.game.put_onto_battlefield(front, "alice", transformed=True)
    scenario.game.add_counters(nicol, Counter.LOYALTY, 5)

    scenario.activate(nicol, index=3, username="alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert _names(scenario.player("bob").library) == [TEN[4]]
    exiled = [c for c in scenario.game.exile if c.owner == "bob"]
    assert sorted(c.name for c in exiled) == sorted(TEN[:4])
    assert not any(c.face_down for c in exiled)
