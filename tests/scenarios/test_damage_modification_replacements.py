"""Replacement effects that modify damage as it would be dealt (CR 614.1a,
CR 614.2, CR 616.1).

- "If a source you control would deal noncombat damage to an opponent or a
  permanent an opponent controls, instead it deals that much damage plus X,
  where X is Hawkeye's power." (Hawkeye, Young Avenger) - Torbran, Thane of
  Red Fell's "... it deals that much damage plus 2 instead." is the second
  printing of the template; the "plus X, where X is `<this>`'s power" amount
  is printed on no other card and is read as the replacement applies. When
  both apply to one event, CR 616.1 lets the affected player or the
  controller of the affected object choose the order - for two additions
  the result is the same either way.
- "If damage would be dealt to Wolverine, instead that damage is dealt, but
  all other damage already dealt to him is healed." (Wolverine, Fierce
  Fighter) - damage already marked (CR 120.3e) is removed as the new damage
  is dealt; damage dealt simultaneously with it (CR 510.2's one combat
  damage event) is not "already dealt" and stays.
- "If a noncreature source you control would deal damage to a creature,
  battle, or opponent, it deals that much damage plus 2 instead." (Invasion
  of Regatha // Disciples of the Inferno, the same template's "quality" read
  as CR 205.2a's plain negation of a card type - `Game._negated_card_type_
  named` - rather than a color the way Torbran's "red source" is) and its own
  recipient list ("a creature, battle, or opponent", `_DAMAGE_RECIPIENTS` in
  `machines/replacement.py`) parsed off the correct comma-split (see that
  module's `_try_source_damage_plus_recipient_list`'s own docstring for why
  the ordinary `_IF_WOULD` splitter misreads this specific sentence's
  internal Oxford-comma recipient list).

CR numbers verified this session with `mise run rules:find`:

- **CR 609.7b** - a source's properties are checked as damage would be dealt.
- **CR 702.16a** - a quality can be "any characteristic value or information".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _bolt(scenario, target, mountain="Mountain", username="alice"):
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources(mountain, username=username),
        username=username,
        targets=[target],
    )


# -- Hawkeye -----------------------------------------------------------------------


def test_hawkeye_adds_his_power_to_noncombat_damage_to_an_opponent():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 2


def test_hawkeye_adds_his_power_to_damage_to_an_opponents_creature():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    giant_damage_before = giant.damage
    _bolt(scenario, giant)
    assert giant.zone is Zone.GRAVEYARD or giant.damage - giant_damage_before == 5


def test_hawkeye_leaves_damage_to_your_own_permanents_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Hawkeye, Young Avenger", "Snapping Sailback", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sailback = scenario.creature("Snapping Sailback", "alice")
    _bolt(scenario, sailback)
    assert sailback.damage == 3


def test_hawkeye_does_not_touch_combat_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hawkeye, Young Avenger", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.combat_damage()
    assert scenario.player("bob").life == 18


def test_hawkeye_reads_his_power_as_the_damage_is_dealt():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Hawkeye, Young Avenger", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hawkeye = scenario.creature("Hawkeye, Young Avenger", "alice")
    hawkeye.add_counters("+1/+1", 3)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 5


def test_an_opponents_source_is_not_one_you_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hawkeye, Young Avenger"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.deal_damage(
        scenario.player("alice"), 3, source=scenario.creature("Hill Giant", "bob")
    )
    assert scenario.player("alice").life == 17


def test_hawkeye_and_torbran_both_add():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Hawkeye, Young Avenger", "Torbran, Thane of Red Fell", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 2 - 2


def test_torbran_adds_two_to_a_red_source():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Torbran, Thane of Red Fell", "Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 15


# -- Wolverine ---------------------------------------------------------------------


def test_wolverine_heals_old_damage_as_new_damage_is_dealt():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.deal_damage(wolverine, 3, source=giant)
    assert wolverine.damage == 3
    scenario.game.deal_damage(wolverine, 4, source=giant)
    scenario.state_based_actions()

    assert wolverine.zone is Zone.BATTLEFIELD, "only the 4 remains - toughness 5"
    assert wolverine.damage == 4


def test_wolverine_still_dies_to_one_lethal_hit():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    scenario.game.deal_damage(wolverine, 5, source=scenario.creature("Hill Giant", "bob"))
    scenario.state_based_actions()
    assert wolverine.zone is Zone.GRAVEYARD


def test_simultaneous_combat_damage_is_not_already_dealt():
    """CR 510.2: two blockers' damage is dealt at once, so neither heals the
    other - 3 and 3 is 6 damage to a toughness-5 Wolverine."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", battlefield=["Hill Giant", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    first, second = scenario.creatures("Hill Giant", "Hill Giant", username="bob")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(wolverine)
    scenario.advance()
    scenario.block(wolverine, first, second)
    scenario.advance()
    scenario.will_assign_combat_damage((first, 3))
    scenario.combat_damage()
    scenario.state_based_actions()
    assert wolverine.zone is Zone.GRAVEYARD


def test_damage_from_an_earlier_step_is_healed_by_a_later_hit():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wolverine, Fierce Fighter"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Hill Giant", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolverine = scenario.creature("Wolverine, Fierce Fighter", "alice")
    scenario.game.deal_damage(wolverine, 4, source=scenario.creature("Hill Giant", "bob"))
    scenario.game.deal_damage(wolverine, 3, source=scenario.creature("Hill Giant", "bob"))
    scenario.state_based_actions()
    assert wolverine.damage == 3
    assert wolverine.zone is Zone.BATTLEFIELD


@pytest.mark.parametrize(
    "name",
    [
        "Hawkeye, Young Avenger",
        "Wolverine, Fierce Fighter",
        "Torbran, Thane of Red Fell",
        "Invasion of Regatha",
    ],
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


# -- Invasion of Regatha // Disciples of the Inferno --------------------------------


def _disciples_of_the_inferno(scenario):
    """Stages Disciples of the Inferno face up directly (`transform_permanent`,
    the same staging technique `test_transforms_into_trigger.py` and its
    siblings already use), sidestepping the Siege's own front-face "another
    target battle or opponent" ETB trigger entirely - a different, already-
    `handled` clause this file is not about. `Invasion of Regatha` is already
    on the battlefield (a battle enters with its printed defense, CR 310.4b -
    irrelevant here), so this only flips its face."""
    siege = scenario.creature("Invasion of Regatha", "alice")
    transform_permanent(scenario.game, siege)
    assert siege.name == "Disciples of the Inferno"
    return siege


def test_disciples_adds_two_to_noncreature_damage_to_an_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Invasion of Regatha", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _disciples_of_the_inferno(scenario)
    mountain = scenario.creature("Mountain", "alice")

    scenario.game.deal_damage(scenario.player("bob"), 3, source=mountain)

    assert scenario.player("bob").life == 20 - 3 - 2


def test_disciples_adds_two_to_noncreature_damage_to_a_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Invasion of Regatha", "Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _disciples_of_the_inferno(scenario)
    mountain = scenario.creature("Mountain", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.game.deal_damage(giant, 1, source=mountain)

    assert giant.damage == 1 + 2


def test_disciples_does_not_boost_damage_from_a_creature_source():
    """The source is "a noncreature source" (CR 205.2a's negation of Type.
    CREATURE): Disciples' own combat damage, dealt by a creature, is
    unaffected - a creature never doubles its own bite."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Invasion of Regatha", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _disciples_of_the_inferno(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.deal_damage(scenario.player("bob"), 2, source=bears)

    assert scenario.player("bob").life == 20 - 2


def test_disciples_adds_two_to_noncreature_damage_to_a_battle():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Invasion of Regatha", "Invasion of Zendikar", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _disciples_of_the_inferno(scenario)
    mountain = scenario.creature("Mountain", "alice")
    zendikar = scenario.creature("Invasion of Zendikar", "alice")
    starting_defense = zendikar.counter_count("defense")

    scenario.game.deal_damage(zendikar, 1, source=mountain)

    assert zendikar.counter_count("defense") == starting_defense - (1 + 2)
