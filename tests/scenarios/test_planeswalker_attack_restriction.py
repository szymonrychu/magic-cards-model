""" "No more than one creature can attack `<subject>` each combat." (CR 508.1c)
- a defender-side attacker cap, granted by Tomik, Orzhov Lawmage to every
planeswalker its controller controls, and printed on The Eternal Wanderer
about itself.

Every CR number here was looked up with `mise run rules:find <number>`
against the checksum-verified 2026-09-25 Comprehensive Rules release in the
session that wrote this file.

- **CR 508.1c** - "The active player checks each creature they control to see
  whether it's affected by any restrictions ... If any restrictions are being
  disobeyed, the declaration of attackers is illegal." Unlike most of
  CR 508.1c's restrictions, which are a fact about the *attacker* (`machines/
  combat.attack_refusal`), this one is a fact about the *defender being
  attacked* - `Game._refuse_illegal_attacker_caps` reads it once over the
  whole declaration rather than once per creature, which is what makes it
  "no more than one creature *at this planeswalker*" rather than "no more
  than one attack total".
- **CR 113.10a** - the activation-instructions-travel-with-the-grant rule
  that also governs `test_planeswalker_ability_grants.py`; irrelevant to a
  restriction's *cost* (it has none) but still what makes Tomik's quoted
  sentence a real ability on the planeswalker it reaches rather than text
  that does nothing off Tomik's own card.

**Two sources for the identical restriction.** Tomik's own line never names a
planeswalker - "Planeswalkers you control have '...'" - so the restriction
`machines/combat.attacker_cap_restriction` finds is a *granted* one, read off
the defender's computed board and matched against the self-referential
"this planeswalker" the grant is worded with. The Eternal Wanderer prints the
identical sentence about itself instead - "No more than one creature can
attack The Eternal Wanderer each combat." - naming its own short name rather
than "this planeswalker". `attacker_cap_restriction` reads both shapes with
one regex, which is the generality this file proves: the restriction is not
special-cased to Tomik's card, only to the sentence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _two_attackers_one_defender(defenders_battlefield: list[str]) -> Scenario:
    """Alice has two ground creatures; bob has whatever `defenders_battlefield`
    names."""
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=defenders_battlefield)
    )


# --------------------------------------------------------------------------
# Tomik, Orzhov Lawmage - a granted restriction, read off "this planeswalker"
# --------------------------------------------------------------------------


def test_two_creatures_against_a_tomik_granted_planeswalker_is_illegal():
    scenario = _two_attackers_one_defender(
        ["Tomik, Orzhov Lawmage", "Jace, Reality Sculptor"]
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    jace = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.attack_with(bears, giant, defending=jace)

    assert scenario.attackers() == [], "CR 508.1: an illegal declaration taps and declares nothing"
    assert bears.untapped and giant.untapped


def test_one_creature_against_a_tomik_granted_planeswalker_is_legal():
    scenario = _two_attackers_one_defender(
        ["Tomik, Orzhov Lawmage", "Jace, Reality Sculptor"]
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    jace = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(bears, defending=jace)

    assert scenario.attackers() == [bears]


def test_the_cap_is_per_planeswalker_not_per_controller():
    """Corner case: Tomik's grant reaches every planeswalker its controller
    has, but CR 508.1c's restriction is judged once per *defender* - one
    creature at each of bob's two Tomik-granted planeswalkers is two legal,
    separate attacks, not "two creatures attacking Tomik's planeswalkers"."""
    scenario = _two_attackers_one_defender(
        ["Tomik, Orzhov Lawmage", "Jace, Reality Sculptor", "Ugin, Eye of the Storms"]
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    jace = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "bob")
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(bears, defending=jace)
    scenario.attack_with(giant, defending=ugin)

    attackers = scenario.attackers()
    assert len(attackers) == 2
    assert bears in attackers and giant in attackers


def test_two_creatures_against_a_plain_planeswalker_bob_also_controls_is_legal():
    """Negative control: without Tomik on the battlefield, Jace carries no
    such restriction at all, so two attackers against him is ordinary
    CR 508.1 - proving the illegal declarations above are Tomik's doing, not
    some other cap on attacking a planeswalker."""
    scenario = _two_attackers_one_defender(["Jace, Reality Sculptor"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    jace = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(bears, giant, defending=jace)

    attackers = scenario.attackers()
    assert len(attackers) == 2
    assert bears in attackers and giant in attackers


# --------------------------------------------------------------------------
# The Eternal Wanderer - the identical restriction, printed on itself
# --------------------------------------------------------------------------


def test_two_creatures_against_the_eternal_wanderer_is_illegal():
    """Off-set generality proof: the same regex that reads Tomik's grant also
    reads a planeswalker's *own* printed line, naming itself rather than
    "this planeswalker"."""
    scenario = _two_attackers_one_defender(["The Eternal Wanderer"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    wanderer = scenario.find("The Eternal Wanderer", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.attack_with(bears, giant, defending=wanderer)

    assert scenario.attackers() == []
    assert bears.untapped and giant.untapped


def test_one_creature_against_the_eternal_wanderer_is_legal():
    scenario = _two_attackers_one_defender(["The Eternal Wanderer"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    wanderer = scenario.find("The Eternal Wanderer", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(bears, defending=wanderer)

    assert scenario.attackers() == [bears]
