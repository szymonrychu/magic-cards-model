"""Past in Flames: "Each instant and sorcery card in your graveyard gains
flashback until end of turn. The flashback cost is equal to its mana cost."

The same CR 601.3 `PlayPermission` shape `test_flashback_grant.py` already
proves for "Flashback" (the spell) - `zone=Zone.GRAVEYARD`, `pays_mana_cost
=True` - generalised from one chosen target to every qualifying card.
CR 702.34a's own "then exile it instead" fires here too, the same way
`test_flashback_grant.py` proves it does for a single granted target:
`PlayPermission.flashback` marks the grant, and `Casting.cast()` writes
`CastRecord.keyword = "Flashback"` from it even though no keyword line was
announced, which is what `machines/replacement.py`'s exile check reads.
`test_the_recast_card_is_exiled_not_returned_to_the_graveyard` below proves
it for Past in Flames specifically.

`test_faithful_mending_under_a_live_permission_still_costs_its_mana_cost`
is the must-still-work case the flashback zone-permission fix (see
`test_flashback.py`) depends on: a card sitting in the graveyard with a live
Past in Flames permission must keep costing `{W}{U}` (the permission's own
`pays_mana_cost=True`, CR 118.9c's mana cost untouched) rather than being
auto-upgraded to Faithful Mending's own printed Flashback `{1}{W}{U}` -
CR 601.2b makes the choice of which permission to use a previously made
choice the player announces, and CR 118.9a allows only one alternative cost
per spell, which presupposes a choice rather than a guess.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 601.3, CR 702.34a, CR 400.7, CR 611.3d,
CR 601.2b, CR 118.9a, CR 118.9c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_every_instant_and_sorcery_in_the_graveyard_gets_a_permission():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Lightning Bolt", "Pyretic Ritual"],
            battlefield=["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    ritual = scenario.find("Pyretic Ritual", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *sources)

    for card in (bolt, ritual):
        permission = scenario.game.play_permission_for(card, "alice", PlayAction.CAST)
        assert permission is not None
        assert permission.pays_mana_cost is True
        assert permission.zone is Zone.GRAVEYARD


def test_permanents_and_an_opponents_cards_in_the_graveyard_are_untouched():
    """ "Instant and sorcery card in your graveyard" - a creature card, and a
    card in the opponent's graveyard, both get nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob", graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    bob_bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *sources)

    assert scenario.game.play_permission_for(alice_bears, "alice", PlayAction.CAST) is None
    assert scenario.game.play_permission_for(bob_bolt, "bob", PlayAction.CAST) is None


def test_the_permission_actually_lets_the_card_be_recast():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain"] * 5,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    flames_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *flames_sources)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK


def test_the_recast_card_is_exiled_not_returned_to_the_graveyard():
    """CR 702.34a's second static ability applies to Past in Flames' granted
    flashback exactly as it does to a printed one - see this file's own
    header."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain"] * 5,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    flames_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *flames_sources)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE


def test_faithful_mending_under_a_live_permission_still_costs_its_mana_cost():
    """The must-still-work counterexample for the flashback zone-permission
    fix (`test_flashback.py`): Faithful Mending sitting in the graveyard
    under a live Past in Flames permission must keep costing its own mana
    cost `{W}{U}` (`permission.pays_mana_cost is True`) - not be silently
    upgraded to its own printed Flashback `{1}{W}{U}` just because that
    keyword also exists. CR 601.2b's announcement is a choice, and CR 118.9a
    allows only one alternative cost per spell; auto-selecting the dearer of
    the two would overrule a legal, cheaper choice the player is entitled to
    make.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Faithful Mending"],
            battlefield=["Mountain"] * 4 + ["Plains", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    flames_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *flames_sources)

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    casting.use_permission()

    assert str(casting.total_cost) == "{W}{U}"


def test_with_no_instants_or_sorceries_in_the_graveyard_nothing_is_granted():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Past in Flames"],
            graveyard=["Grizzly Bears"],
            battlefield=["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Past in Flames", *sources)

    assert scenario.game.play_permissions == []
