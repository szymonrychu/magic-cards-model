""" "The next spell you cast this turn can't be countered." (CR 603.7's
delayed-trigger shape, the same one `test_judge_copying.py`'s Flamehold
Grappler already exercises for "copy the next spell you cast this turn").

Theorist's Proxy is the reported card: "{U}, Sacrifice this creature: The
next spell you cast this turn can't be countered." Mistrise Village (Tarkir:
Dragonstorm) proves the same delayed-trigger shape is general - a land, a
different activation cost, a different set - not a card-specific reading.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_theorist_proxys_grant_protects_the_next_spell_from_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Theorist's Proxy", "Island", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proxy = scenario.creature("Theorist's Proxy", "alice")
    (blue,) = scenario.untapped_sources("Island", username="alice")

    scenario.activate(proxy, blue, sacrificing=[proxy])
    while scenario.game.stack:
        scenario.resolve_top()
    assert proxy.zone is Zone.GRAVEYARD

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    # The delayed trigger goes on the stack above the Bolt; letting it
    # resolve (nobody responds) is what grants the Bolt its protection
    # before anyone gets a chance to counter it.
    while scenario.game.stack and scenario.game.stack[-1] is not bolt:
        scenario.resolve_top()

    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[bolt])
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "the Bolt resolved, not countered"
    assert scenario.player("bob").life == 17


def test_mistrise_villages_grant_generalizes_the_shape_to_a_different_card():
    """Mistrise Village: "{U}, {T}: The next spell you cast this turn can't
    be countered." A land, a different cost shape (tap plus mana, no
    sacrifice), a different set - the same delayed-trigger reader."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mistrise Village", "Island", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    village = scenario.find("Mistrise Village", Zone.BATTLEFIELD, "alice")
    (blue,) = scenario.untapped_sources("Island", username="alice")

    scenario.activate(village, blue, index=1)
    while scenario.game.stack:
        scenario.resolve_top()

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    while scenario.game.stack and scenario.game.stack[-1] is not bolt:
        scenario.resolve_top()

    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[bolt])
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "the Bolt resolved, not countered"
    assert scenario.player("bob").life == 17


def test_a_spell_countered_before_the_delayed_trigger_resolves_is_not_protected():
    """The grant is applied when the delayed trigger *resolves*, not the
    instant the spell is cast - CopyNextSpellYouCast's own documented
    last-known-information race. A counter cast in response to the delayed
    trigger itself, before it resolves, still works: this is normal Magic,
    the same timing gap the existing copy-shape lives with."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Theorist's Proxy", "Island", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proxy = scenario.creature("Theorist's Proxy", "alice")
    (blue,) = scenario.untapped_sources("Island", username="alice")
    scenario.activate(proxy, blue, sacrificing=[proxy])
    while scenario.game.stack:
        scenario.resolve_top()

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    assert scenario.game.stack[-1] is not bolt, "the delayed trigger is above the Bolt"

    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[bolt])
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD  # countered, so it lands in the graveyard too
    assert scenario.player("bob").life == 20, "the Bolt never resolved"
