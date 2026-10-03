"""Scenario: "When you cast this spell, [dig through your own or an
opponent's library]." - five more members of the Eldrazi-ramp cast-trigger
family `test_cast_triggers.py` already covers (the trigger sits above its
own spell on the stack, CR 603.3, and resolves even if the spell is later
countered).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 107.3a** - the caster announces X as part of casting an {X} spell;
  while the spell is on the stack any X in its text equals that value.
  Genesis Hydra's and Old Stickfingers's own X.
- **CR 107.3f** - X appearing in a spell's text but not in its cost is
  self-defined by that text instead. Hatchery Spider's Undergrowth X ("where
  X is the number of creature cards in your graveyard").
- **CR 603.3d** - a triggered ability's targets are chosen the same way as a
  spell's, CR 601.2c-d, as it goes on the stack. Oblivion Sower's own
  "target opponent".
- **CR 701.20a** - to reveal a card is to show it to all players.
- **CR 701.24a** - to shuffle a library is to randomize it so no player
  knows the order.
- **CR 608.2c** - an effect that wants to look at/reveal more cards than
  remain in a library looks at/reveals all of it.
- **CR 608.2d** - a resolution-time "you may" choice among candidates the
  spell or ability did not already choose while being put on the stack.
- **CR 110.4a** - "permanent card": a card that could be put onto the
  battlefield (artifact, battle, creature, enchantment, land, planeswalker).
- **CR 406.2** - to exile an object is to move it to the exile zone from
  wherever it is.
- **CR 108.3** - a card's owner never changes just because another player
  gains control of it.

The five readers are `_parse_cast_trigger_reveal_top_x_put_one_permanent_
clause` (Genesis Hydra, Hatchery Spider), `_parse_cast_trigger_reveal_
until_x_kind_to_graveyard_clause` (Old Stickfingers), `_parse_search_reveal_
shuffle_top_clause` (Conduit of Ruin, widened for "mana value N or greater")
and `_parse_target_opponent_exile_top_then_put_lands_clause` (Oblivion
Sower), all in `machines/effects.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- Genesis Hydra: reveal top X, may put one eligible permanent, shuffle --


def test_genesis_hydra_puts_the_one_eligible_permanent_and_shuffles_the_rest():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Hydra"],
            library=["Llanowar Elves", "Lightning Bolt", "Wumpus Aberration", "Mountain"],
            battlefield=["Forest"] * 5,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_three = scenario.top_of_library(3, "alice")
    elves, bolt, wumpus = top_three
    scenario.will_take_the_may(True, source="Genesis Hydra")
    scenario.will_choose_cards(elves, source="Genesis Hydra")

    sources = scenario.untapped_sources(*(["Forest"] * 5))
    scenario.game.cast(
        scenario.find("Genesis Hydra", Zone.HAND, "alice"), "alice", x_value=3, mana_sources=sources
    )
    resolve_all(scenario)

    assert elves.zone is Zone.BATTLEFIELD
    # Lightning Bolt (not a permanent) and Wumpus Aberration (mana value 4,
    # over the X=3 ceiling) were never offered - only shuffled back in.
    library_ids = {state.id for state in scenario.player("alice").library}
    assert bolt.id in library_ids
    assert wumpus.id in library_ids


def test_genesis_hydra_x_zero_reveals_nothing_but_still_shuffles():
    """Nothing is revealed at X=0 (CR 608.2c's "reveal the top 0 cards" is
    nothing), but the Oracle ruling for Genesis Hydra is explicit: "the rest"
    is still shuffled into the library even when it is zero cards (CR
    701.24d). `Game.shuffles_performed` is the deterministic witness - the
    library holds only two cards, so a real shuffle can legally land back in
    its starting order and an order-based assertion would be flaky."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Hydra"],
            library=["Llanowar Elves", "Mountain"],
            battlefield=["Forest"] * 2,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library_before_ids = {state.id for state in scenario.player("alice").library}
    shuffles_before = scenario.game.shuffles_performed

    sources = scenario.untapped_sources(*(["Forest"] * 2))
    scenario.game.cast(
        scenario.find("Genesis Hydra", Zone.HAND, "alice"), "alice", x_value=0, mana_sources=sources
    )
    resolve_all(scenario)

    assert {state.id for state in scenario.player("alice").library} == library_before_ids
    assert scenario.game.shuffles_performed == shuffles_before + 1
    assert scenario.questions_asked() == []


