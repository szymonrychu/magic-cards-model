"""Scenario: `Game._activation_condition_holds`'s three shapes - Mox Opal's
metalcraft ("you control three or more artifacts"), Fanatic of Rhonas's
ferocious ("you control a creature with power 4 or greater"), and Diamond
City's "two or more creatures entered the battlefield under your control
this turn" - all read a permanent's *computed* characteristics (CR 613.5),
not its printed ones.

Every CR number below was looked up with `mise run rules:find` this session.

- **Metalcraft** counts card types (`Type.ARTIFACT in state.types`, printed).
  Liquimetal Coating's own `{T}: Target permanent becomes an artifact in
  addition to its other types until end of turn.` makes a plain creature an
  artifact computed-only, so a fix that keeps reading the printed line never
  sees the third artifact and metalcraft never turns on.
- **Ferocious** compares `state.power`, which counts CR 122.1a's counters but
  not a sublayer 7c pump (CR 613.4c) - Giant Growth's "+3/+3 until end of
  turn" is invisible to it. `board.of(state).power` sees the pump.
- **Diamond City**'s "entered this turn" clause counts `state.is_creature`
  (printed). A land earthbent (CR 701.66a) the same turn it was played is a
  creature only on the computed board, so it should count as a second
  creature that entered this turn alongside Badgermole Cub itself, and a
  printed read undercounts by one.

The inverse of each - metalcraft with only two real artifacts, ferocious
with no pump, Diamond City with only one creature entering - is covered
too, so a fix that over-reads (treats everything as the counted type) fails
those the same way an under-reading fix fails the positive cases.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_metalcraft_turns_on_once_liquimetal_coating_makes_a_third_artifact():
    """Mox Opal itself and Liquimetal Coating (a real Artifact) are two
    printed artifacts; Liquimetal Coating's own ability makes Grizzly Bears
    an artifact too, computed only, reaching CR 602.5b's "three or more".
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mox Opal", "Liquimetal Coating", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(mox, 0) is not None, "only two real artifacts so far"

    scenario.activate(coating, index=0, targets=[bears])
    scenario.pass_until_resolved()

    from magic_cards_model.models.card import Type

    assert Type.ARTIFACT in scenario.game.characteristics_of(bears).types
    assert scenario.why_cannot_activate(mox, 0) is None, "three artifacts now: metalcraft is on"


def test_metalcraft_stays_off_with_only_two_real_artifacts():
    """The inverse: with no Liquimetal Coating activation, Grizzly Bears
    never becomes an artifact, and Mox Opal's metalcraft never turns on.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mox Opal", "Liquimetal Coating", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD)

    reason = scenario.why_cannot_activate(mox, 0)
    assert reason is not None
    assert "602.5b" in reason


def test_ferocious_turns_on_for_an_earthbent_land_pumped_to_power_4():
    """`CardState.power`/`.toughness` are already board-aware once
    `bind_to_game` has run (see their own docstring) - a plain creature
    pumped by Giant Growth already reads the right power under the old
    code. `is_creature`, built off the *printed* `.types`, is not: an
    earthbent land (CR 701.66a) reads False there right up until CR 613.5's
    computed board is consulted. The land is 0/0 plus earthbend's own one
    +1/+1 counter (CR 613.4c sublayer 7c comes after the counter's own
    sublayer 7c) and Giant Growth's "+3/+3 until end of turn" - 1 + 3 = 4,
    exactly Fanatic of Rhonas's ferocious threshold (CR 602.5b).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Giant Growth"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Fanatic of Rhonas"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.find("Fanatic of Rhonas", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    pay_sources, target_forest, pump_source = sources[:2], sources[2], sources[3]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(target_forest).is_creature
    assert scenario.game.characteristics_of(target_forest).power == 1

    assert scenario.why_cannot_activate(fanatic, 1) is not None, "power 1 does not meet ferocious"

    scenario.cast_and_resolve("Giant Growth", pump_source, targets=[target_forest])

    assert scenario.game.characteristics_of(target_forest).power == 4
    assert scenario.why_cannot_activate(fanatic, 1) is None, "power 4 now: ferocious is on"


