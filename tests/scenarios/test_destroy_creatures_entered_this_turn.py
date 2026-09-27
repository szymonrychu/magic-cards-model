""" "Destroy all creatures that entered this turn." (Force of Despair) - a new
qualifier on `machines/effects.py`'s own mass-destroy grammar
(`_parse_mass_destroy_predicate`), read the identical way
`machines.targeting.must_have_entered_this_turn` already reads the same
phrase for a *targeted* restriction and `_parse_mass_return_entered_this_
turn_clause` reads it for its own mass-*return* subject: `CardState.
turn_entered` compared against `Game.turn.turn_number`. Force of Despair
pairs it with the alternative cost already read generically through
`machines.cost.alternative_cost_offers`/`_ALTERNATIVE_IF_NOT_YOUR_TURN` (the
identical shape Force of Negation's own "exile a blue card" already proves,
just black rather than blue) - nothing new there, only the effect.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 118.9** / **CR 118.9a** - an alternative cost, and a spell may pay
  at most one.
- **CR 302.6** - "A creature's activated ability with the tap symbol or the
  untap symbol in its activation cost can't be activated unless the
  creature has been under its controller's control continuously since their
  most recent turn began" - the same "continuously since the turn began"
  history this reads for a mass destruction's own subject instead.
- **CR 400.7** - an object that changes zones becomes a new object; a
  creature's `turn_entered` is stamped once, as it enters the battlefield.
- **CR 608.2f** - simultaneous processing of a mass instruction's own group.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, bob_battlefield: list[str], alice_hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Force of Despair", *(alice_hand or [])], battlefield=["Swamp"] * 3)
        .player("bob", battlefield=bob_battlefield)
        .build()
    )


def test_only_creatures_that_entered_this_turn_are_destroyed():
    scenario = _board(bob_battlefield=["Grizzly Bears"], alice_hand=["Memnite"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    old_bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    # A real "enters" this turn (CR 400.7 stamps `turn_entered`), rather than
    # a staged permanent from before the game began.
    memnite = scenario.cast_and_resolve("Memnite", username="alice")

    scenario.cast_and_resolve("Force of Despair", *sources)

    assert memnite.zone is Zone.GRAVEYARD, "entered this turn: destroyed"
    assert old_bears.zone is Zone.BATTLEFIELD, "staged before the game began: spared"


def test_nothing_is_destroyed_when_nothing_entered_this_turn():
    scenario = _board(bob_battlefield=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Force of Despair", *sources)

    assert bears.zone is Zone.BATTLEFIELD


def test_the_black_card_pitch_alternative_cost_is_still_available():
    """CR 118.9's own alternative cost, already generic - proved once more
    here so this file's own card is not silently relying only on its mana
    cost."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player(
            "alice",
            hand=["Force of Despair", "Dark Ritual"],
            battlefield=[],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", bob_mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    casting = scenario.cast("Force of Despair", username="alice")
    casting.use_pitch_cost(choosing=[ritual])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)

    assert ritual.zone is Zone.EXILE
