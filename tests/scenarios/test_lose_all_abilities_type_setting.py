"""Losing all abilities together with a type, colour and base power/toughness
set - one instruction, several layers (CR 613.1, CR 613.6).

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 613.1d** layer 4 (type), **CR 613.1e** layer 5 (colour), **CR
  613.1f** layer 6 ("Ability-adding effects, keyword counters,
  ability-removing effects, and effects that say an object can't have an
  ability are applied"), **CR 613.4b** sublayer 7b (base power and toughness
  set), **CR 613.4c** 7c (counters and modifiers apply on top).
- **CR 613.7b** a resolving effect is timestamped as it is created; **CR
  613.7c** "Each counter receives a timestamp as it's put on an object" - so
  a keyword counter put on *after* "loses all abilities" still grants its
  keyword, and one put on *before* it does not survive it.
- **CR 122.1b** a keyword counter causes its object to gain that keyword.
- **CR 611.2c** the set of objects a resolving effect changes is fixed when it
  begins.
- **CR 205.1a** "is a Noggle" replaces the creature types; **CR 205.1b** "in
  addition to its other types" keeps them.
- **CR 105.2c** a colorless object has no colour.

Reported cards: Abigale, Eloquent First-Year; Curious Colossus; Noggle the
Mind. Second printings (legal, in no deck list, oracle text and legality
read off the Scryfall printing 2026-09-27):

- Lizard, Connors's Curse - "up to one other target creature loses all
  abilities and becomes a green Lizard creature with base power and
  toughness 4/4." (the durationless targeted reader, with a type/colour/base
  P/T tail instead of Abigale's counter sentence).
- Sudden Spoiling - "Until end of turn, creatures target player controls
  lose all abilities and have base power and toughness 0/2." (the mass
  reader Curious Colossus widens).
- Eaten by Piranhas - "Enchanted creature loses all abilities and is a black
  Skeleton creature with base power and toughness 1/1." (the Aura reader
  Noggle the Mind widens).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Color, Type, Zone
from tests.scenarios.harness import Scenario

ABIGALE = "Abigale, Eloquent First-Year"
COLOSSUS = "Curious Colossus"
NOGGLE = "Noggle the Mind"
LIZARD = "Lizard, Connors's Curse"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _has(scenario: Scenario, permanent, keyword: Keyword) -> bool:
    return has_keyword(permanent, keyword, scenario.game)


def _end_the_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()


# --------------------------------------------------------------------------
# Abigale, Eloquent First-Year
# --------------------------------------------------------------------------


def _abigale(*, bob=("Serra Angel",), alice=(), hand=(), extra_lands=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[ABIGALE, *hand],
            battlefield=["Plains", "Plains", *extra_lands, *alice],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_abigale(scenario: Scenario, *targets) -> None:
    scenario.will_choose_targets(*targets, username="alice", source=ABIGALE)
    scenario.cast_and_resolve(ABIGALE, *scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()


def test_abigale_strips_printed_abilities_then_the_counters_grant_three_keywords():
    """Serra Angel loses flying and vigilance (CR 613.1f), then the three
    keyword counters - put on after the loss, CR 613.7c - grant flying,
    first strike and lifelink (CR 122.1b)."""
    scenario = _abigale()
    angel = scenario.creature("Serra Angel", "bob")

    _cast_abigale(scenario, angel)

    _chars(scenario, angel)
    assert not _has(scenario, angel, Keyword.VIGILANCE)
    assert _has(scenario, angel, Keyword.FLYING)
    assert _has(scenario, angel, Keyword.FIRST_STRIKE)
    assert _has(scenario, angel, Keyword.LIFELINK)
    assert angel.counters["flying"] == 1
    assert angel.counters["first strike"] == 1
    assert angel.counters["lifelink"] == 1


def test_abigale_strips_an_activated_ability():
    """Llanowar Elves' mana ability is gone (CR 613.1f)."""
    scenario = _abigale(bob=("Llanowar Elves",))
    elves = scenario.creature("Llanowar Elves", "bob")

    _cast_abigale(scenario, elves)

    assert not any("Add {G}" in line for line in _chars(scenario, elves).abilities)
    assert _has(scenario, elves, Keyword.LIFELINK)


