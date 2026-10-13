"""Scenario: amounts counted off the board - devotion (CR 700.5), basic land types
(domain, CR 305.6 / ability word CR 207.2c), party size (CR 700.8) and colors
(CR 105.1) - as the X of a pump, a token count, a counter count, a look-at-the-top
count and a mana count.

CR 608.2h: the count is read once, as the effect applies. CR 107.3f: an X the
text defines ("where X is ...") is that expression, not a cast X. CR 107.1b: a
negative result is zero. Every CR number here was looked up with
`mise run rules:find`: 700.5, 700.8, 305.6, 105.1, 105.2, 107.3f, 107.1b, 608.2h,
611.2c, 701.24, 701.20, 104.2b, 701.17.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

FOREST10 = ["Forest"] * 10


def _build(alice=(), bob=(), *, hand=(), library=None, bob_library=None, graveyard=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(alice),
            library=list(FOREST10 if library is None else library),
            graveyard=list(graveyard),
        )
        .player(
            "bob",
            battlefield=list(bob),
            library=list(FOREST10 if bob_library is None else bob_library),
        )
        .build()
    )


STACK = ["Grizzly Bears", "Hill Giant", "Serra Angel", "Llanowar Elves", "Goblin Guide", "Opt"]
THREE_TYPES = ["Island", "Forest", "Swamp", "Island"]  # three basic land types


def _names(cards):
    return [state.name for state in cards]


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _creature_etb(scenario, name, *, targets=None):
    """Cast a creature, let it resolve, then resolve its enters trigger."""
    if targets is not None:
        scenario.choose_trigger_targets(name, targets)
    scenario.cast_and_resolve(name, auto=True, username="alice")
    scenario.pass_until_resolved()


def _tokens(scenario, token_name, username="alice"):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == token_name and scenario.game.controller_of(state).username == username
    ]


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# --------------------------------------------------------------------------
# Devotion as the number of tokens - "create a number of ... tokens equal to
# your devotion to <color>" (Evangel of Heliod, Reverent Hoplite, Abhorrent
# Overlord, Underworld Hermit, Master of Waves)
# --------------------------------------------------------------------------

WHITE_LANDS = ["Plains"] * 6


def test_evangel_of_heliod_counts_its_own_symbols_and_the_others():
    """{4}{W}{W} is two, Savannah Lions {W} one: three Soldiers."""
    scenario = _main(_build(WHITE_LANDS + ["Savannah Lions"], hand=["Evangel of Heliod"]))
    _creature_etb(scenario, "Evangel of Heliod")
    assert len(_tokens(scenario, "Soldier Token")) == 3


def test_evangel_of_heliod_ignores_the_opponents_permanents_and_other_colors():
    scenario = _main(
        _build(
            WHITE_LANDS + ["Grizzly Bears", "Hill Giant"],
            bob=["Savannah Lions", "Savannah Lions"],
            hand=["Evangel of Heliod"],
        )
    )
    _creature_etb(scenario, "Evangel of Heliod")
    assert len(_tokens(scenario, "Soldier Token")) == 2  # only its own {W}{W}
    assert _tokens(scenario, "Soldier Token", "bob") == []


def test_hybrid_symbol_counts_for_each_of_its_colors():
    """CR 700.5 with CR 107.4e: Kitchen Finks {1}{G/W}{G/W} is two toward white."""
    scenario = _main(_build(WHITE_LANDS + ["Kitchen Finks"], hand=["Evangel of Heliod"]))
    _creature_etb(scenario, "Evangel of Heliod")
    assert len(_tokens(scenario, "Soldier Token")) == 4


def test_reverent_hoplite_makes_human_soldiers_by_white_devotion():
    scenario = _main(_build(WHITE_LANDS + ["Savannah Lions"] * 2, hand=["Reverent Hoplite"]))
    _creature_etb(scenario, "Reverent Hoplite")
    tokens = _tokens(scenario, "Human Soldier Token")
    assert len(tokens) == 3  # Hoplite {4}{W} + two Lions
    assert all(_pt(scenario, token) == (1, 1) for token in tokens)


def test_abhorrent_overlord_makes_flying_harpies_by_black_devotion():
    scenario = _main(_build(["Swamp"] * 7 + ["Vampire Nighthawk"], hand=["Abhorrent Overlord"]))
    _creature_etb(scenario, "Abhorrent Overlord")
    harpies = _tokens(scenario, "Harpy Token")
    assert len(harpies) == 4  # Overlord BB + Nighthawk {1}{B}{B}
    assert all(has_keyword(token, Keyword.FLYING, scenario.game) for token in harpies)


def test_underworld_hermit_makes_squirrels_by_black_devotion():
    scenario = _main(_build(["Swamp"] * 6, hand=["Underworld Hermit"]))
    _creature_etb(scenario, "Underworld Hermit")
    assert len(_tokens(scenario, "Squirrel Token")) == 2


def test_master_of_waves_elementals_get_the_anthem():
    """1/0 blue Elementals; the anthem makes each a 2/1 so they live."""
    scenario = _main(_build(["Island"] * 4 + ["Kraken of the Straits"], hand=["Master of Waves"]))
    _creature_etb(scenario, "Master of Waves")
    elementals = _tokens(scenario, "Elemental Token")
    assert len(elementals) == 3  # Master {U} + Kraken {4}{U}{U}... counted: 1 + 2
    assert all(_pt(scenario, token) == (2, 1) for token in elementals)


def test_another_color_adds_nothing_to_the_count():
    """Savannah Lions' {W} is no devotion to black: the Hermit's own {B}{B} only."""
    scenario = _main(_build(["Swamp"] * 6 + ["Savannah Lions"], hand=["Underworld Hermit"]))
    _creature_etb(scenario, "Underworld Hermit")
    assert len(_tokens(scenario, "Squirrel Token")) == 2


# --------------------------------------------------------------------------
# Devotion as a pump or shrink - "+X/+X", "-X/-X", "+X/+0", "-X/-0"
# --------------------------------------------------------------------------

GREEN_LANDS = ["Forest"] * 6


def test_aspect_of_hydra_pumps_by_green_devotion():
    scenario = _main(
        _build(["Forest"] * 3 + ["Llanowar Elves", "Grizzly Bears"], hand=["Aspect of Hydra"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Aspect of Hydra", auto=True, username="alice", targets=[bears])
    # devotion to green: Llanowar Elves {G} + Grizzly Bears {1}{G} = 2; Bears 2/2 -> 4/4
    assert _pt(scenario, bears) == (4, 4)


def test_aspect_of_hydra_counts_the_other_color_of_a_hybrid_once_per_symbol():
    scenario = _main(
        _build(["Forest"] * 3 + ["Kitchen Finks", "Grizzly Bears"], hand=["Aspect of Hydra"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Aspect of Hydra", auto=True, username="alice", targets=[bears])
    assert _pt(scenario, bears) == (5, 5)  # Finks {G/W}{G/W} = 2, Bears 1


def test_klothys_design_pumps_only_your_creatures_on_resolution():
    scenario = _main(
        _build(
            ["Forest"] * 6 + ["Llanowar Elves", "Grizzly Bears"],
            bob=["Grizzly Bears"],
            hand=["Klothys's Design"],
        )
    )
    scenario.cast_and_resolve("Klothys's Design", auto=True, username="alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert _pt(scenario, mine) == (
        4,
        4,
    )  # Elves and Bears: one {G} each = 2 (the spell is not a permanent)
    assert _pt(scenario, theirs) == (2, 2)


def test_klothys_design_does_not_reach_a_creature_that_arrives_later():
    """CR 611.2c: the set of creatures is fixed when the effect begins."""
    scenario = _main(
        _build(
            ["Forest"] * 7 + ["Grizzly Bears"],
            hand=["Klothys's Design", "Hill Giant"],
        )
    )
    scenario.cast_and_resolve("Klothys's Design", auto=True, username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    assert _pt(scenario, scenario.creature("Hill Giant", "alice")) == (
        3,
        3,
    )  # arrived after: no pump
    assert _pt(scenario, scenario.creature("Grizzly Bears", "alice")) == (
        3,
        3,
    )  # Bears alone: devotion 1


def test_blight_breath_catoblepas_shrinks_an_opposing_creature():
    scenario = _main(
        _build(
            ["Swamp"] * 6,
            bob=["Hill Giant"],
            hand=["Blight-Breath Catoblepas"],
        )
    )
    giant = scenario.creature("Hill Giant", "bob")
    _creature_etb(scenario, "Blight-Breath Catoblepas", targets=[giant])
    # devotion to black is the Catoblepas' {B}{B} = 2: Hill Giant 3/3 -> 1/1
    assert _pt(scenario, giant) == (1, 1)


def test_blight_breath_catoblepas_can_kill():
    scenario = _main(
        _build(
            ["Swamp"] * 6 + ["Vampire Nighthawk"],
            bob=["Grizzly Bears"],
            hand=["Blight-Breath Catoblepas"],
        )
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _creature_etb(scenario, "Blight-Breath Catoblepas", targets=[bears])
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD


def test_nylea_s_huntmaster_gives_plus_x_zero():
    scenario = _main(
        _build(["Forest"] * 4 + ["Llanowar Elves", "Grizzly Bears"], hand=["Nylea's Huntmaster"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _creature_etb(scenario, "Nylea's Huntmaster", targets=[bears])
    assert _pt(scenario, bears) == (5, 2)  # Huntmaster, Elves and Bears: one {G} each


def test_threnody_singer_shrinks_power_only():
    scenario = _main(_build(["Island"] * 3, bob=["Hill Giant"], hand=["Threnody Singer"]))
    giant = scenario.creature("Hill Giant", "bob")
    _creature_etb(scenario, "Threnody Singer", targets=[giant])
    assert _pt(scenario, giant) == (2, 3)  # Singer {1}{U}: devotion 1


def test_thunderous_might_pumps_when_the_enchanted_creature_attacks():
    scenario = _main(
        _build(
            ["Mountain"] * 3 + ["Goblin Guide"],
            hand=["Thunderous Might"],
        )
    )
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.cast_and_resolve("Thunderous Might", auto=True, username="alice", targets=[guide])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.attack_with(guide)
    scenario.pass_until_resolved()
    # Might {1}{R} + Goblin Guide {R}: devotion to red 2 => 2/2 + 2/+0
    assert _pt(scenario, guide) == (4, 2)


# --------------------------------------------------------------------------
# Devotion as the amount of cards or life - Sanguimancy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra", [0, 2])
def test_sanguimancy_draws_and_loses_by_black_devotion(extra):
    battlefield = ["Swamp"] * 6 + ["Vampire Nighthawk"] * (1 if extra else 0)
    scenario = _main(_build(battlefield, hand=["Sanguimancy"]))
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Sanguimancy", auto=True, username="alice")
    drawn = len(scenario.player("alice").hand) - (hand_before - 1)
    assert drawn == extra
    assert scenario.player("alice").life == 20 - extra


# --------------------------------------------------------------------------
# Devotion as a mana value ceiling - Grim Servant
# --------------------------------------------------------------------------


def test_grim_servant_searches_for_a_card_up_to_the_devotion():
    scenario = _main(
        _build(
            ["Swamp"] * 5 + ["Vampire Nighthawk"],
            hand=["Grim Servant"],
            library=["Hill Giant", "Serra Angel", "Grizzly Bears", "Forest"],
        )
    )
    # devotion to black: Servant {B} + Nighthawk {B}{B} = 3: Hill Giant (4) is too big,
    # Grizzly Bears (2) and Forest (0) qualify.
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bears)
    scenario.cast_and_resolve("Grim Servant", auto=True, username="alice")
    scenario.pass_until_resolved()
    assert bears.zone is Zone.HAND
    assert scenario.player("alice").life == 17


def test_grim_servant_cannot_fetch_above_the_devotion():
    scenario = _main(
        _build(
            ["Swamp"] * 5,
            hand=["Grim Servant"],
            library=["Serra Angel", "Hill Giant"],
        )
    )
    scenario.cast_and_resolve("Grim Servant", auto=True, username="alice")
    scenario.pass_until_resolved()
    assert scenario.find("Serra Angel", Zone.LIBRARY, "alice").zone is Zone.LIBRARY
    assert scenario.find("Hill Giant", Zone.LIBRARY, "alice").zone is Zone.LIBRARY
    assert scenario.player("alice").life == 17  # "You lose 3 life" is not conditional


# --------------------------------------------------------------------------
# Devotion as "up to X targets" - Mogis's Marauder
# --------------------------------------------------------------------------


def test_mogis_marauder_gives_intimidate_and_haste_to_up_to_devotion_creatures():
    scenario = _main(
        _build(
            ["Swamp"] * 3 + ["Vampire Nighthawk", "Grizzly Bears", "Hill Giant", "Runeclaw Bear"],
            hand=["Mogis's Marauder"],
        )
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    _creature_etb(scenario, "Mogis's Marauder", targets=[bears, giant])
    for creature in (bears, giant):
        assert has_keyword(creature, Keyword.HASTE, scenario.game)
        assert has_keyword(creature, Keyword.INTIMIDATE, scenario.game)
    other = scenario.creature("Runeclaw Bear", "alice")
    assert not has_keyword(other, Keyword.HASTE, scenario.game)


def test_mogis_marauder_gives_nothing_beyond_the_devotion_cap():
    """ "Up to X target creatures": the X the text defines is also the most targets
    (CR 601.2c with CR 107.3f). Devotion to black is the Marauder's {B} + Nighthawk {B}{B} = 3,
    so a fourth chosen creature gets neither keyword."""
    scenario = _main(
        _build(
            ["Swamp"] * 3
            + ["Vampire Nighthawk", "Grizzly Bears", "Hill Giant", "Runeclaw Bear", "Goblin Guide"],
            hand=["Mogis's Marauder"],
        )
    )
    four = scenario.creatures(
        "Grizzly Bears", "Hill Giant", "Runeclaw Bear", "Goblin Guide", username="alice"
    )
    _creature_etb(scenario, "Mogis's Marauder", targets=four)
    granted = [has_keyword(c, Keyword.INTIMIDATE, scenario.game) for c in four]
    assert sum(granted) <= 3


def test_mogis_marauder_with_no_targets_does_nothing():
    scenario = _main(_build(["Swamp"] * 3 + ["Grizzly Bears"], hand=["Mogis's Marauder"]))
    bears = scenario.creature("Grizzly Bears", "alice")
    _creature_etb(scenario, "Mogis's Marauder", targets=[])
    assert not has_keyword(bears, Keyword.HASTE, scenario.game)
    assert not has_keyword(bears, Keyword.INTIMIDATE, scenario.game)


def test_mogis_marauder_with_one_target_gives_just_that_creature_both_keywords():
    scenario = _main(
        _build(["Swamp"] * 3 + ["Grizzly Bears", "Hill Giant"], hand=["Mogis's Marauder"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    _creature_etb(scenario, "Mogis's Marauder", targets=[bears])
    assert has_keyword(bears, Keyword.HASTE, scenario.game)
    assert has_keyword(bears, Keyword.INTIMIDATE, scenario.game)
    assert not has_keyword(giant, Keyword.HASTE, scenario.game)


# --------------------------------------------------------------------------
# Devotion as the look-at depth - Thassa's Oracle
# --------------------------------------------------------------------------


def test_thassa_s_oracle_keeps_one_on_top_and_bottoms_the_rest():
    """Devotion to blue is the Oracle's {U}{U} = 2: Bears and Giant are looked at, Giant is
    kept on top, Bears goes to the bottom, the unseen cards keep their order."""
    scenario = _main(_build(["Island"] * 2, hand=["Thassa's Oracle"], library=list(STACK)))
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(giant)
    scenario.cast_and_resolve("Thassa's Oracle", auto=True, username="alice")
    scenario.pass_until_resolved()
    library = scenario.player("alice").library
    assert _names(library) == [
        "Hill Giant",
        "Serra Angel",
        "Llanowar Elves",
        "Goblin Guide",
        "Opt",
        "Grizzly Bears",
    ]
    assert scenario.player("alice").life == 20
    assert not scenario.game.is_over


def test_thassa_s_oracle_may_keep_none_and_both_go_to_the_bottom():
    scenario = _main(_build(["Island"] * 2, hand=["Thassa's Oracle"], library=list(STACK)))
    scenario.will_choose_cards()
    scenario.cast_and_resolve("Thassa's Oracle", auto=True, username="alice")
    scenario.pass_until_resolved()
    library = scenario.player("alice").library
    assert _names(library[:4]) == ["Serra Angel", "Llanowar Elves", "Goblin Guide", "Opt"]
    assert sorted(_names(library[4:])) == ["Grizzly Bears", "Hill Giant"]


def test_thassa_s_oracle_wins_when_devotion_reaches_the_library_size():
    scenario = _main(_build(["Island"] * 2, hand=["Thassa's Oracle"], library=["Island", "Island"]))
    scenario.cast_and_resolve("Thassa's Oracle", auto=True, username="alice")
    scenario.pass_until_resolved()
    # devotion to blue is Oracle {U}{U} = 2 >= 2 cards in library
    assert scenario.game.is_over


# --------------------------------------------------------------------------
# Domain as the look-at depth (CR 701.20 look / CR 701.20d reveal): Voda Sea
# Scavenger, Shadow Prophecy, Nael, Sphinx of Clear Skies
# --------------------------------------------------------------------------


def test_voda_looks_at_domain_cards_and_may_put_one_on_top():
    scenario = _main(_build(THREE_TYPES, hand=["Voda Sea Scavenger"], library=list(STACK)))
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(giant)
    scenario.cast_and_resolve("Voda Sea Scavenger", auto=True, username="alice")
    scenario.pass_until_resolved()
    library = scenario.player("alice").library
    assert library[0] is giant
    # the two not kept went to the bottom, Bears and Angel in some order
    assert sorted(_names(library[-2:])) == ["Grizzly Bears", "Serra Angel"]
    assert _names(library[1:4]) == ["Llanowar Elves", "Goblin Guide", "Opt"]


def test_voda_may_decline_and_every_card_looked_at_goes_to_the_bottom():
    scenario = _main(_build(THREE_TYPES, hand=["Voda Sea Scavenger"], library=list(STACK)))
    scenario.will_choose_cards()
    scenario.cast_and_resolve("Voda Sea Scavenger", auto=True, username="alice")
    scenario.pass_until_resolved()
    library = scenario.player("alice").library
    assert _names(library[:3]) == ["Llanowar Elves", "Goblin Guide", "Opt"]
    assert sorted(_names(library[3:])) == ["Grizzly Bears", "Hill Giant", "Serra Angel"]


def test_voda_with_no_basic_land_types_looks_at_nothing():
    scenario = _main(_build([], hand=["Voda Sea Scavenger"], library=list(STACK)))
    scenario.put_onto_battlefield("Voda Sea Scavenger", "alice")
    scenario.pass_until_resolved()
    assert _names(scenario.player("alice").library) == STACK
    assert scenario.questions_asked() == []


def test_voda_counts_a_land_type_once_however_many_lands_have_it():
    """Four lands but only Island and Forest: X is 2."""
    scenario = _main(
        _build(
            ["Island", "Island", "Island", "Forest"],
            hand=["Voda Sea Scavenger"],
            library=list(STACK),
        )
    )
    scenario.will_choose_cards()
    scenario.cast_and_resolve("Voda Sea Scavenger", auto=True, username="alice")
    scenario.pass_until_resolved()
    library = scenario.player("alice").library
    assert _names(library[:4]) == ["Serra Angel", "Llanowar Elves", "Goblin Guide", "Opt"]


def test_shadow_prophecy_takes_up_to_two_and_mills_the_rest():
    scenario = _main(
        _build(["Swamp", "Swamp", "Swamp", "Forest"], hand=["Shadow Prophecy"], library=list(STACK))
    )
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(giant)
    scenario.cast_and_resolve("Shadow Prophecy", auto=True, username="alice")
    # domain 2 (Swamp, Forest): Bears and Giant looked at; Giant to hand, Bears milled
    assert giant.zone is Zone.HAND
    assert "Grizzly Bears" in _names(scenario.player("alice").graveyard)
    assert _names(scenario.player("alice").library)[0] == "Serra Angel"
    assert scenario.player("alice").life == 18


def test_shadow_prophecy_puts_two_into_hand_and_the_remainder_into_the_graveyard():
    scenario = _main(
        _build(
            ["Swamp", "Forest", "Island", "Plains"], hand=["Shadow Prophecy"], library=list(STACK)
        )
    )
    # four types: Bears, Giant, Angel, Elves looked at
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    angel = scenario.find("Serra Angel", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bears, angel)
    scenario.cast_and_resolve("Shadow Prophecy", auto=True, username="alice")
    assert bears.zone is Zone.HAND and angel.zone is Zone.HAND
    graveyard = _names(scenario.player("alice").graveyard)
    assert sorted(graveyard) == ["Hill Giant", "Llanowar Elves", "Shadow Prophecy"]
    assert scenario.player("alice").life == 18


def test_nael_looks_on_combat_damage_and_draws_only_with_five_types():
    five = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
    scenario = _main(_build(five + ["Nael, Avizoa Aeronaut"], library=list(STACK)))
    nael = scenario.creature("Nael, Avizoa Aeronaut", "alice")
    scenario.will_choose_cards(scenario.find("Goblin Guide", Zone.LIBRARY, "alice"))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(nael)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    # five looked at (Bears..Goblin Guide); Guide goes on top and is then drawn (five types)
    assert _names(scenario.player("alice").hand) == ["Goblin Guide"]


def test_nael_does_not_draw_with_fewer_than_five_types():
    scenario = _main(_build(["Island", "Forest", "Nael, Avizoa Aeronaut"], library=list(STACK)))
    nael = scenario.creature("Nael, Avizoa Aeronaut", "alice")
    scenario.will_choose_cards()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(nael)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert scenario.player("alice").hand == []


def test_sphinx_of_clear_skies_splits_into_piles():
    scenario = _main(
        _build(["Island", "Forest", "Swamp", "Sphinx of Clear Skies"], library=list(STACK))
    )
    sphinx = scenario.creature("Sphinx of Clear Skies", "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(bears, username="bob")  # the opponent's pile one
    scenario.will_choose_pile(True, username="alice")  # alice takes pile one into hand
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sphinx)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert bears.zone is Zone.HAND
    assert giant.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Domain as -X/-X, as a counter threshold, as a mana value ceiling
# --------------------------------------------------------------------------


def test_drag_to_the_bottom_shrinks_every_creature_by_one_plus_domain():
    scenario = _main(
        _build(
            ["Swamp", "Swamp", "Forest", "Island", "Hill Giant", "Kraken of the Straits"],
            bob=["Grizzly Bears", "Serra Angel"],
            hand=["Drag to the Bottom"],
        )
    )
    scenario.cast_and_resolve("Drag to the Bottom", auto=True, username="alice")
    # three basic land types: -4/-4 for everyone, the Kraken (6/6) survives as 2/2
    kraken = scenario.creature("Kraken of the Straits", "alice")
    assert _pt(scenario, kraken) == (2, 2)
    scenario.state_based_actions()
    assert "Hill Giant" in _names(scenario.player("alice").graveyard)
    assert "Grizzly Bears" in _names(scenario.player("bob").graveyard)
    assert "Serra Angel" in _names(scenario.player("bob").graveyard)


def test_drag_to_the_bottom_with_no_lands_but_its_own_cost_is_minus_one():
    scenario = _main(
        _build(["Swamp", "Swamp", "Swamp", "Swamp", "Grizzly Bears"], hand=["Drag to the Bottom"])
    )
    scenario.cast_and_resolve("Drag to the Bottom", auto=True, username="alice")
    scenario.state_based_actions()
    # one basic land type (Swamp): -2/-2 kills the 2/2
    assert "Grizzly Bears" in _names(scenario.player("alice").graveyard)


def test_zar_ojanen_counters_only_the_small_creatures_when_it_becomes_tapped():
    scenario = _main(
        _build(
            [
                "Plains",
                "Forest",
                "Island",
                "Zar Ojanen, Scion of Efrava",
                "Grizzly Bears",
                "Hill Giant",
            ],
            bob=["Grizzly Bears"],
        )
    )
    zar = scenario.creature("Zar Ojanen, Scion of Efrava", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(zar)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    # three basic land types: toughness less than 3 gets a counter
    assert scenario.creature("Grizzly Bears", "alice").counter_count(Counter.PLUS_ONE) == 1
    assert scenario.creature("Hill Giant", "alice").counter_count(Counter.PLUS_ONE) == 0
    assert scenario.creature("Grizzly Bears", "bob").counter_count(Counter.PLUS_ONE) == 0


# --------------------------------------------------------------------------
# Party - Emeria Captain and Strength of Solidarity (CR 700.8)
# --------------------------------------------------------------------------

PARTY = ["Codespell Cleric", "Deathcult Rogue", "Fugitive Wizard"]


def test_emeria_captain_gets_a_counter_for_each_party_member_including_itself():
    scenario = _main(_build(["Plains"] * 4 + PARTY, hand=["Emeria Captain"]))
    _creature_etb(scenario, "Emeria Captain")
    # Cleric, Rogue, Wizard and the Captain itself (an Angel Warrior): a full party of four
    assert scenario.creature("Emeria Captain", "alice").counter_count(Counter.PLUS_ONE) == 4


def test_emeria_captain_alone_is_a_party_of_one():
    scenario = _main(_build(["Plains"] * 4, hand=["Emeria Captain"]))
    _creature_etb(scenario, "Emeria Captain")
    assert scenario.creature("Emeria Captain", "alice").counter_count(Counter.PLUS_ONE) == 1


def test_the_party_counts_only_your_own_creatures():
    scenario = _main(_build(["Plains"] * 4, bob=PARTY, hand=["Emeria Captain"]))
    _creature_etb(scenario, "Emeria Captain")
    assert scenario.creature("Emeria Captain", "alice").counter_count(Counter.PLUS_ONE) == 1


def test_strength_of_solidarity_counts_the_party_onto_the_chosen_creature():
    scenario = _main(
        _build(
            ["Forest", "Codespell Cleric", "Deathcult Rogue", "Grizzly Bears"],
            hand=["Strength of Solidarity"],
        )
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Strength of Solidarity", auto=True, username="alice", targets=[bears]
    )
    assert bears.counter_count(Counter.PLUS_ONE) == 2


# --------------------------------------------------------------------------
# Domain as a mana value ceiling - Bortuk Bonerattle
# --------------------------------------------------------------------------

BORTUK_LANDS = ["Swamp", "Swamp", "Swamp", "Forest", "Forest", "Forest"]


def test_bortuk_returns_a_cheap_creature_to_the_battlefield():
    scenario = _main(_build(BORTUK_LANDS, hand=["Bortuk Bonerattle"], graveyard=["Grizzly Bears"]))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    _creature_etb(scenario, "Bortuk Bonerattle", targets=[bears])
    assert bears.zone is Zone.BATTLEFIELD  # mana value 2 <= 2 basic land types


def test_bortuk_puts_an_expensive_creature_into_the_hand():
    scenario = _main(_build(BORTUK_LANDS, hand=["Bortuk Bonerattle"], graveyard=["Hill Giant"]))
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    _creature_etb(scenario, "Bortuk Bonerattle", targets=[giant])
    assert giant.zone is Zone.HAND  # mana value 4 > 2 basic land types


def test_bortuk_does_nothing_when_it_was_not_cast():
    scenario = _main(_build(BORTUK_LANDS, hand=["Bortuk Bonerattle"], graveyard=["Grizzly Bears"]))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Bortuk Bonerattle", [bears])
    scenario.put_onto_battlefield("Bortuk Bonerattle", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Colors of an object / among permanents (CR 105.1)
# --------------------------------------------------------------------------


def test_breathe_your_last_gains_one_life_per_color_of_the_destroyed_creature():
    scenario = _main(
        _build(["Swamp"] * 3, bob=["Kitchen Finks", "Grizzly Bears"], hand=["Breathe Your Last"])
    )
    finks = scenario.creature("Kitchen Finks", "bob")
    scenario.cast_and_resolve("Breathe Your Last", auto=True, username="alice", targets=[finks])
    assert finks.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22  # green and white: two colors


def test_breathe_your_last_gains_nothing_for_a_colorless_permanent():
    """CR 105.2c: a colorless object has no colors; a planeswalker is a legal target too."""
    scenario = _main(_build(["Swamp"] * 3, bob=["Karn, Scion of Urza"], hand=["Breathe Your Last"]))
    karn = scenario.find("Karn, Scion of Urza", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve("Breathe Your Last", auto=True, username="alice", targets=[karn])
    assert karn.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_ancient_cornucopia_gains_once_per_turn_for_each_color_of_the_spell():
    scenario = _main(
        _build(
            ["Ancient Cornucopia", "Forest", "Forest", "Swamp", "Plains"],
            hand=["Kitchen Finks", "Grizzly Bears"],
        )
    )
    scenario.cast_onto_stack("Kitchen Finks", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert scenario.player("alice").life == 22 + 2  # Finks: two colors; Finks' own ETB gains 2
    life = scenario.player("alice").life
    scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert scenario.player("alice").life == life  # "Do this only once each turn"


def test_general_tazri_pumps_allies_by_the_colors_among_them():
    scenario = _main(
        _build(
            ["Plains", "Island", "Swamp", "Mountain", "Forest", "General Tazri", "Grizzly Bears"],
        )
    )
    tazri = scenario.creature("General Tazri", "alice")
    scenario.activate(tazri, auto=True, index=0)
    scenario.pass_until_resolved()
    # Tazri is the only (white) Ally: +1/+1; the Bears are not Allies
    assert _pt(scenario, tazri)[0] == 4
    assert _pt(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)


# --------------------------------------------------------------------------
# One mana of each color among permanents (Bloom Tender, Faeburrow Elder, Tarnation Vista)
# --------------------------------------------------------------------------


def _mana_pool(scenario):
    """The floating mana as {"W": n, ...}, readable as attributes."""

    class Pool:
        def __init__(self, floating):
            self.white, self.blue, self.black, self.red, self.green = (
                floating.get(Color(letter), 0) for letter in "WUBRG"
            )

    return Pool(scenario.player("alice").mana_pool.floating)


def test_bloom_tender_adds_one_mana_of_each_color_among_your_permanents():
    scenario = _main(_build(["Bloom Tender", "Savannah Lions", "Hill Giant", "Llanowar Elves"]))
    tender = scenario.creature("Bloom Tender", "alice")
    scenario.activate(tender)
    pool = _mana_pool(scenario)
    assert (pool.green, pool.white) == (1, 1)  # Tender and Elves green, Lions white, Giant red
    assert pool.red == 1


def test_bloom_tender_ignores_the_opponents_permanents_and_colorless_ones():
    scenario = _main(_build(["Bloom Tender", "Sol Ring"], bob=["Savannah Lions"]))
    scenario.activate(scenario.creature("Bloom Tender", "alice"))
    pool = _mana_pool(scenario)
    assert (pool.green, pool.white, pool.red, pool.blue, pool.black) == (1, 0, 0, 0, 0)


def test_faeburrow_elder_taps_for_each_of_its_colors_and_gets_the_same_bonus():
    scenario = _main(_build(["Faeburrow Elder", "Hill Giant"]))
    elder = scenario.creature("Faeburrow Elder", "alice")
    scenario.activate(elder, index=0)
    pool = _mana_pool(scenario)
    assert (pool.green, pool.white, pool.red) == (1, 1, 1)


def test_tarnation_vista_counts_only_monocolored_permanents():
    scenario = _main(
        _build(["Tarnation Vista", "Kitchen Finks", "Hill Giant", "Mountain", "Forest"])
    )
    vista = scenario.find("Tarnation Vista", Zone.BATTLEFIELD, "alice")
    scenario.activate(vista, auto=True, index=1)
    pool = _mana_pool(scenario)
    assert pool.red == 1  # Hill Giant; Kitchen Finks is multicolored and adds nothing
    assert pool.green == 0 and pool.white == 0


# --------------------------------------------------------------------------
# Second printings that prove the readers are about the mechanic, not the card
# --------------------------------------------------------------------------


def _rebuff_board(bob_permanents):
    return (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"], library=FOREST10)
        .player(
            "bob",
            hand=["Thassa's Rebuff"],
            battlefield=["Island", "Island", *bob_permanents],
            library=FOREST10,
        )
        .build()
    )


def test_thassa_s_rebuff_counters_when_its_controller_cannot_pay_the_devotion():
    """Devotion to blue counts Kraken of the Straits' {U}{U}, so X is 2; alice has one
    floating mana (CR 118.12a: she may pay, and cannot)."""
    scenario = _rebuff_board(["Kraken of the Straits"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").mana_pool.add(Color.COLORLESS, 1)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Thassa's Rebuff", *islands, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD


def test_thassa_s_rebuff_lets_the_spell_resolve_when_its_controller_pays_the_devotion():
    scenario = _rebuff_board(["Kraken of the Straits"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 2)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Thassa's Rebuff")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Thassa's Rebuff", *islands, username="bob", targets=[bears])
    assert bears.zone is Zone.STACK
    assert alice.mana_pool.total == 0


def test_thassa_s_rebuff_with_no_blue_devotion_asks_for_nothing():
    """X is 0 (CR 118.3a: a player can always pay 0): the spell is not countered."""
    scenario = _rebuff_board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.pass_priority("alice")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Thassa's Rebuff")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Thassa's Rebuff", *islands, username="bob", targets=[bears])
    assert bears.zone is Zone.STACK


def test_might_of_the_nephilim_pumps_by_two_for_each_of_the_targets_colors():
    scenario = _main(
        _build(
            ["Forest", "Forest", "Kitchen Finks", "Grizzly Bears"], hand=["Might of the Nephilim"]
        )
    )
    finks = scenario.creature("Kitchen Finks", "alice")
    scenario.cast_and_resolve("Might of the Nephilim", auto=True, username="alice", targets=[finks])
    assert _pt(scenario, finks) == (3 + 4, 2 + 4)  # green and white: two colors, +4/+4


def test_might_of_the_nephilim_gives_a_mono_colored_creature_plus_two():
    scenario = _main(_build(["Forest", "Forest", "Grizzly Bears"], hand=["Might of the Nephilim"]))
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Might of the Nephilim", auto=True, username="alice", targets=[bears])
    assert _pt(scenario, bears) == (4, 4)


def test_might_of_the_nephilim_gives_a_colorless_creature_nothing():
    """CR 105.2c: colorless is not a color, so there is nothing to count."""
    scenario = _main(_build(["Forest", "Forest", "Ornithopter"], hand=["Might of the Nephilim"]))
    thopter = scenario.creature("Ornithopter", "alice")
    scenario.cast_and_resolve(
        "Might of the Nephilim", auto=True, username="alice", targets=[thopter]
    )
    assert _pt(scenario, thopter) == (0, 2)


def _cast_and_settle(scenario, name):
    scenario.cast_onto_stack(name, auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_ramos_gets_a_counter_for_each_color_of_each_spell_cast():
    scenario = _main(
        _build(
            ["Ramos, Dragon Engine", "Forest", "Forest", "Forest", "Forest", "Plains"],
            hand=["Kitchen Finks", "Grizzly Bears"],
        )
    )
    ramos = scenario.creature("Ramos, Dragon Engine", "alice")
    _cast_and_settle(scenario, "Kitchen Finks")
    assert ramos.counter_count(Counter.PLUS_ONE) == 2
    _cast_and_settle(scenario, "Grizzly Bears")
    assert ramos.counter_count(Counter.PLUS_ONE) == 3


def test_ramos_gets_nothing_for_a_colorless_spell():
    scenario = _main(_build(["Ramos, Dragon Engine", "Plains"], hand=["Ornithopter"]))
    ramos = scenario.creature("Ramos, Dragon Engine", "alice")
    _cast_and_settle(scenario, "Ornithopter")
    assert ramos.counter_count(Counter.PLUS_ONE) == 0


def _block_and_cast_tactics(party):
    scenario = _main(
        _build(
            ["Plains", "Hill Giant", *party],
            bob=["Serra Angel"],
            hand=["Practiced Tactics"],
        )
    )
    giant = scenario.creature("Hill Giant", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.block(giant, angel)
    scenario.cast_and_resolve("Practiced Tactics", auto=True, username="alice", targets=[angel])
    return angel


def test_practiced_tactics_deals_twice_the_party_to_the_chosen_blocker():
    """Party: a Cleric and a Rogue (CR 700.8) is two, so 4 damage kills the blocking Angel."""
    angel = _block_and_cast_tactics(["Codespell Cleric", "Deathcult Rogue"])
    assert angel.zone is Zone.GRAVEYARD


def test_practiced_tactics_with_no_party_deals_no_damage():
    angel = _block_and_cast_tactics([])
    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 0


def test_slimefoots_survey_fetches_two_typed_lands_then_looks_at_domain_cards():
    """Island and Swamp come in tapped beside the Forests: three basic land types, so the
    three cards left (the whole library) are looked at and the Angel is kept on top."""
    scenario = _main(
        _build(
            ["Forest"] * 5,
            hand=["Slimefoot's Survey"],
            library=["Island", "Swamp", "Grizzly Bears", "Hill Giant", "Serra Angel"],
        )
    )
    angel = scenario.find("Serra Angel", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(
        scenario.find("Island", Zone.LIBRARY, "alice"),
        scenario.find("Swamp", Zone.LIBRARY, "alice"),
    )
    scenario.will_choose_cards(angel)
    scenario.cast_and_resolve("Slimefoot's Survey", auto=True, username="alice")
    scenario.pass_until_resolved()
    fetched = [s for s in scenario.game.battlefield if s.name in ("Island", "Swamp")]
    assert sorted(s.name for s in fetched) == ["Island", "Swamp"]
    assert all(s.tapped for s in fetched)
    library = scenario.player("alice").library
    assert library[0] is angel
    assert sorted(_names(library[1:])) == ["Grizzly Bears", "Hill Giant"]


def test_moonveil_regent_discards_the_hand_and_draws_per_color_of_the_spell():
    scenario = _main(
        _build(
            ["Moonveil Regent", "Forest", "Forest", "Forest", "Plains"],
            hand=["Kitchen Finks", "Hill Giant", "Opt"],
            library=list(STACK),
        )
    )
    scenario.will_take_the_may(True, username="alice")
    _cast_and_settle(scenario, "Kitchen Finks")
    hand = _names(scenario.player("alice").hand)
    assert hand == ["Grizzly Bears", "Hill Giant"]  # two colors: two cards off the top
    assert {"Hill Giant", "Opt"} <= set(_names(scenario.player("alice").graveyard))


def test_moonveil_regent_may_decline_and_keeps_its_hand():
    scenario = _main(
        _build(
            ["Moonveil Regent", "Forest", "Forest", "Forest"],
            hand=["Grizzly Bears", "Hill Giant"],
            library=list(STACK),
        )
    )
    scenario.will_take_the_may(False, username="alice")
    _cast_and_settle(scenario, "Grizzly Bears")
    assert _names(scenario.player("alice").hand) == ["Hill Giant"]
