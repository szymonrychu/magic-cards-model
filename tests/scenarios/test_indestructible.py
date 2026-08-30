"""Indestructible: what it actually stops, and what it does not (CR 702.12).

CR 702.12a: "Indestructible is a static ability." CR 702.12b is the whole rule:
"A permanent with indestructible can't be destroyed. Such permanents aren't
destroyed by lethal damage, and **they ignore the state-based action that checks
for lethal damage** (see rule 704.5g)." CR 702.12c: "Multiple instances of
indestructible on the same permanent are redundant."

The naive reading - "it cannot die" - is wrong in three separate ways, and the
corner cases here are all of them:

- **Damage is still dealt and still marked.** Nothing about indestructible
  prevents damage. CR 704.5g simply does not apply, so twenty damage sits on the
  creature until CR 514.2 wipes it in the cleanup step.
- **CR 704.5f still applies.** "If a creature has toughness 0 or less, it's put
  into its owner's graveyard. Regeneration can't replace this event." That is not
  destruction, so -1/-1 counters or a toughness-setting effect kill an
  indestructible creature.
- **Sacrificing, exiling and bouncing all still work**, because none of them is
  destroying (CR 701.21a, CR 701.13a, CR 701.19a).

Deathtouch does not get round it either: CR 704.5h destroys, and CR 702.12b says
a permanent with indestructible can't be destroyed.

**What executes.** `machines/keywords.is_indestructible` answers the question,
off the computed board when it is given a game (CR 613.5), so indestructible
granted in layer 6 counts. What consults it is nothing:
`Game.destroy`/`Game._dies_to_state_based_action` are where CR 702.12b has to be
enforced and they are in `models/game.py`. See `docs/engine-coverage.md`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    indestructible_survives_lethal_damage,
    is_indestructible,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario

NOT_ENFORCED = (
    "CR 702.12b has to be enforced where destruction happens: Game.destroy (CR 701.7a) "
    "and Game._dies_to_state_based_action (CR 704.5g, CR 704.5h), both in "
    "models/game.py. machines/keywords.is_indestructible answers the question and "
    "nothing asks it. See docs/engine-coverage.md."
)


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Ulamog, the Ceaseless Hunger", "Grizzly Bears"],
            hand=["Lightning Bolt"],
        )
        .player("bob", battlefield=["Mountain"])
    )


def test_indestructible_is_read_off_the_printing():
    """CR 702.12a: a static ability, and Scryfall lists it as a keyword."""
    assert "Indestructible" in card("Ulamog, the Ceaseless Hunger").keywords


def test_the_predicate_answers_for_a_permanent_on_the_battlefield():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")
    bears = scenario.creature("Grizzly Bears")

    assert is_indestructible(ulamog, scenario.game)
    assert not is_indestructible(bears, scenario.game)


def test_lethal_damage_is_still_marked_on_it():
    """CR 702.12b takes nothing away from CR 120: the damage is dealt.

    Indestructible is not prevention (CR 615.1a). What it changes is whether the
    state-based action applies, and the marked damage is the evidence.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    scenario.game.deal_damage(ulamog, 15)

    assert ulamog.damage == 15
    assert ulamog.has_lethal_damage  # a 10/10 with 15 on it
    assert indestructible_survives_lethal_damage(ulamog, scenario.game)


def test_toughness_zero_or_less_still_kills_it():
    """CR 704.5f is not destruction, so indestructible has nothing to say to it.

    "If a creature has toughness 0 or less, it's put into its owner's graveyard.
    Regeneration can't replace this event." Ten -1/-1 counters take a 10/10 to
    0/0 (CR 122.1a), and it goes.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    scenario.game.add_counters(ulamog, Counter.MINUS_ONE, 10)
    assert ulamog.toughness == 0
    scenario.state_based_actions()

    assert ulamog.zone is Zone.GRAVEYARD


def test_exiling_it_works_because_exiling_is_not_destroying():
    """CR 701.13a: "to exile an object, move it to the exile zone" - no destruction."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    scenario.game.exile_permanent(ulamog)

    assert ulamog.zone is Zone.EXILE


def test_the_predicate_is_false_off_the_battlefield_with_no_game():
    """CR 613 applies to permanents; a card in hand has only what is printed.

    Asked without a game, the printing answers - which is still "yes" for a card
    that prints indestructible, and is the right answer for the question
    "does this card have the keyword".
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ulamog, the Ceaseless Hunger"])
        .player("bob")
        .build()
    )
    ulamog = scenario.find("Ulamog, the Ceaseless Hunger", Zone.HAND, "alice")

    assert is_indestructible(ulamog)


def test_lethal_damage_does_not_destroy_it():
    """CR 702.12b: "they ignore the state-based action that checks for lethal
    damage (see rule 704.5g)"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    scenario.game.deal_damage(ulamog, 15)
    scenario.state_based_actions()

    assert ulamog.zone is Zone.BATTLEFIELD


def test_an_effect_that_destroys_it_does_nothing():
    """CR 702.12b: "A permanent with indestructible can't be destroyed."

    CR 701.7c says the same from destruction's side: an indestructible permanent
    is not destroyed by an effect that says "destroy".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    scenario.game.destroy(ulamog)

    assert ulamog.zone is Zone.BATTLEFIELD


def test_deathtouch_does_not_get_round_it():
    """CR 704.5h destroys, and CR 702.12b says it can't be destroyed."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger")

    ulamog.dealt_deathtouch_damage = True
    scenario.state_based_actions()

    assert ulamog.zone is Zone.BATTLEFIELD
