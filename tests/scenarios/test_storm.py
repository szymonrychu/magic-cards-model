"""Storm (CR 702.40a): "Storm" means "When you cast this spell, copy it for
each other spell that was cast before it this turn. If the spell has any
targets, you may choose new targets for the copies."

CR 702.40a is a triggered ability that functions on the stack (CR 603.1), so
the copying happens through the same keyword-generated-trigger machinery
`machines/keywords.py` already builds for cascade and prowess
(`_TRIGGER_EXPANSIONS`, `KEYWORD_TRIGGER_EFFECTS`) rather than a per-card
`EFFECTS` row - Grapeshot and Empty the Warrens share the same
`_storm_ability`/`_storm_effect` pair, keyed off the printed keyword line, not
the card name.

The count is the whole point of this file: "each *other* spell ... cast
before it" is every spell any player cast this turn (CR 707's copy of a
spell "isn't cast", so a storm spell's own copies never inflate a later
spell's count - `Game.spells_cast_this_turn` is what `Game.copy_spell`
deliberately does not touch), not only the storm spell's own controller's
own casts.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 702.40a, CR 702.40b, CR 707.10, CR 707.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grapeshot", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain"] * 8,
        )
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_grapeshot_with_no_prior_spells_deals_only_its_own_damage():
    """Storm count 0: Grapeshot is the first spell cast this turn, so it
    copies zero times and deals exactly 1 damage."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    life_before = bob.life

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Grapeshot", *sources, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert bob.life == life_before - 1


def test_storm_copies_once_per_spell_cast_before_it_this_turn():
    """Two Lightning Bolts cast first, then Grapeshot: storm count is 2, so
    Grapeshot's own trigger makes two copies and the original plus both
    copies each deal 1 damage - 3 total."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    life_before = bob.life

    (bolt_source_1,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source_1, targets=["bob"])
    (bolt_source_2,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source_2, targets=["bob"])

    grapeshot_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Grapeshot", *grapeshot_sources, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    # Two Lightning Bolts (3 each) plus Grapeshot's own 3 total copies
    # (1 each): 6 + 3 = 9.
    assert bob.life == life_before - 9


def test_storm_counts_a_spell_any_player_cast_this_turn():
    """CR 702.40a says "each other spell that was cast before it this
    turn" - not "you've cast" - so bob's own earlier spell counts toward
    alice's Grapeshot storm trigger too."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.pass_priority("alice")
    (bob_source,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", bob_source, username="bob", targets=["alice"])

    grapeshot_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Grapeshot", *grapeshot_sources, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    # Storm count 1 (bob's Bolt): the original Grapeshot plus one copy.
    assert bob.life == life_before - 2


def test_empty_the_warrens_creates_one_goblin_pair_per_copy():
    """Empty the Warrens has no target, so `offer_new_targets_for_copy` is a
    no-op for every copy - the storm count still governs how many times
    "create two 1/1 red Goblin creature tokens" runs."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Empty the Warrens", "Lightning Bolt"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (bolt_source,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source, targets=["bob"])

    warrens_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_onto_stack("Empty the Warrens", *warrens_sources)
    while scenario.game.stack:
        scenario.resolve_top()

    goblins = [
        state
        for state in scenario.game.battlefield
        if state.name == "Goblin Token" and state.controller == "alice"
    ]
    # Storm count 1 (the Bolt): the original casting plus one copy, two
    # tokens each - four Goblins total.
    assert len(goblins) == 4


def test_a_storm_copy_is_not_cast_and_does_not_inflate_a_later_storm_count():
    """CR 707.10: "a copy of a spell isn't cast." Grapeshot's own copies must
    not count toward Empty the Warrens' storm trigger later the same turn -
    only the *casts* (Grapeshot itself, once) do.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grapeshot", "Empty the Warrens"],
            battlefield=["Mountain"] * 10,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    grapeshot_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Grapeshot", *grapeshot_sources, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    warrens_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_onto_stack("Empty the Warrens", *warrens_sources)
    while scenario.game.stack:
        scenario.resolve_top()

    goblins = [
        state
        for state in scenario.game.battlefield
        if state.name == "Goblin Token" and state.controller == "alice"
    ]
    # Storm count for Empty the Warrens is 1 (only Grapeshot's own cast, not
    # its copies): the original casting plus one copy, two tokens each.
    assert len(goblins) == 4


def test_grapeshots_copies_go_to_the_graveyard_with_the_original():
    """A copy resolves and ceases to exist (CR 111.13) rather than lingering
    on the stack or anywhere else once its own effect runs."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (bolt_source,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source, targets=["bob"])

    grapeshot_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Grapeshot", *grapeshot_sources, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.stack == []
    original = scenario.find("Grapeshot", Zone.GRAVEYARD, "alice")
    assert original.zone is Zone.GRAVEYARD
