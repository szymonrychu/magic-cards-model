"""Scenario: Wear // Tear - a split card (CR 709), and choosing which half to
cast (CR 709.3).

Casting the card with no face chosen already reads as its front half, Wear
("Destroy target artifact.") - `Casting.base_cost` already special-cases a
split card's combined `"{1}{R} // {W}"` mana cost to the first face's own
cost, and `CardState.up_face` falls back to the front face the same way it
does for every other layout, so this half worked before this wave touched
anything.

Casting the *back* half, Tear ("Destroy target enchantment."), needed CR
709.3's actual choice: `Casting.cast_as_split_half` names which face, records
it onto `CardState.face_played` once the spell is cast (CR 709.3b: "while on
the stack, only the characteristics of the half being cast exist"), and
`Casting.targeting` reads that face's own printed text for CR 601.2c's
target requirement instead of the combined text `targeting_profile(card)`
would otherwise fall back to.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 709.2** - "Although split cards have two castable halves, each split
  card is only one card."
- **CR 709.3** - "A player chooses which half of a split card they are
  casting before putting it onto the stack."
- **CR 709.3a** - "Only the chosen half is evaluated to see if it can be
  cast. Only that half is considered to be put onto the stack."
- **CR 709.3b** - "While on the stack, only the characteristics of the half
  being cast exist. The other half's characteristics are treated as though
  they didn't exist."
- **CR 702.102a/702.102d** - Fuse: casting both halves as one spell,
  resolving the left half's instructions and then the right half's. Not
  modelled by this engine (its own reminder line is stripped, not read).
- **CR 701.8a** - "To destroy a permanent, move it from the battlefield to
  its owner's graveyard."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_casting_the_front_half_plain_destroys_an_artifact():
    """No face chosen at all - the ordinary, pre-existing path - still reads
    as Wear, the front half, and costs only {1}{R}.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    _to_main(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    wear = scenario.find("Wear", Zone.HAND, "alice")
    assert wear.name == "Wear"

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Wear", *sources, targets=[ring])

    assert ring.zone is Zone.GRAVEYARD


def test_casting_the_back_half_destroys_an_enchantment_for_one_white():
    """CR 709.3: choosing Tear reads Tear's own {W} cost and Tear's own
    "target enchantment" restriction - not Wear's {1}{R} or Wear's
    "target artifact".
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Plains"])
        .player("bob", battlefield=["Rancor"])
        .build()
    )
    _to_main(scenario)
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Wear")
    casting.cast_as_split_half("Tear")
    casting.choose_targets([rancor])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{W}"
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert rancor.zone is Zone.GRAVEYARD


def test_the_back_half_cannot_target_an_artifact():
    """Tear's own printed restriction is "target enchantment" - an artifact
    is not a legal target for it, even though it would have been for Wear.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Plains"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    _to_main(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Wear")
    casting.cast_as_split_half("Tear")

    with pytest.raises(ValueError):
        casting.choose_targets([ring])


def test_the_front_half_cannot_target_an_enchantment():
    """The mirror case: Wear's own restriction is "target artifact" - an
    enchantment is illegal for it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Rancor"])
        .build()
    )
    _to_main(scenario)
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Wear")

    with pytest.raises(ValueError):
        casting.choose_targets([rancor])


def test_a_resolved_split_card_is_read_as_the_whole_card_again_in_the_graveyard():
    """CR 709.2: off the stack, a split card is "only one card" again - once
    Tear resolves and the card is in the graveyard, `CardState.name` goes
    back to reading the front face the way every other layout's graveyard
    card already does, not "stuck" on whichever half was last cast.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wear // Tear"], battlefield=["Plains"])
        .player("bob", battlefield=["Rancor"])
        .build()
    )
    _to_main(scenario)
    rancor = scenario.find("Rancor", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Wear")
    casting.cast_as_split_half("Tear")
    casting.choose_targets([rancor])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    spell = scenario.put_on_stack(casting)
    assert spell.name == "Tear", (
        "CR 709.3b: only the cast half's characteristics exist on the stack"
    )

    scenario.resolve_top()

    graveyard_card = scenario.find("Wear", Zone.GRAVEYARD, "alice")
    assert graveyard_card is spell
    assert graveyard_card.name == "Wear", "back to the front face once off the stack"
