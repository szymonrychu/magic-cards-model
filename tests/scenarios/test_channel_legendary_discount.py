"""Scenario: a Channel ability's "This ability costs {1} less to activate for
each legendary creature you control." (CR 601.2f via CR 602.2b).

Channel is an ability word (CR 207.2c): it has no rules meaning of its own.
What makes the ability work from a hand is its "Discard this card" cost
(CR 113.6j), and what makes it cheaper is the trailing sentence, read as its
own static ability by `machines/abilities._split_off_trailing_cost_reduction`
and counted by `Game.activation_cost_reduction_for`.

The reduction is generic mana only - CR 118.7a: "Effects that reduce a cost
by an amount of generic mana affect only the generic mana component of that
cost. They can't affect the colored or colorless mana components of that
cost." - so however many legendary creatures its controller has, Takenuma's
{3}{B} never drops below {B}, and CR 601.2f's "It can't be reduced to less
than {0}" floor applies to the generic part alone.

Cards (real printings, `src/magic_cards_model/data/printings/`):

- **Takenuma, Abandoned Mire** - "Channel - {3}{B}, Discard this card: Mill
  three cards, then return a creature or planeswalker card from your graveyard
  to your hand. This ability costs {1} less to activate for each legendary
  creature you control."
- **Eiganjo, Seat of the Empire** (the proof printing: a different colour, a
  different base cost and a targeted effect, not in any api deck) - "Channel -
  {2}{W}, Discard this card: It deals 4 damage to target attacking or blocking
  creature. This ability costs {1} less to activate for each legendary
  creature you control."

Every CR number above was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

TAKENUMA = "Takenuma, Abandoned Mire"
EIGANJO = "Eiganjo, Seat of the Empire"


def _takenuma_cost(alice_battlefield: list[str], bob_battlefield: list[str] | None = None) -> str:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[TAKENUMA],
            battlefield=alice_battlefield,
            library=["Grizzly Bears", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=list(bob_battlefield or []))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    takenuma = scenario.find(TAKENUMA, Zone.HAND, "alice")
    activation = off_battlefield_activation(scenario.game, takenuma, "alice")
    return str(activation.cost.mana)


def test_no_legendary_creature_leaves_the_printed_cost():
    assert _takenuma_cost(["Swamp", "Grizzly Bears"]) == "{3}{B}"


def test_each_legendary_creature_takes_one_generic_off():
    assert _takenuma_cost(["Swamp", "Ragavan, Nimble Pilferer"]) == "{2}{B}"
    assert _takenuma_cost(["Swamp", "Ragavan, Nimble Pilferer", "Questing Beast"]) == "{1}{B}"


def test_three_legendary_creatures_leave_only_the_coloured_symbol():
    assert (
        _takenuma_cost(
            ["Swamp", "Ragavan, Nimble Pilferer", "Questing Beast", "Azusa, Lost but Seeking"]
        )
        == "{B}"
    )


def test_a_fourth_legendary_creature_never_eats_the_black_symbol():
    """CR 118.7a: the excess generic reduction has nothing left to reduce -
    it never reaches {B}."""
    assert (
        _takenuma_cost(
            [
                "Swamp",
                "Ragavan, Nimble Pilferer",
                "Questing Beast",
                "Azusa, Lost but Seeking",
                "Doran, the Siege Tower",
            ]
        )
        == "{B}"
    )


def test_a_legendary_noncreature_permanent_does_not_count():
    """ "Legendary creature" needs both halves: a legendary land is not one."""
    assert _takenuma_cost(["Swamp", "Otawara, Soaring City"]) == "{3}{B}"


def test_a_nonlegendary_creature_does_not_count():
    assert _takenuma_cost(["Swamp", "Grizzly Bears", "Ragavan, Nimble Pilferer"]) == "{2}{B}"


def test_an_opponents_legendary_creature_does_not_count():
    """ "You control": bob's Ragavan discounts nothing for alice."""
    assert _takenuma_cost(["Swamp"], ["Ragavan, Nimble Pilferer", "Questing Beast"]) == "{3}{B}"


def test_the_discounted_channel_is_paid_with_exactly_the_reduced_cost_and_resolves():
    """End to end: two legendary creatures, two Swamps pay {1}{B}, Takenuma is
    discarded as the cost, and the ability resolves - mill three, return the
    creature card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[TAKENUMA],
            battlefield=["Swamp", "Swamp", "Ragavan, Nimble Pilferer", "Questing Beast"],
            library=["Grizzly Bears", "Island", "Island", "Island"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    takenuma = scenario.find(TAKENUMA, Zone.HAND, "alice")
    bears = scenario.top_of_library(1)[0]
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    activation = off_battlefield_activation(scenario.game, takenuma, "alice")
    assert str(activation.cost.mana) == "{1}{B}"
    payment = activation.begin_paying()
    for swamp in swamps:
        payment.tap_for_mana(swamp, mana_from(swamp))
    payment.pay()
    activation.activate()
    assert takenuma.zone is Zone.GRAVEYARD, "discarding it was the cost"

    scenario.will_choose_cards(bears, source=TAKENUMA)
    activation.resolve()

    assert bears.zone is Zone.HAND
    assert scenario.game.cost_modifier_notices == []


# -- the proof printing: Eiganjo's {2}{W} and a targeted effect ------------


def _eiganjo_board(bob_battlefield: list[str]) -> tuple[Scenario, object]:
    """Alice attacks with Grizzly Bears; Bob holds Eiganjo, whose Channel
    needs an attacking or blocking creature to target at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=[EIGANJO], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    return scenario, bears


def _eiganjo_cost(bob_battlefield: list[str]) -> str:
    scenario, bears = _eiganjo_board(bob_battlefield)
    eiganjo = scenario.find(EIGANJO, Zone.HAND, "bob")
    activation = off_battlefield_activation(scenario.game, eiganjo, "bob", targets=[bears])
    return str(activation.cost.mana)


def test_eiganjo_reads_the_same_sentence_off_a_different_base_cost():
    assert _eiganjo_cost(["Plains"]) == "{2}{W}"
    assert _eiganjo_cost(["Plains", "Ragavan, Nimble Pilferer"]) == "{1}{W}"
    assert _eiganjo_cost(["Plains", "Ragavan, Nimble Pilferer", "Questing Beast"]) == "{W}"


def test_eiganjo_never_drops_below_its_white_symbol():
    assert (
        _eiganjo_cost(
            ["Plains", "Ragavan, Nimble Pilferer", "Questing Beast", "Azusa, Lost but Seeking"]
        )
        == "{W}"
    )


def test_eiganjo_paid_with_its_single_white_symbol_deals_its_damage():
    """Two legendary creatures take {2}{W} to {W}: a single Plains pays it,
    Eiganjo is discarded, and its 4 damage kills the attacking 2/2."""
    scenario, bears = _eiganjo_board(["Plains", "Ragavan, Nimble Pilferer", "Questing Beast"])
    eiganjo = scenario.find(EIGANJO, Zone.HAND, "bob")
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "bob")
    activation = off_battlefield_activation(scenario.game, eiganjo, "bob", targets=[bears])
    assert str(activation.cost.mana) == "{W}"
    payment = activation.begin_paying()
    payment.tap_for_mana(plains, mana_from(plains))
    payment.pay()
    activation.activate()
    activation.resolve()
    assert eiganjo.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD, "4 damage to a 2/2 attacker"