def test_genesis_hydra_nothing_eligible_still_shuffles():
    """Both revealed cards are lands - "nonland permanent" excludes both, so
    nothing is offered, but CR 701.24a's shuffle still runs (the "may put"
    finding nothing is not a reason to skip the sentence after it)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Hydra"],
            library=["Forest", "Mountain"],
            battlefield=["Forest"] * 4,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_two = scenario.top_of_library(2, "alice")

    sources = scenario.untapped_sources(*(["Forest"] * 4))
    scenario.game.cast(
        scenario.find("Genesis Hydra", Zone.HAND, "alice"), "alice", x_value=2, mana_sources=sources
    )
    resolve_all(scenario)

    assert scenario.questions_asked() == []
    library_ids = {state.id for state in scenario.player("alice").library}
    assert {state.id for state in top_two} <= library_ids
    assert sorted(scenario.battlefield_names()) == sorted(["Forest"] * 4 + ["Genesis Hydra"])


def test_genesis_hydra_library_smaller_than_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Hydra"],
            library=["Llanowar Elves"],
            battlefield=["Forest"] * 7,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (elves,) = scenario.top_of_library(1, "alice")
    scenario.will_take_the_may(True, source="Genesis Hydra")
    scenario.will_choose_cards(elves, source="Genesis Hydra")

    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.game.cast(
        scenario.find("Genesis Hydra", Zone.HAND, "alice"), "alice", x_value=5, mana_sources=sources
    )
    resolve_all(scenario)

    assert elves.zone is Zone.BATTLEFIELD


def test_genesis_hydra_countered_in_response_still_digs_with_the_cast_x():
    """CR 603.3: the trigger sits *above* Genesis Hydra on the stack, so a
    counterspell can answer Genesis Hydra itself while the trigger still
    waits - and the Oracle ruling for this whole cast-trigger family
    (Hydroid Krasis, Genesis Hydra, Old Stickfingers, Geometer's Arthropod)
    agrees: the trigger still resolves with the cast X even though there is
    no longer a Genesis Hydra permanent to show for it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Hydra"],
            library=["Llanowar Elves", "Lightning Bolt", "Wumpus Aberration", "Mountain"],
            battlefield=["Forest"] * 5,
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_three = scenario.top_of_library(3, "alice")
    elves, bolt, wumpus = top_three
    scenario.will_take_the_may(True, source="Genesis Hydra")
    scenario.will_choose_cards(elves, source="Genesis Hydra")

    sources = scenario.untapped_sources(*(["Forest"] * 5))
    hydra = scenario.game.cast(
        scenario.find("Genesis Hydra", Zone.HAND, "alice"), "alice", x_value=3, mana_sources=sources
    )
    assert scenario.stack_names() == ["Genesis Hydra", "Genesis Hydra's triggered ability"]

    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.game.cast(
        scenario.find("Counterspell", Zone.HAND, "bob"),
        "bob",
        mana_sources=islands,
        targets=[hydra],
    )
    assert scenario.stack_names() == [
        "Genesis Hydra",
        "Genesis Hydra's triggered ability",
        "Counterspell",
    ]

    scenario.resolve_top()  # Counterspell counters Genesis Hydra
    assert hydra.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # the trigger still resolves - X was 3, not 0
    scenario.game.put_triggers_on_stack()

    assert elves.zone is Zone.BATTLEFIELD
    library_ids = {state.id for state in scenario.player("alice").library}
    assert bolt.id in library_ids
    assert wumpus.id in library_ids


# -- Hatchery Spider: Undergrowth X, may put one green permanent, bottom ---


def test_hatchery_spider_undergrowth_x_puts_the_green_permanent_to_bottom_rest():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hatchery Spider"],
            library=["Elvish Mystic", "Fencing Ace", "Mountain"],
            graveyard=["Grizzly Bears", "Llanowar Elves"],
            battlefield=["Forest"] * 7,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_two = scenario.top_of_library(2, "alice")
    mystic, ace = top_two
    scenario.will_take_the_may(True, source="Hatchery Spider")
    scenario.will_choose_cards(mystic, source="Hatchery Spider")

    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.cast_onto_stack("Hatchery Spider", *sources)
    resolve_all(scenario)

    assert mystic.zone is Zone.BATTLEFIELD
    library = scenario.player("alice").library
    bottom_ids = {state.id for state in library[-1:]}
    assert ace.id in bottom_ids
    # The undergrowth count came from the graveyard, not the battlefield or
    # hand - two creature cards there means X=2, so two cards were revealed.
    assert {state.name for state in scenario.player("alice").graveyard} == {
        "Grizzly Bears",
        "Llanowar Elves",
    }


def test_hatchery_spider_no_creatures_in_graveyard_reveals_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hatchery Spider"],
            library=["Elvish Mystic", "Mountain"],
            battlefield=["Forest"] * 7,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library_before = list(scenario.player("alice").library)

    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.cast_onto_stack("Hatchery Spider", *sources)
    resolve_all(scenario)

    assert scenario.player("alice").library == library_before
    assert scenario.questions_asked() == []


def test_hatchery_spider_nothing_eligible_still_bottoms_the_rest():
    """Both revealed cards are lands - "green permanent" excludes both."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hatchery Spider"],
            library=["Forest", "Mountain"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest"] * 7,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_one = scenario.top_of_library(1, "alice")

    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.cast_onto_stack("Hatchery Spider", *sources)
    resolve_all(scenario)

    assert scenario.questions_asked() == []
    library = scenario.player("alice").library
    assert top_one[0].id in {state.id for state in library}


# -- Old Stickfingers: reveal until X creatures, all to graveyard ----------


def test_old_stickfingers_mills_x_creatures_to_graveyard_rest_to_bottom():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Old Stickfingers"],
            library=["Lightning Bolt", "Grizzly Bears", "Forest", "Llanowar Elves", "Mountain"],
            battlefield=["Swamp", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_five = scenario.top_of_library(5, "alice")
    bolt, bears, forest, elves, mountain = top_five

    swamp, f1, f2, f3 = scenario.untapped_sources("Swamp", "Forest", "Forest", "Forest")
    scenario.game.cast(
        scenario.find("Old Stickfingers", Zone.HAND, "alice"),
        "alice",
        x_value=2,
        mana_sources=[swamp, f1, f2, f3],
    )
    resolve_all(scenario)

    assert {state.id for state in scenario.player("alice").graveyard} == {bears.id, elves.id}
    library = scenario.player("alice").library
    assert library[0].id == mountain.id, "never revealed, so it never moved"
    bottom_ids = {state.id for state in library[-2:]}
    assert bottom_ids == {bolt.id, forest.id}


def test_old_stickfingers_x_zero_reveals_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Old Stickfingers"],
            library=["Grizzly Bears", "Forest"],
            # A creature already in the graveyard keeps Old Stickfingers's
            # own power/toughness (its static CDA) above 0/0, so it survives
            # CR 704.5f state-based actions long enough to matter here - the
            # test is about the X=0 dig, not about the creature that carries
            # it dying to its own zero toughness.
            graveyard=["Watchwolf"],
            battlefield=["Swamp", "Forest"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library_before = list(scenario.player("alice").library)
    graveyard_before = list(scenario.player("alice").graveyard)

    swamp, forest = scenario.untapped_sources("Swamp", "Forest")
    scenario.game.cast(
        scenario.find("Old Stickfingers", Zone.HAND, "alice"),
        "alice",
        x_value=0,
        mana_sources=[swamp, forest],
    )
    resolve_all(scenario)

    assert scenario.player("alice").library == library_before
    assert scenario.player("alice").graveyard == graveyard_before


def test_old_stickfingers_no_creatures_at_all_bottoms_the_whole_library():
    """Fewer than X creature cards anywhere in the library - CR 608.2c reveals
    the whole thing looking for them, finds none, and bottoms all of it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Old Stickfingers"],
            library=["Lightning Bolt", "Forest", "Mountain"],
            # See test_old_stickfingers_x_zero_reveals_nothing: without a
            # creature already in the graveyard, finding none here leaves
            # Old Stickfingers's own power/toughness CDA at 0/0 and CR
            # 704.5f kills it before this test can check anything about the
            # dig itself.
            graveyard=["Watchwolf"],
            battlefield=["Swamp", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_three = scenario.top_of_library(3, "alice")
    graveyard_before = list(scenario.player("alice").graveyard)

    swamp, f1, f2, f3 = scenario.untapped_sources("Swamp", "Forest", "Forest", "Forest")
    scenario.game.cast(
        scenario.find("Old Stickfingers", Zone.HAND, "alice"),
        "alice",
        x_value=2,
        mana_sources=[swamp, f1, f2, f3],
    )
    resolve_all(scenario)

    assert scenario.player("alice").graveyard == graveyard_before
    library_ids = {state.id for state in scenario.player("alice").library}
    assert library_ids == {state.id for state in top_three}


def test_old_stickfingers_library_smaller_than_x_mills_what_it_has():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Old Stickfingers"],
            library=["Grizzly Bears", "Llanowar Elves"],
            battlefield=["Swamp"] + ["Forest"] * 6,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, elves = scenario.top_of_library(2, "alice")

    sources = scenario.untapped_sources("Swamp", *(["Forest"] * 6))
    scenario.game.cast(
        scenario.find("Old Stickfingers", Zone.HAND, "alice"),
        "alice",
        x_value=5,
        mana_sources=list(sources),
    )
    resolve_all(scenario)

    assert {state.id for state in scenario.player("alice").graveyard} == {bears.id, elves.id}
    assert scenario.player("alice").library == []


# -- Conduit of Ruin: search a colorless creature MV 7+, shuffle, on top --


def test_conduit_of_ruin_finds_the_eligible_colossus_and_puts_it_on_top():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Conduit of Ruin"],
            library=["Sire of Seven Deaths", "Wurmcoil Engine", "Forest", "Mountain"],
            battlefield=["Forest"] * 6,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Conduit of Ruin")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Conduit of Ruin", *sources)
    resolve_all(scenario)

    library = scenario.player("alice").library
    assert library[0].name == "Sire of Seven Deaths", (
        "mana value 7 meets the '7 or greater' floor and was put on top"
    )
    assert "Wurmcoil Engine" in {state.name for state in library}, (
        "mana value 6 misses the floor and was left in library, only shuffled"
    )


def test_conduit_of_ruin_declined_search_leaves_the_library_untouched():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Conduit of Ruin"],
            library=["Sire of Seven Deaths", "Forest"],
            battlefield=["Forest"] * 6,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library_before = list(scenario.player("alice").library)
    scenario.will_take_the_may(False, source="Conduit of Ruin")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Conduit of Ruin", *sources)
    resolve_all(scenario)

    assert scenario.player("alice").library == library_before


def test_conduit_of_ruin_nothing_meets_the_floor():
    """Wurmcoil Engine's mana value 6 is under the '7 or greater' floor -
    CR 701.23b's search still may find nothing, and CR 701.24a's shuffle
    still runs (`Game.search_library`'s own always-shuffle-on-search)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Conduit of Ruin"],
            library=["Wurmcoil Engine", "Forest", "Mountain"],
            battlefield=["Forest"] * 6,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Conduit of Ruin")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Conduit of Ruin", *sources)
    resolve_all(scenario)

    library_names = {state.name for state in scenario.player("alice").library}
    assert library_names == {"Wurmcoil Engine", "Forest", "Mountain"}


# -- Oblivion Sower: opponent exiles four, lands come back under control --


def test_oblivion_sower_puts_both_exiled_lands_under_its_controllers_control():
    scenario = (
        Scenario()
        .player("alice", hand=["Oblivion Sower"], battlefield=["Forest"] * 6)
        .player(
            "bob",
            library=["Forest", "Grizzly Bears", "Mountain", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest, bears, mountain, elves = scenario.top_of_library(4, "bob")
    scenario.choose_trigger_targets("Oblivion Sower", ["bob"])
    scenario.will_choose_cards(forest, mountain, source="Oblivion Sower")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Oblivion Sower", *sources)
    resolve_all(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert mountain.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(forest).username == "alice"
    assert scenario.game.controller_of(mountain).username == "alice"
    assert forest.owner == "bob", "CR 108.3: gaining control never changes ownership"
    assert bears.zone is Zone.EXILE
    assert elves.zone is Zone.EXILE


def test_oblivion_sower_may_take_fewer_than_all_the_lands():
    scenario = (
        Scenario()
        .player("alice", hand=["Oblivion Sower"], battlefield=["Forest"] * 6)
        .player("bob", library=["Forest", "Mountain", "Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest, mountain, bears, elves = scenario.top_of_library(4, "bob")
    scenario.choose_trigger_targets("Oblivion Sower", ["bob"])
    scenario.will_choose_cards(forest, source="Oblivion Sower")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Oblivion Sower", *sources)
    resolve_all(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert mountain.zone is Zone.EXILE, "declined, so it stays exiled - CR 608.2d, not mandatory"


def test_oblivion_sower_no_lands_among_the_exiled_cards_asks_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Oblivion Sower"], battlefield=["Forest"] * 6)
        .player("bob", library=["Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, elves = scenario.top_of_library(2, "bob")
    scenario.choose_trigger_targets("Oblivion Sower", ["bob"])

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Oblivion Sower", *sources)
    resolve_all(scenario)

    assert scenario.questions_asked() == []
    assert bears.zone is Zone.EXILE
    assert elves.zone is Zone.EXILE


def test_oblivion_sower_library_smaller_than_four_exiles_what_it_has():
    scenario = (
        Scenario()
        .player("alice", hand=["Oblivion Sower"], battlefield=["Forest"] * 6)
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.top_of_library(1, "bob")
    scenario.choose_trigger_targets("Oblivion Sower", ["bob"])
    scenario.will_choose_cards(forest, source="Oblivion Sower")

    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_onto_stack("Oblivion Sower", *sources)
    resolve_all(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").library == []
