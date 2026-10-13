"""EP-02 R3 T4: library look / search / return with amount-bounded criteria
(mana value <= N, any number, for each, total mana value, twice X, ...).

Rules, each read in full with `mise run rules:find` in this session:

- CR 701.20a / CR 701.20e - to reveal is to show; to look is to show only the
  looker; the card stays where it is.
- CR 701.23a / CR 701.23b - to search is to find a card matching a description,
  and with a stated quality the searcher need not find it.
- CR 608.2c - instructions are followed in order; "this way" is the earlier
  instruction's own outcome.
- CR 608.2d - an option that is illegal or impossible cannot be chosen.
- CR 202.3 - mana value.
- CR 107.3a - X on a spell or ability is announced by its controller.
- CR 603.12 - a reflexive triggered ability.
- CR 118.9 / CR 608.2g - cast during resolution without paying its mana cost.
- CR 110.2a - put onto the battlefield, not cast.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import PlayedScenario, Scenario

LISTED = [
    "All Suns' Dawn",
    "Alpine Houndmaster",
    "Angrath, Minotaur Pirate",
    "Blex, Vexing Pest // Search for Blex",
    "Bloodsoaked Insight // Sanguine Morass",
    "Bring to Light",
    "Clarion Ultimatum",
    "Discovery // Dispersal",
    "Doubling Chant",
    "Eddie Brock // Venom, Lethal Protector",
    "Hide // Seek",
    "Kaya, Spirits' Justice",
    "Knight-Errant of Eos",
    "Light-Paws, Emperor's Voice",
    "Loot, Exuberant Explorer",
    "Necromentia",
    "Niv-Mizzet Reborn",
    "Nylea's Intervention",
    "Orzhov Charm",
    "Point the Way",
    "Protean Hulk",
    "Pyre of Heroes",
    "Rogues' Gallery",
    "Search for Glory",
    "Stargaze",
    "The End",
    "Thwart the Grave",
    "Velomachus Lorehold",
    "Vivien's Invocation",
    "Wild Pair",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


PROOF: list[str] = []


@pytest.mark.parametrize("name", PROOF)
def test_every_proof_printing_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


LANDS = ("Plains", "Island", "Swamp", "Mountain", "Forest")


def _board(
    *,
    hand=(),
    battlefield=(),
    library=("Island",) * 12,
    graveyard=(),
    bob_battlefield=(),
    bob_library=("Island",) * 8,
    bob_hand=(),
    bob_graveyard=(),
    start=Step.PRECOMBAT_MAIN,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            library=list(library),
            graveyard=list(graveyard),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=list(bob_library),
            graveyard=list(bob_graveyard),
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _in_library(scenario: PlayedScenario, name: str, username: str = "alice"):
    return next(state for state in scenario.player(username).library if state.name == name)


def _names(scenario: PlayedScenario, zone: Zone, username: str = "alice") -> list[str]:
    return sorted(state.name for state in getattr(scenario.player(username), zone.value))


def _offered(scenario: PlayedScenario, source: str) -> list[str] | None:
    """The cards the first `CHOOSE_CARDS` question from `source` offered."""
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == source
    ]
    if not questions:
        return None
    offered = set(questions[0].cards)
    return sorted(state.name for state in scenario.all_card_states() if state.id in offered)


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_x(scenario: PlayedScenario, name: str, x: int, *, user: str = "alice") -> None:
    spell = scenario.find(name, Zone.HAND, user)
    scenario.game.cast(
        spell,
        user,
        x_value=x,
        mana_sources=scenario.untapped_sources(*scenario.battlefield_names(), username=user),
    )
    _resolve_all(scenario)


# --------------------------------------------------------------------------
# Search for Blex: "put any number of them into your hand and the rest into
# your graveyard. You lose 3 life for each card you put into your hand this way"
# --------------------------------------------------------------------------

BLEX = "Blex, Vexing Pest // Search for Blex"
SEARCH_FOR_BLEX = "Search for Blex"
BLEX_FRONT = "Blex, Vexing Pest"  # CR 712.8a: a card in the graveyard has its front face
FIVE = ["Grizzly Bears", "Hill Giant", "Serra Angel", "Opt", "Forest"]


def _search_for_blex(library: list[str]) -> PlayedScenario:
    return _board(hand=[BLEX], battlefield=["Swamp"] * 4, library=library)


def _cast_search_for_blex(scenario: PlayedScenario) -> None:
    casting = scenario.cast(BLEX, "alice")
    casting.cast_as_split_half(SEARCH_FOR_BLEX)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_search_for_blex_puts_chosen_cards_in_hand_and_the_rest_in_graveyard():
    scenario = _search_for_blex([*FIVE, "Island", "Island"])
    chosen = [_in_library(scenario, "Hill Giant"), _in_library(scenario, "Opt")]
    scenario.will_choose_cards(*chosen, username="alice", source=SEARCH_FOR_BLEX)

    _cast_search_for_blex(scenario)

    assert {state.name for state in scenario.player("alice").hand} == {"Hill Giant", "Opt"}
    assert _names(scenario, Zone.GRAVEYARD) == sorted(
        [*(n for n in FIVE if n not in ("Hill Giant", "Opt")), BLEX_FRONT]
    )
    assert scenario.player("alice").life == 20 - 3 * 2, "3 life for each card put into hand"
    assert len(scenario.player("alice").library) == 2, "only the top five were looked at"


def test_search_for_blex_may_put_none_and_loses_no_life():
    scenario = _search_for_blex([*FIVE, "Island"])
    scenario.will_choose_cards(username="alice", source=SEARCH_FOR_BLEX)

    _cast_search_for_blex(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 20
    assert len(_names(scenario, Zone.GRAVEYARD)) == 6, "five looked-at cards and the spell"


def test_search_for_blex_may_put_all_five():
    scenario = _search_for_blex([*FIVE, "Island"])
    scenario.will_choose_cards(
        *(_in_library(scenario, name) for name in FIVE), username="alice", source=SEARCH_FOR_BLEX
    )

    _cast_search_for_blex(scenario)

    assert len(scenario.player("alice").hand) == 5
    assert scenario.player("alice").life == 20 - 15


def test_search_for_blex_with_a_short_library_looks_at_what_there_is():
    scenario = _search_for_blex(["Opt", "Forest"])
    scenario.will_choose_cards(
        _in_library(scenario, "Opt"), username="alice", source=SEARCH_FOR_BLEX
    )

    _cast_search_for_blex(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Opt"]
    assert _names(scenario, Zone.GRAVEYARD) == sorted(["Forest", BLEX_FRONT])
    assert scenario.player("alice").life == 17


# --------------------------------------------------------------------------
# Stargaze: "Look at twice X cards from the top of your library. Put X cards
# from among them into your hand and the rest into your graveyard. You lose X
# life." (CR 107.3a: X is announced)
# --------------------------------------------------------------------------

STARGAZE = "Stargaze"
SIX = ["Grizzly Bears", "Hill Giant", "Serra Angel", "Opt", "Forest", "Craw Wurm"]


def _stargaze(library: list[str]) -> PlayedScenario:
    return _board(hand=[STARGAZE], battlefield=["Swamp"] * 6, library=library)


def test_stargaze_x2_looks_at_four_and_takes_exactly_two():
    scenario = _stargaze([*SIX, "Island", "Island"])
    chosen = [_in_library(scenario, "Serra Angel"), _in_library(scenario, "Opt")]
    scenario.will_choose_cards(*chosen, username="alice", source=STARGAZE)

    _cast_x(scenario, STARGAZE, 2)

    assert {state.name for state in scenario.player("alice").hand} == {"Serra Angel", "Opt"}
    assert _names(scenario, Zone.GRAVEYARD) == sorted(["Grizzly Bears", "Hill Giant", STARGAZE])
    assert scenario.player("alice").life == 18
    assert len(scenario.player("alice").library) == 4, "twice X = four cards were looked at"


def test_stargaze_x3_looks_at_six():
    scenario = _stargaze([*SIX, "Island", "Island"])
    chosen = [_in_library(scenario, name) for name in ("Hill Giant", "Opt", "Craw Wurm")]
    scenario.will_choose_cards(*chosen, username="alice", source=STARGAZE)

    _cast_x(scenario, STARGAZE, 3)

    assert len(scenario.player("alice").hand) == 3
    assert len(_names(scenario, Zone.GRAVEYARD)) == 4
    assert scenario.player("alice").life == 17


def test_stargaze_x0_looks_at_nothing_and_loses_nothing():
    scenario = _stargaze([*SIX])
    _cast_x(scenario, STARGAZE, 0)

    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 6
    assert scenario.player("alice").life == 20


def test_stargaze_with_a_short_library_puts_every_looked_at_card_when_x_exceeds_it():
    scenario = _stargaze(["Opt", "Forest"])
    _cast_x(scenario, STARGAZE, 2)

    assert {state.name for state in scenario.player("alice").hand} == {"Opt", "Forest"}
    assert scenario.player("alice").life == 18


# --------------------------------------------------------------------------
# Knight-Errant of Eos: "look at the top six cards ... reveal up to two
# creature cards with mana value X or less ..., where X is the number of
# creatures that convoked this creature. Put the revealed cards into your
# hand, then shuffle." (CR 702.51c)
# --------------------------------------------------------------------------

KNIGHT = "Knight-Errant of Eos"
KNIGHT_TOP = [
    "Grizzly Bears",
    "Hill Giant",
    "Llanowar Elves",
    "Serra Angel",
    "Forest",
    "Opt",
]


def _knight_errant(convokers: int, library: list[str]) -> PlayedScenario:
    scenario = _board(
        hand=[KNIGHT],
        battlefield=["Ornithopter"] * convokers + ["Plains"] * (5 - convokers),
        library=library,
    )
    casting = scenario.cast(KNIGHT)
    payment = casting.begin_paying()
    for ornithopter in scenario.creatures(*["Ornithopter"] * convokers):
        convoke(payment, casting.spell, ornithopter)
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    return scenario


def test_knight_errant_offers_creatures_up_to_the_convoking_creature_count():
    scenario = _knight_errant(2, [*KNIGHT_TOP, "Island", "Island"])
    bears = _in_library(scenario, "Grizzly Bears")
    elves = _in_library(scenario, "Llanowar Elves")
    scenario.will_choose_cards(bears, elves, username="alice", source=KNIGHT)

    scenario.resolve_top()
    _resolve_all(scenario)

    assert _offered(scenario, KNIGHT) == ["Grizzly Bears", "Llanowar Elves"], (
        "two creatures convoked it: mana value 2 or less; Hill Giant (3) and Serra Angel (5) "
        "and the noncreatures are never offered"
    )
    assert {state.name for state in scenario.player("alice").hand} == {
        "Grizzly Bears",
        "Llanowar Elves",
    }
    assert len(scenario.player("alice").library) == 6, "the rest stays in the library"


def test_knight_errant_may_reveal_just_one():
    scenario = _knight_errant(2, [*KNIGHT_TOP, "Island"])
    scenario.will_choose_cards(
        _in_library(scenario, "Grizzly Bears"), username="alice", source=KNIGHT
    )

    scenario.resolve_top()
    _resolve_all(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_knight_errant_cast_without_convoke_offers_only_mana_value_zero():
    scenario = _knight_errant(0, [*KNIGHT_TOP, "Island"])

    scenario.resolve_top()
    _resolve_all(scenario)

    assert _offered(scenario, KNIGHT) is None, "X is 0 and no creature card there has mana value 0"
    assert scenario.player("alice").hand == []


# --------------------------------------------------------------------------
# Loot, Exuberant Explorer: "{4}{G}{G}, {T}: Look at the top six cards ...
# reveal a creature card with mana value less than or equal to the number of
# lands you control from among them and put it onto the battlefield. Put the
# rest on the bottom in a random order."
# --------------------------------------------------------------------------

LOOT = "Loot, Exuberant Explorer"
LOOT_TOP = ["Protean Hulk", "Craw Wurm", "Grizzly Bears", "Opt", "Forest", "Serra Angel"]


def _loot(lands: int) -> PlayedScenario:
    return _board(
        battlefield=[LOOT, *["Forest"] * lands],
        library=[*LOOT_TOP, "Island", "Island"],
    )


def _activate_loot(scenario: PlayedScenario) -> None:
    loot = scenario.creature(LOOT)
    scenario.activate(loot, *scenario.untapped_sources(*["Forest"] * 6), index=0)
    _resolve_all(scenario)


def test_loot_bound_is_the_number_of_lands_you_control():
    scenario = _loot(7)
    hulk = _in_library(scenario, "Protean Hulk")
    scenario.will_choose_cards(hulk, username="alice", source=LOOT)

    _activate_loot(scenario)

    assert hulk.zone is Zone.BATTLEFIELD and hulk.controller == "alice"
    assert _offered(scenario, LOOT) == [
        "Craw Wurm",
        "Grizzly Bears",
        "Protean Hulk",
        "Serra Angel",
    ], "seven lands: a mana value 7 creature is offered; noncreature cards never are"
    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Island", "Island"]
    assert sorted(library[2:]) == sorted(n for n in LOOT_TOP if n != "Protean Hulk")


def test_loot_with_six_lands_does_not_offer_the_seven_drop():
    scenario = _loot(6)
    wurm = _in_library(scenario, "Craw Wurm")
    scenario.will_choose_cards(wurm, username="alice", source=LOOT)

    _activate_loot(scenario)

    assert wurm.zone is Zone.BATTLEFIELD
    assert "Protean Hulk" not in (_offered(scenario, LOOT) or [])


def test_loot_may_choose_none_and_bottoms_all_six():
    scenario = _loot(7)
    scenario.will_choose_cards(username="alice", source=LOOT)

    _activate_loot(scenario)

    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Island", "Island"] and sorted(library[2:]) == sorted(LOOT_TOP)


def test_loot_put_is_not_a_cast():
    """CR 110.2a: put onto the battlefield, not cast."""
    scenario = _loot(7)
    scenario.will_choose_cards(
        _in_library(scenario, "Grizzly Bears"), username="alice", source=LOOT
    )

    _activate_loot(scenario)

    assert scenario.game.spells_cast_this_turn.get("alice", []) == []


# --------------------------------------------------------------------------
# Velomachus Lorehold: "look at the top seven cards. You may cast an instant
# or sorcery spell with mana value less than or equal to ~'s power from among
# them without paying its mana cost. Put the rest on the bottom ..."
# --------------------------------------------------------------------------

VELOMACHUS = "Velomachus Lorehold"
VELO_TOP = [
    "Clarion Ultimatum",
    "Opt",
    "Grizzly Bears",
    "Lightning Bolt",
    "Counterspell",
    "Forest",
    "Divination",
]


def _velomachus_attacks(library: list[str]) -> PlayedScenario:
    scenario = _board(battlefield=[VELOMACHUS], library=[*library, "Island", "Island"])
    scenario.attack_with(scenario.creature(VELOMACHUS))
    return scenario


def test_velomachus_casts_a_spell_with_mana_value_up_to_its_power_free():
    scenario = _velomachus_attacks(VELO_TOP)
    divination = _in_library(scenario, "Divination")
    scenario.will_choose_cards(divination, username="alice", source=VELOMACHUS)
    scenario.will_take_the_may(username="alice", source=VELOMACHUS)

    _resolve_all(scenario)

    assert _offered(scenario, VELOMACHUS) == ["Divination", "Lightning Bolt", "Opt"], (
        "power 5: Clarion Ultimatum (7) is over the bound; creatures and lands are not spells; "
        "Counterspell has no spell to target (CR 608.2d: only a spell that can be cast is offered)"
    )
    assert divination.zone is Zone.GRAVEYARD, "Divination was cast and resolved"
    assert len(scenario.game.spells_cast_this_turn.get("alice", [])) == 1
    assert len(scenario.player("alice").hand) == 2, "Divination drew two"


def test_velomachus_may_decline_and_bottoms_all_seven():
    scenario = _velomachus_attacks(VELO_TOP)
    scenario.will_take_the_may(False, username="alice", source=VELOMACHUS)

    _resolve_all(scenario)

    assert scenario.game.spells_cast_this_turn.get("alice", []) == []
    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Island", "Island"] and sorted(library[2:]) == sorted(VELO_TOP)


def test_velomachus_with_nothing_castable_asks_nothing():
    scenario = _velomachus_attacks(["Clarion Ultimatum", "Grizzly Bears", "Forest"])

    _resolve_all(scenario)

    assert _offered(scenario, VELOMACHUS) is None
    assert len(scenario.player("alice").library) == 5


# --------------------------------------------------------------------------
# Vivien's Invocation: "Look at the top seven cards of your library. You may
# put a creature card from among them onto the battlefield. Put the rest on
# the bottom of your library in a random order. When a creature is put onto
# the battlefield this way, it deals damage equal to its power to target
# creature an opponent controls." (CR 603.12)
# --------------------------------------------------------------------------

VIVIEN = "Vivien's Invocation"
VIVIEN_TOP = ["Hill Giant", "Grizzly Bears", "Opt", "Forest", "Serra Angel", "Island", "Island"]


def _viviens_invocation(library: list[str], bob_battlefield=("Grizzly Bears",)) -> PlayedScenario:
    return _board(
        hand=[VIVIEN],
        battlefield=["Forest"] * 7,
        library=[*library, "Island"],
        bob_battlefield=list(bob_battlefield),
    )


def test_viviens_invocation_creature_deals_damage_equal_to_its_power():
    scenario = _viviens_invocation(VIVIEN_TOP)
    giant = _in_library(scenario, "Hill Giant")
    victim = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(giant, username="alice", source=VIVIEN)

    scenario.cast_onto_stack(VIVIEN, auto=True)
    scenario.resolve_top()
    scenario.will_choose_targets(victim, username="alice")
    _resolve_all(scenario)

    assert giant.zone is Zone.BATTLEFIELD and giant.controller == "alice"
    assert victim.zone is Zone.GRAVEYARD, "Hill Giant's power 3 killed the 2/2"
    assert giant.damage == 0, "the creature deals the damage; it takes none"


def test_viviens_invocation_with_no_creature_chosen_deals_no_damage():
    scenario = _viviens_invocation(VIVIEN_TOP)
    victim = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(username="alice", source=VIVIEN)

    scenario.cast_onto_stack(VIVIEN, auto=True)
    _resolve_all(scenario)

    assert victim.zone is Zone.BATTLEFIELD
    library = [state.name for state in scenario.player("alice").library]
    assert sorted(library[1:]) == sorted(VIVIEN_TOP)


def test_viviens_invocation_with_no_opposing_creature_just_puts_the_creature():
    scenario = _viviens_invocation(VIVIEN_TOP, bob_battlefield=())
    giant = _in_library(scenario, "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=VIVIEN)

    scenario.cast_onto_stack(VIVIEN, auto=True)
    _resolve_all(scenario)

    assert giant.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Niv-Mizzet Reborn: "reveal the top ten cards of your library. For each color
# pair, choose a card that's exactly those colors from among them. Put the
# chosen cards into your hand and the rest on the bottom of your library in a
# random order."
# --------------------------------------------------------------------------

NIV = "Niv-Mizzet Reborn"
GOLD = {
    ("W", "U"): "Absolute Virtue",
    ("W", "B"): "Agent of Masks",
    ("W", "R"): "Akroan Hoplite",
    ("W", "G"): "Ahn-Crop Champion",
    ("U", "B"): "Architects of Will",
    ("U", "R"): "Abandon Attachments",
    ("U", "G"): "Absorbing Man",
    ("B", "R"): "Anathemancer",
    ("B", "G"): "Abrupt Decay",
    ("R", "G"): "Aerid Konstrari",
}


def _niv_enters(library: list[str]) -> PlayedScenario:
    scenario = _board(hand=[NIV], library=[*library, "Island", "Island"])
    scenario.put_onto_battlefield(NIV, "alice")
    scenario.game.put_triggers_on_stack()
    return scenario


def test_niv_mizzet_takes_one_card_for_each_color_pair_present():
    top = [GOLD[("W", "U")], GOLD[("B", "R")], GOLD[("R", "G")], "Forest", "Opt", "Grizzly Bears"]
    top += ["Serra Angel", "Hill Giant", "Craw Wurm", "Llanowar Elves"]
    scenario = _niv_enters(top)

    scenario.pass_until_resolved()

    assert {state.name for state in scenario.player("alice").hand} == {
        GOLD[("W", "U")],
        GOLD[("B", "R")],
        GOLD[("R", "G")],
    }
    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Island", "Island"]
    assert sorted(library[2:]) == sorted(n for n in top if n not in scenario_hand(scenario))


def scenario_hand(scenario: PlayedScenario) -> set[str]:
    return {state.name for state in scenario.player("alice").hand}


def test_niv_mizzet_chooses_among_several_cards_of_the_same_pair():
    top = ["Architects of Will", "Bane Alley Broker", "Forest", "Opt"] + ["Island"] * 6
    scenario = _niv_enters(top)
    broker = _in_library(scenario, "Bane Alley Broker")
    scenario.will_choose_cards(broker, username="alice", source=NIV)

    scenario.pass_until_resolved()

    assert "Bane Alley Broker" in scenario_hand(scenario)
    assert "Architects of Will" not in scenario_hand(scenario)


def test_niv_mizzet_with_no_pair_present_takes_nothing():
    scenario = _niv_enters(["Grizzly Bears", "Forest", "Opt", "Hill Giant"])

    scenario.pass_until_resolved()

    assert scenario_hand(scenario) == set()
    assert len(scenario.player("alice").library) == 6


def test_niv_mizzet_ignores_cards_of_one_or_three_colors():
    scenario = _niv_enters(["Serra Angel", "Wrath of God", "Counterspell"])

    scenario.pass_until_resolved()

    assert scenario_hand(scenario) == set()
