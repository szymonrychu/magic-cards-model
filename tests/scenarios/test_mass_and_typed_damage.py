"""Scenario: mass and conditional damage - four shapes across this task's
listed cards, two of them read by pre-existing, general `machines/effects.py`
machinery (proven here on their own listed printing, not widened by this
task) and two new merge-clause readers this task adds.

- **Desolation of Smaug**: "deals 3 damage to each non-Dragon creature." -
  `_GROUP_NON_SUBTYPE_RE`/`_parse_damage_group_phrase`'s pre-existing
  "non-`<Subtype>` `<group>`" filter (Fiery Cannonade's own "non-Pirate
  creature").
- **Easy Pickings**: "deals 1 damage to each creature your opponents
  control." - `_GROUP_CONTROLLER_RE`'s pre-existing controller filter.
- **The Black Arrow**: "deals 1 damage to any target. If a Dragon is dealt
  damage this way, destroy it." - the new `_merge_damage_any_target_then_
  destroy_if_type_clauses`, proven generic on Silver Bolt's real,
  modern/pioneer-legal "It deals 3 damage to target creature. If a
  Werewolf is dealt damage this way, destroy it." - a differently worded
  recipient ("target creature" rather than "any target") on an activated
  ability rather than a triggered one.
- **Spew Flame** (Smaug, the Great Calamity's adventure half): "deals 5
  damage to target creature." - the plain, pre-existing single-target
  damage reader, exercised through CR 715.3's Adventure cast.

CR 608.2c ("if the effect... [is] separated by a period, each sentence in
that group is a separate instruction") and CR 615.6 ("prevented damage is
not dealt") were verified with `mise run rules:find` in the session that
wrote this file - see `machines/effects.py`'s own docstrings for the exact
wording they already cite for the merge-clause pattern and for `Game.
deal_damage`'s return value respectively.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Desolation of Smaug: deals 3 damage to each non-Dragon creature --------


def test_desolation_of_smaug_spares_dragons_and_kills_a_small_bear():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Desolation of Smaug"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Desert Were-Worm"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worm = scenario.creature("Desert Were-Worm", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert "Dragon" in scenario.game.characteristics_of(worm).subtypes

    scenario.will_choose("R", source="Desolation of Smaug")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Desolation of Smaug", *sources, username="alice")

    assert worm.damage == 0, "a Dragon - spared"
    assert bears.zone is Zone.GRAVEYARD, "not a Dragon, 3 damage to a 2-toughness bear"


# -- Easy Pickings: deals 1 damage to each creature your opponents control --


def test_easy_pickings_hits_only_the_opponents_creatures():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Glóin the Mighty"], battlefield=["Mountain", "Mountain", "Mountain"]
        )
        .player("bob", battlefield=["Mogg Fanatic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Mogg Fanatic", "bob")

    casting = scenario.cast("Glóin the Mighty")
    casting.cast_as_adventure()
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert fanatic.zone is Zone.GRAVEYARD, "1 damage kills the 1/1 Mogg Fanatic"


def test_easy_pickings_does_not_touch_its_own_controllers_creatures():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glóin the Mighty"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mogg Fanatic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own_fanatic = scenario.creature("Mogg Fanatic", "alice")

    casting = scenario.cast("Glóin the Mighty")
    casting.cast_as_adventure()
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert own_fanatic.zone is Zone.BATTLEFIELD
    assert own_fanatic.damage == 0


# -- The Black Arrow: deals 1 damage to any target, destroy if a Dragon -----


def test_black_arrow_destroys_a_dragon_dealt_damage_this_way():
    scenario = (
        Scenario()
        .player("alice", hand=["The Black Arrow"], battlefield=["Wastes", "Wastes", "Wastes"])
        .player("bob", battlefield=["Desert Were-Worm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worm = scenario.creature("Desert Were-Worm", "bob")

    scenario.choose_trigger_targets("The Black Arrow", [worm])
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes")
    scenario.cast_and_resolve("The Black Arrow", *sources, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert worm.zone is Zone.GRAVEYARD, "a Dragon dealt damage this way is destroyed outright"


def test_black_arrow_leaves_a_non_dragon_merely_damaged():
    scenario = (
        Scenario()
        .player("alice", hand=["The Black Arrow"], battlefield=["Wastes", "Wastes", "Wastes"])
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Wurmcoil Engine", "bob")

    scenario.choose_trigger_targets("The Black Arrow", [wurm])
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes")
    scenario.cast_and_resolve("The Black Arrow", *sources, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert wurm.zone is Zone.BATTLEFIELD
    assert wurm.damage == 1


def test_silver_bolt_a_second_real_printing_destroys_a_werewolf_dealt_damage_this_way():
    """Silver Bolt: "{3}, {T}, Sacrifice this artifact: It deals 3 damage to
    target creature. If a Werewolf is dealt damage this way, destroy it." -
    an activated ability, "target creature" instead of "any target"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Silver Bolt", "Wastes", "Wastes", "Wastes"],
        )
        .player("bob", battlefield=["Werewolf Pack Leader"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Silver Bolt", Zone.BATTLEFIELD, "alice")
    leader = scenario.creature("Werewolf Pack Leader", "bob")

    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes")
    scenario.activate(bolt, *sources, targets=[leader])
    scenario.resolve_top()

    assert leader.zone is Zone.GRAVEYARD, "a Werewolf dealt damage this way is destroyed"


# -- Spew Flame (Smaug, the Great Calamity's adventure): plain targeted -----
# -- damage, read the ordinary way through CR 715.3's Adventure cast --------


def test_spew_flame_deals_5_damage_to_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smaug, the Great Calamity // Spew Flame"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Smaug, the Great Calamity")
    casting.cast_as_adventure()
    casting.choose_targets([bears])
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD, "5 damage to a 2-toughness bear"
