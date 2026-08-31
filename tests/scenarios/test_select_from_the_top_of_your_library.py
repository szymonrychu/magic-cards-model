"""The "see the top N, then optionally move one of them" family.

One printed shape, several cards. A player sees the top N cards of their own
library - by **milling** them or by **looking at** them - and is then offered an
*optional* follow-up: put one of what they saw into the hand, onto the
battlefield, or into the graveyard.

`test_six.py` covers the one card the engine used to read by name. This file is
about the shape being a *family*: Ostrich-Horse and Ainok Wayfarer print the
identical sentence on different creatures, Scout the City prints it as a spell
mode with a life-gain tail, and Fecund Greenshell prints its conditional cousin.
None of them has a per-card entry in `machines/effects.py`.

Cards and text verified with `resolve_cards` in the session that wrote this;
decklist provenance for the shape's presence in Standard is in the report - the
mono green aggro list piloted by Trevorgilmore, mtgtop8 event 90203, 2026-08-30,
runs Fecund Greenshell.

CR numbers looked up with `knowledge_search(type="rules")` in this session:

- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 701.17b** - a player can't mill more cards than are in their library; if
  instructed to, they mill as many as possible.
- **CR 701.17c** - an effect referring to a milled card finds it in the zone it
  moved to, as long as that zone is public. This is what makes "from among
  them" the three cards *this* mill moved rather than the whole graveyard.
- **CR 401.2** - "Each library must be kept in a single face-down pile. Players
  can't look at or change the order of cards in a library." An effect saying
  "look at" lifts that for itself and moves nothing.
- **CR 608.2d** - a resolving effect's choices are made by "the player" as it
  resolves; that is the ability's controller unless the effect names someone
  else.
- **CR 609.3** / **CR 101.3** - an effect that attempts something impossible
  does only as much as possible; an impossible part of an instruction is
  ignored.
- **CR 110.4a** - "permanent card" means an artifact, battle, creature,
  enchantment, land, or planeswalker card.
- **CR 122.1a** - a +1/+1 counter adds 1 to power and 1 to toughness.
- **CR 119.3** - a life-gain instruction adjusts the life total.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def enters(creature: str, library: list[str], *, lands: int = 3) -> Scenario:
    """A board that casts `creature` off basic Forests, with `library` stacked."""
    return (
        Scenario()
        .player(
            "alice",
            hand=[creature],
            battlefield=["Forest"] * lands,
            library=library,
        )
        .player("bob")
    )


# -- The mill arm: Ostrich-Horse and Ainok Wayfarer -------------------------


def test_ostrich_horse_mills_three_and_may_keep_a_land_from_among_them():
    """The happy path (CR 701.17a, CR 701.17c, CR 608.2d).

    Three cards leave the library for the graveyard; the land among them is the
    only legal candidate, and taking it moves it on to the hand.
    """
    scenario = enters("Ostrich-Horse", ["Forest", "Lightning Bolt", "Lightning Bolt", "Island"])
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest_on_top = scenario.player("alice").library[0]
    scenario.will_choose_cards(forest_on_top, source="Ostrich-Horse")

    scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    assert forest_on_top.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").graveyard] == [
        "Lightning Bolt",
        "Lightning Bolt",
    ]
    assert [c.name for c in scenario.player("alice").library] == ["Island"]


def test_ainok_wayfarer_prints_the_same_sentence_and_needs_no_second_entry():
    """The whole point of a family: a different creature, the identical text,
    and no per-card row anywhere in `machines/effects.py`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ainok Wayfarer"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Forest", "Lightning Bolt", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.player("alice").library[1]
    scenario.will_choose_cards(forest, source="Ainok Wayfarer")

    scenario.cast_and_resolve("Ainok Wayfarer", *scenario.untapped_sources("Forest", "Forest"))
    resolve_all(scenario)

    assert forest.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").graveyard] == [
        "Lightning Bolt",
        "Lightning Bolt",
    ]


def test_declining_the_may_leaves_the_land_milled_and_adds_the_counter_instead():
    """CR 608.2d's "you may" is a real question, and "If you don't" is the
    branch that answers no - the land stays in the graveyard and the creature
    gets a +1/+1 counter (CR 122.1a)."""
    scenario = enters("Ostrich-Horse", ["Forest", "Lightning Bolt", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Ostrich-Horse")

    horse = scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    assert [c.name for c in scenario.player("alice").graveyard] == [
        "Forest",
        "Lightning Bolt",
        "Lightning Bolt",
    ]
    assert scenario.player("alice").hand == []
    assert horse.counters["+1/+1"] == 1
    assert (horse.power, horse.toughness) == (4, 2)


def test_no_land_among_the_milled_cards_is_never_asked_at_all():
    """CR 608.2d offers a choice only where one exists. With nothing legal to
    choose, the "you may" is not put to the player - and "If you don't" still
    fires, because the follow-up was not taken."""
    scenario = enters(
        "Ostrich-Horse", ["Lightning Bolt", "Lightning Bolt", "Lightning Bolt", "Forest"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    horse = scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    asked = [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Ostrich-Horse"
        and decision.kind in (DecisionKind.MAY, DecisionKind.CHOOSE_CARDS)
    ]
    assert asked == []
    assert horse.counters["+1/+1"] == 1
    # The fourth card was never milled, so it is not "among them" (CR 701.17c).
    assert [c.name for c in scenario.player("alice").library] == ["Forest"]


def test_an_empty_library_mills_nothing_and_asks_nothing():
    """CR 701.17b: a player can't mill more cards than they have. With none at
    all the whole follow-up is impossible and is ignored (CR 101.3, CR 609.3) -
    and "If you don't" still puts the counter on."""
    scenario = enters("Ostrich-Horse", []).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    horse = scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    assert scenario.player("alice").graveyard == []
    assert scenario.player("alice").hand == []
    assert [
        decision for decision in scenario.questions_asked() if decision.source == "Ostrich-Horse"
    ] == []
    assert horse.counters["+1/+1"] == 1


def test_fewer_cards_than_three_mills_only_what_is_there():
    """CR 701.17b's "as many as possible": two cards in the library means a mill
    of two, and the land among those two is still a legal candidate."""
    scenario = enters("Ostrich-Horse", ["Lightning Bolt", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.player("alice").library[1]
    scenario.will_choose_cards(forest, source="Ostrich-Horse")

    scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    assert scenario.player("alice").library == []
    assert forest.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").graveyard] == ["Lightning Bolt"]


def test_the_chosen_card_really_changes_zones_and_is_in_exactly_one():
    """The chosen card makes two zone changes in one resolution - library to
    graveyard (the mill), then graveyard to hand - and must end up recorded in
    exactly one zone, not left behind in the graveyard it passed through."""
    scenario = enters("Ostrich-Horse", ["Forest", "Lightning Bolt", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.player("alice").library[0]
    scenario.will_choose_cards(forest, source="Ostrich-Horse")

    scenario.cast_and_resolve(
        "Ostrich-Horse", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    resolve_all(scenario)

    scenario.assert_in_exactly_one_zone(forest)
    assert forest.zone is Zone.HAND
    assert forest not in scenario.player("alice").graveyard
    assert forest not in scenario.player("alice").library


# -- The spell arm: Scout the City's "Look Around" mode ---------------------


def test_scout_the_city_look_around_mills_three_and_keeps_a_permanent_card():
    """The same family on a spell's mode (CR 608.2c), with a different card
    kind - "permanent card" is CR 110.4a - and a life-gain tail (CR 119.3).

    A creature card is a permanent card and an instant is not, which is what
    picks the candidate out of the three milled cards.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Scout the City"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Grizzly Bears", "Lightning Bolt", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.player("alice").library[1]
    scenario.will_choose_cards(bears, source="Scout the City")

    casting = scenario.cast("Scout the City")
    casting.choose_modes([1])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    resolve_all(scenario)

    assert bears.zone is Zone.HAND
    assert scenario.player("alice").life == 23
    assert [c.name for c in scenario.player("alice").library] == ["Island"]


def test_scout_the_city_gains_the_life_even_with_no_permanent_card_to_keep():
    """CR 608.2c follows the instructions in order: a follow-up nobody could
    take does not stop the sentence after it from happening."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Scout the City"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Scout the City")
    casting.choose_modes([1])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    resolve_all(scenario)

    assert scenario.player("alice").life == 23
    assert scenario.player("alice").hand == []


# -- The look arm: Fecund Greenshell's conditional cousin -------------------


def greenshell_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fecund Greenshell"],
            battlefield=["Forest"] * 5,
            library=library,
        )
        .player("bob")
    )


def test_fecund_greenshell_puts_the_top_land_onto_the_battlefield_tapped():
    """The look arm moves nothing until the choice is made (CR 401.2 - looking
    is not a zone change), and the taken branch puts the card straight onto the
    battlefield without casting it."""
    scenario = greenshell_board(["Island", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.player("alice").library[0]

    scenario.cast_and_resolve(
        "Fecund Greenshell",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    resolve_all(scenario)

    assert island.zone is Zone.BATTLEFIELD
    assert island.tapped
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]


def test_declining_greenshells_may_leaves_the_land_on_top_of_the_library():
    """ "Otherwise" is the card failing the condition, not the player declining
    the may - so a declined "you may" leaves the land exactly where CR 401.2
    keeps it, on top of the library, and does *not* put it into the hand."""
    scenario = greenshell_board(["Island", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.player("alice").library[0]
    scenario.will_take_the_may(False, source="Fecund Greenshell")

    scenario.cast_and_resolve(
        "Fecund Greenshell",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    resolve_all(scenario)

    assert island.zone is Zone.LIBRARY
    assert [c.name for c in scenario.player("alice").library] == ["Island", "Lightning Bolt"]
    assert scenario.player("alice").hand == []


def test_a_nonland_top_card_goes_to_hand_without_any_question_being_asked():
    """The "Otherwise" branch is not optional: nothing is put to the player,
    because CR 608.2d only asks about the branch the card offers a choice on."""
    scenario = greenshell_board(["Lightning Bolt", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.player("alice").library[0]

    scenario.cast_and_resolve(
        "Fecund Greenshell",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    resolve_all(scenario)

    assert bolt.zone is Zone.HAND
    assert [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Fecund Greenshell" and decision.kind is DecisionKind.MAY
    ] == []


def test_greenshell_with_an_empty_library_has_no_top_card_and_does_nothing():
    """CR 609.3 / CR 101.3: there is no card to look at, so no branch of the
    sentence can happen and none of it is attempted."""
    scenario = greenshell_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Fecund Greenshell",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    resolve_all(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").library == []
    assert [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Fecund Greenshell"
    ] == []
