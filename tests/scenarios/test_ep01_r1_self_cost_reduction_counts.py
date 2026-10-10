"""CR 601.2f self reductions that count something or read a condition, each
proved by a real cast whose determined total cost is asserted (EP-01 round 1,
task T7).

Rules read whole with `mise run rules:find` this session:

- **CR 601.2f** - the total cost is the mana cost plus increases minus
  reductions, determined once the spell is on the stack; it can't be reduced
  below {0}.
- **CR 118.7a** - "Effects that reduce a cost by an amount of generic mana
  affect only the generic mana component of that cost."
- **CR 118.7c** - a reduction of coloured mana reduces only that colour; one
  the cost has none of is not reduced.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def _cost(scenario, name, *, targets=None, username="alice") -> str:
    casting = scenario.cast(name, username, targets=targets)
    scenario.game.determine_total_cost(casting)
    mana = str(casting.total_cost.mana)
    casting.cancel()
    return mana


def _main(**players) -> Scenario:
    builder = Scenario()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- "for each <quality> card in your graveyard" (and/or) --------------------


def test_chitin_gravestalker_counts_artifact_and_or_creature_cards():
    scenario = _main(
        alice={
            "hand": ["Chitin Gravestalker"],
            "graveyard": ["Sol Ring", "Grizzly Bears", "Lightning Bolt"],
        }
    )
    # {5}{B} printed: the artifact and the creature count, the instant does not.
    assert _cost(scenario, "Chitin Gravestalker") == "{3}{B}"


def test_chitin_gravestalker_empty_graveyard_pays_full():
    scenario = _main(alice={"hand": ["Chitin Gravestalker"]})
    assert _cost(scenario, "Chitin Gravestalker") == "{5}{B}"


# -- permanents with oil counters --------------------------------------------


def test_cinderslash_ravager_counts_only_permanents_with_oil_counters():
    scenario = _main(
        alice={
            "hand": ["Cinderslash Ravager"],
            "battlefield": ["Mindsplice Apparatus", "Sol Ring", "Grizzly Bears"],
        }
    )
    apparatus = scenario.find("Mindsplice Apparatus", Zone.BATTLEFIELD, "alice")
    apparatus.add_counters("oil", 2)
    assert _cost(scenario, "Cinderslash Ravager") == "{3}{R}{G}"


def test_cinderslash_ravager_without_oil_pays_full():
    scenario = _main(alice={"hand": ["Cinderslash Ravager"], "battlefield": ["Sol Ring"]})
    assert _cost(scenario, "Cinderslash Ravager") == "{4}{R}{G}"


# -- creatures that died this turn --------------------------------------------


def test_death_rattle_oni_costs_two_less_per_creature_that_died_this_turn():
    scenario = _main(
        alice={"hand": ["Death-Rattle Oni", "Lightning Bolt"], "battlefield": ["Mountain"]},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    base = ManaCost.parse(_cost(scenario, "Death-Rattle Oni"))
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.put_into_graveyard(bears)
    after = ManaCost.parse(_cost(scenario, "Death-Rattle Oni"))
    assert base.converted - after.converted == 2


# -- coloured per-unit reductions ----------------------------------------------


def test_khalni_hydra_costs_a_green_less_per_green_creature():
    scenario = _main(
        alice={
            "hand": ["Khalni Hydra"],
            "battlefield": ["Grizzly Bears", "Grizzly Bears", "Llanowar Elves"],
        }
    )
    # Three green creatures take three {G} off {G}x8.
    assert _cost(scenario, "Khalni Hydra") == "{G}{G}{G}{G}{G}"


def test_khalni_hydra_ignores_non_green_creatures():
    scenario = _main(alice={"hand": ["Khalni Hydra"], "battlefield": ["Serra Angel"]})
    assert _cost(scenario, "Khalni Hydra") == "{G}{G}{G}{G}{G}{G}{G}{G}"


# -- attacking creatures --------------------------------------------------------


def _attacking(builder_hand, battlefield, *, bob=None):
    scenario = (
        Scenario()
        .player("alice", hand=builder_hand, battlefield=battlefield)
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_embercleave_costs_one_less_per_attacking_creature_you_control():
    scenario = _attacking(["Embercleave"], ["Grizzly Bears", "Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.attack_with(bears, elves)
    assert _cost(scenario, "Embercleave") == "{2}{R}{R}"


def test_embercleave_before_attackers_pays_full():
    scenario = _attacking(["Embercleave"], ["Grizzly Bears"])
    assert _cost(scenario, "Embercleave") == "{4}{R}{R}"


def test_static_snare_counts_every_attacking_creature_whoever_controls_it():
    scenario = _attacking(["Static Snare"], ["Grizzly Bears"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert _cost(scenario, "Static Snare") == "{3}{W}"


def test_search_party_captain_counts_creatures_you_attacked_with_this_turn():
    scenario = _attacking(["Search Party Captain"], ["Grizzly Bears", "Llanowar Elves"])
    scenario.attack_with(
        scenario.creature("Grizzly Bears", "alice"), scenario.creature("Llanowar Elves", "alice")
    )
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
    assert _cost(scenario, "Search Party Captain") == "{1}{W}"


# -- party (CR 700.8) ----------------------------------------------------------


def test_party_reductions_count_one_creature_per_role():
    scenario = _main(
        alice={
            "hand": ["Sea Gate Colossus", "Journey to Oblivion", "Tazri, Beacon of Unity"],
            "battlefield": ["Codespell Cleric", "Relic Robber", "Ash Zealot", "Grizzly Bears"],
        }
    )
    assert _cost(scenario, "Sea Gate Colossus") == "{4}"
    assert _cost(scenario, "Journey to Oblivion") == "{1}{W}"


def test_a_party_counts_each_role_once():
    scenario = _main(
        alice={"hand": ["Sea Gate Colossus"], "battlefield": ["Ash Zealot", "Kronch Wrangler"]}
    )
    # Two Warriors are one party member (CR 700.8b).
    assert _cost(scenario, "Sea Gate Colossus") == "{6}"


# -- modified creatures ---------------------------------------------------------


def test_walking_skyscraper_counts_modified_creatures_you_control():
    scenario = _main(
        alice={
            "hand": ["Walking Skyscraper"],
            "battlefield": ["Grizzly Bears", "Llanowar Elves", "Serra Angel"],
        }
    )
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    scenario.creature("Serra Angel", "alice").add_counters("+1/+1", 2)
    assert _cost(scenario, "Walking Skyscraper") == "{6}"


# -- other spells cast this turn -------------------------------------------------


def test_thrasta_costs_three_less_per_other_spell_cast_this_turn():
    scenario = _main(
        alice={
            "hand": ["Thrasta, Tempest's Roar", "Lightning Bolt", "Lightning Bolt"],
            "battlefield": ["Mountain", "Mountain"],
        },
        bob={},
    )
    assert _cost(scenario, "Thrasta, Tempest's Roar") == "{10}{G}{G}"
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], targets=["bob"])
    assert _cost(scenario, "Thrasta, Tempest's Roar") == "{7}{G}{G}"
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], targets=["bob"])
    assert _cost(scenario, "Thrasta, Tempest's Roar") == "{4}{G}{G}"


# -- where X is ------------------------------------------------------------------


def test_the_pride_of_hull_clade_costs_its_creatures_total_toughness_less():
    scenario = _main(
        alice={"hand": ["The Pride of Hull Clade"], "battlefield": ["Grizzly Bears", "Serra Angel"]}
    )
    # toughness 2 + 4.
    assert _cost(scenario, "The Pride of Hull Clade") == "{4}{G}"


def test_excalibur_counts_the_total_mana_value_of_historic_permanents():
    scenario = _main(
        alice={"hand": ["Excalibur, Sword of Eden"], "battlefield": ["Sol Ring", "Grizzly Bears"]}
    )
    # Sol Ring (artifact, MV 1) is historic, the Bears are not.
    assert _cost(scenario, "Excalibur, Sword of Eden") == "{11}"


def test_metalwork_colossus_counts_noncreature_artifacts_only():
    scenario = _main(
        alice={"hand": ["Metalwork Colossus"], "battlefield": ["Sol Ring", "Walking Skyscraper"]}
    )
    assert _cost(scenario, "Metalwork Colossus") == "{10}"


def test_chandras_incinerator_counts_noncombat_damage_dealt_to_opponents_this_turn():
    scenario = _main(
        alice={"hand": ["Chandra's Incinerator", "Lightning Bolt"], "battlefield": ["Mountain"]},
        bob={},
    )
    assert _cost(scenario, "Chandra's Incinerator") == "{5}{R}"
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    assert _cost(scenario, "Chandra's Incinerator") == "{2}{R}"


def test_chandras_incinerator_ignores_damage_dealt_to_its_own_controller():
    scenario = _main(
        alice={"hand": ["Chandra's Incinerator", "Lightning Bolt"], "battlefield": ["Mountain"]},
        bob={},
    )
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["alice"])
    assert _cost(scenario, "Chandra's Incinerator") == "{5}{R}"


# -- if <condition> ----------------------------------------------------------------


def test_avatar_of_might_is_cheaper_when_an_opponent_has_four_more_creatures():
    scenario = _main(
        alice={"hand": ["Avatar of Might"], "battlefield": ["Grizzly Bears"]},
        bob={"battlefield": ["Grizzly Bears"] * 5},
    )
    assert _cost(scenario, "Avatar of Might") == "{G}{G}"


def test_avatar_of_might_pays_full_with_only_three_more():
    scenario = _main(
        alice={"hand": ["Avatar of Might"], "battlefield": ["Grizzly Bears"]},
        bob={"battlefield": ["Grizzly Bears"] * 4},
    )
    assert _cost(scenario, "Avatar of Might") == "{6}{G}{G}"


def test_avatar_of_woe_counts_creature_cards_in_all_graveyards():
    scenario = _main(
        alice={"hand": ["Avatar of Woe"], "graveyard": ["Grizzly Bears"] * 6},
        bob={"graveyard": ["Grizzly Bears"] * 4},
    )
    assert _cost(scenario, "Avatar of Woe") == "{B}{B}"


def test_avatar_of_woe_pays_full_with_nine():
    scenario = _main(
        alice={"hand": ["Avatar of Woe"], "graveyard": ["Grizzly Bears"] * 5},
        bob={"graveyard": ["Grizzly Bears"] * 4},
    )
    assert _cost(scenario, "Avatar of Woe") == "{6}{B}{B}"


def test_swampsnare_trap_is_cheaper_only_when_it_targets_a_flier():
    scenario = _main(
        alice={"hand": ["Swampsnare Trap", "Swampsnare Trap"]},
        bob={"battlefield": ["Serra Angel", "Grizzly Bears"]},
    )
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert _cost(scenario, "Swampsnare Trap", targets=[angel]) == "{1}{B}"
    assert _cost(scenario, "Swampsnare Trap", targets=[bears]) == "{2}{B}"


# -- the Demilich / Valiant Changeling shapes -----------------------------------------


def test_demilich_costs_a_blue_less_per_instant_or_sorcery_cast_this_turn():
    scenario = _main(
        alice={"hand": ["Demilich", "Lightning Bolt"], "battlefield": ["Mountain"]},
        bob={},
    )
    assert _cost(scenario, "Demilich") == "{U}{U}{U}{U}"
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    assert _cost(scenario, "Demilich") == "{U}{U}{U}"


def test_valiant_changeling_counts_creature_types_among_your_creatures():
    scenario = _main(
        alice={"hand": ["Valiant Changeling"], "battlefield": ["Grizzly Bears", "Llanowar Elves"]}
    )
    # Bear, Elf, Druid: three types.
    assert _cost(scenario, "Valiant Changeling") == "{2}{W}{W}"


def test_valiant_changeling_reduction_is_capped_at_five():
    scenario = _main(alice={"hand": ["Valiant Changeling"], "battlefield": ["Changeling Outcast"]})
    # A changeling is every creature type (CR 702.73a), far more than five.
    assert _cost(scenario, "Valiant Changeling") == "{W}{W}"


def test_hamlet_glutton_is_cheaper_only_when_bargained():
    """CR 702.166b: bargaining is the optional additional cost, so the cast
    record knows it by the time CR 601.2f determines the total cost."""
    scenario = _main(alice={"hand": ["Hamlet Glutton"], "battlefield": ["Sol Ring"]})
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    plain = scenario.cast("Hamlet Glutton", "alice")
    scenario.game.determine_total_cost(plain)
    assert str(plain.total_cost.mana) == "{5}{G}{G}"
    plain.cancel()
    bargained = scenario.cast("Hamlet Glutton", "alice")
    bargained.pay_bargain(sol_ring)
    scenario.game.determine_total_cost(bargained)
    assert str(bargained.total_cost.mana) == "{3}{G}{G}"
