"""Gaining every creature type, and the "level chain" of permanent
type/base-P/T changes that each check the creature's current type.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 205.3m** the creature types ("Creatures and kindreds share their
  lists of subtypes; these subtypes are called creature types").
- **CR 205.1a** "becomes a Kithkin Scout" *sets* the creature types - the
  new ones replace the old.
- **CR 613.1d** layer 4 (type), **CR 613.1f** layer 6 (abilities), **CR
  613.4b** sublayer 7b (base power and toughness set), **CR 613.4c** 7c
  (counters and modifiers on top), **CR 613.7b** a resolving effect is
  timestamped as it is created, so a later set in 7b wins.
- **CR 611.2a** a resolving effect lasts as stated; with nothing stated,
  until the end of the game.
- **CR 702.16i** "protection from each [set]" is one protection per member;
  **CR 702.16k** protection from a player - can't be targeted by that
  player's spells or abilities, blocked by their creatures, or dealt damage
  by their sources.
- **CR 702.73a** changeling is every creature type.

Reported cards: Glamer Gifter ("choose up to one other target creature.
Until end of turn, that creature has base power and toughness 4/4 and gains
all creature types.") and Figure of Fable (three abilities, each permanent,
the second and third checking a creature type as they resolve).

Second printings (legal in Modern, in no deck list, Scryfall printing read
2026-09-27): Wings of Velis Vel ("Until end of turn, target creature has base
power and toughness 4/4, gains all creature types, and gains flying.") and
Amoeboid Changeling ("{T}: Target creature gains all creature types until
end of turn." / "loses all creature types") for the creature-type half;
Figure of Destiny (the same chain, "8/8, flying, and first strike" as its
last tail) and Warden of the First Tree ("If this creature is a Warrior, it
becomes a Human Spirit Warrior with trample and lifelink." - no base P/T)
for the chain.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario

GIFTER = "Glamer Gifter"
FABLE = "Figure of Fable"
DESTINY = "Figure of Destiny"
WARDEN = "Warden of the First Tree"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _has(scenario: Scenario, permanent, keyword: Keyword) -> bool:
    return has_keyword(permanent, keyword, scenario.game)


def _end_the_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()


# --------------------------------------------------------------------------
# Glamer Gifter
# --------------------------------------------------------------------------


def _gifter(*, alice=("Grizzly Bears",), bob=(), hand=(), lands=("Island", "Island")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GIFTER, *hand],
            battlefield=[*lands, *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_gifter(scenario: Scenario, *targets) -> None:
    scenario.will_choose_targets(*targets, username="alice", source=GIFTER)
    scenario.cast_and_resolve(GIFTER, *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()


def test_gifter_makes_its_target_a_4_4_of_every_creature_type():
    scenario = _gifter()
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_gifter(scenario, bears)

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (4, 4)
    # CR 205.3m: every creature type, the old one included.
    for kind in ("Bear", "Elf", "Goblin", "Merfolk", "Noggle", "Time Lord"):
        assert kind in chars.subtypes


def test_gifter_ends_at_cleanup():
    scenario = _gifter()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_gifter(scenario, bears)

    _end_the_turn(scenario)

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Goblin" not in chars.subtypes
    assert "Bear" in chars.subtypes


def test_gifter_can_shrink_an_opposing_creature():
    """4/4 is a set, not a pump: Serra Angel's 4/4 base stays 4/4 but a big
    creature shrinks (CR 613.4b)."""
    scenario = _gifter(alice=(), bob=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")

    _cast_gifter(scenario, giant)

    assert (_chars(scenario, giant).power, _chars(scenario, giant).toughness) == (4, 4)


def test_counters_and_pumps_still_apply_on_top():
    """CR 613.4c: a +1/+1 counter is 7c, after the 7b set."""
    scenario = _gifter()
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)

    _cast_gifter(scenario, bears)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (5, 5)


def test_gifter_with_no_target_does_nothing():
    scenario = _gifter()
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_gifter(scenario)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (2, 2)
    assert "Goblin" not in _chars(scenario, bears).subtypes


def test_gifter_cannot_target_itself():
    """ "Other target creature" - with no other creature around the only
    legal choice is none."""
    scenario = _gifter(alice=())
    _cast_gifter(scenario)
    gifter = scenario.creature(GIFTER, "alice")

    assert (_chars(scenario, gifter).power, _chars(scenario, gifter).toughness) == (1, 2)


def test_a_later_type_setting_effect_wins_over_every_creature_type():
    """CR 613.7b: Turn to Frog is later in layer 4, so the creature is a Frog
    only, and later in 7b, so it is 1/1."""
    scenario = _gifter(hand=("Turn to Frog",), lands=("Island",) * 4)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_gifter(scenario, bears)

    scenario.cast_and_resolve(
        "Turn to Frog", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )

    chars = _chars(scenario, bears)
    assert "Frog" in chars.subtypes
    assert "Goblin" not in chars.subtypes
    assert (chars.power, chars.toughness) == (1, 1)


# --------------------------------------------------------------------------
# Figure of Fable
# --------------------------------------------------------------------------


def _fable(*, lands=("Forest",) * 10, bob=(), bob_hand=(), alice=(), hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[FABLE, *lands, *alice],
            library=["Forest"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob),
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _level(scenario: Scenario, figure, index: int) -> None:
    scenario.activate(figure, index=index, auto=True)
    scenario.resolve_top()


def test_fable_first_ability_makes_a_2_3_kithkin_scout_permanently():
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")

    _level(scenario, figure, 0)
    _end_the_turn(scenario)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (2, 3)
    assert set(chars.subtypes) >= {"Kithkin", "Scout"}


def test_fable_climbs_the_whole_chain():
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")

    _level(scenario, figure, 0)
    _level(scenario, figure, 1)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (4, 5)
    # CR 205.1a: "becomes a Kithkin Soldier" replaces Scout.
    assert "Soldier" in chars.subtypes
    assert "Scout" not in chars.subtypes

    _level(scenario, figure, 2)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (7, 8)
    assert set(chars.subtypes) == {"Kithkin", "Avatar"}
    assert "Protection from each of your opponents" in chars.abilities


def test_fable_second_ability_does_nothing_unless_it_is_a_scout():
    """The card's ruling: each ability checks the creature types as it
    resolves; a Kithkin that is not a Scout gets nothing."""
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")

    _level(scenario, figure, 1)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (1, 1)
    assert "Soldier" not in chars.subtypes


def test_fable_third_ability_skips_straight_from_scout_does_nothing():
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")
    _level(scenario, figure, 0)

    _level(scenario, figure, 2)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (2, 3)
    assert "Avatar" not in chars.subtypes


def test_the_type_check_happens_on_resolution_not_activation():
    """Activate the second ability while not a Scout, then the first in
    response: the first resolves first, so the second finds a Scout."""
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")

    scenario.activate(figure, index=1, auto=True)
    scenario.activate(figure, index=0, auto=True)
    scenario.resolve_top()
    scenario.resolve_top()

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (4, 5)
    assert "Soldier" in chars.subtypes


def test_a_later_type_and_base_pt_effect_overwrites_the_level_until_it_ends():
    """The card's ruling: a set that starts after the ability resolved
    overwrites it (CR 613.7b, in layer 4 and in sublayer 7b) - and when it
    ends, the indefinite Scout is what is left."""
    scenario = _fable(lands=("Forest",) * 6 + ("Island", "Island"), hand=("Turn to Frog",))
    figure = scenario.creature(FABLE, "alice")
    _level(scenario, figure, 0)

    scenario.cast_and_resolve(
        "Turn to Frog", *scenario.untapped_sources("Island", "Island"), targets=[figure]
    )
    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (1, 1)
    assert "Scout" not in chars.subtypes

    _end_the_turn(scenario)
    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (2, 3)
    assert "Scout" in chars.subtypes


def test_counters_apply_on_top_of_the_levelled_base():
    scenario = _fable()
    figure = scenario.creature(FABLE, "alice")
    _level(scenario, figure, 0)

    figure.add_counters("+1/+1", 1)

    assert (_chars(scenario, figure).power, _chars(scenario, figure).toughness) == (3, 4)


def test_the_avatar_cannot_be_targeted_by_the_opponents_spells():
    """CR 702.16k: protection from bob - bob's Lightning Bolt cannot target
    it."""
    scenario = _fable(bob=("Mountain",), bob_hand=("Lightning Bolt",))
    figure = scenario.creature(FABLE, "alice")
    for index in (0, 1, 2):
        _level(scenario, figure, index)

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([figure])


def test_the_avatar_can_still_be_targeted_by_its_controller():
    """Protection from each of *your opponents* - never from yourself."""
    scenario = _fable(lands=("Forest",) * 11, hand=("Giant Growth",))
    figure = scenario.creature(FABLE, "alice")
    for index in (0, 1, 2):
        _level(scenario, figure, index)

    scenario.cast_and_resolve(
        "Giant Growth", *scenario.untapped_sources("Forest"), targets=[figure]
    )

    assert (_chars(scenario, figure).power, _chars(scenario, figure).toughness) == (10, 11)


def test_the_avatar_cannot_be_blocked_by_the_opponents_creatures():
    """CR 702.16k: "can't be ... blocked by creatures that player controls"."""
    scenario = _fable(bob=("Grizzly Bears",))
    figure = scenario.creature(FABLE, "alice")
    for index in (0, 1, 2):
        _level(scenario, figure, index)
    figure.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(figure)
    scenario.advance()
    with pytest.raises(ValueError, match="protection"):
        scenario.block(figure, bears)


def test_damage_from_the_opponents_sources_is_prevented():
    """CR 702.16k: damage from a source bob controls is prevented."""
    scenario = _fable(bob=("Grizzly Bears",))
    figure = scenario.creature(FABLE, "alice")
    for index in (0, 1, 2):
        _level(scenario, figure, index)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.deal_damage(figure, 3, source=bears)

    assert figure.damage == 0


def test_damage_from_its_controllers_own_sources_is_not_prevented():
    scenario = _fable(alice=("Grizzly Bears",))
    figure = scenario.creature(FABLE, "alice")
    for index in (0, 1, 2):
        _level(scenario, figure, index)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.deal_damage(figure, 3, source=bears)

    assert figure.damage == 3


# --------------------------------------------------------------------------
# Second printings
# --------------------------------------------------------------------------


def test_wings_of_velis_vel_sets_4_4_every_type_and_flying():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wings of Velis Vel"],
            battlefield=["Island", "Island", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Wings of Velis Vel", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )

    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Wizard" in chars.subtypes
    assert _has(scenario, bears, Keyword.FLYING)
    _end_the_turn(scenario)
    assert not _has(scenario, bears, Keyword.FLYING)
    assert "Wizard" not in _chars(scenario, bears).subtypes


def _amoeboid():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Amoeboid Changeling", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    changeling = scenario.creature("Amoeboid Changeling", "alice")
    changeling.summoning_sick = False
    return scenario, changeling


def test_amoeboid_changeling_gives_every_creature_type_until_end_of_turn():
    scenario, changeling = _amoeboid()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(changeling, index=0, targets=[bears])
    scenario.resolve_top()

    assert "Sliver" in _chars(scenario, bears).subtypes
    assert "Bear" in _chars(scenario, bears).subtypes
    _end_the_turn(scenario)
    assert "Sliver" not in _chars(scenario, bears).subtypes


def test_amoeboid_changeling_takes_every_creature_type_away():
    """Its second ability: layer 4, after changeling's own CDA (CR 613.3),
    so even a changeling loses them all."""
    scenario, changeling = _amoeboid()

    scenario.activate(changeling, index=1, targets=[changeling])
    scenario.resolve_top()

    assert not [kind for kind in _chars(scenario, changeling).subtypes if kind in ("Elf", "Bear")]


def _destiny(*, name=DESTINY, lands=("Mountain",) * 10):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[name, *lands], library=["Mountain"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice")


def test_figure_of_destiny_climbs_to_an_8_8_flying_first_striker():
    scenario, figure = _destiny()
    for index in (0, 1, 2):
        _level(scenario, figure, index)

    chars = _chars(scenario, figure)
    assert (chars.power, chars.toughness) == (8, 8)
    assert set(chars.subtypes) == {"Kithkin", "Spirit", "Warrior", "Avatar"}
    assert _has(scenario, figure, Keyword.FLYING)
    assert _has(scenario, figure, Keyword.FIRST_STRIKE)


def test_figure_of_destiny_warrior_step_needs_a_spirit():
    scenario, figure = _destiny()

    _level(scenario, figure, 1)

    assert (_chars(scenario, figure).power, _chars(scenario, figure).toughness) == (1, 1)


def test_warden_of_the_first_tree_gains_trample_and_lifelink_keeping_its_3_3():
    scenario, warden = _destiny(name=WARDEN, lands=("Plains",) * 10)

    _level(scenario, warden, 0)
    _level(scenario, warden, 1)

    chars = _chars(scenario, warden)
    assert (chars.power, chars.toughness) == (3, 3)
    assert set(chars.subtypes) == {"Human", "Spirit", "Warrior"}
    assert _has(scenario, warden, Keyword.TRAMPLE)
    assert _has(scenario, warden, Keyword.LIFELINK)


@pytest.mark.parametrize(
    "name", [GIFTER, FABLE, "Wings of Velis Vel", "Amoeboid Changeling", DESTINY, WARDEN]
)
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail
