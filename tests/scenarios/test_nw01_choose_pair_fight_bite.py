"""The "Choose target creature you control and target creature <you don't
control | an opponent controls>." template, read as one instruction: an
optional conditional rider (a pump or +1/+1 counters, gated on a printed
condition checked as the spell resolves), then a fight or a bite.

Rules verified with `mise run rules:find`:

- **CR 701.14a** - fight: "Each of those creatures deals damage equal to its
  power to the other creature."
- **CR 701.14b** - a creature no longer on the battlefield or no longer a
  creature neither fights nor deals damage.
- **CR 608.2b** - a target that is illegal on resolution is not affected; the
  spell still resolves while one target remains legal, so the survivor still
  gets the rider but nothing fights.
- **CR 608.2c** - the instructions happen in printed order: the rider's pump
  or counter lands before the fight, so it changes the damage dealt.
- **CR 207.2c** - Coven and Delirium are ability words with no rules meaning
  of their own; the printed "if" is the condition.
- **CR 205.4g** - snow is a supertype, counted from the permanents' computed
  characteristics.
- **CR 120.3** - damage dealt equal to toughness (Grim Contest) is an
  ordinary damage event, not a fight.

Reported cards: Blizzard Brawl, Beastie Beatdown, Duel for Dominance, Joust,
Malamet Battle Glyph, Tail Swipe, Grim Contest. Longstalk Brawl is the off-set
second printing for the template (a gift condition, a counter rider).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _all_notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _power_toughness(scenario, card) -> tuple[int | None, int | None]:
    return (
        scenario.game.continuous_effects.board(scenario.game.battlefield).of(card).power_toughness
    )


def _setup(spell, alice_bf, bob_bf, *, step=Step.PRECOMBAT_MAIN, graveyard=None, library=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=alice_bf,
            graveyard=graveyard or [],
            library=library or ["Forest"],
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(step)
    return scenario


def _cast(scenario, spell, mine, theirs, *land_names):
    sources = scenario.untapped_sources(*land_names)
    scenario.cast_and_resolve(spell, *sources, targets=[mine, theirs])
    assert _all_notices(scenario) == []


# --------------------------------------------------------------------------
# Blizzard Brawl: snow count, pump + indestructible, then fight
# --------------------------------------------------------------------------


def test_blizzard_brawl_with_three_snow_permanents_pumps_and_protects_before_the_fight():
    scenario = _setup(
        "Blizzard Brawl",
        ["Snow-Covered Forest"] * 3 + ["Grizzly Bears"],
        ["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Blizzard Brawl", bears, angel, "Snow-Covered Forest")

    assert _power_toughness(scenario, bears) == (3, 2)
    assert is_indestructible(bears, scenario.game)
    assert angel.damage == 3, "the +1/+0 landed before the fight (CR 608.2c)"
    assert bears.zone is Zone.BATTLEFIELD, "4 damage does not destroy an indestructible creature"
    assert bears.damage == 4


def test_blizzard_brawl_with_only_two_snow_permanents_is_a_plain_fight():
    scenario = _setup(
        "Blizzard Brawl",
        ["Snow-Covered Forest"] * 2 + ["Grizzly Bears"],
        ["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Blizzard Brawl", bears, angel, "Snow-Covered Forest")

    assert not is_indestructible(bears, scenario.game)
    assert angel.damage == 2
    assert bears.zone is Zone.GRAVEYARD


def test_blizzard_brawl_counts_every_snow_permanent_not_only_lands():
    """Two snow lands plus a snow creature are three snow permanents."""
    scenario = _setup(
        "Blizzard Brawl",
        ["Snow-Covered Forest"] * 2 + ["Icehide Golem", "Grizzly Bears"],
        ["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Blizzard Brawl", bears, angel, "Snow-Covered Forest")

    assert _power_toughness(scenario, bears) == (3, 2)
    assert is_indestructible(bears, scenario.game)


def test_blizzard_brawl_opposing_creature_gone_still_pumps_but_nothing_fights():
    """CR 608.2b: one legal target keeps the spell resolving; the rider
    applies to the legal creature you control, and no fight happens."""
    scenario = _setup(
        "Blizzard Brawl",
        ["Snow-Covered Forest"] * 3 + ["Grizzly Bears"],
        ["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast("Blizzard Brawl")
    casting.choose_targets([bears, angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Snow-Covered Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(angel)
    scenario.resolve_top()

    assert _power_toughness(scenario, bears) == (3, 2)
    assert is_indestructible(bears, scenario.game)
    assert bears.damage == 0, "a creature that left the battlefield deals no fight damage"


def test_blizzard_brawl_your_creature_gone_means_no_fight_and_no_damage():
    scenario = _setup(
        "Blizzard Brawl",
        ["Snow-Covered Forest"] * 3 + ["Grizzly Bears"],
        ["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast("Blizzard Brawl")
    casting.choose_targets([bears, angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Snow-Covered Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(bears)
    scenario.resolve_top()

    assert angel.damage == 0


# --------------------------------------------------------------------------
# Beastie Beatdown: delirium counters, then a one-directional power bite
# --------------------------------------------------------------------------


def test_beastie_beatdown_with_delirium_puts_two_counters_then_bites_for_the_new_power():
    scenario = _setup(
        "Beastie Beatdown",
        ["Mountain", "Forest", "Grizzly Bears"],
        ["Serra Angel"],
        graveyard=["Icehide Golem", "Forest", "Lightning Bolt", "Ponder"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Beastie Beatdown", bears, angel, "Mountain", "Forest")

    assert _power_toughness(scenario, bears) == (4, 4)
    assert angel.zone is Zone.GRAVEYARD, "4 damage from the grown bear kills a 4/4"
    assert bears.damage == 0, "a bite is one-directional: nothing comes back"


def test_beastie_beatdown_without_delirium_bites_with_unchanged_power():
    scenario = _setup(
        "Beastie Beatdown",
        ["Mountain", "Forest", "Grizzly Bears"],
        ["Serra Angel"],
        graveyard=["Forest", "Lightning Bolt", "Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Beastie Beatdown", bears, angel, "Mountain", "Forest")

    assert _power_toughness(scenario, bears) == (2, 2)
    assert angel.damage == 2
    assert bears.damage == 0


def test_beastie_beatdown_opposing_creature_gone_still_gets_the_counters():
    scenario = _setup(
        "Beastie Beatdown",
        ["Mountain", "Forest", "Grizzly Bears"],
        ["Serra Angel"],
        graveyard=["Icehide Golem", "Forest", "Lightning Bolt", "Ponder"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast("Beastie Beatdown")
    casting.choose_targets([bears, angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(angel)
    scenario.resolve_top()

    assert _power_toughness(scenario, bears) == (4, 4)
    assert _all_notices(scenario) == []


# --------------------------------------------------------------------------
# Duel for Dominance: coven, counter on "the chosen creature you control"
# --------------------------------------------------------------------------


def test_duel_for_dominance_with_three_different_powers_adds_a_counter_before_the_fight():
    scenario = _setup(
        "Duel for Dominance",
        ["Forest", "Forest", "Grizzly Bears", "Llanowar Elves", "Elder Gargaroth"],
        ["Wall of Omens"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Duel for Dominance", bears, wall, "Forest", "Forest")

    assert _power_toughness(scenario, bears) == (3, 3)
    assert wall.damage == 3
    assert bears.damage == 0, "the Wall has 0 power"


def test_duel_for_dominance_with_repeated_powers_is_not_coven():
    """Bears, Bears and Wargling are three creatures but one distinct power."""
    scenario = _setup(
        "Duel for Dominance",
        ["Forest", "Forest", "Grizzly Bears", "Grizzly Bears", "Wargling"],
        ["Wall of Omens"],
    )
    bears = scenario.creatures("Grizzly Bears", username="alice")[0]
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Duel for Dominance", bears, wall, "Forest", "Forest")

    assert _power_toughness(scenario, bears) == (2, 2)
    assert wall.damage == 2


def test_duel_for_dominance_two_creatures_with_different_powers_is_not_enough():
    scenario = _setup(
        "Duel for Dominance",
        ["Forest", "Forest", "Grizzly Bears", "Elder Gargaroth"],
        ["Wall of Omens"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Duel for Dominance", bears, wall, "Forest", "Forest")

    assert wall.damage == 2


# --------------------------------------------------------------------------
# Joust: "+2/+1 ... if it's a Knight"
# --------------------------------------------------------------------------


def test_joust_pumps_a_knight_before_it_fights():
    scenario = _setup("Joust", ["Mountain", "Mountain", "Knight of Grace"], ["Serra Angel"])
    knight = scenario.creature("Knight of Grace", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Joust", knight, angel, "Mountain", "Mountain")

    assert angel.zone is Zone.GRAVEYARD, "a 4-power Knight kills a 4/4"
    assert knight.zone is Zone.GRAVEYARD, "and the Angel's 4 damage kills the 4/3 Knight"


def test_joust_does_not_pump_a_non_knight():
    scenario = _setup("Joust", ["Mountain", "Mountain", "Grizzly Bears"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Joust", bears, wall, "Mountain", "Mountain")

    assert _power_toughness(scenario, bears) == (2, 2)
    assert wall.damage == 2


def test_joust_knight_survives_when_the_pump_raises_toughness_past_the_damage():
    scenario = _setup("Joust", ["Mountain", "Mountain", "Knight of Grace"], ["Grizzly Bears"])
    knight = scenario.creature("Knight of Grace", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Joust", knight, bears, "Mountain", "Mountain")

    assert bears.zone is Zone.GRAVEYARD
    assert knight.zone is Zone.BATTLEFIELD
    assert knight.damage == 2


# --------------------------------------------------------------------------
# Malamet Battle Glyph: "if the creature you control entered this turn"
# --------------------------------------------------------------------------


def test_malamet_battle_glyph_adds_a_counter_to_a_creature_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Malamet Battle Glyph"],
            battlefield=["Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Wall of Omens"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice", from_zone=Zone.LIBRARY)
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Malamet Battle Glyph", bears, wall, "Forest")

    assert _power_toughness(scenario, bears) == (3, 3)
    assert wall.damage == 3


def test_malamet_battle_glyph_adds_nothing_for_a_creature_that_was_already_there():
    scenario = _setup("Malamet Battle Glyph", ["Forest", "Grizzly Bears"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Malamet Battle Glyph", bears, wall, "Forest")

    assert _power_toughness(scenario, bears) == (2, 2)
    assert wall.damage == 2


# --------------------------------------------------------------------------
# Tail Swipe: "if you cast this spell during your main phase"
# --------------------------------------------------------------------------


def test_tail_swipe_cast_in_your_main_phase_pumps_before_the_fight():
    scenario = _setup("Tail Swipe", ["Forest", "Grizzly Bears"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Tail Swipe", bears, wall, "Forest")

    assert _power_toughness(scenario, bears) == (3, 3)
    assert wall.damage == 3


def test_tail_swipe_cast_outside_a_main_phase_is_a_plain_fight():
    scenario = _setup(
        "Tail Swipe",
        ["Forest", "Grizzly Bears"],
        ["Wall of Omens"],
        step=Step.BEGINNING_OF_COMBAT,
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Tail Swipe", bears, wall, "Forest")

    assert _power_toughness(scenario, bears) == (2, 2)
    assert wall.damage == 2


# --------------------------------------------------------------------------
# Grim Contest: both deal damage equal to their own toughness
# --------------------------------------------------------------------------


def test_grim_contest_each_creature_deals_damage_equal_to_its_toughness():
    scenario = _setup(
        "Grim Contest", ["Swamp", "Forest", "Forest", "Wall of Omens"], ["Grizzly Bears"]
    )
    wall = scenario.creature("Wall of Omens", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Grim Contest", wall, bears, "Swamp", "Forest", "Forest")

    assert bears.zone is Zone.GRAVEYARD, "the 0/4 Wall deals 4 (its toughness)"
    assert wall.damage == 2, "the bear deals 2 (its toughness) back"


def test_grim_contest_a_big_toughness_creature_survives_the_exchange_it_started():
    scenario = _setup(
        "Grim Contest", ["Swamp", "Forest", "Forest", "Grizzly Bears"], ["Wall of Omens"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Grim Contest", bears, wall, "Swamp", "Forest", "Forest")

    assert wall.damage == 2
    assert bears.zone is Zone.GRAVEYARD, "the wall's 4 toughness is 4 damage to the bear"


def test_grim_contest_opposing_creature_gone_deals_nothing():
    scenario = _setup(
        "Grim Contest", ["Swamp", "Forest", "Forest", "Wall of Omens"], ["Grizzly Bears"]
    )
    wall = scenario.creature("Wall of Omens", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Grim Contest")
    casting.choose_targets([wall, bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(bears)
    scenario.resolve_top()

    assert wall.damage == 0


# --------------------------------------------------------------------------
# Longstalk Brawl: the second printing - a gift condition and a trailing "if"
# --------------------------------------------------------------------------


def _cast_longstalk(*, gift):
    scenario = _setup("Longstalk Brawl", ["Forest", "Grizzly Bears"], ["Wall of Omens"])
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Wall of Omens", "bob")
    spell = scenario.find("Longstalk Brawl", Zone.HAND, "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.game.cast(spell, "alice", targets=[bears, angel], mana_sources=[forest], gift=gift)
    scenario.pass_until_resolved()
    return scenario, bears, angel


def test_longstalk_brawl_with_the_gift_promised_adds_a_counter_before_the_fight():
    scenario, bears, wall = _cast_longstalk(gift="bob")

    assert _power_toughness(scenario, bears) == (3, 3)
    assert wall.damage == 3
    assert _all_notices(scenario) == []


def test_longstalk_brawl_without_the_gift_is_a_plain_fight():
    scenario, bears, wall = _cast_longstalk(gift=None)

    assert _power_toughness(scenario, bears) == (2, 2)
    assert wall.damage == 2
    assert _all_notices(scenario) == []


def test_joust_a_knight_that_survives_shows_the_plus_two_plus_one_until_end_of_turn():
    scenario = _setup("Joust", ["Mountain", "Mountain", "Knight of Grace"], ["Wall of Omens"])
    knight = scenario.creature("Knight of Grace", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    _cast(scenario, "Joust", knight, wall, "Mountain", "Mountain")

    assert _power_toughness(scenario, knight) == (4, 3)
    assert wall.zone is Zone.GRAVEYARD, "4 damage is lethal to a 0/4"


# --------------------------------------------------------------------------
# Time to Feed: a turn-scoped "when that creature dies" watch, then a fight
# --------------------------------------------------------------------------


def _time_to_feed(alice_bf, bob_bf, *, hand_extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Time to Feed", *hand_extra],
            battlefield=["Forest", "Forest", "Forest", "Mountain", *alice_bf],
            library=["Forest"],
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_time_to_feed_gains_three_life_when_the_fight_kills_the_chosen_creature():
    scenario = _time_to_feed(["Elder Gargaroth"], ["Grizzly Bears"])
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Time to Feed", *sources, targets=[bears, gargaroth])
    scenario.resolve_top()  # the delayed "when that creature dies" ability

    assert bears.zone is Zone.GRAVEYARD
    assert gargaroth.damage == 2
    assert scenario.player("alice").life == 23
    assert _all_notices(scenario) == []


def test_time_to_feed_survivor_gains_nothing_until_it_dies_later_this_turn():
    scenario = _time_to_feed(["Grizzly Bears"], ["Wall of Omens"], hand_extra=["Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Time to Feed", *sources, targets=[wall, bears])

    assert wall.damage == 2
    assert scenario.player("alice").life == 20, "the wall survived the fight: no life yet"

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[wall])
    scenario.resolve_top()

    assert wall.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23, "the watch lasts the whole turn (CR 603.7b)"


def test_time_to_feed_your_creature_gone_still_watches_but_nothing_fights():
    scenario = _time_to_feed(["Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Time to Feed")
    casting.choose_targets([theirs, mine])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(mine)
    scenario.resolve_top()

    assert theirs.damage == 0, "no fight with a creature that is no longer a legal target"
    assert _all_notices(scenario) == []


def test_time_to_feed_chosen_creature_gone_creates_no_watch_and_no_fight():
    scenario = _time_to_feed(["Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Time to Feed")
    casting.choose_targets([theirs, mine])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(theirs)
    scenario.resolve_top()

    assert mine.damage == 0
    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# Moonlight Hunt: each creature you control of a given type deals its own damage
# --------------------------------------------------------------------------


def _moonlight(alice_bf, bob_bf):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Moonlight Hunt"],
            battlefield=["Forest", "Forest", *alice_bf],
            library=["Forest"],
        )
        .player("bob", battlefield=bob_bf, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_moonlight_hunt_every_wolf_and_werewolf_deals_its_own_power():
    scenario = _moonlight(
        ["Wargling", "Watchwolf", "Werewolf Pack Leader", "Grizzly Bears"], ["Elder Gargaroth"]
    )
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Moonlight Hunt", *sources, targets=[gargaroth])

    assert gargaroth.zone is Zone.GRAVEYARD, "2 + 3 + 3 from the pack is lethal to a 6/6"
    assert _all_notices(scenario) == []


def test_moonlight_hunt_a_creature_that_is_neither_wolf_nor_werewolf_deals_nothing():
    scenario = _moonlight(["Wargling", "Grizzly Bears", "Serra Angel"], ["Elder Gargaroth"])
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Moonlight Hunt", *sources, targets=[gargaroth])

    assert gargaroth.damage == 2, "only the Wolf (power 2) bites"
    assert gargaroth.zone is Zone.BATTLEFIELD


def test_moonlight_hunt_counts_only_creatures_you_control():
    scenario = _moonlight(["Wargling"], ["Elder Gargaroth", "Watchwolf"])
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Moonlight Hunt", *sources, targets=[gargaroth])

    assert gargaroth.damage == 2, "the opponent's Watchwolf does not join in"


def test_moonlight_hunt_with_no_wolves_deals_nothing_and_is_not_a_notice():
    scenario = _moonlight(["Grizzly Bears"], ["Elder Gargaroth"])
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Moonlight Hunt", *sources, targets=[gargaroth])

    assert gargaroth.damage == 0
    assert _all_notices(scenario) == []


def test_moonlight_hunt_chosen_creature_gone_deals_nothing():
    scenario = _moonlight(["Wargling"], ["Elder Gargaroth"])
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    casting = scenario.cast("Moonlight Hunt")
    casting.choose_targets([gargaroth])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.game.exile_permanent(gargaroth)
    scenario.resolve_top()

    assert _all_notices(scenario) == []
