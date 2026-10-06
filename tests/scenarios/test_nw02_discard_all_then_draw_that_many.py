"""Scenario: "Discard all the cards in your hand, then draw that many cards."

Fateful Showdown: "Fateful Showdown deals damage to any target equal to the
number of cards in your hand. Discard all the cards in your hand, then draw
that many cards." The damage is read first (instruction order, CR 608.2c), off
the hand as it stands once the spell has left it for the stack; "that many" is
the number of cards actually discarded (CR 608.2c, CR 701.9a), so a hand of
three draws three, and an empty hand draws none.

Shattered Perception (a sorcery) and Soratami Seer (an activated ability) print
the same sentence on their own, which is the off-set proof that the reader is
the template and not the one card.

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step

from .harness import Scenario

_LIBRARY = ["Forest", "Island", "Swamp", "Plains", "Mountain", "Forest", "Island", "Swamp"]


def _showdown_board(hand_extra, library=_LIBRARY):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fateful Showdown", *hand_extra],
            library=list(library),
            battlefield=["Mountain"] * 4,
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )


def _hand_names(scenario):
    return sorted(card.name for card in scenario.player("alice").hand)


def test_fateful_showdown_damages_for_the_hand_then_discards_and_draws_that_many():
    scenario = _showdown_board(["Grizzly Bears", "Memnite", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Fateful Showdown", auto=True, targets=[dreadmaw])

    assert dreadmaw.damage == 3
    graveyard = sorted(card.name for card in scenario.player("alice").graveyard)
    assert graveyard == ["Fateful Showdown", "Grizzly Bears", "Lightning Bolt", "Memnite"]
    assert _hand_names(scenario) == ["Forest", "Island", "Swamp"]
    assert len(scenario.player("alice").library) == len(_LIBRARY) - 3


def test_the_damage_is_the_hand_size_before_the_discard():
    """Read in printed order: the cards are still in hand when the damage is
    counted, so discarding them afterwards does not make it zero."""
    scenario = _showdown_board(["Grizzly Bears", "Memnite"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Fateful Showdown", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 18


def test_an_empty_hand_deals_nothing_and_draws_nothing():
    scenario = _showdown_board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Fateful Showdown", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 20
    assert len(scenario.player("alice").hand) == 0
    assert len(scenario.player("alice").library) == len(_LIBRARY)


def test_the_spell_itself_is_not_in_the_hand_it_counts_or_discards():
    scenario = _showdown_board(["Memnite"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Fateful Showdown", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 19
    assert len(scenario.player("alice").hand) == 1


def test_a_short_library_still_discards_the_whole_hand_first():
    """The discard happens in full before any draw is attempted; a library with
    fewer cards than were discarded does not shorten it."""
    scenario = _showdown_board(["Memnite", "Grizzly Bears"], library=["Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Fateful Showdown", auto=True, targets=["bob"])

    graveyard = sorted(card.name for card in scenario.player("alice").graveyard)
    assert graveyard == ["Fateful Showdown", "Grizzly Bears", "Memnite"]
    assert scenario.player("bob").life == 18


# --------------------------------------------------------------------------
# Off-set proofs
# --------------------------------------------------------------------------


def test_shattered_perception_discards_the_hand_and_draws_that_many():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shattered Perception", "Grizzly Bears", "Memnite", "Lightning Bolt"],
            library=list(_LIBRARY),
            battlefield=["Mountain"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Shattered Perception", auto=True)

    assert _hand_names(scenario) == ["Forest", "Island", "Swamp"]
    assert sorted(card.name for card in scenario.player("alice").graveyard) == [
        "Grizzly Bears",
        "Lightning Bolt",
        "Memnite",
        "Shattered Perception",
    ]


def test_shattered_perception_with_nothing_else_in_hand_draws_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shattered Perception"],
            library=list(_LIBRARY),
            battlefield=["Mountain"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Shattered Perception", auto=True)

    assert len(scenario.player("alice").hand) == 0
    assert len(scenario.player("alice").library) == len(_LIBRARY)


def test_heartwarming_redemption_draws_one_more_than_it_discarded_then_gains_for_the_new_hand():
    """ "... then draw that many cards plus one. You gain life equal to the
    number of cards in your hand." - two discarded, three drawn, three gained."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Heartwarming Redemption", "Grizzly Bears", "Memnite"],
            library=list(_LIBRARY),
            battlefield=["Mountain", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life = scenario.player("alice").life

    scenario.cast_and_resolve("Heartwarming Redemption", auto=True)

    assert _hand_names(scenario) == ["Forest", "Island", "Swamp"]
    assert scenario.player("alice").life == life + 3


def test_soratami_seer_discards_the_hand_returned_lands_included_and_draws_that_many():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Memnite"],
            library=list(_LIBRARY),
            battlefield=["Soratami Seer"] + ["Island"] * 4 + ["Forest"] * 2,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Soratami Seer", "alice")

    scenario.activate(seer, auto=True)
    scenario.resolve_top()

    # Two lands came back to hand as the cost, so the hand held four cards.
    assert _hand_names(scenario) == sorted(_LIBRARY[:4])
    assert len(scenario.player("alice").graveyard) == 4