def test_abigale_loss_lasts_past_cleanup_and_after_abigale_leaves():
    """No duration is printed: the loss is indefinite (the card's own
    ruling), and it outlives its source (CR 611.2a)."""
    scenario = _abigale()
    angel = scenario.creature("Serra Angel", "bob")
    _cast_abigale(scenario, angel)
    abigale = scenario.creature(ABIGALE, "alice")

    scenario.game.destroy(abigale)
    _end_the_turn(scenario)

    _chars(scenario, angel)
    assert not _has(scenario, angel, Keyword.VIGILANCE)
    assert _has(scenario, angel, Keyword.FLYING)


def test_abigale_with_no_target_does_nothing():
    """ "Up to one": zero targets is a legal choice (CR 601.2c via CR
    603.3d) and nobody gets counters."""
    scenario = _abigale()
    angel = scenario.creature("Serra Angel", "bob")

    _cast_abigale(scenario)

    assert _has(scenario, angel, Keyword.VIGILANCE)
    assert angel.counters["flying"] == 0


def test_abigale_cannot_target_herself():
    """ "Other target creature" (CR 115.1)."""
    scenario = _abigale(bob=())
    scenario.will_choose_targets(username="alice", source=ABIGALE)
    scenario.cast_and_resolve(ABIGALE, *scenario.untapped_sources("Plains", "Plains"))
    abigale = scenario.creature(ABIGALE, "alice")
    scenario.pass_until_resolved()

    _chars(scenario, abigale)
    assert _has(scenario, abigale, Keyword.FLYING)
    assert abigale.counters["flying"] == 0


