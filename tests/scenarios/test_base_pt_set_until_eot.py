"""Triggered abilities that set a creature's *base* power and toughness until
end of turn (CR 613.4b: "Effects that refer to the base power and/or
toughness of a creature apply in this layer" - sublayer 7b).

Three printings, three wordings of the one mechanic:

- Galion, Elvenking's Butler: "Whenever Galion attacks, choose up to one
  other target creature you control. Its base power and toughness become
  equal to Galion's power and toughness until end of turn." - a copied value,
  read once as the ability resolves (CR 608.2h: information from a specific
  object is its current information), then fixed.
- Mirkwood Meditator: "Landfall - Whenever a land you control enters, you may
  have this creature's base power and toughness become 4/2 until end of
  turn." - a printed value, optional (CR 608.2d), on the source itself.
- Eldrazi Mimic (the off-set proof, not a listed card and in no deck list):
  "Whenever another colorless creature you control enters, you may have this
  creature's base power and toughness become equal to that creature's power
  and toughness until end of turn." - optional, on the source, copying the
  triggering creature.

Sublayer 7b comes before 7c (CR 613.4b before CR 613.4c), so a +1/+1 counter
or a pump still applies on top of the new base whichever came first.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _pt(scenario, creature):
    return scenario.game.computed_board().of(creature).power_toughness


# -- Galion, Elvenking's Butler -------------------------------------------


def _galion_attacks(scenario, *, target):
    galion = scenario.creature("Galion, Elvenking's Butler", "alice")
    scenario.choose_trigger_targets("Galion, Elvenking's Butler", [target] if target else [])
    scenario.attack_with(galion)
    scenario.pass_until_resolved()
    return galion


def test_galion_gives_another_creature_its_own_base_power_and_toughness():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Galion, Elvenking's Butler", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    _galion_attacks(scenario, target=bears)

    assert _pt(scenario, bears) == (4, 4)


def test_galions_values_are_read_once_and_do_not_follow_a_later_pump():
    """CR 608.2h: Galion's power and toughness are read as the ability
    resolves. A Giant Growth on Galion afterwards grows Galion, not the Bears."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Galion, Elvenking's Butler", "Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    galion = _galion_attacks(scenario, target=bears)

    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[galion]
    )

    assert _pt(scenario, galion) == (7, 7)
    assert _pt(scenario, bears) == (4, 4)


def test_galions_current_power_and_toughness_are_what_is_copied():
    """A pump already on Galion when the trigger resolves is part of the
    value copied - it is Galion's power and toughness, not its printed box."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Galion, Elvenking's Butler", "Grizzly Bears", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    galion = scenario.creature("Galion, Elvenking's Butler", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[galion]
    )

    scenario.start_at(Step.DECLARE_ATTACKERS)
    _galion_attacks(scenario, target=bears)

    assert _pt(scenario, bears) == (7, 7)


def test_a_counter_on_the_target_still_applies_on_top_of_the_new_base():
    """7b sets, 7c adds: a +1/+1 counter lands on the new 4/4 base."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Galion, Elvenking's Butler", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)

    _galion_attacks(scenario, target=bears)

    assert _pt(scenario, bears) == (5, 5)


def test_galions_effect_ends_at_cleanup():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Galion, Elvenking's Butler", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    _galion_attacks(scenario, target=bears)
    assert _pt(scenario, bears) == (4, 4)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert _pt(scenario, bears) == (2, 2)


def test_galion_choosing_no_target_changes_nothing():
    """ "up to one" (CR 115.6): zero targets is a legal choice."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Galion, Elvenking's Butler", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    galion = _galion_attacks(scenario, target=None)

    assert _pt(scenario, bears) == (2, 2)
    assert _pt(scenario, galion) == (4, 4)


# -- Mirkwood Meditator -----------------------------------------------------


def test_mirkwood_meditator_becomes_a_four_two_when_its_controller_says_yes():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Mirkwood Meditator"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meditator = scenario.creature("Mirkwood Meditator", "alice")
    assert _pt(scenario, meditator) == (2, 4)

    scenario.will_take_the_may(True)
    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    assert _pt(scenario, meditator) == (4, 2)


def test_mirkwood_meditator_stays_a_two_four_when_declined():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Mirkwood Meditator"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meditator = scenario.creature("Mirkwood Meditator", "alice")

    scenario.will_take_the_may(False)
    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    assert _pt(scenario, meditator) == (2, 4)


def test_mirkwood_meditator_counter_applies_on_top_and_the_effect_ends_at_cleanup():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Mirkwood Meditator"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meditator = scenario.creature("Mirkwood Meditator", "alice")
    scenario.game.add_counters(meditator, Counter.PLUS_ONE, 1)

    scenario.will_take_the_may(True)
    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    assert _pt(scenario, meditator) == (5, 3)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    assert _pt(scenario, meditator) == (3, 5)


def test_an_opponents_land_does_not_trigger_landfall():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mirkwood Meditator"])
        .player("bob", hand=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meditator = scenario.creature("Mirkwood Meditator", "alice")

    scenario.put_onto_battlefield("Forest", "bob")

    assert scenario.pending_triggers == []
    assert _pt(scenario, meditator) == (2, 4)


# -- Eldrazi Mimic (off-set proof) ------------------------------------------


def test_eldrazi_mimic_copies_the_entering_colorless_creatures_power_and_toughness():
    scenario = (
        Scenario()
        .player("alice", hand=["Reality Smasher"], battlefield=["Eldrazi Mimic"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mimic = scenario.creature("Eldrazi Mimic", "alice")
    assert _pt(scenario, mimic) == (2, 1)

    scenario.will_take_the_may(True, source="Eldrazi Mimic")
    scenario.put_onto_battlefield("Reality Smasher", "alice")
    scenario.pass_until_resolved()

    assert _pt(scenario, mimic) == (5, 5)


def test_eldrazi_mimic_declined_stays_a_two_one():
    scenario = (
        Scenario()
        .player("alice", hand=["Memnite"], battlefield=["Eldrazi Mimic"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mimic = scenario.creature("Eldrazi Mimic", "alice")

    scenario.will_take_the_may(False, source="Eldrazi Mimic")
    scenario.put_onto_battlefield("Memnite", "alice")
    scenario.pass_until_resolved()

    assert _pt(scenario, mimic) == (2, 1)


def test_eldrazi_mimic_ignores_a_colored_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Eldrazi Mimic"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mimic = scenario.creature("Eldrazi Mimic", "alice")

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert scenario.pending_triggers == []
    assert _pt(scenario, mimic) == (2, 1)


def test_eldrazi_mimic_copies_a_small_creature_downward_too():
    """ "become equal to" sets, it does not take the larger value: Memnite's
    1/1 makes the Mimic a 1/1."""
    scenario = (
        Scenario()
        .player("alice", hand=["Memnite"], battlefield=["Eldrazi Mimic"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mimic = scenario.creature("Eldrazi Mimic", "alice")

    scenario.will_take_the_may(True, source="Eldrazi Mimic")
    scenario.put_onto_battlefield("Memnite", "alice")
    scenario.pass_until_resolved()

    assert _pt(scenario, mimic) == (1, 1)
