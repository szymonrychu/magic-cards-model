"""Scenario: a land whose own two activated abilities are linked (CR 607.2a,
CR 406.6) - the first exiles, the second reads "the exiled cards" or "exiled
with [this object]" back.

Northampton Farm: "{1}, {T}: Exile target creature you own. / {2}, {T},
Sacrifice this land: Return a creature card exiled with this land to the
battlefield under your control. Return each other card exiled with this
land to its owner's hand." Neither ability needed a card-specific reader:
`machines/effects.link_cards_exiled_during` already marks whatever the first
ability exiles as `ExileMarker.LINKED` to this land's own id and
`zone_change_stamp` the moment it notices the second ability's printed text
contains "exiled with" (`_LINKED_EXILE_READER_RE`) - the identical machinery
Skyclave Apparition's enters/leaves pair already uses. What is new
(`machines/linked_exile.py`) is reading the return pair itself: one
ability names a single characteristic ("a creature card") of what the other
exiled, and a second sweeps up whatever is left, in printed order.

`ability.source_stamp` (CR 400.7) is what makes the second ability still
find its own land's pile even after "Sacrifice this land" has already moved
the land to the graveyard as part of paying for the very ability that reads
it back.

Proof printing (Modern/Pioneer-legal, added with `scripts/add_card.py`, not
Northampton Farm and not in any deck list): **Endless Sands** - "{2}, {T}:
Exile target creature you control. / {4}, {T}, Sacrifice this land: Return
each creature card exiled with this land to the battlefield under its
owner's control." No second "sweep the rest to hand" sentence at all (there
is nothing else to name), "each" instead of "a" (every linked creature card
returns, not only the first), and "its owner's control" rather than "your
control" - proving `machines/linked_exile.py`'s reader reads the
quantifier and the controller phrase off the card rather than assuming
Northampton Farm's own wording.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 607.2a (the linked-ability rule, quoted in
`machines/effects.link_cards_exiled_during`'s own docstring), 607.3 ("the
exiled card" answers for each of several linked cards), 400.7 (a moved
object is new; `zone_change_stamp` is what tells one incarnation of this
land from another), 701.21a (sacrifice moves a permanent straight to its
owner's graveyard - no destruction, so indestructible would not have
mattered here either), 111.8 (a token that already left the battlefield is
not read back).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

FARM = "Northampton Farm"
ENDLESS_SANDS = "Endless Sands"


def test_listed_and_proof_printings_are_handled():
    for name in (FARM, ENDLESS_SANDS):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _farm_board(**extra):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[FARM, "Grizzly Bears", "Hill Giant"] + ["Plains"] * 4,
            library=["Plains"] * 10,
            **extra,
        )
        .player("bob", library=["Plains"] * 10)
        .build()
    )


def _to_alices_next_untap(scenario):
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.advance()  # untap -> upkeep: the land is untapped now


def test_exiling_a_creature_links_it_to_the_land():
    scenario = _farm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farm = scenario.find(FARM, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.activate(farm, plains, index=1, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE


def test_the_return_ability_brings_the_creature_back_under_the_activators_control():
    scenario = _farm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farm = scenario.find(FARM, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.activate(farm, plains[0], index=1, targets=[bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    _to_alices_next_untap(scenario)
    scenario.activate(farm, *plains[1:3], index=2, sacrificing=[farm])
    scenario.pass_until_resolved()

    returned = scenario.creature("Grizzly Bears", "alice")
    assert returned.zone is Zone.BATTLEFIELD
    assert farm.zone is Zone.GRAVEYARD, "sacrificed as part of the cost"


def test_a_second_exiled_creature_goes_to_hand_as_each_other_card():
    """Two activations of the exile ability (across a turn boundary, so the
    land can untap between them) link two creatures to the same land; the
    return ability brings back only the first-exiled creature card and sends
    the rest to hand."""
    scenario = _farm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farm = scenario.find(FARM, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.activate(farm, plains[0], index=1, targets=[bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    _to_alices_next_untap(scenario)  # the land can only tap once per turn

    scenario.activate(farm, plains[1], index=1, targets=[giant])
    scenario.pass_until_resolved()
    assert giant.zone is Zone.EXILE

    _to_alices_next_untap(scenario)
    scenario.activate(farm, *plains[2:4], index=2, sacrificing=[farm])
    scenario.pass_until_resolved()

    battlefield_names = [c.name for c in scenario.game.battlefield if c.controller == "alice"]
    hand_names = [c.name for c in scenario.player("alice").hand]
    assert "Grizzly Bears" in battlefield_names, "the first linked creature returns to the field"
    assert "Hill Giant" in hand_names, "the second linked card sweeps to hand instead"
    assert "Hill Giant" not in battlefield_names


def test_a_creature_exiled_by_something_else_is_not_read_back():
    """CR 607.2a: only a card *this land's own ability* exiled is "exiled
    with" it - a creature some unrelated effect happened to exile is not
    part of its pile, linked or not."""
    scenario = _farm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farm = scenario.find(FARM, Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant")
    scenario.game.exile_permanent(giant)  # exiled by no ability of the land's at all
    plains = scenario.untapped_sources("Plains", "Plains")

    scenario.activate(farm, *plains, index=2, sacrificing=[farm])
    scenario.pass_until_resolved()

    assert giant.zone is Zone.EXILE, "never linked to the land, so never read back"


# -- proof printing: Endless Sands' own "each" quantifier, no sweep sentence -


def test_endless_sands_returns_every_linked_creature_card_under_its_owner():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ENDLESS_SANDS, "Grizzly Bears", "Hill Giant"] + ["Plains"] * 8,
            library=["Plains"] * 10,
        )
        .player("bob", library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sands = scenario.find(ENDLESS_SANDS, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    plains = scenario.untapped_sources(*["Plains"] * 8)
    scenario.activate(sands, plains[0], plains[1], index=1, targets=[bears])
    scenario.pass_until_resolved()

    _to_alices_next_untap(scenario)  # the land can only tap once per turn

    scenario.activate(sands, plains[2], plains[3], index=1, targets=[giant])
    scenario.pass_until_resolved()

    _to_alices_next_untap(scenario)
    scenario.activate(sands, *plains[4:8], index=2, sacrificing=[sands])
    scenario.pass_until_resolved()

    battlefield_names = sorted(c.name for c in scenario.game.battlefield if c.controller == "alice")
    assert "Grizzly Bears" in battlefield_names and "Hill Giant" in battlefield_names
