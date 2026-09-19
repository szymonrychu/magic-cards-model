"""Ojer Pakpatiq, Deepest Epoch's own "Whenever you cast an instant spell
from your hand, it gains rebound." (CR 702.88, CR 702.88a) - rebound granted
*by another card* rather than printed on the spell itself.

`CardState.granted_rebound` and `machines.keywords.has_rebound_now` exist
for exactly this: both places that used to ask `has_rebound(spell.card)`
alone (`machines/replacement._stack_replacements`'s exile-instead-of-
graveyard swap, `Game._create_rebound_delayed_trigger`'s own guard) now also
honour a rebound granted this way (CR 614.12: a granted static ability
"functions" the same as a printed one for as long as it applies).

Lightning Bolt (no printed rebound of its own) is the proof: cast from
alice's hand while Ojer Pakpatiq watches, it goes to exile instead of the
graveyard as it resolves - `test_rebound.py` already covers the recast half
of the mechanic (Ephemerate's own printed rebound), so this file only needs
to prove the *granting* half works, not re-derive the whole keyword.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_a_bolt_cast_while_ojer_pakpatiq_watches_is_exiled_not_binned():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Ojer Pakpatiq, Deepest Epoch"] + ["Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE
    assert bolt not in scenario.player("alice").graveyard


def test_a_sorcery_cast_while_ojer_pakpatiq_watches_is_not_granted_rebound():
    """ "An instant spell" - a sorcery cast the same way is unaffected, and
    goes to the graveyard as usual."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Assault Strobe"],
            battlefield=["Ojer Pakpatiq, Deepest Epoch"] + ["Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bears = scenario.creature("Grizzly Bears", "bob")

    strobe = scenario.cast_and_resolve("Assault Strobe", mountain, targets=[bears])

    assert strobe.zone is Zone.GRAVEYARD
    assert strobe.granted_rebound is False
