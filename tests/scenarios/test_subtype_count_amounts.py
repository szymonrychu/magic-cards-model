"""Amounts counted off the permanents a player controls, by subtype.

One mechanic: a number an effect uses is "the number of `<subtype>`s you
control" (or "for each `<subtype>` you control"), read off the board as CR
613's layers have left it - so a land that is a Mountain only because of a
dual land's printed type line (CR 205.3i) or a type-changing effect counts,
and one that is tapped does not when the text says "untapped".

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- **CR 608.2h** - "If an effect requires information from the game (such as
  the number of creatures on the battlefield), the answer is determined only
  once, when the effect is applied." A one-shot (Honden's trigger, Ben-Ben's
  and Koth's abilities, Nissa's -7) counts as it resolves, not when it was put
  on the stack.
- **CR 611.3a** - a static ability's continuous effect "isn't 'locked in'; it
  applies at any given moment to whatever its text indicates" - Outcaster
  Greenblade's and Hold the Gates' pumps follow the Desert/Gate count live.
- **CR 611.2c** - a resolving effect that modifies characteristics fixes the
  set of objects it affects when it begins.
- **CR 613.4c** - power/toughness modifications apply in sublayer 7c.
- **CR 110.5** - tapped/untapped is a permanent's status, not a
  characteristic.

Proof printings (not a listed card, not in any api deck, legality checked
against Scryfall on 2026-09-23): Koth, Fire of Resistance (Modern, Pioneer) and
Omnath, Locus of the Roil (Modern, Pioneer) for "deals damage to `<target>`
equal to the number of `<subtype>`s you control"; Hold the Gates (Modern,
Pioneer) for the static "get +N/+M for each `<subtype>` you control"; Tromp
the Domains (Modern) for the until-end-of-turn team pump "for each".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

HONDEN = "Honden of Infinite Rage"
BEN_BEN = "Ben-Ben, Akki Hermit"
KOTH = "Koth, Fire of Resistance"
OMNATH = "Omnath, Locus of the Roil"


# --------------------------------------------------------------------------
# "deals damage to <target> equal to the number of <subtype>s you control"
# --------------------------------------------------------------------------


def _honden_board(*, shrines: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3, battlefield=[HONDEN, *shrines])
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    return scenario


def test_honden_deals_damage_equal_to_the_shrines_you_control():
    """Two Shrines (Honden itself and Go-Shintai of Boundless Vigor): the
    upkeep trigger deals 2 to its target."""
    scenario = _honden_board(shrines=["Go-Shintai of Boundless Vigor"])
    scenario.choose_trigger_targets(HONDEN, ["bob"])

    scenario.advance()
    assert scenario.stack_names() == [f"{HONDEN}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("bob").life == 18


def test_honden_alone_counts_itself():
    """Honden is a Shrine too: alone on the battlefield it deals 1."""
    scenario = _honden_board(shrines=[])
    scenario.choose_trigger_targets(HONDEN, ["bob"])

    scenario.advance()
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_honden_counts_as_it_resolves_not_as_it_triggers():
    """CR 608.2h: the Shrine count is taken when the trigger resolves. A
    Shrine that leaves while the trigger waits on the stack is not counted."""
    scenario = _honden_board(shrines=["Go-Shintai of Boundless Vigor"])
    scenario.choose_trigger_targets(HONDEN, ["bob"])
    scenario.advance()
    go_shintai = scenario.find("Go-Shintai of Boundless Vigor", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(go_shintai)

    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_honden_ignores_shrines_an_opponent_controls():
    """ "You control": bob's Shrine adds nothing to alice's count."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3, battlefield=[HONDEN])
        .player("bob", library=["Forest"] * 3, battlefield=["Go-Shintai of Boundless Vigor"])
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.choose_trigger_targets(HONDEN, ["bob"])

    scenario.advance()
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_honden_can_aim_at_a_creature():
    """ "Any target" includes a creature: 2 damage marked on Craw Wurm."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 3,
            battlefield=[HONDEN, "Go-Shintai of Boundless Vigor"],
        )
        .player("bob", library=["Forest"] * 3, battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.UNTAP)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.choose_trigger_targets(HONDEN, [wurm])

    scenario.advance()
    scenario.resolve_top()

    assert wurm.damage == 2


def _ben_ben_combat(*, mountains: int, tapped: int) -> tuple[Scenario, object, object]:
    """Bob (the active player) attacks alice with Craw Wurm; alice holds Ben-Ben and `mountains`
    Mountains, `tapped` of them already tapped."""
    scenario = (
        Scenario()
        .player("bob", library=["Forest"] * 3, battlefield=["Craw Wurm", "Grizzly Bears"])
        .player("alice", library=["Forest"] * 3, battlefield=[BEN_BEN] + ["Mountain"] * mountains)
        .build()
    )
    for mountain in scenario.untapped_sources(*["Mountain"] * tapped, username="alice"):
        mountain.tap()
    # Staged: alice's own previous turn began with Ben-Ben already here (CR 302.6).
    scenario.game.begin_turn_for("alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.attack_with(wurm)
    scenario.pass_priority("bob")
    ben_ben = scenario.creature(BEN_BEN, "alice")
    return scenario, ben_ben, wurm


def test_ben_ben_counts_only_untapped_mountains():
    """Four Mountains, one tapped: 3 damage to the attacking Craw Wurm."""
    scenario, ben_ben, wurm = _ben_ben_combat(mountains=4, tapped=1)

    scenario.activate(ben_ben, username="alice", targets=[wurm])
    scenario.resolve_top()

    assert wurm.damage == 3


def test_ben_ben_count_follows_a_mountain_tapped_in_response():
    """CR 608.2h and CR 110.5: tapping a Mountain for mana after activating
    (with the ability on the stack) lowers the count it resolves with."""
    scenario, ben_ben, wurm = _ben_ben_combat(mountains=4, tapped=0)

    scenario.activate(ben_ben, username="alice", targets=[wurm])
    (mountain, *_) = scenario.untapped_sources("Mountain", username="alice")
    mountain.tap()
    scenario.resolve_top()

    assert wurm.damage == 3


def test_ben_ben_cannot_target_a_creature_that_is_not_attacking():
    """ "Target attacking creature": Grizzly Bears stayed home."""
    scenario, ben_ben, _wurm = _ben_ben_combat(mountains=2, tapped=0)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.activate(ben_ben, username="alice", targets=[bears])


def test_ben_ben_with_every_mountain_tapped_deals_nothing():
    """Zero untapped Mountains is zero damage, not a failure."""
    scenario, ben_ben, wurm = _ben_ben_combat(mountains=2, tapped=2)

    scenario.activate(ben_ben, username="alice", targets=[wurm])
    scenario.resolve_top()

    assert wurm.damage == 0
    assert wurm.zone is Zone.BATTLEFIELD


def test_koth_counts_a_dual_land_with_the_mountain_type():
    """Koth, Fire of Resistance (proof printing) -3: "Koth deals damage to
    target creature equal to the number of Mountains you control." Sacred
    Foundry is a Mountain Plains (CR 205.3i), so a Mountain plus Sacred
    Foundry plus a Forest is two Mountains."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[KOTH, "Mountain", "Sacred Foundry", "Forest"])
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    koth = scenario.find(KOTH, Zone.BATTLEFIELD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.activate(koth, index=1, targets=[wurm])
    scenario.resolve_top()

    assert wurm.damage == 2


def test_omnath_enters_and_counts_elementals_including_itself():
    """Omnath, Locus of the Roil (proof printing): "When Omnath enters, it
    deals damage to any target equal to the number of Elementals you
    control." Omnath is an Elemental and is on the battlefield as its own
    trigger resolves, so with one other Elemental (Hearth Elemental) the
    count is two."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[OMNATH],
            battlefield=["Hearth Elemental", "Island", "Mountain", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(OMNATH, ["bob"])

    scenario.cast_and_resolve(OMNATH, auto=True)
    scenario.resolve_top()

    assert scenario.player("bob").life == 18


# --------------------------------------------------------------------------
# Static "gets +N/+M for each <subtype> you control" (CR 611.3a, 613.4c)
# --------------------------------------------------------------------------

GREENBLADE = "Outcaster Greenblade"
HOLD_THE_GATES = "Hold the Gates"


def _pt(scenario: Scenario, permanent) -> tuple[int | None, int | None]:
    return scenario.game.characteristics_of(permanent).power_toughness


def test_greenblade_grows_with_each_desert_you_control():
    """1/2 printed, two Deserts: 3/4."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[GREENBLADE, "Sunscorched Desert", "Desert of the True"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _pt(scenario, scenario.creature(GREENBLADE, "alice")) == (3, 4)


def test_greenblade_without_a_desert_is_its_printed_size():
    scenario = Scenario().player("alice", battlefield=[GREENBLADE, "Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _pt(scenario, scenario.creature(GREENBLADE, "alice")) == (1, 2)


def test_greenblade_follows_the_desert_count_live():
    """CR 611.3a: not locked in - a Desert leaving shrinks it at once."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[GREENBLADE, "Sunscorched Desert", "Desert of the True"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    greenblade = scenario.creature(GREENBLADE, "alice")

    scenario.game.destroy(scenario.find("Desert of the True", Zone.BATTLEFIELD, "alice"))

    assert _pt(scenario, greenblade) == (2, 3)


def test_greenblade_ignores_an_opponents_desert():
    scenario = (
        Scenario()
        .player("alice", battlefield=[GREENBLADE])
        .player("bob", battlefield=["Sunscorched Desert"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _pt(scenario, scenario.creature(GREENBLADE, "alice")) == (1, 2)


def test_greenblade_fetches_a_desert_that_then_counts_once_played():
    """The enters trigger's "a Desert card" search, and the static counting
    the Desert once it is on the battlefield."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[GREENBLADE],
            library=["Sunscorched Desert", "Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(scenario.find("Sunscorched Desert", Zone.LIBRARY, "alice"))

    greenblade = scenario.cast_and_resolve(GREENBLADE, auto=True)
    scenario.resolve_top()
    scenario.play_land("Sunscorched Desert")

    assert _pt(scenario, greenblade) == (2, 3)


def test_hold_the_gates_pumps_the_team_per_gate_and_grants_vigilance():
    """Hold the Gates (proof printing): "Creatures you control get +0/+1 for
    each Gate you control and have vigilance." Two Gates: Grizzly Bears is
    2/4 with vigilance; bob's Bears are untouched."""
    from magic_cards_model.machines.combat import Keyword, has_keyword

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                HOLD_THE_GATES,
                "Grizzly Bears",
                "Azorius Guildgate",
                "Selesnya Guildgate",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _pt(scenario, bears) == (2, 4)
    assert has_keyword(bears, Keyword.VIGILANCE, scenario.game)
    assert _pt(scenario, scenario.creature("Grizzly Bears", "bob")) == (2, 2)


def test_hold_the_gates_with_no_gate_still_grants_vigilance():
    """Zero Gates is +0/+0 - the keyword half does not depend on the count."""
    from magic_cards_model.machines.combat import Keyword, has_keyword

    scenario = (
        Scenario()
        .player("alice", battlefield=[HOLD_THE_GATES, "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _pt(scenario, bears) == (2, 2)
    assert has_keyword(bears, Keyword.VIGILANCE, scenario.game)


# --------------------------------------------------------------------------
# Until end of turn, "creatures you control get +N/+N for each ..."
# (CR 608.2h, 611.2c)
# --------------------------------------------------------------------------

NISSA = "Nissa, Ascended Animist"
TROMP = "Tromp the Domains"


def _nissa_board(lands: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Forest"],
            battlefield=[NISSA, "Craw Wurm", *lands],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_nissa_minus_seven_pumps_per_forest_and_grants_trample():
    """Three Forests - one of them Breeding Pool, a Forest Island (CR
    205.3i): Craw Wurm is 9/7 with trample; bob's creature is untouched."""
    from magic_cards_model.machines.combat import Keyword, has_keyword

    scenario = _nissa_board(["Forest", "Forest", "Breeding Pool", "Island"])
    wurm = scenario.creature("Craw Wurm", "alice")

    scenario.activate(scenario.find(NISSA, Zone.BATTLEFIELD, "alice"), index=2)
    scenario.resolve_top()

    assert _pt(scenario, wurm) == (9, 7)
    assert has_keyword(wurm, Keyword.TRAMPLE, scenario.game)
    assert _pt(scenario, scenario.creature("Grizzly Bears", "bob")) == (2, 2)


def test_nissa_minus_seven_counts_once_as_it_resolves():
    """CR 608.2h: a Forest played after the ability resolved does not raise
    the pump, and CR 611.2c: a creature cast afterwards is not pumped."""
    scenario = _nissa_board(["Forest", "Forest"])
    wurm = scenario.creature("Craw Wurm", "alice")
    scenario.activate(scenario.find(NISSA, Zone.BATTLEFIELD, "alice"), index=2)
    scenario.resolve_top()

    scenario.play_land("Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", auto=True)

    assert _pt(scenario, wurm) == (8, 6)
    assert _pt(scenario, bears) == (2, 2)


def test_nissa_minus_seven_ends_at_end_of_turn():
    scenario = _nissa_board(["Forest", "Forest"])
    wurm = scenario.creature("Craw Wurm", "alice")
    scenario.activate(scenario.find(NISSA, Zone.BATTLEFIELD, "alice"), index=2)
    scenario.resolve_top()

    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _pt(scenario, wurm) == (6, 4)


def test_tromp_the_domains_counts_basic_land_types():
    """Tromp the Domains (proof printing, the other word order): "Until end of
    turn, creatures you control gain trample and get +1/+1 for each basic
    land type among lands you control." Forest, Island and Mountain (Breeding
    Pool adds nothing new): +3/+3 and trample."""
    from magic_cards_model.machines.combat import Keyword, has_keyword

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TROMP],
            battlefield=["Grizzly Bears", "Forest", "Island", "Mountain", "Breeding Pool"]
            + ["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(TROMP, auto=True)

    assert _pt(scenario, bears) == (5, 5)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
