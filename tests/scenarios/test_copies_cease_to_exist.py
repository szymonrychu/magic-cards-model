"""CR 704.5e / 707.10a, both sentences, as one state-based action: "If a copy
of a spell is in a zone other than the stack, it ceases to exist. If a copy
of a card is in any zone other than the stack or the battlefield, it ceases
to exist."

Three independent proofs, on purpose, none sharing a card or a mechanism with
either of the others: Enroot (a CR 722.3c prepare-spell copy, this stream's
own reported gap - **first sentence**, a copy that was cast and resolved),
Alania, Divergent Storm's copy of Lightning Bolt (CR 707.10, already in the
pool before this fix existed - **first sentence** again, off-mechanic), and
Isochron Scepter's own copy of its imprinted card, abandoned with its "cast
the copy?" question unanswered (**second sentence** - a copy that was never
cast at all, so it is only ever "a copy of a card", never "a copy of a
spell", and the ability's own hand-written cleanup for a *declined* cast
never runs to remove it by hand the way it normally would).

CR 707.10f/111.13 is the one carve-out: "Some effects copy a permanent spell.
As that copy resolves, it ceases being a copy of a spell and becomes a token
permanent" - so a copied *permanent* spell is never swept by this at all, it
simply stops being a copy the moment it resolves. `CardState.is_copy` is
cleared there for exactly that reason (`Game._resolve_top_impl`); a scenario
proving that half already exists (`test_alania_divergent_storm.py`'s copy of
an Otter, or `test_frontline_heroism.py`) and stays untouched by this file.

CR 722.3c's own exile copy is this rule's one *written* exception ("This is
an exception to rule 704.5e"), for as long as some battlefield permanent's
`prepared_copy_id` still names it - `tests/scenarios/test_prepare.py` already
covers that a fresh copy survives sitting in exile; this file is about what
happens once nothing exempts it any more.

Every CR number here was verified this session with `mise run rules:find`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionPending
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario

from .test_scepter_chant_deck import imprint, imprinted_scepter_board

# -- Enroot: a CR 722.3c prepare-spell copy -------------------------------


def test_enroots_own_copy_ceases_to_exist_instead_of_reaching_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Carnivorous Cultivator"],
            library=["Forest", "Island", "Mountain"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cultivator = scenario.cast_and_resolve(
        "Carnivorous Cultivator", *scenario.untapped_sources("Forest", "Forest")
    )
    copy = scenario.game.find_by_id(cultivator.prepared_copy_id)
    assert copy.name == "Enroot"
    assert copy.is_copy is True
    graveyard_before = len(scenario.player("alice").graveyard)

    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    graveyard = scenario.player("alice").graveyard
    lands = [state for state in graveyard if state.card.is_land]
    assert len(lands) == 1 and lands[0].name == "Forest", "the searched land landed"
    assert len(graveyard) == graveyard_before + 1, (
        "the copy of Enroot itself ceased to exist (CR 704.5e) rather than "
        "reaching the graveyard alongside the land it found"
    )
    assert not any(state.id == copy.id for state in scenario.game.exile)
    assert scenario.game.find_by_id(copy.id) is None, "gone from every zone, not just moved"


# -- off-mechanic: Alania, Divergent Storm's copy of Lightning Bolt --------


def _alania_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Alania, Divergent Storm"] + ["Mountain"] * 4,
        )
        .player("bob", life=20, library=["Forest"] * 10)
    )


def test_a_copied_instant_ceases_to_exist_instead_of_reaching_the_graveyard():
    """CR 707.10: a copy of a non-permanent spell has nowhere but a graveyard
    to go as it finishes resolving (CR 608.2h) - this is what stops it
    getting there, off a mechanism (Alania's CR 707.10c copy) that owes
    nothing to CR 722."""
    scenario = _alania_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm")
    scenario.choose_trigger_targets("Alania, Divergent Storm", ["bob"])
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    graveyard_before = len(scenario.player("alice").graveyard)

    while scenario.game.stack:
        scenario.resolve_top()
    scenario.state_based_actions()

    assert bolt.zone is Zone.GRAVEYARD, "the real Bolt still goes to its owner's graveyard"
    graveyard = scenario.player("alice").graveyard
    assert len(graveyard) == graveyard_before + 1, (
        "only the real Bolt reached the graveyard - its copy ceased to exist (CR 704.5e)"
    )
    assert all(state.id == bolt.id or not state.is_copy for state in graveyard)


# -- CR 704.5e's second sentence: a copy of a card, never cast -------------


def test_a_declined_scepter_copy_ceases_to_exist_even_when_the_declined_cleanup_never_runs():
    """Isochron Scepter's own "You may copy the exiled card. If you do, you
    may cast the copy without paying its mana cost." already removes a
    *declined* copy by hand (`machines/effects._parse_copy_exiled_card_and_
    cast`) - but only because nothing ever gives another player a priority
    window between the copy's creation and that second question, so the
    whole ability resolves as one atomic step. Pausing on the second
    question instead (`DecisionPending`, nothing scripted for it) leaves the
    ability's own Python frame suspended before it ever reaches that cleanup
    line, so the copy is left sitting in exile, genuinely uncleaned-up: only
    this state-based action removes it.
    """
    scenario = imprinted_scepter_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = imprint(scenario)
    scenario.game.decisions.pause_when_unanswered = True
    scenario.will_take_the_may(True, source="Isochron Scepter")  # only the first "may"

    scenario.activate(scepter, auto=True, username="alice")
    with pytest.raises(DecisionPending):
        scenario.resolve_top()

    copies = [state for state in scenario.game.exile if state.is_copy]
    assert len(copies) == 1, "the copy exists, mid-resolution, uncleaned-up"
    assert copies[0].name == "Orim's Chant"

    scenario.state_based_actions()

    assert not any(state.is_copy for state in scenario.game.exile), (
        "CR 704.5e's second sentence: a copy of a card outside the stack and "
        "the battlefield ceases to exist, whether or not it was ever cast"
    )
    imprinted = scenario.game.card_imprinted_on(scepter.id)
    assert imprinted is not None and imprinted.name == "Orim's Chant", (
        "the original imprinted card - not a copy - is untouched"
    )
