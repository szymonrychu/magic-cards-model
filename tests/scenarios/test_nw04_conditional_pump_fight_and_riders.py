"""Scenario: riders on a pump, a protection grant or a bite - a pump gated on
the target's own power before a fight, a type-conditional counter after a
protection grant, the colorless-or-colour protection choice, and the poison
counter an opponent gets after a bite.

Reported cards (NW-04 T2):

- Savage Swipe - "Target creature you control gets +2/+2 until end of turn if
  its power is 2. Then it fights target creature you don't control."
- Angelic Intervention - "Target creature or planeswalker you control gains
  protection from colorless or from the color of your choice until end of
  turn. If it's a creature, put a +1/+1 counter on it."
- Infectious Bite - "... deals damage equal to its power to target creature
  you don't control. Each opponent gets a poison counter."

Second printings (legal in Modern, Pioneer or Standard, in no deck under
`magic-cards-model-api/decks/`): Giver of Runes (the colorless-or-colour
protection from an activated ability), Prologue to Phyresis and Infectious
Inquiry ("Each opponent gets a poison counter." beside a draw / a life loss).
No other legal printing carries the conditional pump-then-fight template; the
pair reader is the Burrog Barrage pair widened, and its bite form stays covered
by that card's own scenarios.

Every CR number below was looked up with `mise run rules:find`:

- **CR 608.2c** - instructions are followed in order; "it" is the earlier
  instruction's target, and its power is read as the spell resolves.
- **CR 701.14a** - fighting creatures each deal damage equal to their power to
  the other; **CR 701.14b** - a creature no longer on the battlefield does not
  fight.
- **CR 702.16a** - protection from a quality; **CR 105.2c** - a colorless
  object has no color.
- **CR 122.1f** - poison counters; **CR 704.5c** - ten or more lose the game.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _board(*, hand=(), alice=(), bob=("Runeclaw Bear",), lands=(), bob_hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=[*alice, *lands], library=["Forest"] * 10)
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob),
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    return scenario


@pytest.mark.parametrize(
    "name",
    [
        "Savage Swipe",
        "Angelic Intervention",
        "Infectious Bite",
        "Giver of Runes",
        "Prologue to Phyresis",
        "Infectious Inquiry",
    ],
)
def test_every_card_is_handled(name: str) -> None:
    clauses = [c for c in classify_clauses(card(name)) if c.text]
    assert {c.category for c in clauses} == {HANDLED}, [(c.category, c.text) for c in clauses]


# -- Savage Swipe -----------------------------------------------------------------


def test_a_power_two_creature_is_pumped_then_fights() -> None:
    scenario = _board(hand=["Savage Swipe"], alice=["Grizzly Bears"], lands=["Forest"])
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    scenario.cast_and_resolve("Savage Swipe", auto=True, targets=[bears, runeclaw])
    scenario.state_based_actions()

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (4, 4)
    assert runeclaw.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD, "the 4/4 took 2"
    assert notices(scenario) == []


def test_a_creature_of_other_power_is_not_pumped_but_still_fights() -> None:
    """CR 608.2c / CR 701.14a: the condition gates only the pump."""
    scenario = _board(hand=["Savage Swipe"], alice=["Llanowar Elves"], lands=["Forest"])
    elves = scenario.creature("Llanowar Elves")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    scenario.cast_and_resolve("Savage Swipe", auto=True, targets=[elves, runeclaw])
    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD
    assert runeclaw.zone is Zone.BATTLEFIELD
    assert runeclaw.damage == 1
    assert notices(scenario) == []


def test_a_power_three_creature_is_not_pumped() -> None:
    scenario = _board(
        hand=["Savage Swipe"], alice=["Plague Nurse"], lands=["Forest"], bob=["Memnite"]
    )
    nurse = scenario.creature("Plague Nurse")
    memnite = scenario.creature("Memnite", "bob")

    scenario.cast_and_resolve("Savage Swipe", auto=True, targets=[nurse, memnite])
    scenario.state_based_actions()

    assert (computed(scenario).of(nurse).power, computed(scenario).of(nurse).toughness) == (3, 4)
    assert memnite.zone is Zone.GRAVEYARD


def test_no_fight_when_the_other_creature_is_gone() -> None:
    """CR 701.14b: the pump still happens; nobody fights."""
    scenario = _board(
        hand=["Savage Swipe"],
        alice=["Grizzly Bears"],
        lands=["Forest"],
        bob_hand=["Lightning Bolt"],
        bob=["Runeclaw Bear", "Mountain"],
    )
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    scenario.cast_onto_stack("Savage Swipe", auto=True, targets=[bears, runeclaw])
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority()
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[runeclaw])
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert runeclaw.zone is Zone.GRAVEYARD
    assert bears.damage == 0
    assert computed(scenario).of(bears).power == 4


# -- Angelic Intervention / Giver of Runes ---------------------------------------


def test_angelic_intervention_colorless_protection_and_a_counter() -> None:
    scenario = _board(
        hand=["Angelic Intervention"], alice=["Grizzly Bears"], lands=["Plains", "Plains"]
    )
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("colorless")

    scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[bears])

    board = computed(scenario).of(bears)
    assert board.has_ability("Protection from colorless")
    assert bears.counters[Counter.PLUS_ONE] == 1
    assert (board.power, board.toughness) == (3, 3)
    assert notices(scenario) == []


def test_protection_from_colorless_refuses_a_colorless_blocker() -> None:
    """CR 702.16a."""
    scenario = _board(
        hand=["Angelic Intervention"],
        alice=["Grizzly Bears"],
        lands=["Plains", "Plains"],
        bob=["Memnite", "Runeclaw Bear"],
    )
    bears = scenario.creature("Grizzly Bears")
    memnite = scenario.creature("Memnite", "bob")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    scenario.will_choose("colorless")
    scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[bears])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    with pytest.raises(ValueError):
        scenario.block(bears, memnite)
    scenario.block(bears, runeclaw)  # a green blocker is fine


def test_protection_from_red_stops_a_red_spell_targeting_it() -> None:
    scenario = _board(
        hand=["Angelic Intervention"],
        alice=["Grizzly Bears"],
        lands=["Plains", "Plains"],
        bob=["Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("R")
    scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[bears])

    assert computed(scenario).of(bears).has_ability("Protection from red")
    with pytest.raises(ValueError):
        scenario.cast("Lightning Bolt", username="bob", targets=[bears])


def test_a_planeswalker_gets_protection_but_no_counter() -> None:
    """The rider applies only "if it's a creature" (CR 608.2c)."""
    scenario = _board(
        hand=["Angelic Intervention", "Vraska, Scheming Gorgon"], lands=["Plains", "Plains"]
    )
    vraska = scenario.put_onto_battlefield("Vraska, Scheming Gorgon", "alice")
    loyalty = vraska.counters[Counter.LOYALTY]
    scenario.will_choose("colorless")

    scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[vraska])

    assert computed(scenario).of(vraska).has_ability("Protection from colorless")
    assert vraska.counters[Counter.PLUS_ONE] == 0
    assert vraska.counters[Counter.LOYALTY] == loyalty
    assert notices(scenario) == []


def test_the_protection_ends_at_cleanup_but_the_counter_stays() -> None:
    scenario = _board(
        hand=["Angelic Intervention"], alice=["Grizzly Bears"], lands=["Plains", "Plains"]
    )
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("G")
    scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[bears])

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not computed(scenario).of(bears).has_ability("Protection from green")
    assert bears.counters[Counter.PLUS_ONE] == 1


def test_the_choice_refuses_anything_but_colorless_or_a_color() -> None:
    scenario = _board(
        hand=["Angelic Intervention"], alice=["Grizzly Bears"], lands=["Plains", "Plains"]
    )
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("artifacts")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Angelic Intervention", auto=True, targets=[bears])


def test_giver_of_runes_grants_protection_from_colorless() -> None:
    scenario = _board(alice=["Giver of Runes", "Grizzly Bears"])
    giver = scenario.creature("Giver of Runes")
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("colorless")

    scenario.activate(giver, targets=[bears])
    _resolve_stack(scenario)

    assert computed(scenario).of(bears).has_ability("Protection from colorless")
    assert bears.counters[Counter.PLUS_ONE] == 0
    assert notices(scenario) == []


def test_giver_of_runes_can_still_name_a_color() -> None:
    scenario = _board(alice=["Giver of Runes", "Grizzly Bears"])
    giver = scenario.creature("Giver of Runes")
    bears = scenario.creature("Grizzly Bears")
    scenario.will_choose("B")

    scenario.activate(giver, targets=[bears])
    _resolve_stack(scenario)

    assert computed(scenario).of(bears).has_ability("Protection from black")


def test_giver_of_runes_cannot_target_itself() -> None:
    scenario = _board(alice=["Giver of Runes"])
    giver = scenario.creature("Giver of Runes")

    with pytest.raises(ValueError):
        scenario.activate(giver, targets=[giver])


# -- poison counters ----------------------------------------------------------------


def test_infectious_bite_bites_and_poisons_the_opponent() -> None:
    scenario = _board(hand=["Infectious Bite"], alice=["Grizzly Bears"], lands=["Forest"] * 2)
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    scenario.cast_and_resolve("Infectious Bite", auto=True, targets=[bears, runeclaw])
    scenario.state_based_actions()

    assert runeclaw.zone is Zone.GRAVEYARD
    assert bears.damage == 0, "a bite is one-sided"
    assert scenario.player("bob").counters[Counter.POISON] == 1
    assert scenario.player("alice").counters[Counter.POISON] == 0
    assert notices(scenario) == []


def test_the_tenth_poison_counter_loses_the_game() -> None:
    """CR 704.5c."""
    scenario = _board(hand=["Prologue to Phyresis"], lands=["Island"] * 2)
    scenario.game.add_player_counters(scenario.player("bob"), Counter.POISON, 9)

    scenario.cast_and_resolve("Prologue to Phyresis", auto=True)
    scenario.state_based_actions()

    assert "bob" in scenario.game.losers


def test_prologue_to_phyresis_poisons_and_draws() -> None:
    scenario = _board(hand=["Prologue to Phyresis"], lands=["Island"] * 2)

    scenario.cast_and_resolve("Prologue to Phyresis", auto=True)

    assert scenario.player("bob").counters[Counter.POISON] == 1
    assert len(scenario.player().hand) == 1
    assert notices(scenario) == []


def test_infectious_inquiry_draws_loses_life_and_poisons() -> None:
    scenario = _board(hand=["Infectious Inquiry"], lands=["Swamp"] * 3)

    scenario.cast_and_resolve("Infectious Inquiry", auto=True)

    assert len(scenario.player().hand) == 2
    assert scenario.player().life == 18
    assert scenario.player("bob").counters[Counter.POISON] == 1
    assert scenario.player().counters[Counter.POISON] == 0
    assert notices(scenario) == []
