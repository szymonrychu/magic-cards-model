"""Scenario: "Choose a counter on target <object>. Put another counter of that
kind on it." - one counter kind is chosen among the kinds the target already
has, and one more counter of exactly that kind goes on it.

Printings (oracle text read from the pool this session):

- Dathon, His Heart Open (TRK): "{2}: Choose a counter on target enchantment
  you control. Put another counter of that kind on it. Activate only as a
  sorcery."
- Ichormoon Gauntlet (ONE, proof printing: Modern legal, not a listed card):
  "Whenever you cast a noncreature spell, choose a counter on target
  permanent. Put an additional counter of that kind on that permanent." - a
  trigger, "additional", and the object named again as "that permanent".
- Animation Module (KLD, proof printing): "{3}, {T}: Choose a counter on
  target permanent or player. Give that permanent or player another counter
  of that kind." - "give", and a player as a legal target.

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 122.1** - counters with the same name are interchangeable, so the
  "kind" is the name.
- **CR 122.6 / 122.6a** - giving a counter is putting one (replacement effects
  such as Hardened Scales apply), and the ability's controller puts it.
- **CR 608.2d** - the choice is made as the ability resolves, by its
  controller, and cannot be an illegal option: a kind the target has none of.
- **CR 608.2b** - a target that went illegal is not affected.
- **CR 602.5d** - "Activate only as a sorcery".
- **CR 107.15a** - a lore counter put on a Saga triggers the chapter it
  reaches.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

DATHON = "Dathon, His Heart Open"


def _dathon_board(*, alice=("Furnace of Rath",), bob=()) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[DATHON, "Forest", "Forest", *alice])
        .player("bob", battlefield=list(bob))
    )


def _activate_dathon(scenario, target):
    dathon = scenario.creature(DATHON, "alice")
    dathon.summoning_sick = False
    scenario.activate(dathon, *scenario.untapped_sources("Forest", "Forest"), targets=[target])


def _enchantment(scenario, name="Furnace of Rath", username="alice"):
    return scenario.find(name, Zone.BATTLEFIELD, username)


# -- Dathon: the activated, one-target, sorcery-speed form ----------------------


def test_the_only_kind_present_gets_one_more_without_a_question():
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 2)

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    assert furnace.counter_count("oil") == 3
    assert scenario.questions_asked() == []


def test_the_chosen_kind_is_the_only_one_that_grows():
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 2)
    furnace.add_counters("shield", 1)
    scenario.will_choose("shield")

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    assert furnace.counter_count("shield") == 2
    assert furnace.counter_count("oil") == 2


def test_choosing_the_other_kind_grows_that_one_instead():
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 2)
    furnace.add_counters("shield", 1)
    scenario.will_choose("oil")

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    assert furnace.counter_count("oil") == 3
    assert furnace.counter_count("shield") == 1


def test_the_question_lists_exactly_the_kinds_on_the_target_and_goes_to_its_controller():
    """CR 608.2d: no option the target cannot support (a kind it lacks)."""
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 1)
    furnace.add_counters("shield", 1)
    scenario.will_choose("oil")

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    (question,) = scenario.questions_asked()
    assert set(question.options) == {"oil", "shield"}
    assert question.player == "alice"


def test_a_kind_the_target_does_not_have_is_refused():
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 1)
    furnace.add_counters("shield", 1)
    scenario.will_choose("stun")

    _activate_dathon(scenario, furnace)
    with pytest.raises(ValueError):
        scenario.resolve_top()


def test_a_target_with_no_counters_gets_nothing_and_asks_nothing():
    """There is nothing to choose, so there is no kind to add another of."""
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    assert dict(furnace.counters.counts) == {}
    assert scenario.questions_asked() == []


def test_only_one_counter_is_added_not_one_per_kind():
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 1)
    furnace.add_counters("shield", 1)
    furnace.add_counters("stun", 1)
    scenario.will_choose("stun")

    _activate_dathon(scenario, furnace)
    scenario.resolve_top()

    assert sum(furnace.counters.counts.values()) == 4


def test_an_enchantment_the_opponent_controls_is_not_a_legal_target():
    scenario = _dathon_board(bob=("Furnace of Rath",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = _enchantment(scenario, username="bob")
    theirs.add_counters("oil", 1)

    with pytest.raises(ValueError):
        _activate_dathon(scenario, theirs)


def test_a_creature_is_not_a_legal_target():
    scenario = _dathon_board(alice=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)

    with pytest.raises(ValueError):
        _activate_dathon(scenario, bears)


def test_the_ability_is_sorcery_speed():
    """CR 602.5d."""
    scenario = _dathon_board().build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    dathon = scenario.creature(DATHON, "alice")
    dathon.summoning_sick = False

    assert scenario.why_cannot_activate(dathon) is not None


def test_a_target_gone_by_resolution_gets_nothing():
    """CR 608.2b: the only target is illegal, so the ability does nothing."""
    scenario = _dathon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    furnace = _enchantment(scenario)
    furnace.add_counters("oil", 1)

    _activate_dathon(scenario, furnace)
    scenario.game.put_into_graveyard(furnace)
    scenario.resolve_top()

    assert furnace.zone is Zone.GRAVEYARD
    assert furnace.counter_count("oil") == 0
    assert scenario.questions_asked() == []


def test_a_lore_counter_given_to_a_saga_triggers_the_chapter_it_reaches():
    """CR 107.15a: Dathon's counter is a lore counter put on the Saga."""
    scenario = _dathon_board(alice=("History of Benalia",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = _enchantment(scenario, "History of Benalia")
    assert saga.counter_count("lore") == 1  # the one it entered with

    _activate_dathon(scenario, saga)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()

    assert saga.counter_count("lore") == 2
    assert any("History of Benalia" in name for name in scenario.stack_names())


# -- Ichormoon Gauntlet: the triggered form, "additional ... that permanent" ------


def _gauntlet_board(*, alice=("Grizzly Bears",), bob=()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Shock", "Grizzly Bears"],
            battlefield=["Ichormoon Gauntlet", "Mountain", "Forest", "Forest", *alice],
        )
        .player("bob", battlefield=list(bob))
    )


def _cast_shock(scenario, target, chosen):
    scenario.choose_trigger_targets("Ichormoon Gauntlet", [chosen])
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Shock", mountain, targets=[target])


def test_a_noncreature_spell_puts_an_additional_counter_of_the_chosen_kind():
    scenario = _gauntlet_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    bears.add_counters("shield", 1)
    scenario.will_choose("shield")

    _cast_shock(scenario, "bob", bears)
    assert scenario.stack_names()[-1] == "Ichormoon Gauntlet's triggered ability"
    scenario.resolve_top()

    assert bears.counter_count("shield") == 2
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_the_trigger_resolves_before_the_spell_that_caused_it():
    scenario = _gauntlet_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("oil", 1)

    _cast_shock(scenario, "bob", bears)
    scenario.resolve_top()

    assert scenario.stack_names() == ["Shock"]
    assert bears.counter_count("oil") == 2


def test_a_creature_spell_does_not_trigger_it():
    scenario = _gauntlet_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_onto_stack("Grizzly Bears", forest, forest2)

    assert scenario.stack_names() == ["Grizzly Bears"]


def test_an_opponents_permanent_may_be_the_target():
    scenario = _gauntlet_board(bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters("oil", 3)

    _cast_shock(scenario, "bob", theirs)
    scenario.resolve_top()

    assert theirs.counter_count("oil") == 4


def test_a_permanent_with_no_counters_gets_nothing():
    scenario = _gauntlet_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_shock(scenario, "bob", bears)
    scenario.resolve_top()

    assert dict(bears.counters.counts) == {}
    assert scenario.questions_asked() == []


def test_hardened_scales_sees_the_counter_being_put():
    """CR 122.6: an additional counter is a counter put on the creature, so
    Hardened Scales makes the +1/+1 one two."""
    scenario = _gauntlet_board(alice=("Grizzly Bears", "Hardened Scales")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)

    _cast_shock(scenario, "bob", bears)
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_a_player_is_not_a_legal_target_of_a_permanent_only_trigger():
    scenario = _gauntlet_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("bob").add_counters(Counter.POISON, 1)

    with pytest.raises(ValueError, match="cannot target the player"):
        scenario.choose_trigger_targets("Ichormoon Gauntlet", ["bob"])


# -- Animation Module: "give ... that permanent or player", players included ------


def _module_board(*, bob=("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Animation Module", "Forest", "Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=list(bob))
    )


def _activate_module(scenario, target):
    module = scenario.find("Animation Module", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        module, *scenario.untapped_sources("Forest", "Forest", "Forest"), targets=[target]
    )


def test_a_player_is_given_another_counter_of_the_chosen_kind():
    scenario = _module_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bob.add_counters(Counter.POISON, 3)
    bob.add_counters(Counter.ENERGY, 1)
    scenario.will_choose(str(Counter.POISON))

    _activate_module(scenario, bob)
    scenario.resolve_top()

    assert bob.counter_count(Counter.POISON) == 4
    assert bob.counter_count(Counter.ENERGY) == 1


def test_a_player_with_only_one_kind_is_given_it_without_a_question():
    scenario = _module_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bob.add_counters(Counter.ENERGY, 2)

    _activate_module(scenario, bob)
    scenario.resolve_top()

    assert bob.counter_count(Counter.ENERGY) == 3
    assert scenario.questions_asked() == []


def test_a_player_with_no_counters_gets_nothing():
    scenario = _module_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    _activate_module(scenario, bob)
    scenario.resolve_top()

    assert dict(bob.counters.counts) == {}


def test_a_permanent_is_given_another_counter_of_the_chosen_kind():
    scenario = _module_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters(Counter.PLUS_ONE, 1)
    theirs.add_counters("oil", 1)
    scenario.will_choose("oil")

    _activate_module(scenario, theirs)
    scenario.resolve_top()

    assert theirs.counter_count("oil") == 2
    assert theirs.counter_count(Counter.PLUS_ONE) == 1