def test_ferocious_stays_off_without_a_pump():
    """The inverse: Grizzly Bears alone, unpumped, never satisfies ferocious."""
    scenario = (
        Scenario().player("alice", battlefield=["Fanatic of Rhonas", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.find("Fanatic of Rhonas", Zone.BATTLEFIELD)

    reason = scenario.why_cannot_activate(fanatic, 1)
    assert reason is not None
    assert "power 4 or greater" in reason.lower() or "602.5b" in reason


def test_diamond_city_counts_an_earthbent_land_among_creatures_that_entered():
    """Badgermole Cub itself entered this turn (one creature, printed and
    computed alike); the Forest it earthbends was also played this turn and
    is a creature only on the computed board. Diamond City's own ability
    needs "two or more creatures entered the battlefield under your control
    this turn" (CR 602.5b) to activate - only true if the animated land
    counts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Forest"],
            battlefield=["Forest", "Forest", "Diamond City"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = scenario.find("Diamond City", Zone.BATTLEFIELD)
    pay_sources = scenario.untapped_sources("Forest", "Forest")
    new_forest = scenario.play_land("Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [new_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(new_forest).is_creature
    assert new_forest.turn_entered == scenario.game.turn.turn_number

    move_shield = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(diamond_city))
        if "shield counter" in (ability.text or "").lower() and "target creature" in ability.text
    )

    reason = scenario.why_cannot_activate(diamond_city, move_shield)
    assert reason is None, "two creatures entered this turn: Badgermole Cub and the animated Forest"


def test_diamond_city_refuses_with_only_one_creature_entering():
    """The inverse: with no earthbend, only Badgermole Cub itself entered
    this turn as a creature, so Diamond City's ability stays refused.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Forest", "Forest", "Diamond City"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = scenario.find("Diamond City", Zone.BATTLEFIELD)
    old_forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Badgermole Cub", [old_forest])
    scenario.put_onto_battlefield("Badgermole Cub")
    scenario.pass_until_resolved()

    assert old_forest.turn_entered != scenario.game.turn.turn_number, (
        "the earthbent land is a creature, but it did not enter this turn"
    )

    move_shield = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(diamond_city))
        if "shield counter" in (ability.text or "").lower() and "target creature" in ability.text
    )

    reason = scenario.why_cannot_activate(diamond_city, move_shield)
    assert reason is not None
    assert "602.5b" in reason


# -- "Activate only if" read for any count, any counted noun (CR 602.5b) --------
#
# The count is read by `magic_cards_model.numbers`, never a table that stops at
# some word, and the counted noun is read as a quality phrase rather than as a
# bare card type - so "snow permanents" is not silently treated as "no
# restriction at all". A restriction this engine cannot read refuses the
# activation and says so, rather than letting it through unchecked.


def _gated(
    battlefield: list[str], *, graveyard: list[str] | None = None, bob: list[str] | None = None
):
    scenario = (
        Scenario()
        .player("alice", battlefield=battlefield, graveyard=graveyard or [])
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_shrine_of_the_forsaken_gods_needs_seven_lands_not_six():
    six = _gated(["Shrine of the Forsaken Gods"] + ["Mountain"] * 5)
    shrine = six.find("Shrine of the Forsaken Gods", Zone.BATTLEFIELD)
    reason = six.why_cannot_activate(shrine, 1)
    assert reason is not None and "602.5b" in reason, "six lands: the {C}{C} ability is refused"

    seven = _gated(["Shrine of the Forsaken Gods"] + ["Mountain"] * 6)
    shrine = seven.find("Shrine of the Forsaken Gods", Zone.BATTLEFIELD)
    assert seven.why_cannot_activate(shrine, 1) is None, "seven lands: allowed"


def test_cryptic_caves_needs_five_lands_not_four():
    four = _gated(["Cryptic Caves"] + ["Island"] * 3)
    caves = four.find("Cryptic Caves", Zone.BATTLEFIELD)
    assert four.why_cannot_activate(caves, 1) is not None

    five = _gated(["Cryptic Caves"] + ["Island"] * 4)
    caves = five.find("Cryptic Caves", Zone.BATTLEFIELD)
    assert five.why_cannot_activate(caves, 1) is None


def test_kelpie_guide_needs_eight_lands():
    seven = _gated(["Kelpie Guide"] + ["Island"] * 7)
    guide = seven.find("Kelpie Guide", Zone.BATTLEFIELD)
    assert seven.why_cannot_activate(guide, 1) is not None

    eight = _gated(["Kelpie Guide"] + ["Island"] * 8)
    guide = eight.find("Kelpie Guide", Zone.BATTLEFIELD)
    assert eight.why_cannot_activate(guide, 1) is None


def test_barbarian_ring_threshold_counts_the_cards_in_your_graveyard():
    """ "Activate only if there are seven or more cards in your graveyard." -
    a restriction with no reader used to let the activation through at any
    graveyard size."""
    six = _gated(["Barbarian Ring", "Mountain"], graveyard=["Mountain"] * 6)
    ring = six.find("Barbarian Ring", Zone.BATTLEFIELD)
    reason = six.why_cannot_activate(ring, 1)
    assert reason is not None and "602.5b" in reason

    seven = _gated(["Barbarian Ring", "Mountain"], graveyard=["Mountain"] * 7)
    ring = seven.find("Barbarian Ring", Zone.BATTLEFIELD)
    assert seven.why_cannot_activate(ring, 1) is None


def test_rimewind_cryomancer_counts_snow_permanents_only():
    """CR 205.4a's snow supertype is part of the counted noun: three snow
    lands and two plain Islands are five permanents but three snow ones."""
    short = _gated(["Rimewind Cryomancer"] + ["Snow-Covered Island"] * 3 + ["Island"] * 2)
    cryomancer = short.find("Rimewind Cryomancer", Zone.BATTLEFIELD)
    assert short.why_cannot_activate(cryomancer, 0) is not None

    enough = _gated(["Rimewind Cryomancer"] + ["Snow-Covered Island"] * 4)
    cryomancer = enough.find("Rimewind Cryomancer", Zone.BATTLEFIELD)
    assert enough.why_cannot_activate(cryomancer, 0) is None


def test_tectonic_edge_counts_the_opponents_lands_not_yours():
    """ "Activate only if an opponent controls four or more lands." Alice's own
    lands never count toward it."""
    short = _gated(["Tectonic Edge"] + ["Mountain"] * 6, bob=["Forest"] * 3)
    edge = short.find("Tectonic Edge", Zone.BATTLEFIELD)
    assert short.why_cannot_activate(edge, 1) is not None

    enough = _gated(["Tectonic Edge", "Mountain"], bob=["Forest"] * 4)
    edge = enough.find("Tectonic Edge", Zone.BATTLEFIELD)
    assert enough.why_cannot_activate(edge, 1) is None


def test_xerex_strobe_knight_counts_the_spells_you_cast_this_turn():
    """ "Activate only if you've cast two or more spells this turn." - counted
    off `Game.spells_cast_this_turn`, the caster's own list."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Xerex Strobe-Knight", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.find("Xerex Strobe-Knight", Zone.BATTLEFIELD)

    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    assert scenario.why_cannot_activate(knight, 0) is not None, "one spell so far"

    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    assert scenario.why_cannot_activate(knight, 0) is None, "two spells: allowed"


def test_an_unread_activation_restriction_refuses_and_says_so():
    """A restriction `condition_holds` cannot read answers None, and refusing
    with the restriction named is the fail-closed answer; allowing it would
    be a silent guess. Lagomos's "five or more creatures died this turn" was
    the pool's example until it became read
    (`test_activation_restriction_turn_history.py`); no pool printing prints
    an unread one any more, so the reader's own None is what is pinned, and
    Lagomos is now refused because its restriction is *not met*."""
    scenario = _gated(["Lagomos, Hand of Hatred"])
    lagomos = scenario.find("Lagomos, Hand of Hatred", Zone.BATTLEFIELD)

    assert scenario.game.condition_holds("alice", "the moon is full", lagomos) is None
    reason = scenario.why_cannot_activate(lagomos, 0)
    assert reason is not None
    assert "not met" in reason
