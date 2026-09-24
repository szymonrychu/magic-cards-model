"""Scenario: what an effect makes, chosen or conditioned as it resolves.

- **"create a `<Predefined>` token or a `<Predefined>` token"** - Ant-Man's
  Army's enters trigger; Tireless Provisioner (WOE, not listed, not in a deck)
  prints the identical instruction on a landfall trigger. The player chooses
  which as it resolves (CR 608.2d); both are CR 111.10's predefined tokens.
- **"`<effect>` if there are N or more `<quality>` cards in your graveyard.
  Otherwise, `<effect>`."** - HYDRA Troopers. CR 608.2c: the condition is read
  as the ability resolves, and exactly one of the two instructions happens.
- **"Target player investigates. Target creature gets +1/+0 and gains flying
  until end of turn. Untap it."** - Panther Pounce (CR 701.16a).
- **"Search your library and/or graveyard for `<a card>` ... If you search your
  library this way, shuffle."** - Vision Quest ("... put it onto the
  battlefield with X additional +1/+1 counters on it. If X is 4 or greater,
  it gains haste until end of turn."), and Fang-Druid Summoner (DFT, not
  listed, not in a deck: "you may search your library and/or graveyard for a
  creature card with no abilities, reveal it, and put it into your hand").
- **"Target player gains N life, then searches their library for ... Put a
  +1/+1 counter on up to one target creature."** - Restorative Technique.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 111.10a** / **CR 111.10b** - the Treasure and Food predefined tokens.
- **CR 608.2c** - instructions are followed in order, and later text can
  modify earlier text.
- **CR 608.2d** - a choice made as the spell or ability resolves.
- **CR 701.16a** - "'Investigate' means 'Create a Clue token.'"
- **CR 701.17a** - milling.
- **CR 701.23a** / **CR 701.23b** - searching, and a stated-quality search
  may find nothing.
- **CR 107.3a** - the X announced for Vision Quest.
- **CR 113.12** - a creature card "with no abilities" (the Runeclaw Bear
  example).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _tokens(scenario, name: str, username: str = "alice") -> list:
    return [p for p in scenario.game.battlefield if p.name == name and p.controller == username]


# -- "create a Food token or a Treasure token" ---------------------------------


def test_ant_mans_army_makes_a_food_when_food_is_chosen():
    scenario = Scenario().player("alice", hand=["Ant-Man's Army"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Food", username="alice")

    scenario.put_onto_battlefield("Ant-Man's Army", "alice")
    _resolve_all(scenario)

    assert len(_tokens(scenario, "Food Token")) == 1
    assert _tokens(scenario, "Treasure Token") == []


def test_ant_mans_army_makes_a_treasure_when_treasure_is_chosen():
    scenario = Scenario().player("alice", hand=["Ant-Man's Army"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Treasure", username="alice")

    scenario.put_onto_battlefield("Ant-Man's Army", "alice")
    _resolve_all(scenario)

    assert len(_tokens(scenario, "Treasure Token")) == 1
    assert _tokens(scenario, "Food Token") == []


def test_the_choice_is_offered_as_exactly_the_two_tokens():
    scenario = Scenario().player("alice", hand=["Ant-Man's Army"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Food", username="alice")

    scenario.put_onto_battlefield("Ant-Man's Army", "alice")
    _resolve_all(scenario)

    (question,) = [q for q in scenario.questions_asked() if q.options]
    assert set(question.options) == {"Food", "Treasure"}


def test_tireless_provisioner_makes_one_on_each_landfall():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Tireless Provisioner"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Treasure", username="alice")

    scenario.play_land("Forest")
    _resolve_all(scenario)

    assert len(_tokens(scenario, "Treasure Token")) == 1


# -- "... if there are two or more creature cards in your graveyard. Otherwise,
# mill two cards." -----------------------------------------------------------


def test_hydra_troopers_makes_a_tapped_villain_with_two_creatures_in_the_yard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["HYDRA Troopers"],
            graveyard=["Grizzly Bears", "Grizzly Bears"],
            library=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("HYDRA Troopers", "alice")
    _resolve_all(scenario)

    (villain,) = _tokens(scenario, "Villain Token")
    assert villain.tapped
    assert (villain.power, villain.toughness) == (2, 1)
    assert has_keyword(villain, Keyword.MENACE, scenario.game)
    assert len(scenario.player("alice").library) == 4, "no mill"


def test_hydra_troopers_mills_two_otherwise():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["HYDRA Troopers"],
            graveyard=["Grizzly Bears", "Island"],
            library=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("HYDRA Troopers", "alice")
    _resolve_all(scenario)

    assert _tokens(scenario, "Villain Token") == []
    assert len(scenario.player("alice").library) == 2
    assert len(scenario.player("alice").graveyard) == 4


def test_hydra_troopers_counts_only_its_controllers_graveyard():
    scenario = (
        Scenario()
        .player("alice", hand=["HYDRA Troopers"], library=["Island"] * 4)
        .player("bob", graveyard=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("HYDRA Troopers", "alice")
    _resolve_all(scenario)

    assert _tokens(scenario, "Villain Token") == []
    assert len(scenario.player("alice").library) == 2


# -- Panther Pounce -----------------------------------------------------------


def test_panther_pounce_investigates_pumps_and_untaps():
    scenario = (
        Scenario()
        .player("alice", hand=["Panther Pounce"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Panther Pounce", plains, targets=["alice", bears])

    assert len(_tokens(scenario, "Clue Token")) == 1
    assert not bears.tapped
    assert scenario.game.power_of(bears) == 3
    assert has_keyword(bears, Keyword.FLYING, scenario.game)


def test_panther_pounce_can_give_an_opponent_the_clue():
    scenario = (
        Scenario()
        .player("alice", hand=["Panther Pounce"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Panther Pounce", plains, targets=["bob", bears])

    assert len(_tokens(scenario, "Clue Token", "bob")) == 1
    assert _tokens(scenario, "Clue Token") == []


def test_panther_pounce_still_investigates_if_the_creature_is_gone():
    """CR 608.2b: one target illegal - the rest of the spell still happens."""
    scenario = (
        Scenario()
        .player("alice", hand=["Panther Pounce"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (plains,) = scenario.untapped_sources("Plains")

    casting = scenario.cast("Panther Pounce", "alice", targets=["alice", bears])
    casting.determine_cost()
    payment = casting.begin_paying()
    scenario.pay_with(payment, plains)
    scenario.put_on_stack(casting)
    scenario.game.put_into_graveyard(bears)
    scenario.resolve_top()

    assert len(_tokens(scenario, "Clue Token")) == 1


# -- Restorative Technique ----------------------------------------------------


def test_restorative_technique_gains_fetches_and_grows():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Restorative Technique"],
            battlefield=["Forest", "Forest", "Forest", "Grizzly Bears"],
            library=["Plains", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    library_plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(library_plains, username="alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Restorative Technique", *forests, targets=["alice", bears])

    assert scenario.player("alice").life == 22
    assert library_plains.zone is Zone.BATTLEFIELD and library_plains.tapped
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_restorative_technique_can_target_an_opponent_and_no_creature():
    """ "Target player" may be anyone - bob gains the life and fetches his own
    land - and "up to one target creature" may be none."""
    scenario = (
        Scenario()
        .player("alice", hand=["Restorative Technique"], battlefield=["Forest"] * 3)
        .player("bob", library=["Swamp", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.find("Swamp", Zone.LIBRARY, "bob")
    scenario.will_choose_cards(swamp, username="bob")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Restorative Technique", *forests, targets=["bob"])

    assert scenario.player("bob").life == 22
    assert swamp.zone is Zone.BATTLEFIELD and swamp.controller == "bob"


# -- "Search your library and/or graveyard for ..." ---------------------------


def _vision_quest(x_value: int, *, library=(), graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Vision Quest"],
            battlefield=["Island", "Mountain"] + ["Island"] * x_value,
            library=list(library),
            graveyard=list(graveyard),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_vision_quest(scenario, x_value: int) -> None:
    sources = scenario.untapped_sources("Island", "Mountain", *(["Island"] * x_value))
    casting = scenario.cast("Vision Quest", "alice")
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_vision_quest_takes_from_the_graveyard_with_x_counters():
    scenario = _vision_quest(2, library=["Island"], graveyard=["Solemn Simulacrum", "Memnite"])
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(False, username="alice")  # not the library
    scenario.will_choose_cards(memnite, username="alice")

    _cast_vision_quest(scenario, 2)

    assert memnite.zone is Zone.BATTLEFIELD
    assert memnite.counter_count(Counter.PLUS_ONE) == 2
    assert not has_keyword(memnite, Keyword.HASTE, scenario.game), "X is below 4"


def test_vision_quest_takes_from_the_library_and_gives_haste_at_four():
    scenario = _vision_quest(4, library=["Solemn Simulacrum", "Island"])
    solemn = scenario.find("Solemn Simulacrum", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(solemn, username="alice")

    _cast_vision_quest(scenario, 4)
    _resolve_all(scenario)

    assert solemn.zone is Zone.BATTLEFIELD
    assert solemn.counter_count(Counter.PLUS_ONE) == 4
    assert has_keyword(solemn, Keyword.HASTE, scenario.game)


def test_vision_quest_refuses_a_card_above_x():
    """ "mana value X or less": Solemn Simulacrum (4) is not a candidate at
    X = 2, so only Memnite is offered."""
    scenario = _vision_quest(2, graveyard=["Solemn Simulacrum", "Memnite"])
    scenario.will_take_the_may(False, username="alice")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(memnite, username="alice")

    _cast_vision_quest(scenario, 2)

    (question,) = [q for q in scenario.questions_asked() if q.cards]
    assert set(question.cards) == {memnite.id}


def test_vision_quest_refuses_a_non_artifact_creature():
    scenario = _vision_quest(2, graveyard=["Grizzly Bears"])
    scenario.will_take_the_may(False, username="alice")

    _cast_vision_quest(scenario, 2)

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert [q for q in scenario.questions_asked() if q.cards] == []


def test_vision_quest_may_find_nothing():
    """CR 701.23b: a stated-quality search need not find anything."""
    scenario = _vision_quest(2, graveyard=["Memnite"])
    scenario.will_take_the_may(False, username="alice")
    scenario.will_choose_cards(username="alice")

    _cast_vision_quest(scenario, 2)

    assert scenario.find("Memnite", Zone.GRAVEYARD, "alice") is not None


def test_fang_druid_summoner_finds_a_vanilla_creature_for_the_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fang-Druid Summoner"],
            graveyard=["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, username="alice")  # search at all
    scenario.will_take_the_may(False, username="alice")  # not the library
    scenario.will_choose_cards(bears, username="alice")

    scenario.put_onto_battlefield("Fang-Druid Summoner", "alice")
    _resolve_all(scenario)

    assert bears.zone is Zone.HAND
    offered = [q for q in scenario.questions_asked() if q.cards]
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert elves.id not in offered[0].cards, "Llanowar Elves has an ability"


def test_fang_druid_summoner_may_decline_the_search():
    scenario = (
        Scenario()
        .player("alice", hand=["Fang-Druid Summoner"], graveyard=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice")

    scenario.put_onto_battlefield("Fang-Druid Summoner", "alice")
    _resolve_all(scenario)

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
