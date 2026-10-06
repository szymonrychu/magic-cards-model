"""Scenario: damage amounts read from three count terms.

- **Converge** (CR 207.2c, an ability word with no rules meaning of its own):
  "where X is the number of colors of mana spent to cast this spell" read as a
  where-X definition of ANY damage clause, not only the one-template-per-card
  readers it used to need. Radiant Flames (a group, "to each creature") is the
  listed card; Kaleidoscorch ("to any target") is the second printing. The
  count is of colours of mana actually spent (CR 601.2h; CR 105.1's five
  colours - colourless is not one), and 0 for a spell cast without paying mana.
- **Snow** (CR 205.4g: any permanent with the supertype snow is a snow
  permanent): "the number of snow permanents you control" (Skred) and "snow
  lands you control" (Priest of the Haunted Edge); Conifer Wurm proves
  the permanents phrase in another position.
- **A list of types and subtypes** with a plain "and" (Road Rage's "2 plus the
  number of Mounts and Vehicles you control"; Runebound Wolf's "the number of
  Wolves and Werewolves you control"): a permanent that matches several items
  of the list is one permanent and counts once.

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# ---------------------------------------------------------------------------
# Radiant Flames - "Converge - Radiant Flames deals X damage to each creature,
# where X is the number of colors of mana spent to cast this spell."
# ---------------------------------------------------------------------------


def _flames_board(alice_lands, *, hand=("Radiant Flames",), bf_extra=()):
    return _main(
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*alice_lands, "Colossal Dreadmaw", *bf_extra],
        )
        .player("bob", battlefield=["Craw Wurm", "Grizzly Bears"])
        .build()
    )


def test_radiant_flames_deals_a_damage_per_colour_to_each_creature():
    scenario = _flames_board(["Mountain", "Forest", "Island"])
    sources = scenario.untapped_sources("Mountain", "Forest", "Island")
    scenario.cast_and_resolve("Radiant Flames", *sources)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    assert dreadmaw.damage == 3  # R, G and U were spent: three colours
    assert wurm.damage == 3
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None


def test_one_colour_spent_three_times_is_one():
    scenario = _flames_board(["Mountain", "Mountain", "Mountain"])
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Radiant Flames", *sources)
    assert scenario.creature("Colossal Dreadmaw", "alice").damage == 1
    assert scenario.creature("Craw Wurm", "bob").damage == 1
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob") is not None


def test_colourless_mana_is_not_a_colour_spent():
    """CR 105.1/105.2c: Wastes make {C}, which pays the generic part but is
    not one of the five colours, so {2}{R} paid R + C + C is one colour."""
    scenario = _flames_board(["Mountain", "Wastes", "Wastes"])
    sources = scenario.untapped_sources("Mountain", "Wastes", "Wastes")
    scenario.cast_and_resolve("Radiant Flames", *sources)
    assert scenario.creature("Colossal Dreadmaw", "alice").damage == 1


def test_two_colours_spent_is_two():
    scenario = _flames_board(["Mountain", "Mountain", "Island"])
    sources = scenario.untapped_sources("Mountain", "Mountain", "Island")
    scenario.cast_and_resolve("Radiant Flames", *sources)
    assert scenario.creature("Colossal Dreadmaw", "alice").damage == 2
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None


def test_cast_without_paying_mana_spends_no_colour_so_deals_zero():
    """CR 601.2h: nothing is paid, so no colour of mana was spent; CR 107.1b's
    zero comes out and the creatures are untouched (Zaffai and the Tempests'
    free cast of a sorcery, once each turn)."""
    scenario = _flames_board([], bf_extra=["Zaffai and the Tempests"])
    casting = scenario.cast("Radiant Flames")
    casting.use_alternative_cost("Zaffai and the Tempests")
    payment = casting.begin_paying()
    scenario.pay_with(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.creature("Colossal Dreadmaw", "alice").damage == 0
    assert scenario.creature("Grizzly Bears", "bob").damage == 0
    assert scenario.find("Radiant Flames", Zone.GRAVEYARD, "alice") is not None


# ---------------------------------------------------------------------------
# Kaleidoscorch - "Converge - Kaleidoscorch deals X damage to any target,
# where X is the number of colors of mana spent to cast this spell." (second
# printing: a single target, a different position for the same where-X.)
# ---------------------------------------------------------------------------


def _scorch_board(lands):
    return _main(
        Scenario()
        .player("alice", hand=["Kaleidoscorch"], battlefield=lands)
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )


def test_kaleidoscorch_two_colours_deals_two_to_a_player():
    scenario = _scorch_board(["Mountain", "Island"])
    sources = scenario.untapped_sources("Mountain", "Island")
    scenario.cast_and_resolve("Kaleidoscorch", *sources, targets=["bob"])
    assert scenario.player("bob").life == 18


def test_kaleidoscorch_one_colour_deals_one_to_a_creature():
    scenario = _scorch_board(["Mountain", "Mountain"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Kaleidoscorch", *sources, targets=[dreadmaw])
    assert dreadmaw.damage == 1


# ---------------------------------------------------------------------------
# Skred - "Skred deals damage to target creature equal to the number of snow
# permanents you control."
# ---------------------------------------------------------------------------


def _skred_board(alice_bf, bob_bf=("Colossal Dreadmaw",)):
    return _main(
        Scenario()
        .player("alice", hand=["Skred"], battlefield=list(alice_bf))
        .player("bob", battlefield=list(bob_bf))
        .build()
    )


def test_skred_counts_the_snow_permanents_you_control():
    scenario = _skred_board(["Snow-Covered Mountain", "Snow-Covered Mountain", "Mountain"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (snow, *_rest) = scenario.untapped_sources("Snow-Covered Mountain", "Snow-Covered Mountain")
    scenario.cast_and_resolve("Skred", snow, targets=[dreadmaw])
    # The tapped snow land still counts: two snow permanents, not the Mountain.
    assert dreadmaw.damage == 2


def test_skred_with_no_snow_permanents_deals_nothing():
    scenario = _skred_board(["Mountain", "Mountain"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (mountain, *_rest) = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Skred", mountain, targets=[dreadmaw])
    assert dreadmaw.damage == 0


def test_skred_does_not_count_an_opponents_snow_permanents():
    scenario = _skred_board(
        ["Snow-Covered Mountain"], bob_bf=["Colossal Dreadmaw", "Snow-Covered Forest"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (snow,) = scenario.untapped_sources("Snow-Covered Mountain")
    scenario.cast_and_resolve("Skred", snow, targets=[dreadmaw])
    assert dreadmaw.damage == 1


def test_skred_counts_a_snow_creature_as_a_snow_permanent():
    scenario = _skred_board(["Snow-Covered Mountain", "Conifer Wurm"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (snow,) = scenario.untapped_sources("Snow-Covered Mountain")
    scenario.cast_and_resolve("Skred", snow, targets=[dreadmaw])
    assert dreadmaw.damage == 2


# ---------------------------------------------------------------------------
# Snow permanents in other positions - Conifer Wurm ("{3}{G}: This creature gets
# +X/+X until end of turn, where X is the number of snow permanents you
# control.") and Priest of the Haunted Edge ("snow lands you control").
# ---------------------------------------------------------------------------


def test_conifer_wurm_pump_counts_snow_permanents_including_itself():
    scenario = _main(
        Scenario()
        .player(
            "alice",
            battlefield=["Conifer Wurm", *["Snow-Covered Forest"] * 4, "Forest"],
        )
        .player("bob")
        .build()
    )
    wurm = scenario.creature("Conifer Wurm", "alice")
    sources = scenario.untapped_sources(
        "Snow-Covered Forest", "Snow-Covered Forest", "Snow-Covered Forest", "Forest"
    )
    scenario.activate(wurm, *sources)
    scenario.resolve_top()
    # Four snow lands and the snow creature itself: +5/+5.
    assert scenario.game.characteristics_of(wurm).power == 9


def test_priest_of_the_haunted_edge_counts_snow_lands_only():
    scenario = _main(
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Priest of the Haunted Edge",
                "Snow-Covered Mountain",
                "Snow-Covered Forest",
                "Mountain",
                "Conifer Wurm",
            ],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    priest = scenario.creature("Priest of the Haunted Edge", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.activate(priest, targets=[dreadmaw], sacrificing=[priest])
    scenario.resolve_top()
    # Two snow lands - the snow creatures (the Priest, the Wurm) do not count.
    assert scenario.game.characteristics_of(dreadmaw).power == 4


# ---------------------------------------------------------------------------
# Road Rage - "Road Rage deals X damage to target creature or planeswalker,
# where X is 2 plus the number of Mounts and Vehicles you control."
# ---------------------------------------------------------------------------


def _road_rage_board(alice_bf):
    return _main(
        Scenario()
        .player("alice", hand=["Road Rage"], battlefield=["Mountain", "Mountain", *alice_bf])
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )


def _road_rage(alice_bf):
    scenario = _road_rage_board(alice_bf)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Road Rage", auto=True, targets=[dreadmaw])
    return dreadmaw.damage


def test_road_rage_with_neither_is_just_two():
    assert _road_rage([]) == 2


def test_road_rage_counts_a_mount():
    assert _road_rage(["Gloryheath Lynx"]) == 3


def test_road_rage_counts_a_vehicle():
    assert _road_rage(["Flywheel Racer"]) == 3


def test_road_rage_counts_both_lists_together():
    assert _road_rage(["Gloryheath Lynx", "Giant Beaver", "Flywheel Racer"]) == 5


def test_road_rage_counts_a_changeling_once_though_it_is_a_mount():
    """A changeling is every creature type (CR 702.73a), Mount included, but it
    is one permanent: one count."""
    assert _road_rage(["Changeling Outcast"]) == 3


def test_road_rage_ignores_other_creatures_and_opponents_mounts():
    scenario = _main(
        Scenario()
        .player("alice", hand=["Road Rage"], battlefield=["Mountain", "Mountain", "Memnite"])
        .player("bob", battlefield=["Colossal Dreadmaw", "Gloryheath Lynx", "Flywheel Racer"])
        .build()
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve("Road Rage", auto=True, targets=[dreadmaw])
    assert dreadmaw.damage == 2


# ---------------------------------------------------------------------------
# Runebound Wolf - "{3}{R}, {T}: This creature deals damage equal to the
# number of Wolves and Werewolves you control to target opponent." (second
# printing of the "X and Y you control" list, without the "plus".)
# ---------------------------------------------------------------------------


def _wolf_board(extra):
    return _main(
        Scenario()
        .player(
            "alice",
            battlefield=["Runebound Wolf", "Mountain", "Mountain", "Mountain", "Mountain", *extra],
        )
        .player("bob")
        .build()
    )


def test_runebound_wolf_counts_itself_and_other_wolves():
    scenario = _wolf_board(["Watchwolf"])
    wolf = scenario.creature("Runebound Wolf", "alice")
    scenario.activate(wolf, auto=True, targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_runebound_wolf_counts_a_changeling_once():
    scenario = _wolf_board(["Changeling Outcast"])
    wolf = scenario.creature("Runebound Wolf", "alice")
    scenario.activate(wolf, auto=True, targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 18  # the Wolf and the changeling, once each
