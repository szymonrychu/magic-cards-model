"""Past in Flames: "Each instant and sorcery card in your graveyard gains
flashback until end of turn. The flashback cost is equal to its mana cost."

The same CR 601.3 `PlayPermission` shape `test_flashback_grant.py` already
proves for "Flashback" (the spell) - `zone=Zone.GRAVEYARD`, `pays_mana_cost
=True` - generalised from one chosen target to every qualifying card. The
same documented gap applies here too: CR 702.34a's own "then exile it
instead" only fires off `CastRecord.keyword == "flashback"`, which a
`PlayPermission`-driven cast never sets, so a card recast this way returns
to the graveyard rather than being exiled - `test_the_recast_card_goes_to_
the_graveyard_not_exile` below makes that concrete rather than merely
claimed, mirroring `test_flashback_grant.py`'s own equivalent case.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 601.3, CR 702.34a, CR 400.7.
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


def test_the_recast_card_goes_to_the_graveyard_not_exile():
    """The documented deviation from CR 702.34a, made concrete rather than
    merely claimed - see this file's own header."""
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

    assert bolt.zone is Zone.GRAVEYARD, "not exiled - the known, documented gap"


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
