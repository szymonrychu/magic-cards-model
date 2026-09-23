"""Scenario: a static ability gated on the card types among cards "exiled
with" its own permanent (CR 607.2a).

Keen-Eyed Curator: "As long as there are four or more card types among cards
exiled with this creature, it gets +4/+4 and has trample.\n{1}: Exile target
card from a graveyard."

The two abilities are linked (CR 607.2a: "an ability printed on it that
refers either to 'the exiled cards' or to cards 'exiled with [this
object],'" and "the second ability refers only to cards in the exile zone
that were put there as a result of an instruction to exile them in the first
ability"). The count is CR 205.2a's card types, so an artifact creature
counts for two. CR 400.7 makes a Curator that left and came back "a new
object with no memory of, or relation to, its previous existence", so the
cards its earlier self exiled no longer count for it.

The pile read here shares its reader with Dragon's Rage Channeler's delirium
(`machines/layers._GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE`, widened to
"cards exiled with this `<type>`"); a card_search for "card types among cards
exiled with" on 2026-09-23 found no other printing carrying the linked-exile
half of the template, which is recorded in MEMORY.md.

CR numbers verified with `mise run rules:find` this session: 607.2a, 205.2a,
400.7, 613.4c, 613.1f.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState

from .harness import PlayedScenario, Scenario


def _board(*, graveyard: list[str], bob_graveyard: list[str] | None = None, **extra):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Keen-Eyed Curator", *["Forest"] * 6, *extra.pop("battlefield", [])],
            graveyard=graveyard,
            library=["Forest"] * 5,
            **extra,
        )
        .player("bob", graveyard=bob_graveyard or [], library=["Forest"] * 5)
        .build()
    )


def _exile_with(scenario: PlayedScenario, curator: CardState, card: CardState) -> None:
    """Activate the Curator's own "{1}: Exile target card from a graveyard."
    and let it resolve."""
    (forest, *_) = scenario.untapped_sources("Forest", username="alice")
    scenario.activate(curator, forest, targets=[card])
    scenario.pass_until_resolved()
    assert card.zone is Zone.EXILE


def _stats(scenario: PlayedScenario, curator: CardState) -> tuple[int, int, bool]:
    computed = scenario.game.characteristics_of(curator)
    return computed.power, computed.toughness, has_keyword(curator, "trample", scenario.game)


def test_three_card_types_is_below_the_threshold():
    scenario = _board(graveyard=["Lightning Bolt", "Forest", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    for name in ("Lightning Bolt", "Forest", "Grizzly Bears"):
        _exile_with(scenario, curator, scenario.find(name, Zone.GRAVEYARD, "alice"))

    assert _stats(scenario, curator) == (3, 3, False), "instant, land, creature: three types"


def test_an_artifact_creature_counts_as_two_card_types():
    """CR 205.2a: artifact and creature are two card types, so Ornithopter
    plus an instant plus a land is four."""
    scenario = _board(graveyard=["Lightning Bolt", "Forest", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    for name in ("Lightning Bolt", "Forest"):
        _exile_with(scenario, curator, scenario.find(name, Zone.GRAVEYARD, "alice"))
    assert _stats(scenario, curator) == (3, 3, False)

    _exile_with(scenario, curator, scenario.find("Ornithopter", Zone.GRAVEYARD, "alice"))

    assert _stats(scenario, curator) == (7, 7, True), "CR 613.4c +4/+4, CR 613.1f trample"


def test_cards_from_an_opponents_graveyard_count_too():
    """ "Exile target card from a graveyard" - any graveyard; the pile is
    whatever this creature exiled, whoever owns it."""
    scenario = _board(graveyard=["Lightning Bolt", "Forest"], bob_graveyard=["Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    for name in ("Lightning Bolt", "Forest"):
        _exile_with(scenario, curator, scenario.find(name, Zone.GRAVEYARD, "alice"))
    _exile_with(scenario, curator, scenario.find("Ornithopter", Zone.GRAVEYARD, "bob"))

    assert _stats(scenario, curator) == (7, 7, True)


def test_cards_in_exile_that_this_creature_did_not_exile_do_not_count():
    """CR 607.2a: the reader "refers only to cards in the exile zone that were
    put there as a result of" its own linked ability - four card types
    already sitting in exile mean nothing to it."""
    scenario = _board(
        graveyard=[], exile=["Lightning Bolt", "Forest", "Ornithopter", "Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")

    assert len(scenario.game.exile) == 4
    assert _stats(scenario, curator) == (3, 3, False)


def test_another_curators_pile_is_its_own():
    """Two Curators: each one's pile is linked to that object alone."""
    scenario = _board(
        graveyard=["Lightning Bolt", "Forest", "Ornithopter"],
        battlefield=["Keen-Eyed Curator"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Keen-Eyed Curator", "Keen-Eyed Curator", username="alice")
    for name in ("Lightning Bolt", "Forest", "Ornithopter"):
        _exile_with(scenario, first, scenario.find(name, Zone.GRAVEYARD, "alice"))

    assert _stats(scenario, first) == (7, 7, True)
    assert _stats(scenario, second) == (3, 3, False)


def test_the_bonus_ends_when_the_count_drops_below_four():
    """Karn, the Great Creator's -2 takes the face-up Ornithopter back out of
    exile: the pile is down to an instant and a land, and the bonus stops the
    next time the board is computed (CR 613.5)."""
    scenario = _board(
        graveyard=["Lightning Bolt", "Forest", "Ornithopter"],
        battlefield=["Karn, the Great Creator"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    for name in ("Lightning Bolt", "Forest", "Ornithopter"):
        _exile_with(scenario, curator, scenario.find(name, Zone.GRAVEYARD, "alice"))
    assert _stats(scenario, curator) == (7, 7, True)

    karn = scenario.creature("Karn, the Great Creator", "alice")
    ornithopter = scenario.find("Ornithopter", Zone.EXILE, "alice")
    scenario.will_choose_cards(ornithopter, username="alice")
    scenario.activate(karn, index=1)
    scenario.pass_until_resolved()

    assert ornithopter.zone is Zone.HAND
    assert _stats(scenario, curator) == (3, 3, False)


def test_a_curator_that_left_and_returned_is_a_new_object():
    """CR 400.7: Ephemerate's flicker returns a new object. The four card
    types its earlier self exiled are still in exile, but none of them were
    exiled with *this* object."""
    scenario = _board(
        graveyard=["Lightning Bolt", "Forest", "Ornithopter"],
        hand=["Ephemerate"],
        battlefield=["Plains"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    for name in ("Lightning Bolt", "Forest", "Ornithopter"):
        _exile_with(scenario, curator, scenario.find(name, Zone.GRAVEYARD, "alice"))
    assert _stats(scenario, curator) == (7, 7, True)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Ephemerate", plains, username="alice", targets=[curator])

    returned = scenario.creature("Keen-Eyed Curator", "alice")
    assert returned.zone is Zone.BATTLEFIELD
    assert {card.name for card in scenario.game.exile} >= {
        "Lightning Bolt",
        "Forest",
        "Ornithopter",
    }
    assert _stats(scenario, returned) == (3, 3, False)
