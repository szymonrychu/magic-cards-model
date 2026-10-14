"""EP-02 R3 T4: library searches whose criteria are bounded by an amount -
mana value <= N, a total mana value, "up to X" with X defined elsewhere, the
same name / total power and toughness as another object, a quality list, or a
named pair.

Rules, each read in full with `mise run rules:find` in this session:

- CR 701.23a / CR 701.23b - to search is to find a matching card; with a stated
  quality the searcher need not find it.
- CR 701.24a / CR 701.24b - the shuffle; found cards are not in it.
- CR 107.3a - X on a spell is announced; CR 107.3f - X from text.
- CR 202.3 - mana value (a split card's is the combined halves in the library).
- CR 105.1 / converge - colors of mana spent.
- CR 702.179 - speed.
- CR 608.2d - an illegal option cannot be chosen.
- CR 303.4i - an Aura put onto the battlefield attached to something it cannot
  enchant stays where it was.
"""

import pytest

from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario

from .test_ep02_r3_library_amounts import _board, _in_library, _names, _offered, _resolve_all


def _cast_half(
    scenario: PlayedScenario,
    card_name: str,
    half: str,
    *,
    targets=None,
    username: str = "alice",
) -> None:
    """Cast one half of a split / modal double-faced card and let everything resolve."""
    casting = scenario.cast(card_name, username)
    casting.cast_as_split_half(half)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=username)
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


# --------------------------------------------------------------------------
# Bring to Light: converge - mana value <= the number of colors of mana spent
# --------------------------------------------------------------------------

BRING = "Bring to Light"
BRING_LIB = ["Lightning Bolt", "Grizzly Bears", "Hill Giant", "Serra Angel", "Forest", "Divination"]


def _bring_to_light(paid_with: list[str], library=BRING_LIB) -> PlayedScenario:
    return _board(hand=[BRING], battlefield=paid_with, library=[*library, "Island", "Island"])


def _cast_bring(scenario: PlayedScenario) -> None:
    scenario.cast_onto_stack(BRING, auto=True)
    _resolve_all(scenario)


def test_bring_to_light_two_colors_spent_finds_mana_value_two_or_less_and_casts_it_free():
    scenario = _bring_to_light(["Forest", "Island", "Forest", "Forest", "Island"])
    bears = _in_library(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=BRING)
    scenario.will_take_the_may(username="alice", source=BRING)

    _cast_bring(scenario)

    assert _offered(scenario, BRING) == ["Grizzly Bears", "Lightning Bolt"], (
        "two colors spent: mana value 2 or less among creature, instant and sorcery cards; "
        "Divination (3), Hill Giant (4), Serra Angel (5) and Forest are never offered"
    )
    assert bears.zone is Zone.BATTLEFIELD, "found, exiled, then cast without paying and resolved"
    assert bears not in scenario.player("alice").library


