"""R0b proofs: plain removal and burn spells read straight off their text.

Day of Judgment ("Destroy all creatures."), Sear ("deals 4 damage to target
creature or planeswalker."), Vanishing Verse ("Exile target monocolored
permanent.") and Reckless Rage ("deals 4 damage to target creature you don't
control and 2 damage to target creature you control.") were all `handled` by
the generic templates and untested. Each ability is proved through the engine
here, corner cases first.

Every CR number below was looked up with `mise run rules:find`:

- **CR 702.12b** - indestructible permanents can't be destroyed.
- **CR 120.3c** - damage to a planeswalker causes that many loyalty counters
  to be removed from it.
- **CR 115.2** - only permanents are legal targets unless the text says so.
- **CR 601.2c** - a spell's targets are announced as it is cast.
- **CR 105.2a / 105.2b / 105.2c** - monocolored is exactly one color,
  multicolored two or more, colorless none.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _start(scenario: Scenario):
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


# -- Day of Judgment -----------------------------------------------------------------


def test_day_of_judgment_destroys_every_creature_on_both_sides():
    scenario = _start(
        Scenario()
        .player(
            "alice",
            hand=["Day of Judgment"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Grizzly Bears", "Mind Stone"],
        )
        .player("bob", battlefield=["Memnite", "Ornithopter"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")

    scenario.cast_and_resolve("Day of Judgment", *sources)

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.GRAVEYARD
    assert thopter.zone is Zone.GRAVEYARD
    assert stone.zone is Zone.BATTLEFIELD, "a noncreature artifact is not destroyed"


def test_day_of_judgment_leaves_an_indestructible_creature_standing():
    """CR 702.12b."""
    scenario = _start(
        Scenario()
        .player(
            "alice",
            hand=["Day of Judgment"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Blightsteel Colossus"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")

    scenario.cast_and_resolve("Day of Judgment", *sources)

    assert bears.zone is Zone.GRAVEYARD
    assert colossus.zone is Zone.BATTLEFIELD


def test_day_of_judgment_with_no_creatures_does_nothing_and_still_resolves():
    scenario = _start(
        Scenario()
        .player(
            "alice",
            hand=["Day of Judgment"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Mind Stone"],
        )
        .player("bob")
    )
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")

    spell = scenario.cast_and_resolve("Day of Judgment", *sources)

    assert spell.zone is Zone.GRAVEYARD


# -- Sear ----------------------------------------------------------------------------


def test_sear_deals_four_damage_to_a_creature():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Sear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Sear", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_sear_four_damage_does_not_kill_a_five_toughness_creature():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Sear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Blightsteel Colossus"])
    )
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Sear", *sources, targets=[colossus])

    assert colossus.zone is Zone.BATTLEFIELD
    assert colossus.damage == 4


def test_sear_removes_four_loyalty_from_a_planeswalker():
    """CR 120.3c: Liliana of the Veil starts at 3 loyalty, so four damage kills her."""
    scenario = _start(
        Scenario()
        .player("alice", hand=["Sear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Liliana of the Veil"])
    )
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    assert liliana.loyalty == 3

    scenario.cast_and_resolve("Sear", *sources, targets=[liliana])

    assert liliana.zone is Zone.GRAVEYARD


def test_sear_cannot_target_a_player():
    """CR 115.2 / CR 601.2c: "creature or planeswalker" excludes a player."""
    scenario = _start(
        Scenario()
        .player("alice", hand=["Sear"], battlefield=["Mountain", "Mountain"])
        .player("bob")
    )
    with pytest.raises(ValueError):
        scenario.cast("Sear", targets=["bob"])


def test_sear_cannot_target_a_noncreature_artifact():
    scenario = _start(
        Scenario()
        .player("alice", hand=["Sear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Mind Stone"])
    )
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError):
        scenario.cast("Sear", targets=[stone])


# -- Vanishing Verse -----------------------------------------------------------------


def _verse_board(**bob):
    return _start(
        Scenario()
        .player("alice", hand=["Vanishing Verse"], battlefield=["Plains", "Swamp"])
        .player("bob", **bob)
    )


def test_vanishing_verse_exiles_a_monocolored_creature():
    scenario = _verse_board(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Plains", "Swamp", username="alice")

    scenario.cast_and_resolve("Vanishing Verse", *sources, targets=[bears])

    assert bears.zone is Zone.EXILE


def test_vanishing_verse_exiles_a_monocolored_noncreature_permanent():
    """Any permanent, not only creatures: a white enchantment is monocolored."""
    scenario = _verse_board(battlefield=["Ghostly Prison"])
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Plains", "Swamp", username="alice")

    scenario.cast_and_resolve("Vanishing Verse", *sources, targets=[prison])

    assert prison.zone is Zone.EXILE


def test_vanishing_verse_refuses_a_colorless_permanent():
    """CR 105.2c: colorless is no color at all, so not monocolored (CR 105.2a)."""
    scenario = _verse_board(battlefield=["Ornithopter"])
    thopter = scenario.creature("Ornithopter", "bob")
    with pytest.raises(ValueError, match="monocolored"):
        scenario.cast("Vanishing Verse", targets=[thopter])


def test_vanishing_verse_refuses_a_land():
    scenario = _verse_board(battlefield=["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError, match="monocolored"):
        scenario.cast("Vanishing Verse", targets=[forest])


def test_vanishing_verse_refuses_a_multicolored_permanent():
    scenario = _verse_board(battlefield=["Kitchen Finks"])
    finks = scenario.creature("Kitchen Finks", "bob")
    with pytest.raises(ValueError, match="monocolored"):
        scenario.cast("Vanishing Verse", targets=[finks])


def test_vanishing_verse_can_exile_your_own_monocolored_permanent():
    scenario = _start(
        Scenario()
        .player(
            "alice",
            hand=["Vanishing Verse"],
            battlefield=["Plains", "Swamp", "Grizzly Bears"],
        )
        .player("bob")
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Swamp", username="alice")

    scenario.cast_and_resolve("Vanishing Verse", *sources, targets=[bears])

    assert bears.zone is Zone.EXILE


# -- Reckless Rage -------------------------------------------------------------------


def _rage_board(*, alice_creatures, bob_creatures):
    return _start(
        Scenario()
        .player(
            "alice",
            hand=["Reckless Rage"],
            battlefield=["Mountain", *alice_creatures],
        )
        .player("bob", battlefield=bob_creatures)
    )


def test_reckless_rage_deals_four_to_theirs_and_two_to_yours():
    scenario = _rage_board(
        alice_creatures=["Blightsteel Colossus"], bob_creatures=["Grizzly Bears"]
    )
    mine = scenario.creature("Blightsteel Colossus", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Reckless Rage", *sources, targets=[theirs, mine])

    assert theirs.zone is Zone.GRAVEYARD
    assert mine.zone is Zone.BATTLEFIELD
    assert mine.damage == 2


def test_reckless_rage_can_kill_both_when_yours_is_small():
    scenario = _rage_board(alice_creatures=["Memnite"], bob_creatures=["Grizzly Bears"])
    mine = scenario.creature("Memnite", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Reckless Rage", *sources, targets=[theirs, mine])

    assert theirs.zone is Zone.GRAVEYARD
    assert mine.zone is Zone.GRAVEYARD


def test_reckless_rage_is_illegal_when_you_control_no_creature():
    """Two targets are required (CR 601.2c); with no creature of your own the
    second is unavailable, so the spell cannot be cast."""
    scenario = _rage_board(alice_creatures=[], bob_creatures=["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Reckless Rage", targets=[theirs])


def test_reckless_rage_refuses_your_own_creature_as_the_first_target():
    scenario = _rage_board(alice_creatures=["Memnite", "Ornithopter"], bob_creatures=[])
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Reckless Rage", targets=[memnite, thopter])


def test_reckless_rage_refuses_their_creature_as_the_second_target():
    scenario = _rage_board(alice_creatures=["Memnite"], bob_creatures=["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Reckless Rage", targets=[theirs, theirs])
