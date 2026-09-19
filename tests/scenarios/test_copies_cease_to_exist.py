"""CR 704.5e's first sentence, as a state-based action: "If a copy of a spell
is in a zone other than the stack, it ceases to exist."

Two independent proofs, on purpose: Enroot (a CR 722.3c prepare-spell copy,
this stream's own reported gap) and Alania, Divergent Storm's copy of
Lightning Bolt (an unrelated mechanism, CR 707.10, already in the pool before
this fix existed) - the same state-based action has to catch both, since
neither is special-cased by name.

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

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario

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