def test_bring_to_light_five_colors_spent_reaches_mana_value_three():
    scenario = _bring_to_light(["Plains", "Island", "Swamp", "Mountain", "Forest"])
    giant = _in_library(scenario, "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=BRING)
    scenario.will_take_the_may(username="alice", source=BRING)

    _cast_bring(scenario)

    assert "Hill Giant" in (_offered(scenario, BRING) or [])
    assert "Serra Angel" in (_offered(scenario, BRING) or []), "five colors: mana value 5 or less"
    assert giant.zone is Zone.BATTLEFIELD


def test_bring_to_light_may_decline_the_free_cast_and_the_card_stays_exiled():
    scenario = _bring_to_light(["Forest", "Island", "Forest", "Forest", "Island"])
    bolt = _in_library(scenario, "Lightning Bolt")
    scenario.will_choose_cards(bolt, username="alice", source=BRING)
    scenario.will_take_the_may(False, username="alice", source=BRING)

    _cast_bring(scenario)

    assert bolt.zone is Zone.EXILE


# --------------------------------------------------------------------------
# Search for Glory: a quality list, and life for each snow mana spent
# --------------------------------------------------------------------------

GLORY = "Search for Glory"
GLORY_LIB = [
    "Snow-Covered Island",
    "Isamaru, Hound of Konda",
    "Ballad of the Black Flag",
    "Grizzly Bears",
    "Forest",
]


def _glory(paid_with: list[str]) -> PlayedScenario:
    return _board(hand=[GLORY], battlefield=paid_with, library=[*GLORY_LIB, "Island"])


def test_search_for_glory_finds_a_snow_permanent_a_legend_or_a_saga_and_gains_per_snow_mana():
    scenario = _glory(["Snow-Covered Plains"] * 3)
    saga = _in_library(scenario, "Ballad of the Black Flag")
    scenario.will_choose_cards(saga, username="alice", source=GLORY)

    scenario.cast_onto_stack(GLORY, auto=True)
    _resolve_all(scenario)

    assert _offered(scenario, GLORY) == [
        "Ballad of the Black Flag",
        "Isamaru, Hound of Konda",
        "Snow-Covered Island",
    ], "a snow permanent card, a legendary card, or a Saga card - nothing else"
    assert [state.name for state in scenario.player("alice").hand] == ["Ballad of the Black Flag"]
    assert scenario.player("alice").life == 23, "1 life for each {S} spent: three snow lands"


def test_search_for_glory_gains_nothing_when_no_snow_mana_was_spent():
    scenario = _glory(["Plains"] * 3)
    scenario.will_choose_cards(
        _in_library(scenario, "Isamaru, Hound of Konda"), username="alice", source=GLORY
    )

    scenario.cast_onto_stack(GLORY, auto=True)
    _resolve_all(scenario)

    assert scenario.player("alice").life == 20
    assert [state.name for state in scenario.player("alice").hand] == ["Isamaru, Hound of Konda"]


# --------------------------------------------------------------------------
# Nylea's Intervention: "up to X land cards" and "twice X damage"
# --------------------------------------------------------------------------

NYLEA = "Nylea's Intervention"


def _nylea(mode: int, x: int, bob_battlefield=()) -> PlayedScenario:
    scenario = _board(
        hand=[NYLEA],
        battlefield=["Forest"] * 6,
        library=["Forest", "Forest", "Mountain", "Grizzly Bears", "Island", "Island"],
        bob_battlefield=list(bob_battlefield),
    )
    spell = scenario.find(NYLEA, Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        modes=[mode],
        x_value=x,
        mana_sources=scenario.untapped_sources(*["Forest"] * 6),
    )
    return scenario


def test_nylea_search_mode_finds_up_to_x_lands_into_hand():
    scenario = _nylea(1, 2)
    lands = [_in_library(scenario, "Mountain"), _in_library(scenario, "Forest")]
    scenario.will_choose_cards(*lands, username="alice", source=NYLEA)

    _resolve_all(scenario)

    assert sorted(state.name for state in scenario.player("alice").hand) == ["Forest", "Mountain"]


def test_nylea_search_mode_with_x_zero_finds_nothing():
    scenario = _nylea(1, 0)

    _resolve_all(scenario)

    assert scenario.player("alice").hand == []


def test_nylea_damage_mode_deals_twice_x_to_each_flier_only():
    scenario = _nylea(2, 2, bob_battlefield=["Serra Angel", "Wind Drake", "Hill Giant"])

    _resolve_all(scenario)

    assert _names(scenario, Zone.GRAVEYARD, "bob") == ["Serra Angel", "Wind Drake"], (
        "twice X = 4 damage kills the 4/4 and the 2/2 fliers"
    )
    assert scenario.creature("Hill Giant", "bob").damage == 0, "no flying, no damage"


# --------------------------------------------------------------------------
# Point the Way: "up to X basic land cards, where X is your speed"
# --------------------------------------------------------------------------

POINT = "Point the Way"


def _point_the_way(speed: int | None) -> PlayedScenario:
    scenario = _board(
        battlefield=[POINT, *["Forest"] * 4],
        library=["Forest", "Mountain", "Island", "Sol Ring", "Plains", "Swamp"],
    )
    scenario.player("alice").speed = speed
    scenario.activate(
        next(s for s in scenario.game.battlefield if s.name == POINT),
        *scenario.untapped_sources(*["Forest"] * 4),
        sacrificing=[next(s for s in scenario.game.battlefield if s.name == POINT)],
    )
    return scenario


def test_point_the_way_finds_up_to_speed_basic_lands_tapped():
    scenario = _point_the_way(3)
    picks = [_in_library(scenario, name) for name in ("Mountain", "Island", "Swamp")]
    scenario.will_choose_cards(*picks, username="alice", source=POINT)

    _resolve_all(scenario)

    assert all(pick.zone is Zone.BATTLEFIELD and pick.tapped for pick in picks)
    assert _offered(scenario, POINT) == sorted(
        ["Forest", "Island", "Mountain", "Plains", "Swamp"]
    ), "basic land cards only - Sol Ring is never offered"


def test_point_the_way_speed_two_finds_at_most_two():
    scenario = _point_the_way(2)
    questions = []
    _resolve_all(scenario)
    questions = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert questions and questions[0].amount == 2


def test_point_the_way_with_no_speed_finds_nothing():
    scenario = _point_the_way(None)
    before = len(scenario.player("alice").library)

    _resolve_all(scenario)

    assert len(scenario.player("alice").library) == before


# --------------------------------------------------------------------------
# Protean Hulk: "any number of creature cards with total mana value 6 or less"
# --------------------------------------------------------------------------

HULK = "Protean Hulk"
HULK_LIB = ["Grizzly Bears", "Llanowar Elves", "Ornithopter", "Gray Ogre", "Serra Angel", "Opt"]


def _hulk_dies(library=HULK_LIB) -> PlayedScenario:
    scenario = _board(battlefield=[HULK], library=[*library, "Island"])
    scenario.game.sacrifice(scenario.creature(HULK))
    scenario.game.put_triggers_on_stack()
    return scenario


def test_protean_hulk_puts_creatures_with_total_mana_value_six_onto_the_battlefield():
    scenario = _hulk_dies()
    picks = [
        _in_library(scenario, name)
        for name in ("Grizzly Bears", "Llanowar Elves", "Ornithopter", "Gray Ogre")
    ]
    scenario.will_choose_cards(*picks, username="alice", source=HULK)

    _resolve_all(scenario)

    assert all(pick.zone is Zone.BATTLEFIELD for pick in picks), "2 + 1 + 0 + 3 = 6"
    assert _offered(scenario, HULK) == sorted(
        ["Grizzly Bears", "Gray Ogre", "Llanowar Elves", "Ornithopter", "Serra Angel"]
    )


def test_protean_hulk_refuses_a_set_over_the_total():
    scenario = _hulk_dies()
    picks = [_in_library(scenario, name) for name in ("Gray Ogre", "Serra Angel")]
    scenario.will_choose_cards(*picks, username="alice", source=HULK)

    with pytest.raises(ValueError, match="total mana value"):
        _resolve_all(scenario)


def test_protean_hulk_may_find_none():
    scenario = _hulk_dies()
    scenario.will_choose_cards(username="alice", source=HULK)

    _resolve_all(scenario)

    assert not any(s.name in HULK_LIB for s in scenario.game.battlefield)


# --------------------------------------------------------------------------
# Wild Pair: "a creature card with the same total power and toughness"
# --------------------------------------------------------------------------

PAIR = "Wild Pair"


def test_wild_pair_finds_a_creature_with_the_same_total_power_and_toughness():
    scenario = _board(
        hand=["Hill Giant"],
        battlefield=[PAIR, *["Mountain"] * 4],
        library=["Pillarfield Ox", "Canyon Minotaur", "Grizzly Bears", "Craw Wurm", "Island"],
    )
    ox = _in_library(scenario, "Pillarfield Ox")
    minotaur = _in_library(scenario, "Canyon Minotaur")
    scenario.will_take_the_may(username="alice", source=PAIR)
    scenario.will_choose_cards(ox, username="alice", source=PAIR)

    scenario.cast_onto_stack("Hill Giant", auto=True)
    _resolve_all(scenario)

    assert _offered(scenario, PAIR) == ["Canyon Minotaur", "Pillarfield Ox"], (
        "Hill Giant is 3/3 = 6 total; a 2/4 and a 3/3 match, a 2/2 and a 6/4 do not"
    )
    assert ox.zone is Zone.BATTLEFIELD and minotaur.zone is Zone.LIBRARY


def test_wild_pair_does_not_trigger_for_a_creature_not_cast_from_hand():
    scenario = _board(
        hand=["Hill Giant"],
        battlefield=[PAIR],
        library=["Pillarfield Ox", "Island"],
    )

    scenario.put_onto_battlefield("Hill Giant", "alice")
    _resolve_all(scenario)

    assert _offered(scenario, PAIR) is None


# --------------------------------------------------------------------------
# Light-Paws, Emperor's Voice: an Aura with mana value <= that Aura and a
# different name than each Aura you control, put onto the battlefield attached
# --------------------------------------------------------------------------

PAWS = "Light-Paws, Emperor's Voice"


def test_light_paws_fetches_a_cheaper_differently_named_aura_attached_to_itself():
    scenario = _board(
        hand=["Pacifism"],
        battlefield=[PAWS, "Plains", "Plains"],
        library=["Pacifism", "Agoraphobia", "Bequeathal", "Rancor", "Island"],
        bob_battlefield=["Grizzly Bears"],
    )
    rancor = _in_library(scenario, "Rancor")
    scenario.will_take_the_may(username="alice", source=PAWS)
    scenario.will_choose_cards(rancor, username="alice", source=PAWS)

    scenario.cast_onto_stack(
        "Pacifism", targets=[scenario.creature("Grizzly Bears", "bob")], auto=True
    )
    _resolve_all(scenario)

    assert _offered(scenario, PAWS) == ["Agoraphobia", "Bequeathal", "Rancor"], (
        "mana value 2 or less, and not another Pacifism (an Aura named Pacifism is already here)"
    )
    assert rancor.zone is Zone.BATTLEFIELD
    assert rancor.attached_to == scenario.creature(PAWS).id


def test_light_paws_does_not_trigger_for_an_aura_you_did_not_cast():
    scenario = _board(
        hand=["Pacifism"],
        battlefield=[PAWS],
        library=["Rancor", "Island"],
        bob_battlefield=["Grizzly Bears"],
    )
    pacifism = scenario.find("Pacifism", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(pacifism, "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert _offered(scenario, PAWS) is None


# --------------------------------------------------------------------------
# Pyre of Heroes: shares a creature type with the sacrificed creature and has
# mana value equal to 1 plus its mana value
# --------------------------------------------------------------------------

PYRE = "Pyre of Heroes"


def test_pyre_of_heroes_finds_a_creature_one_mana_value_higher_sharing_a_type():
    scenario = _board(
        battlefield=[PYRE, "Llanowar Elves", "Mountain", "Mountain"],
        library=["Elvish Warrior", "Priest of Titania", "Elvish Mystic", "Grizzly Bears", "Island"],
    )
    warrior = _in_library(scenario, "Elvish Warrior")
    scenario.will_choose_cards(warrior, username="alice", source=PYRE)

    scenario.activate(
        next(s for s in scenario.game.battlefield if s.name == PYRE),
        *scenario.untapped_sources("Mountain", "Mountain"),
        sacrificing=[scenario.creature("Llanowar Elves")],
    )
    _resolve_all(scenario)

    assert _offered(scenario, PYRE) == ["Elvish Warrior", "Priest of Titania"], (
        "an Elf (shares a type) with mana value 1 + 1 = 2; the 1-drop Elf and the Bear are out"
    )
    assert warrior.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Alpine Houndmaster: a card named A and/or a card named B
# --------------------------------------------------------------------------

HOUNDMASTER = "Alpine Houndmaster"


def test_alpine_houndmaster_fetches_both_named_cards():
    scenario = _board(
        hand=[HOUNDMASTER],
        battlefield=["Mountain", "Plains"],
        library=["Alpine Watchdog", "Igneous Cur", "Grizzly Bears", "Island"],
    )
    both = [_in_library(scenario, "Alpine Watchdog"), _in_library(scenario, "Igneous Cur")]
    scenario.will_take_the_may(username="alice", source=HOUNDMASTER)
    scenario.will_choose_cards(*both, username="alice", source=HOUNDMASTER)

    scenario.cast_onto_stack(HOUNDMASTER, auto=True)
    _resolve_all(scenario)

    assert sorted(state.name for state in scenario.player("alice").hand) == [
        "Alpine Watchdog",
        "Igneous Cur",
    ]


def test_alpine_houndmaster_with_only_one_present_fetches_that_one():
    scenario = _board(
        hand=[HOUNDMASTER],
        battlefield=["Mountain", "Plains"],
        library=["Igneous Cur", "Grizzly Bears", "Island"],
    )
    scenario.will_take_the_may(username="alice", source=HOUNDMASTER)
    scenario.will_choose_cards(
        _in_library(scenario, "Igneous Cur"), username="alice", source=HOUNDMASTER
    )

    scenario.cast_onto_stack(HOUNDMASTER, auto=True)
    _resolve_all(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Igneous Cur"]


def test_alpine_houndmaster_attack_trigger_counts_the_other_attackers():
    scenario = _board(battlefield=[HOUNDMASTER, "Grizzly Bears", "Hill Giant"])
    master = scenario.creature(HOUNDMASTER)
    scenario.attack_with(
        master, scenario.creature("Grizzly Bears"), scenario.creature("Hill Giant")
    )

    _resolve_all(scenario)

    assert scenario.game.power_of(master) == 2 + 2, "+X/+0 where X = the two other attackers"


def test_alpine_houndmaster_attacking_alone_gets_nothing():
    scenario = _board(battlefield=[HOUNDMASTER, "Grizzly Bears"])
    master = scenario.creature(HOUNDMASTER)
    scenario.attack_with(master)

    _resolve_all(scenario)

    assert scenario.game.power_of(master) == 2
