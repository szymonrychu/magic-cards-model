"""Flood counters: a land that is an Island for as long as it has one, and
what counts those lands.

One mechanic, three abilities of Eluge, the Shoreless Sea:

- "Eluge's power and toughness are each equal to the number of Islands you
  control." - a characteristic-defining ability (CR 604.3), sublayer 7a
  (CR 613.4a), counting Islands on the board as layer 4 (CR 613.1d) has left
  it, so a flooded land counts.
- "Whenever Eluge enters or attacks, put a flood counter on target land. It's
  an Island in addition to its other types for as long as it has a flood
  counter on it." - a layer 4 type-adding effect (CR 205.1b "in addition to")
  with a "for as long as" duration (CR 611.2b): it ends when the counter goes
  and does not begin again. The land gains the Island's intrinsic mana
  ability (CR 305.6).
- "The first instant or sorcery spell you cast each turn costs {U} (or {1})
  less to cast for each land you control with a flood counter on it." - a cost
  reduction applied as the total cost is determined (CR 601.2f); a {U}
  reduction the cost has no {U} for reduces generic mana instead (CR 118.7b,
  118.7c).

Every CR number in this file was read with `mise run rules:find` in the
session that wrote it.

Proof printings (Scryfall legality checked 2026-09-23, none in an api deck):
Dungrove Elder (Modern) for the subtype-count CDA; Aquitect's Will (Modern)
for "put a flood counter on target land. That land is an Island ... for as
long as it has a flood counter on it"; Melek, Reforged Researcher (Modern,
Pioneer, Standard) for "the first instant or sorcery spell you cast each turn
costs ... less" (and its own graveyard-count CDA); Mindsplice Apparatus
(Modern, Pioneer) for a spell-type cost reduction "for each" count;
Armorcraft Judge (Modern, Pioneer) for "for each creature you control with a
+1/+1 counter on it", the counter-qualified count Eluge's reduction reads.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

ELUGE = "Eluge, the Shoreless Sea"


def _pt(scenario: Scenario, permanent) -> tuple[int | None, int | None]:
    return scenario.game.characteristics_of(permanent).power_toughness


def _subtypes(scenario: Scenario, permanent) -> tuple[str, ...]:
    return scenario.game.characteristics_of(permanent).subtypes


def _flood(scenario: Scenario, land) -> None:
    scenario.game.add_counters(land, "flood", 1)


# --------------------------------------------------------------------------
# The characteristic-defining ability
# --------------------------------------------------------------------------


def test_eluge_is_as_big_as_the_islands_you_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ELUGE, "Island", "Island", "Breeding Pool", "Forest"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    # Breeding Pool is a Forest Island (CR 205.3i); bob's Island is not alice's.
    assert _pt(scenario, scenario.creature(ELUGE, "alice")) == (3, 3)


def test_eluge_with_no_island_is_zero_zero_and_dies():
    """CR 704.5f: toughness 0 is put into its owner's graveyard."""
    scenario = Scenario().player("alice", battlefield=[ELUGE, "Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eluge = scenario.creature(ELUGE, "alice")

    assert _pt(scenario, eluge) == (0, 0)
    scenario.state_based_actions()
    assert eluge.zone is Zone.GRAVEYARD


def test_dungrove_elder_counts_forests():
    """Dungrove Elder (proof printing): "power and toughness are each equal to
    the number of Forests you control"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dungrove Elder", "Forest", "Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _pt(scenario, scenario.creature("Dungrove Elder", "alice")) == (2, 2)


# --------------------------------------------------------------------------
# The flood counter
# --------------------------------------------------------------------------


def _eluge_cast(extra: list[str] | None = None) -> tuple[Scenario, object]:
    """Alice casts Eluge ({1}{U}{U}{U}) off three Islands and a Mountain; its
    enters trigger floods her Forest."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ELUGE],
            library=["Island"] * 3,
            battlefield=["Island", "Island", "Island", "Mountain", "Forest", *(extra or [])],
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets(ELUGE, [forest])
    sources = scenario.untapped_sources("Island", "Island", "Island", "Mountain")
    scenario.cast_and_resolve(ELUGE, *sources)
    scenario.resolve_top()
    return scenario, forest


def test_entering_floods_a_land_that_becomes_an_island_as_well():
    """The Forest keeps being a Forest and is an Island too (CR 205.1b)."""
    scenario, forest = _eluge_cast()

    assert forest.counters["flood"] == 1
    assert "Island" in _subtypes(scenario, forest)
    assert "Forest" in _subtypes(scenario, forest)


def test_the_flooded_land_counts_for_eluge():
    """Three Islands plus the flooded Forest: Eluge is 4/4 (layer 4 before 7a)."""
    scenario, _forest = _eluge_cast()

    assert _pt(scenario, scenario.creature(ELUGE, "alice")) == (4, 4)


def test_the_flooded_land_taps_for_blue():
    """CR 305.6: an Island has "{T}: Add {U}."."""
    scenario, forest = _eluge_cast()

    abilities = scenario.game.activated_abilities(forest)
    (blue,) = [i for i, ability in enumerate(abilities) if "{U}" in ability.text]

    scenario.activate(forest, index=blue)

    assert scenario.player("alice").mana_pool.floating[Color.BLUE] == 1


def test_the_island_lasts_only_while_the_counter_does():
    """CR 611.2b: once the last flood counter is gone the effect ends, and a
    flood counter put back later by something else does not restart it."""
    scenario, forest = _eluge_cast()

    forest.remove_counters("flood", 1)
    assert "Island" not in _subtypes(scenario, forest)
    assert _pt(scenario, scenario.creature(ELUGE, "alice")) == (3, 3)

    _flood(scenario, forest)
    assert "Island" not in _subtypes(scenario, forest)


def test_the_island_outlasts_eluge():
    """The duration is the counter's, not Eluge's: destroying Eluge leaves the
    Forest an Island."""
    scenario, forest = _eluge_cast()

    scenario.game.destroy(scenario.creature(ELUGE, "alice"))

    assert "Island" in _subtypes(scenario, forest)


def test_attacking_floods_another_land():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ELUGE, "Island", "Mountain"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.game.begin_turn_for("alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    eluge = scenario.creature(ELUGE, "alice")
    assert _pt(scenario, eluge) == (1, 1)
    scenario.choose_trigger_targets(ELUGE, [mountain])

    scenario.attack_with(eluge)
    scenario.resolve_top()

    assert "Island" in _subtypes(scenario, mountain)
    assert _pt(scenario, eluge) == (2, 2)


def test_aquitects_will_floods_and_draws_with_a_merfolk():
    """Aquitect's Will (proof printing): the same flood, then "If you control a
    Merfolk, draw a card."."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aquitect's Will"],
            library=["Island"] * 3,
            battlefield=["Island", "Plains", "Merfolk Looter"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Aquitect's Will", *scenario.untapped_sources("Island"), targets=[plains]
    )

    assert plains.counters["flood"] == 1
    assert "Island" in _subtypes(scenario, plains)
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


def test_aquitects_will_without_a_merfolk_floods_but_draws_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aquitect's Will"],
            library=["Island"] * 3,
            battlefield=["Island", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")

    scenario.cast_and_resolve(
        "Aquitect's Will", *scenario.untapped_sources("Island"), targets=[plains]
    )

    assert "Island" in _subtypes(scenario, plains)
    assert len(scenario.player("alice").hand) == 0


# --------------------------------------------------------------------------
# The cost reduction
# --------------------------------------------------------------------------


def _reduction_board(*, flooded: int, hand: list[str], bob: list[str] | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            library=["Island"] * 5,
            battlefield=[ELUGE, "Island", "Island", "Mountain", "Mountain", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5, battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for forest in [p for p in scenario.game.battlefield if p.name == "Forest"][:flooded]:
        _flood(scenario, forest)
    return scenario


def test_two_flooded_lands_take_the_first_spell_to_nothing():
    """Anticipate {1}{U}: one {U} comes off the blue pip, the other off the
    generic (CR 118.7c) - {0}."""
    scenario = _reduction_board(flooded=2, hand=["Anticipate"])

    casting = scenario.cast("Anticipate")

    assert casting.total_cost.mana.converted == 0


def test_one_flooded_land_takes_one_blue_off():
    scenario = _reduction_board(flooded=1, hand=["Anticipate"])

    casting = scenario.cast("Anticipate")

    assert casting.total_cost.mana == ManaCost.parse("{1}")


def test_a_cost_with_no_blue_loses_generic_instead():
    """CR 118.7b: Pyretic Ritual {1}{R} does not require {U}, so the {U}
    reduction takes {1}."""
    scenario = _reduction_board(flooded=1, hand=["Pyretic Ritual"])

    casting = scenario.cast("Pyretic Ritual")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_no_flooded_land_no_reduction():
    scenario = _reduction_board(flooded=0, hand=["Anticipate"])

    assert scenario.cast("Anticipate").total_cost.mana == ManaCost.parse("{1}{U}")


def test_only_the_first_instant_or_sorcery_each_turn():
    """The second instant this turn pays in full."""
    scenario = _reduction_board(flooded=2, hand=["Anticipate", "Opt"])
    scenario.cast_and_resolve("Anticipate")
    scenario.will_choose_top(times=None)

    casting = scenario.cast("Opt")

    assert casting.total_cost.mana == ManaCost.parse("{U}")


def test_a_creature_spell_neither_benefits_nor_uses_it_up():
    """A creature is not an instant or sorcery: Grizzly Bears pays {1}{G},
    and the Anticipate cast after it is still the first - {0}."""
    scenario = _reduction_board(flooded=2, hand=["Grizzly Bears", "Anticipate"])

    bears = scenario.cast("Grizzly Bears")
    assert bears.total_cost.mana == ManaCost.parse("{1}{G}")
    scenario.pay_with(bears.begin_paying(), *scenario.untapped_sources("Forest", "Mountain"))
    scenario.put_on_stack(bears)
    scenario.resolve_top()

    assert scenario.cast("Anticipate").total_cost.mana.converted == 0


def test_the_opponent_gets_no_reduction_from_alices_flooded_lands():
    """ "You cast" and "you control": bob's Anticipate pays full price."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 5,
            battlefield=[ELUGE, "Island", "Forest", "Forest"],
        )
        .player("bob", hand=["Anticipate"], library=["Island"] * 5, battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for forest in [p for p in scenario.game.battlefield if p.name == "Forest"]:
        _flood(scenario, forest)
    scenario.pass_priority("alice")

    casting = scenario.cast("Anticipate", username="bob")

    assert casting.total_cost.mana == ManaCost.parse("{1}{U}")


def test_lands_flooded_under_an_opponents_control_do_not_count():
    scenario = _reduction_board(flooded=0, hand=["Anticipate"], bob=["Forest", "Forest"])
    for forest in [p for p in scenario.game.battlefield if p.controller == "bob"]:
        _flood(scenario, forest)

    assert scenario.cast("Anticipate").total_cost.mana == ManaCost.parse("{1}{U}")


def test_melek_first_instant_or_sorcery_costs_three_less():
    """Melek, Reforged Researcher (proof printing): "The first instant or
    sorcery spell you cast each turn costs {3} less to cast." - a generic
    reduction with no count. Stock Up {2}{U} costs {U}; the next, Anticipate,
    full price."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stock Up", "Anticipate"],
            library=["Island"] * 8,
            battlefield=["Melek, Reforged Researcher", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    stock_up = scenario.cast("Stock Up")
    assert stock_up.total_cost.mana == ManaCost.parse("{U}")
    scenario.pay_with(stock_up.begin_paying(), *scenario.untapped_sources("Island"))
    scenario.will_choose_cards(*scenario.top_of_library(2))
    scenario.put_on_stack(stock_up)
    scenario.resolve_top()

    assert scenario.cast("Anticipate").total_cost.mana == ManaCost.parse("{1}{U}")


def test_melek_is_twice_the_instants_and_sorceries_in_your_graveyard():
    """Melek's own CDA: two instant/sorcery cards in the graveyard make it
    4/4; a land card there does not count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Melek, Reforged Researcher"],
            graveyard=["Opt", "Ponder", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _pt(scenario, scenario.creature("Melek, Reforged Researcher", "alice")) == (4, 4)


def test_mindsplice_apparatus_reduces_every_instant_per_oil_counter():
    """Mindsplice Apparatus (proof printing): "Instant and sorcery spells you
    cast cost {1} less to cast for each oil counter on this artifact." - not
    only the first: two oil counters take {2} off both spells."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stock Up", "Anticipate"],
            library=["Island"] * 8,
            battlefield=["Mindsplice Apparatus", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    apparatus = scenario.find("Mindsplice Apparatus", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(apparatus, "oil", 2)

    stock_up = scenario.cast("Stock Up")
    assert stock_up.total_cost.mana == ManaCost.parse("{U}")
    scenario.pay_with(stock_up.begin_paying(), *scenario.untapped_sources("Island"))
    scenario.will_choose_cards(*scenario.top_of_library(2))
    scenario.put_on_stack(stock_up)
    scenario.resolve_top()

    assert scenario.cast("Anticipate").total_cost.mana == ManaCost.parse("{U}")


@pytest.mark.parametrize("countered", [0, 2])
def test_armorcraft_judge_draws_per_creature_with_a_counter(countered: int):
    """Armorcraft Judge (proof printing): "draw a card for each creature you
    control with a +1/+1 counter on it"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Armorcraft Judge"],
            library=["Island"] * 5,
            battlefield=["Grizzly Bears", "Grizzly Bears", "Craw Wurm"] + ["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for bears in [p for p in scenario.game.battlefield if p.name == "Grizzly Bears"][:countered]:
        scenario.game.add_counters(bears, "+1/+1", 1)

    scenario.cast_and_resolve("Armorcraft Judge", auto=True)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == countered
