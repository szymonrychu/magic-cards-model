"""Scenario: FRA S9's Aura statics - animating a non-creature permanent, and
a "doesn't untap" grant read at the untap step itself.

`machines/layers.py` had no reader for either shape before this file:

- **Puppet Crafting** (Reality Fracture), "Enchanted permanent is a Construct
  creature with base power and toughness 5/5 in addition to its other
  types." - `_attached_creature_loses_and_becomes_builder`'s twin with no
  "loses all abilities" and a bare "permanent" subject (the whole point is
  animating something that was not a creature). **Ensoul Artifact** and
  **Zoetic Glyph** (off-set, real cards: one with no subtype at all, one with
  a different subtype and a different base toughness) prove the shape reads
  the sentence, not "Construct" or "5/5".
- **Traxos, Scourge Eternal** (Reality Fracture), "Traxos doesn't untap
  during your untap step."; **Infinite Coursework** (Reality Fracture),
  "Enchanted creature loses all abilities and doesn't untap during its
  controller's untap step." - both grant the same canonical
  `DOESNT_UNTAP_TEXT`, read once, at the one place every route to untapping
  passes through (`Game._untap_step_impl`), the same way CR 122.1d's stun
  counter already is. **Basalt Monolith** (off-set, a real noncreature
  artifact with the identical self-only sentence) and **Enchanted River's
  Grasp** (off-set, a real Aura with the identical combined sentence) prove
  both shapes generalise past their FRA cards.

The rules these rest on:

- **CR 205.1b** - "in addition to" keeps every card type a permanent already
  had, which is the whole difference between animating a permanent and
  replacing it.
- **CR 613.1d** (layer 4, the card type and the optional subtype) and
  **CR 613.4b** (sublayer 7b, the *set* of base power and toughness, ahead of
  any 7c modifier regardless of which was created first).
- **CR 613.1f** (layer 6) for the ability loss Infinite Coursework and
  Enchanted River's Grasp print and for the "doesn't untap" grant itself,
  read as ordinary ability text - not a keyword, not a replacement effect
  stored elsewhere - so `Game._untap_step_impl` asks the computed board the
  same way `has_keyword` already does for defender.
- **CR 502.3** - the untap step untaps everything the active player controls
  "simultaneously"; the filter here removes a permanent from that batch
  before it runs, the same way CR 122.1d's stun-counter replacement removes
  one counter instead of skipping the whole step.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice", **kwargs):
    return card_state(
        name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller, **kwargs
    )


def board_of(*permanents):
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# --------------------------------------------------------------------------
# "Enchanted permanent is a Construct creature with base power and
# toughness 5/5 in addition to its other types." (Puppet Crafting)
# --------------------------------------------------------------------------


def test_puppet_crafting_animates_a_noncreature_artifact():
    crafting = permanent("Puppet Crafting")
    ring = permanent("Sol Ring")
    crafting.attach_to(ring)

    board = board_of(crafting, ring)
    chars = board.of(ring)
    assert Type.CREATURE in chars.types
    assert Type.ARTIFACT in chars.types, "CR 205.1b - the artifact type is not lost"
    assert "Construct" in chars.subtypes
    assert chars.power_toughness == (5, 5)


def test_puppet_crafting_keeps_the_permanents_other_abilities():
    """No "loses all abilities" in the sentence - Sol Ring's own mana ability
    must survive."""
    crafting = permanent("Puppet Crafting")
    ring = permanent("Sol Ring")
    crafting.attach_to(ring)

    board = board_of(crafting, ring)
    assert board.of(ring).has_ability("{T}: Add {C}{C}.")


def test_ensoul_artifact_animates_with_no_subtype_off_set():
    """Off-set proof: a real card, no Construct subtype at all."""
    ensoul = permanent("Ensoul Artifact")
    ring = permanent("Sol Ring")
    ensoul.attach_to(ring)

    board = board_of(ensoul, ring)
    chars = board.of(ring)
    assert Type.CREATURE in chars.types
    assert chars.subtypes == ()
    assert chars.power_toughness == (5, 5)


def test_zoetic_glyph_animates_with_a_different_subtype_and_toughness_off_set():
    """Off-set proof: a different subtype (Golem) and a different base
    toughness (5/4, not 5/5)."""
    glyph = permanent("Zoetic Glyph")
    ring = permanent("Sol Ring")
    glyph.attach_to(ring)

    board = board_of(glyph, ring)
    chars = board.of(ring)
    assert "Golem" in chars.subtypes
    assert chars.power_toughness == (5, 4)


def test_puppet_crafting_produces_nothing_while_unattached():
    crafting = permanent("Puppet Crafting")
    assert board_of(crafting).of(crafting).power_toughness == (None, None)


# --------------------------------------------------------------------------
# "Doesn't untap during its controller's untap step." (Traxos; Infinite
# Coursework)
# --------------------------------------------------------------------------


def test_traxos_does_not_untap_in_its_controllers_untap_step():
    scenario = (
        Scenario().player("alice", battlefield=["Traxos, Scourge Eternal"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    traxos = scenario.creature("Traxos, Scourge Eternal", "alice")
    traxos.tapped = True

    scenario.game.untap_step()

    assert traxos.tapped, "Traxos's own static grant kept it tapped through the untap step"


def test_basalt_monolith_does_not_untap_either_off_set():
    """Off-set proof: a real noncreature artifact with the identical
    self-only sentence."""
    scenario = Scenario().player("alice", battlefield=["Basalt Monolith"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    monolith = scenario.find("Basalt Monolith", Zone.BATTLEFIELD, "alice")
    monolith.tapped = True

    scenario.game.untap_step()

    assert monolith.tapped


def test_infinite_coursework_stops_the_enchanted_creature_untapping():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Infinite Coursework", "Serra Angel"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coursework = scenario.find("Infinite Coursework", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "alice")
    coursework.attach_to(angel)
    angel.tapped = True

    assert not scenario.game.characteristics_of(angel).has_ability("Flying"), (
        "loses all abilities - the printed flying line is gone too"
    )

    scenario.game.untap_step()

    assert angel.tapped


def test_enchanted_rivers_grasp_stops_untapping_too_off_set():
    """Off-set proof: a real Aura with the identical combined sentence."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Enchanted River's Grasp", "Serra Angel"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grasp = scenario.find("Enchanted River's Grasp", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "alice")
    grasp.attach_to(angel)
    angel.tapped = True

    scenario.game.untap_step()

    assert angel.tapped


def test_a_creature_with_no_such_grant_untaps_normally():
    """The control case: nothing here breaks the ordinary untap step for a
    creature with no "doesn't untap" text at all."""
    scenario = Scenario().player("alice", battlefield=["Serra Angel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    angel.tapped = True

    scenario.game.untap_step()

    assert not angel.tapped
