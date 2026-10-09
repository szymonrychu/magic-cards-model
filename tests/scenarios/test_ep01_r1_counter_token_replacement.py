"""EP-01 round 1, task 6: counter and token replacement statics (CR 614.16,
CR 122.6, CR 701.7b).

Counters are raised through a real `Game.add_counters`; tokens through the real
`create_tokens` / `create_predefined_tokens` choke point. Every shape has its
negative: a permanent the subject does not name, another controller, a token or
counter kind it does not read.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _handled(name, containing="would"):
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _on_battlefield(scenario, name):
    return [c for c in scenario.game.battlefield if c.name == name]


# -- "that many plus one +1/+1 counters" ----------------------------------------


def test_caradora_adds_one_counter_to_a_creature_you_control():
    scenario = _board(["Caradora, Heart of Alacria", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "+1/+1", 2)

    assert bears.counter_count("+1/+1") == 3


def test_caradora_leaves_an_opponents_creature_alone():
    scenario = _board(["Caradora, Heart of Alacria"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, "+1/+1", 2)

    assert theirs.counter_count("+1/+1") == 2


def test_caradora_reads_only_the_named_counter_kind():
    scenario = _board(["Caradora, Heart of Alacria", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, "-1/-1", 2)

    assert bears.counter_count("-1/-1") == 2


def test_mowu_only_affects_itself():
    scenario = _board(["Mowu, Loyal Companion", "Grizzly Bears"])
    mowu = scenario.creature("Mowu, Loyal Companion", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(mowu, "+1/+1", 1)
    scenario.game.add_counters(bears, "+1/+1", 1)

    assert mowu.counter_count("+1/+1") == 2
    assert bears.counter_count("+1/+1") == 1


def test_mauhur_reads_a_subtype_list():
    scenario = _board(["Mauhúr, Uruk-hai Captain", "Goblin Guide", "Grizzly Bears"])
    goblin = scenario.creature("Goblin Guide", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(goblin, "+1/+1", 1)
    scenario.game.add_counters(bears, "+1/+1", 1)

    assert goblin.counter_count("+1/+1") == 2
    assert bears.counter_count("+1/+1") == 1


def test_loading_zone_doubles_every_kind_on_its_listed_permanents():
    scenario = _board(["Loading Zone", "Grizzly Bears"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(bears, "+1/+1", 2)
    scenario.game.add_counters(bears, "shield", 1)
    scenario.game.add_counters(theirs, "+1/+1", 2)

    assert bears.counter_count("+1/+1") == 4
    assert bears.counter_count("shield") == 2
    assert theirs.counter_count("+1/+1") == 2


# -- tokens --------------------------------------------------------------------


def _make(scenario, definition, who="alice", count=1):
    return create_tokens(scenario.game, definition, who, count)


def test_xorn_adds_a_treasure_to_treasure_creation_only():
    scenario = _board(["Xorn"])
    _make(scenario, PREDEFINED["Treasure"])
    assert len(_on_battlefield(scenario, "Treasure Token")) == 2

    _make(scenario, PREDEFINED["Food"])
    assert len(_on_battlefield(scenario, "Food Token")) == 1


def test_xorn_does_not_help_the_opponent():
    scenario = _board(["Xorn"])
    _make(scenario, PREDEFINED["Treasure"], who="bob")
    assert len(_on_battlefield(scenario, "Treasure Token")) == 1


def test_worldwalker_helm_adds_a_map_to_artifact_tokens():
    scenario = _board(["Worldwalker Helm"])
    _make(scenario, PREDEFINED["Treasure"])
    assert len(_on_battlefield(scenario, "Map Token")) == 1

    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert len(_on_battlefield(scenario, "Map Token")) == 1  # a creature token: no


def test_peregrin_took_adds_a_food_to_any_token_you_create():
    scenario = _board(["Peregrin Took"])
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert len(_on_battlefield(scenario, "Food Token")) == 1


def test_academy_manufactor_makes_one_of_each():
    scenario = _board(["Academy Manufactor"])
    _make(scenario, PREDEFINED["Treasure"])
    assert [
        len(_on_battlefield(scenario, n)) for n in ("Clue Token", "Food Token", "Treasure Token")
    ] == [1, 1, 1]


def test_academy_manufactor_ignores_other_tokens():
    scenario = _board(["Academy Manufactor"])
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert _on_battlefield(scenario, "Clue Token") == []


def test_jinnie_fay_may_swap_for_cats_or_dogs():
    scenario = _board(["Jinnie Fay, Jetmir's Second"])
    scenario.will_choose("Cat Token", username="alice")
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)), count=2)
    assert len([c for c in scenario.game.battlefield if "Cat" in c.name]) == 2

    scenario = _board(["Jinnie Fay, Jetmir's Second"])
    scenario.will_choose("keep", username="alice")
    _make(scenario, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)))
    assert [c for c in scenario.game.battlefield if "Cat" in c.name] == []


@pytest.mark.parametrize(
    "name",
    [
        "Caradora, Heart of Alacria",
        "Mauhúr, Uruk-hai Captain",
        "Mowu, Loyal Companion",
        "Loading Zone",
        "Xorn",
        "Worldwalker Helm",
        "Peregrin Took",
        "Academy Manufactor",
        "Jinnie Fay, Jetmir's Second",
    ],
)
def test_counter_and_token_lines_are_handled(name):
    _handled(name)


# -- life and poison -------------------------------------------------------------


def test_tainted_remedy_turns_an_opponents_gain_into_a_loss():
    scenario = _board(["Tainted Remedy"])
    scenario.game.gain_life("bob", 3)
    assert scenario.player("bob").life == 17


def test_tainted_remedy_leaves_your_own_gain_alone():
    scenario = _board(["Tainted Remedy"])
    scenario.game.gain_life("alice", 3)
    assert scenario.player("alice").life == 23


def test_rain_of_gore_hits_any_player_but_not_lifelink():
    scenario = _board(["Rain of Gore", "Vampire Nighthawk"])
    scenario.game.gain_life("alice", 3)
    assert scenario.player("alice").life == 17

    hawk = scenario.creature("Vampire Nighthawk", "alice")
    scenario.game.deal_damage(scenario.player("bob"), 2, source=hawk)  # lifelink gain
    assert scenario.player("alice").life == 19  # 17 + 2: lifelink is not a spell or ability


def test_phial_doubles_life_gain_at_five_or_less_only():
    scenario = _board(["Phial of Galadriel"])
    scenario.game.gain_life("alice", 2)
    assert scenario.player("alice").life == 22

    scenario.player("alice").life = 5
    scenario.game.gain_life("alice", 2)
    assert scenario.player("alice").life == 9  # twice 2 at 5 life


def test_bloodletter_doubles_opponent_life_loss_on_your_turn_only():
    scenario = _board(["Bloodletter of Aclazotz"])
    assert scenario.game.active_player.username == "alice"
    scenario.game.lose_life("bob", 2)
    assert scenario.player("bob").life == 16

    scenario.game.lose_life("alice", 2)
    assert scenario.player("alice").life == 18  # your own loss is not doubled


def test_worship_floors_damage_at_one_only_while_you_control_a_creature():
    scenario = _board(["Worship", "Grizzly Bears"])
    scenario.player("alice").life = 3
    scenario.game.deal_damage(scenario.player("alice"), 10, source=None)
    assert scenario.player("alice").life == 1

    scenario = _board(["Worship"])
    scenario.player("alice").life = 3
    scenario.game.deal_damage(scenario.player("alice"), 10, source=None)
    assert scenario.player("alice").life == -7


def test_melira_caps_poison_at_one_counter_this_turn():
    scenario = _board(["Melira, the Living Cure"])
    scenario.game.add_player_counters("alice", "poison", 3)
    assert scenario.player("alice").counter_count("poison") == 1
    scenario.game.add_player_counters("alice", "poison", 2)
    assert scenario.player("alice").counter_count("poison") == 1  # none additional


def test_melira_does_not_cap_the_opponents_poison():
    scenario = _board(["Melira, the Living Cure"])
    scenario.game.add_player_counters("bob", "poison", 3)
    assert scenario.player("bob").counter_count("poison") == 3


@pytest.mark.parametrize(
    "name",
    [
        "Tainted Remedy",
        "Rain of Gore",
        "Phial of Galadriel",
        "Bloodletter of Aclazotz",
        "Worship",
        "Melira, the Living Cure",
    ],
)
def test_life_and_poison_lines_are_handled(name):
    _handled(name)


# -- one-event families: search, mill, coin, proliferate, explore, life payment,
#    dice, cycling draws, noncombat damage floors ------------------------------

from magic_cards_model.machines.combat import has_keyword  # noqa: E402
from magic_cards_model.machines.effects.library import _mill  # noqa: E402
from magic_cards_model.models import Zone  # noqa: E402


def _names(cards):
    return [c.name for c in cards]


def _search_for(scenario, who, name):
    return scenario.game.search_library(who, lambda c: c.name == name, optional=True, shuffle=False)


def _search_board(alice_battlefield, bob_battlefield):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4 + ["Forest", "Island"],
            battlefield=list(alice_battlefield),
        )
        .player(
            "bob", library=["Island"] * 4 + ["Forest", "Island"], battlefield=list(bob_battlefield)
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_aven_mindcensor_hides_everything_below_the_top_four_from_an_opponents_search():
    scenario = _search_board([], ["Aven Mindcensor"])

    assert _search_for(scenario, "alice", "Forest") == []


def test_aven_mindcensor_still_lets_an_opponent_find_a_card_in_the_top_four():
    scenario = _search_board([], ["Aven Mindcensor"])
    scenario.player("alice").library[2] = scenario.player("alice").library.pop(4)

    assert _names(_search_for(scenario, "alice", "Forest")) == ["Forest"]


def test_aven_mindcensor_does_not_limit_its_controllers_own_search():
    scenario = _search_board([], ["Aven Mindcensor"])

    assert _names(_search_for(scenario, "bob", "Forest")) == ["Forest"]


def test_a_search_without_aven_mindcensor_sees_the_whole_library():
    scenario = _search_board([], [])

    assert _names(_search_for(scenario, "alice", "Forest")) == ["Forest"]


def test_aven_mindcensor_and_the_water_crystal_are_handled():
    _handled("Aven Mindcensor", "search a library")
    _handled("The Water Crystal", "mill one or more")


def _mill_board(alice_battlefield, hand=()):
    scenario = (
        Scenario()
        .player(
            "alice", library=["Island"] * 10, battlefield=list(alice_battlefield), hand=list(hand)
        )
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_water_crystal_makes_an_opponent_mill_four_more():
    scenario = _mill_board(["The Water Crystal"])

    _mill(scenario.game, scenario.player("bob"), 2)

    assert len(scenario.player("bob").graveyard) == 6


def test_the_water_crystal_leaves_its_controllers_own_mill_alone():
    scenario = _mill_board(["The Water Crystal"])

    _mill(scenario.game, scenario.player("alice"), 2)

    assert len(scenario.player("alice").graveyard) == 2


def test_a_mill_without_the_water_crystal_is_the_printed_count():
    scenario = _mill_board([])

    _mill(scenario.game, scenario.player("bob"), 2)

    assert len(scenario.player("bob").graveyard) == 2


def test_the_water_crystal_activation_mills_cards_equal_to_its_controllers_hand_plus_four():
    scenario = _mill_board(
        ["The Water Crystal"] + ["Island"] * 6, hand=["Forest", "Forest", "Forest"]
    )
    crystal = scenario.find("The Water Crystal", Zone.BATTLEFIELD, "alice")

    scenario.activate(crystal, auto=True)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").graveyard) == 3 + 4


def test_the_water_crystal_activation_with_an_empty_hand_mills_nothing_so_nothing_is_replaced():
    scenario = _mill_board(["The Water Crystal"] + ["Island"] * 6)
    crystal = scenario.find("The Water Crystal", Zone.BATTLEFIELD, "alice")

    scenario.activate(crystal, auto=True)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").graveyard) == 0, "CR 701.17a: milling zero is no mill"


# -- Krark's Thumb: CR 705, 614.1a ------------------------------------------------


def _flips(battlefield, count, *, who="alice"):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, [scenario.game.flip_coin(who) for _ in range(count)]


def test_krarks_thumb_flips_two_coins_and_keeps_the_better_one():
    _, plain = _flips([], 40)
    scenario, thumbed = _flips(["Krark's Thumb"], 20)

    assert thumbed == [plain[2 * i] or plain[2 * i + 1] for i in range(20)]
    assert scenario.game.coin_flips_performed == 40
    assert not all(plain), "the fixed seed must give at least one losing flip to ignore"


def test_krarks_thumb_does_not_change_an_opponents_flip():
    _, plain = _flips([], 20)
    scenario, theirs = _flips(["Krark's Thumb"], 20, who="bob")

    assert theirs == plain
    assert scenario.game.coin_flips_performed == 20


def test_krarks_thumb_is_handled():
    _handled("Krark's Thumb", "flip a coin")


# -- Tekuthal: CR 701.34, 614.1a ---------------------------------------------------


def _proliferate_board(battlefield):
    scenario = _board(battlefield)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "+1/+1", 1)
    return scenario, bears


def test_tekuthal_makes_its_controller_proliferate_twice():
    scenario, bears = _proliferate_board(["Tekuthal, Inquiry Dominus", "Grizzly Bears"])

    assert scenario.game.proliferation_count("alice") == 2
    for _ in range(scenario.game.proliferation_count("alice")):
        scenario.game.proliferate([bears])

    assert bears.counter_count("+1/+1") == 3


def test_tekuthal_leaves_an_opponents_proliferate_alone():
    scenario, _ = _proliferate_board(["Grizzly Bears"])
    scenario.game.battlefield  # noqa: B018 - the board exists
    other = (
        Scenario()
        .player("alice", library=["Island"] * 2)
        .player("bob", battlefield=["Tekuthal, Inquiry Dominus"], library=["Island"] * 2)
        .build()
    )
    other.start_at(Step.PRECOMBAT_MAIN)

    assert other.game.proliferation_count("alice") == 1
    assert other.game.proliferation_count("bob") == 2


def test_tekuthal_is_handled():
    _handled("Tekuthal, Inquiry Dominus", "proliferate")


# -- Twists and Turns: CR 701.44, 614.1a --------------------------------------------


def _explore_board(
    alice_battlefield, alice_library, bob_battlefield=(), bob_library=("Island", "Swamp")
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice_battlefield) + ["Forest"],
            hand=["Enter the Unknown"],
            library=list(alice_library),
        )
        .player("bob", battlefield=list(bob_battlefield), library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_the_unknown(scenario, target):
    scenario.cast_onto_stack(
        "Enter the Unknown",
        *scenario.untapped_sources("Forest", username="alice"),
        targets=[target],
    )
    scenario.resolve_top()


def test_twists_and_turns_scries_one_before_a_creature_you_control_explores():
    scenario = _explore_board(
        ["Twists and Turns", "Grizzly Bears"], ["Mountain", "Forest", "Island"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    mountain = scenario.top_of_library(1, "alice")[0]
    scenario.scry_bottoming(mountain)

    _enter_the_unknown(scenario, bears)

    assert "Forest" in _names(scenario.player("alice").hand), "the scried-away top card was skipped"
    assert _names(scenario.player("alice").library)[-1] == "Mountain"


def test_without_twists_and_turns_explore_reveals_the_top_card_as_printed():
    scenario = _explore_board(["Grizzly Bears"], ["Mountain", "Forest", "Island"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _enter_the_unknown(scenario, bears)

    assert "Mountain" in _names(scenario.player("alice").hand)
    assert not [q for q in scenario.questions_asked() if q.kind.name == "SCRY"]


def test_twists_and_turns_does_not_scry_for_an_opponents_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Forest"],
            hand=["Enter the Unknown"],
            library=["Mountain", "Swamp"],
        )
        .player("bob", battlefield=["Twists and Turns"], library=["Island"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enter_the_unknown(scenario, bears)

    assert "Mountain" in _names(scenario.player("alice").hand)
    assert not [q for q in scenario.questions_asked() if q.kind.name == "SCRY"]


def test_twists_and_turns_is_handled():
    _handled("Twists and Turns // Mycoid Maze", "would explore")


# -- Ashiok, Wicked Manipulator: CR 118.3, 119.4, 614.1a ------------------------------


def _ashiok_board(library_size, *, with_ashiok=True):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * library_size,
            battlefield=["Ashiok, Wicked Manipulator"] if with_ashiok else [],
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_ashiok_exiles_cards_from_the_library_instead_of_paying_life():
    scenario = _ashiok_board(5)
    scenario.will_pay_the_life()

    assert scenario.game.may_pay_life("alice", 3) is True

    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").library) == 2
    assert len(scenario.game.exile) == 3


def test_ashiok_does_not_apply_when_the_library_is_too_small():
    scenario = _ashiok_board(2)
    scenario.will_pay_the_life()

    scenario.game.may_pay_life("alice", 3)

    assert scenario.player("alice").life == 17
    assert len(scenario.player("alice").library) == 2


def test_ashiok_does_not_touch_life_loss_that_is_not_a_payment():
    scenario = _ashiok_board(5)

    scenario.game.lose_life("alice", 3)

    assert scenario.player("alice").life == 17
    assert len(scenario.player("alice").library) == 5


def test_ashiok_does_not_change_an_opponents_life_payment():
    scenario = _ashiok_board(5)
    scenario.will_pay_the_life(username="bob")

    scenario.game.may_pay_life("bob", 3)

    assert scenario.player("bob").life == 17
    assert len(scenario.player("bob").library) == 3


def test_ashiok_is_handled():
    _handled("Ashiok, Wicked Manipulator", "pay life")


# -- Pixie Guide, Barbarian Class: CR 706, 614.1a -------------------------------------


def _dice(battlefield, sides, count, *, who="alice", rolls=1):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, [scenario.game.roll_dice(who, sides, count) for _ in range(rolls)]


def test_pixie_guide_rolls_one_extra_die_and_ignores_the_lowest():
    _, plain = _dice([], 20, 2, rolls=6)
    scenario, boosted = _dice(["Pixie Guide"], 20, 1, rolls=6)

    assert boosted == [[max(pair)] for pair in plain]
    assert scenario.game.coin_flips_performed == 12


def test_pixie_guide_with_two_dice_rolls_three_and_ignores_the_lowest():
    _, plain = _dice([], 20, 3, rolls=4)
    _, boosted = _dice(["Pixie Guide"], 20, 2, rolls=4)

    def drop_lowest(rolls):
        kept = list(rolls)
        kept.remove(min(kept))
        return kept

    assert boosted == [drop_lowest(trio) for trio in plain]


def test_pixie_guide_does_not_change_an_opponents_roll():
    _, plain = _dice([], 20, 1, who="bob", rolls=4)
    scenario, theirs = _dice(["Pixie Guide"], 20, 1, who="bob", rolls=4)

    assert theirs == plain
    assert scenario.game.coin_flips_performed == 4


def test_barbarian_class_level_one_rolls_an_extra_die_too():
    _, plain = _dice([], 6, 2, rolls=6)
    _, boosted = _dice(["Barbarian Class"], 6, 1, rolls=6)

    assert boosted == [[max(pair)] for pair in plain]


def test_barbarian_class_level_two_pumps_a_creature_when_you_roll_dice():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Barbarian Class", "Grizzly Bears"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Barbarian Class", Zone.BATTLEFIELD, "alice").class_level = 2
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.roll_dice("alice", 20, 1)
    scenario.choose_trigger_targets("Barbarian Class", [bears])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).power == 4
    assert has_keyword(bears, "menace", scenario.game)


def test_barbarian_class_level_one_does_not_trigger_on_a_roll():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Barbarian Class", "Grizzly Bears"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.roll_dice("alice", 20, 1)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_pixie_guide_and_barbarian_class_are_handled():
    _handled("Pixie Guide", "roll one or more dice")
    _handled("Barbarian Class", "roll one or more dice")
    _handled("Barbarian Class", "Whenever you roll")


# -- Unpredictable Cyclone: CR 702.29, 614.1a, 614.11 ---------------------------------


def _cyclone_board(*, cyclone=True):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=(["Unpredictable Cyclone"] if cyclone else []) + ["Island", "Island"],
            hand=["Archfiend of Ifnir"],
            library=["Island", "Grizzly Bears", "Swamp"],
        )
        .player("bob", library=["Island"] * 3, hand=["Archfiend of Ifnir"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_unpredictable_cyclone_exiles_to_a_shared_type_and_casts_it_instead_of_drawing():
    scenario = _cyclone_board()
    cycled = scenario.find("Archfiend of Ifnir", Zone.HAND, "alice")

    scenario.cycle(cycled, *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert _names(scenario.player("alice").hand) == []
    assert "Grizzly Bears" in scenario.battlefield_names()
    assert _names(scenario.player("alice").library) == ["Swamp", "Island"]


def test_cycling_without_unpredictable_cyclone_draws_a_card():
    scenario = _cyclone_board(cyclone=False)
    cycled = scenario.find("Archfiend of Ifnir", Zone.HAND, "alice")

    scenario.cycle(cycled, *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()

    assert _names(scenario.player("alice").hand) == ["Island"]


def test_unpredictable_cyclone_does_not_replace_an_opponents_cycling():
    scenario = _cyclone_board()
    scenario.game.battlefield  # noqa: B018 - the board exists
    cycled = scenario.find("Archfiend of Ifnir", Zone.HAND, "bob")
    for _ in range(2):
        scenario.game.put_onto_battlefield(scenario.find("Island", Zone.LIBRARY, "bob"), "bob")

    scenario.cycle(
        cycled, *scenario.untapped_sources("Island", "Island", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()

    assert _names(scenario.player("bob").hand) == ["Island"]


def test_unpredictable_cyclone_is_handled():
    _handled("Unpredictable Cyclone", "cycling ability")


# -- Ojer Axonil: CR 614.1a, 120.3 -----------------------------------------------------


def _ojer_board(battlefield=("Ojer Axonil, Deepest Might",)):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), library=["Island"] * 3)
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bolt(scenario, source, amount, target="bob"):
    scenario.game.deal_damage(scenario.player(target), amount, source=source)


def test_ojer_axonil_raises_small_noncombat_damage_from_a_red_source_to_its_power():
    scenario = _ojer_board(["Ojer Axonil, Deepest Might", "Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "alice")

    _bolt(scenario, guide, 1)

    assert scenario.player("bob").life == 20 - 4


def test_ojer_axonil_leaves_damage_at_or_above_its_power_alone():
    scenario = _ojer_board(["Ojer Axonil, Deepest Might", "Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "alice")

    _bolt(scenario, guide, 6)

    assert scenario.player("bob").life == 20 - 6


def test_ojer_axonil_ignores_a_source_that_is_not_red():
    scenario = _ojer_board(["Ojer Axonil, Deepest Might", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _bolt(scenario, bears, 1)

    assert scenario.player("bob").life == 19


def test_ojer_axonil_does_not_raise_damage_to_its_controller():
    scenario = _ojer_board(["Ojer Axonil, Deepest Might", "Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "alice")

    _bolt(scenario, guide, 1, target="alice")

    assert scenario.player("alice").life == 19


def test_ojer_axonil_is_handled():
    _handled("Ojer Axonil, Deepest Might // Temple of Power", "noncombat damage")
