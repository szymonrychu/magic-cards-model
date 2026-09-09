"""Meld (CR 701.42, CR 712.4-712.21): two cards becoming one permanent.

Every CR number below was looked up with `mise run rules:find` against the
2026-08-19 Comprehensive Rules in the session that wrote this file.

- **CR 701.42a** - "Meld is a keyword action that appears in an ability on
  one card in a meld pair. To meld the two cards in a meld pair, put them
  onto the battlefield with their back faces up and combined. The resulting
  permanent is a single object represented by two cards."
- **CR 701.42b/c** - only the two cards of a real meld pair can be melded;
  an effect that instructs melding objects that can't be melded leaves them
  where they are.
- **CR 712.5b** - Hanweir Garrison and Hanweir Battlements meld to form
  Hanweir, the Writhing Township (the deck-pool pair). **CR 712.5a** -
  Midnight Scavengers and Graf Rats meld to form Chittering Host (the
  generality pair - a *triggered*, not activated, meld ability, added with
  `scripts/add_card.py`).
- **CR 712.8g** - "While the two cards of a meld pair are on the battlefield
  as a melded permanent, the object represented by those cards has only the
  characteristics of the combined back face, and its mana value is the sum
  of the mana values of its front faces."
- **CR 712.21/712.21a/712.21b/712.21e** - "If a melded permanent leaves the
  battlefield, one permanent leaves the battlefield and two cards are put
  into the appropriate zone" - one object for the purposes of a trigger
  counting objects, two cards for the purposes of one counting cards.

The brief this closes guessed CR 712.8g for the leaves-the-battlefield rule;
712.8g is actually the characteristics rule, and CR 712.21 is the one that
governs leaving - both looked up fresh in this session, not trusted from
that guess.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_melding_forms_one_permanent_with_the_combined_back_faces_characteristics():
    """CR 701.42a/712.14c/712.8g, driven through Hanweir Battlements' own
    activated ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Hanweir Battlements",
                "Hanweir Garrison",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlements = scenario.creature("Hanweir Battlements")
    sources = scenario.untapped_sources(*(["Mountain"] * 5))
    battlefield_before = len(scenario.game.battlefield)

    scenario.activate(battlements, *sources, index=2)
    scenario.resolve_top()

    assert len(scenario.game.battlefield) == battlefield_before - 1
    melded = scenario.creature("Hanweir, the Writhing Township")
    assert melded.id == battlements.id
    assert melded.zone is Zone.BATTLEFIELD
    assert melded.power == 7
    assert melded.toughness == 4
    assert set(melded.keywords) == {"Trample", "Haste"}
    assert melded.mana_value == 3.0
    assert melded.name == "Hanweir, the Writhing Township"
    assert "legendary" in [s.value for s in melded.supertypes]
    assert scenario.game.melded_pairs.get(melded.id) is not None
    partner = scenario.game.melded_pairs[melded.id]
    assert partner.name == "Hanweir Garrison"
    assert partner not in scenario.game.battlefield
    assert not any(state.name == "Hanweir Garrison" for state in scenario.game.battlefield)


def test_melding_reverts_after_a_replay_round_trip_and_stays_one_permanent():
    """The round-trip/replay invariant (`tests/scenarios/conftest.py`) already
    proves every scenario replays byte-identically - this test's own point is
    that the melded state (`meld_result`, `melded_partner_id`, `Game.
    melded_pairs`) is exactly what a decode has to reproduce for that to be
    true at all, so a defect here would show up as this test's own assertions
    failing, not only as the harness's generic check."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Hanweir Battlements",
                "Hanweir Garrison",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlements = scenario.creature("Hanweir Battlements")
    sources = scenario.untapped_sources(*(["Mountain"] * 5))

    scenario.activate(battlements, *sources, index=2)
    scenario.resolve_top()

    melded = scenario.creature("Hanweir, the Writhing Township")
    assert melded.power == 7 and melded.toughness == 4


def test_only_one_half_present_the_ability_does_nothing():
    """CR 701.42c: "If an effect instructs a player to meld objects that
    can't be melded, they stay in their current zone." """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Hanweir Battlements",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlements = scenario.creature("Hanweir Battlements")
    sources = scenario.untapped_sources(*(["Mountain"] * 5))
    battlefield_before = len(scenario.game.battlefield)

    scenario.activate(battlements, *sources, index=2)
    scenario.resolve_top()

    assert len(scenario.game.battlefield) == battlefield_before
    assert battlements.zone is Zone.BATTLEFIELD
    assert battlements.meld_result is None
    assert battlements.name == "Hanweir Battlements"


def test_a_melded_permanent_dying_puts_both_cards_in_the_graveyard():
    """CR 712.21: "one permanent leaves the battlefield and two cards are
    put into the appropriate zone." """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Hanweir Battlements",
                "Hanweir Garrison",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlements = scenario.creature("Hanweir Battlements")
    sources = scenario.untapped_sources(*(["Mountain"] * 5))
    scenario.activate(battlements, *sources, index=2)
    scenario.resolve_top()
    melded = scenario.creature("Hanweir, the Writhing Township")
    alice = scenario.player("alice")

    scenario.game.put_into_graveyard(melded)

    assert melded.zone is Zone.GRAVEYARD
    assert melded.meld_result is None
    assert melded.name == "Hanweir Battlements"
    names_in_graveyard = sorted(state.name for state in alice.graveyard)
    assert names_in_graveyard == ["Hanweir Battlements", "Hanweir Garrison"]
    assert scenario.game.melded_pairs == {}
    assert not any(
        state.name == "Hanweir, the Writhing Township" for state in scenario.game.battlefield
    )


def test_a_melded_permanent_exiled_puts_both_cards_in_exile():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Hanweir Battlements",
                "Hanweir Garrison",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlements = scenario.creature("Hanweir Battlements")
    sources = scenario.untapped_sources(*(["Mountain"] * 5))
    scenario.activate(battlements, *sources, index=2)
    scenario.resolve_top()
    melded = scenario.creature("Hanweir, the Writhing Township")

    scenario.game.exile_permanent(melded)

    assert melded.zone is Zone.EXILE
    names_in_exile = sorted(state.name for state in scenario.game.exile)
    assert names_in_exile == ["Hanweir Battlements", "Hanweir Garrison"]
    assert scenario.game.melded_pairs == {}


# -- generality: a second meld pair, melded through a triggered ability -----


def test_chittering_host_a_triggered_meld_ability_and_a_different_pair():
    """Midnight Scavengers/Graf Rats meld into Chittering Host (CR 712.5a) -
    a completely different pair from the deck-pool one, melded through Graf
    Rats' own *triggered* ability ("At the beginning of combat on your turn,
    if you both own and control ..."), not an activated one, proving
    `machines/meld.py`'s shared clause parser reads both shapes.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Midnight Scavengers", "Graf Rats"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlefield_before = len(scenario.game.battlefield)

    scenario.advance()  # into Step.BEGINNING_OF_COMBAT, putting the trigger on the stack
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.resolve_top()

    assert len(scenario.game.battlefield) == battlefield_before - 1
    melded = scenario.creature("Chittering Host")
    assert melded.power == 5
    assert melded.toughness == 6
    assert set(melded.keywords) == {"Haste", "Menace"}
    assert melded.mana_value == 7.0
    partner = scenario.game.melded_pairs[melded.id]
    assert partner.name in ("Midnight Scavengers", "Graf Rats")