def test_abigale_target_gone_means_no_counters():
    """CR 608.2b: the only target left the battlefield, so the ability does
    nothing - no counters land anywhere."""
    scenario = _abigale(hand=("Lightning Bolt",), extra_lands=("Mountain",), bob=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice", source=ABIGALE)
    scenario.cast_and_resolve(ABIGALE, *scenario.untapped_sources("Plains", "Plains"))
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert bears.counters["flying"] == 0


def test_a_later_loss_of_abilities_removes_the_older_keyword_counters():
    """CR 613.7c / 613.7b: Turn to Frog resolves after the counters were put
    on, so its "loses all abilities" is applied after them in layer 6 and
    the counters' keywords are gone until end of turn - then come back."""
    scenario = _abigale(hand=("Turn to Frog",), extra_lands=("Island", "Island"))
    angel = scenario.creature("Serra Angel", "bob")
    _cast_abigale(scenario, angel)

    scenario.cast_and_resolve(
        "Turn to Frog", *scenario.untapped_sources("Island", "Island"), targets=[angel]
    )

    chars = _chars(scenario, angel)
    assert not _has(scenario, angel, Keyword.FLYING)
    assert not _has(scenario, angel, Keyword.LIFELINK)
    assert (chars.power, chars.toughness) == (1, 1)

    _end_the_turn(scenario)
    chars = _chars(scenario, angel)
    assert _has(scenario, angel, Keyword.FLYING)
    assert _has(scenario, angel, Keyword.LIFELINK)
    assert not _has(scenario, angel, Keyword.VIGILANCE)


def test_an_ability_gained_after_abigale_is_kept():
    """The card's own ruling: an ability gained after the loss stays - a
    later layer 6 grant is applied after the older loss (CR 613.7)."""
    scenario = _abigale(hand=("Rancor",), extra_lands=("Forest",), bob=(), alice=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_abigale(scenario, bears)

    scenario.cast_and_resolve("Rancor", *scenario.untapped_sources("Forest"), targets=[bears])

    chars = _chars(scenario, bears)
    assert _has(scenario, bears, Keyword.TRAMPLE)
    assert (chars.power, chars.toughness) == (4, 2)


# --------------------------------------------------------------------------
# Curious Colossus
# --------------------------------------------------------------------------


def _colossus(*, bob=("Serra Angel", "Grizzly Bears"), alice=(), bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[COLOSSUS],
            battlefield=["Plains"] * 7 + list(alice),
            library=["Plains"] * 5,
        )
        .player("bob", hand=list(bob_hand), battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_colossus(scenario: Scenario) -> None:
    scenario.will_choose_targets("bob", username="alice", source=COLOSSUS)
    scenario.cast_and_resolve(COLOSSUS, *scenario.untapped_sources(*["Plains"] * 7))
    scenario.pass_until_resolved()


def test_colossus_makes_each_opposing_creature_a_1_1_coward_with_no_abilities():
    scenario = _colossus()
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_colossus(scenario)

    for creature, kept in ((angel, "Angel"), (bears, "Bear")):
        chars = _chars(scenario, creature)
        assert (chars.power, chars.toughness) == (1, 1)
        # CR 205.1b: "in addition to its other types".
        assert "Coward" in chars.subtypes
        assert kept in chars.subtypes
        assert Type.CREATURE in chars.types
    assert not _has(scenario, angel, Keyword.FLYING)
    assert not _has(scenario, angel, Keyword.VIGILANCE)


def test_colossus_leaves_its_controllers_creatures_alone():
    scenario = _colossus(alice=("Serra Angel",), bob=("Grizzly Bears",))
    mine = scenario.creature("Serra Angel", "alice")

    _cast_colossus(scenario)

    chars = _chars(scenario, mine)
    assert (chars.power, chars.toughness) == (4, 4)
    assert _has(scenario, mine, Keyword.FLYING)
    assert "Coward" not in chars.subtypes
    colossus = _chars(scenario, scenario.creature(COLOSSUS, "alice"))
    assert (colossus.power, colossus.toughness) == (7, 7)


def test_colossus_effect_is_permanent_and_outlives_its_source():
    scenario = _colossus()
    angel = scenario.creature("Serra Angel", "bob")
    _cast_colossus(scenario)

    scenario.game.destroy(scenario.creature(COLOSSUS, "alice"))
    _end_the_turn(scenario)

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (1, 1)
    assert not _has(scenario, angel, Keyword.FLYING)


def test_a_creature_the_opponent_gets_later_is_not_affected():
    """CR 611.2c: the set is fixed as the ability resolves."""
    scenario = _colossus(bob=("Grizzly Bears",), bob_hand=("Serra Angel",))
    _cast_colossus(scenario)

    angel = scenario.put_onto_battlefield("Serra Angel", "bob")

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Coward" not in chars.subtypes


def test_counters_and_anthems_still_apply_on_top_of_the_1_1_base():
    """CR 613.4c: 7c after 7b, whatever the timestamps."""
    scenario = _colossus(bob=("Grizzly Bears", "Glorious Anthem"))
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_colossus(scenario)

    bears.add_counters("+1/+1", 1)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 3)


def test_colossus_with_an_opponent_who_has_no_creatures_does_nothing():
    scenario = _colossus(bob=("Island",))

    _cast_colossus(scenario)

    colossus = _chars(scenario, scenario.creature(COLOSSUS, "alice"))
    assert (colossus.power, colossus.toughness) == (7, 7)


# --------------------------------------------------------------------------
# Noggle the Mind
# --------------------------------------------------------------------------


def _noggle(*, bob=("Serra Angel",), alice_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[NOGGLE, *alice_hand],
            battlefield=["Island", "Island", "Plains"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enchant(scenario: Scenario, aura: str, creature):
    return scenario.cast_and_resolve(
        aura, *scenario.untapped_sources("Island", "Island", username="alice"), targets=[creature]
    )


def test_noggle_makes_a_colorless_1_1_noggle_with_no_abilities():
    scenario = _noggle()
    angel = scenario.creature("Serra Angel", "bob")

    _enchant(scenario, NOGGLE, angel)

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (1, 1)
    # CR 205.1a: "is a colorless Noggle" replaces the creature types.
    assert "Noggle" in chars.subtypes
    assert "Angel" not in chars.subtypes
    assert Type.CREATURE in chars.types
    # CR 105.2c, layer 5 (CR 613.1e): white is gone.
    assert set(chars.colors) == set()
    assert not _has(scenario, angel, Keyword.FLYING)
    assert not _has(scenario, angel, Keyword.VIGILANCE)


def test_noggle_keeps_the_card_types_of_an_artifact_creature():
    scenario = _noggle(bob=("Ornithopter",))
    thopter = scenario.creature("Ornithopter", "bob")

    _enchant(scenario, NOGGLE, thopter)

    chars = _chars(scenario, thopter)
    assert Type.ARTIFACT in chars.types
    assert "Thopter" not in chars.subtypes
    assert "Noggle" in chars.subtypes
    assert (chars.power, chars.toughness) == (1, 1)


def test_noggle_counters_still_apply_on_top():
    scenario = _noggle(bob=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "bob")
    _enchant(scenario, NOGGLE, bears)

    bears.add_counters("+1/+1", 2)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 3)


def test_the_creature_is_restored_when_noggle_leaves():
    scenario = _noggle()
    angel = scenario.creature("Serra Angel", "bob")
    aura = _enchant(scenario, NOGGLE, angel)

    scenario.game.destroy(aura)

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (4, 4)
    assert set(chars.colors) == {Color.WHITE}
    assert "Angel" in chars.subtypes
    assert _has(scenario, angel, Keyword.FLYING)


def test_noggle_on_your_own_changeling_leaves_it_only_a_noggle():
    """Changeling's every-creature-type (CR 702.73a, a layer 4 CDA) applies
    first (CR 613.3), then "is a Noggle" replaces every creature type."""
    scenario = _noggle(bob=("Amoeboid Changeling",))
    changeling = scenario.creature("Amoeboid Changeling", "bob")

    _enchant(scenario, NOGGLE, changeling)

    chars = _chars(scenario, changeling)
    assert "Noggle" in chars.subtypes
    assert "Goblin" not in chars.subtypes


# --------------------------------------------------------------------------
# Second printings
# --------------------------------------------------------------------------


def test_lizard_permanently_makes_its_target_a_green_4_4_lizard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[LIZARD],
            battlefield=["Forest"] * 4,
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Ornithopter"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.will_choose_targets(thopter, username="alice", source=LIZARD)
    scenario.cast_and_resolve(LIZARD, *scenario.untapped_sources(*["Forest"] * 4))
    scenario.pass_until_resolved()

    _end_the_turn(scenario)

    chars = _chars(scenario, thopter)
    assert (chars.power, chars.toughness) == (4, 4)
    assert set(chars.colors) == {Color.GREEN}
    assert "Lizard" in chars.subtypes
    assert "Thopter" not in chars.subtypes
    # CR 205.1a: "becomes a ... Lizard creature" sets the card type too.
    assert Type.ARTIFACT not in chars.types
    assert Type.CREATURE in chars.types
    assert not _has(scenario, thopter, Keyword.FLYING)


def test_sudden_spoiling_still_reads_through_the_widened_mass_reader():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Sudden Spoiling"],
            battlefield=["Swamp"] * 3,
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Sudden Spoiling", *scenario.untapped_sources(*["Swamp"] * 3), targets=["bob"]
    )

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (0, 2)
    assert not _has(scenario, angel, Keyword.FLYING)
    _end_the_turn(scenario)
    assert _has(scenario, angel, Keyword.FLYING)


def test_eaten_by_piranhas_still_reads_through_the_widened_aura_reader():
    scenario = _noggle(alice_hand=("Eaten by Piranhas",))
    angel = scenario.creature("Serra Angel", "bob")

    _enchant(scenario, "Eaten by Piranhas", angel)

    chars = _chars(scenario, angel)
    assert (chars.power, chars.toughness) == (1, 1)
    assert set(chars.colors) == {Color.BLACK}
    assert "Skeleton" in chars.subtypes
    assert not _has(scenario, angel, Keyword.FLYING)


@pytest.mark.parametrize("name", [ABIGALE, COLOSSUS, NOGGLE, LIZARD])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail
