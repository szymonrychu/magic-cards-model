"""Scenario: "target spell or `<permanent type>`" - a bare "spell" noun that
comes *first* in a two-item noun list (CR 112.1, CR 115.1).

Fatehold Charm's second mode reads "Return target spell or creature to its
owner's hand." `machines/targeting.py`'s `_read_phrase` already had
`TargetRequirement.or_any_spell` for the *opposite* order (Aang, Swift
Savior's "target creature or spell") - but the noun-reading loop decided
`zones` the moment it read the word "spell", before it had any way to know
whether more nouns followed. Read first, "spell" always took the `zones =
{Zone.STACK}` branch, which - unioned with `card_types = {CREATURE}` added by
the *second* noun - asked for an object that is simultaneously a creature
spell on the stack and nothing else, refusing every creature actually on the
battlefield. "spell or creature" collapsed to "creature spell".

Fixed by deferring the decision (`spell_seen`) until the whole noun list has
been read: two or more nouns get `or_any_spell` (whichever position "spell"
was in), and only a bare, single-item "target spell" keeps the old `zones =
{Zone.STACK}` reading.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import spell_profile_for_text
from magic_cards_model.models import Type, Zone

from .harness import Scenario


def test_fatehold_charms_mode_profile_keeps_the_battlefield_open():
    profile = spell_profile_for_text("Return target spell or creature to its owner's hand.")
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.card_types == {Type.CREATURE}
    assert requirement.or_any_spell
    assert Zone.BATTLEFIELD in requirement.zones
    assert Zone.STACK not in requirement.zones


def test_fatehold_charm_bounces_a_creature_on_the_battlefield():
    """The reported misread: mode two refused every creature already on the
    battlefield, because "spell or creature" collapsed to "creature spell"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fatehold Charm"], battlefield=["Plains", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Fatehold Charm", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND


def test_fatehold_charm_still_bounces_a_spell_on_the_stack():
    """`or_any_spell` still lets the other half of the disjunction through -
    the fix must not have narrowed the requirement to *only* creatures."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fatehold Charm", "Lightning Bolt"],
            battlefield=["Plains", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # alice casts her own Lightning Bolt and, keeping priority (CR 117.3c),
    # responds to it with Fatehold Charm - who controls the targeted spell is
    # irrelevant to CR 115.1's "target spell", so this sidesteps nothing.
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        username="alice",
        targets=["bob"],
    )

    casting = scenario.cast("Fatehold Charm", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND


def test_fatehold_charm_cannot_target_a_land():
    """`or_any_spell` widens what may be targeted; it must not widen past
    CR 115.1's own "spell or creature" - a land is neither."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fatehold Charm"], battlefield=["Plains", "Island"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Fatehold Charm", username="alice")
    casting.choose_modes([2])
    with pytest.raises(ValueError):
        casting.choose_targets([forest])


# -- off-set proof: a different card, no modes at all, the identical -------
# -- "spell or creature" sentence printed as the whole card ----------------


def test_unsubstantiate_bounces_a_creature_on_the_battlefield():
    """Unsubstantiate: "Return target spell or creature to its owner's
    hand." - the same sentence Fatehold Charm's mode prints, but as a plain
    single-clause instant rather than a modal charm, proving the fix is not
    an artifact of how modal targeting is read."""
    scenario = (
        Scenario()
        .player("alice", hand=["Unsubstantiate"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.cast_and_resolve("Unsubstantiate", *sources, targets=[bears])

    assert bears.zone is Zone.HAND
