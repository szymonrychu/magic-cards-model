""" "This land becomes a copy of target X [until end of turn]." (CR 706, CR
707.2) - The Mycosynth Gardens (indefinite, a permanent on the battlefield)
and Shifting Woodland (until end of turn, a card in the graveyard).

`docs/engine-coverage.md` used to list "Entering as a copy" as entirely
unbuilt, because `CardState` had no copiable values at all. This file is the
first wave that builds real copy machinery: a Layer 1 (CR 613.1a) continuous
effect that overwrites a permanent's *computed* characteristics - name, mana
value, types, subtypes, supertypes, colors, ability text, power/toughness -
with a snapshot of the target's own printed values, taken once as the
ability resolves.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 707.2** - "When copying an object, the copy acquires the copiable
  values of the original object's characteristics" - name, mana cost,
  color, color indicator, card type, subtype, supertype, rules text,
  power, and toughness (CR 707.2a fills in that color and abilities are
  themselves *derived from* mana cost/color indicator and rules text).
- **CR 707.4** - "Some effects cause a permanent that's copying a permanent
  to copy a different object while remaining on the battlefield. The change
  doesn't cause enters-the-battlefield or leaves-the-battlefield abilities
  to trigger." This is exactly "becomes a copy" - the permanent stays on the
  battlefield throughout, distinct from CR 614.1c's "enters as a copy".
- **CR 707.2b** - "Once an object has been copied, changing the copiable
  values of the original object won't cause the copy to change" - the
  snapshot-at-resolution design this file's `_become_a_copy_builder` uses.
- **CR 611.1/611.2a** - a continuous effect lasts "for a fixed or indefinite
  period", and a resolution effect that states no duration lasts
  indefinitely - The Mycosynth Gardens' own clause, with no "until end of
  turn", against Shifting Woodland's, which has one.
- **CR 207.2c** - *Delirium* is an ability word with no rules meaning of its
  own; the whole gate is Shifting Woodland's own printed sentence, "Activate
  only if there are four or more card types among cards in your graveyard."
- **CR 205.2a, CR 300.1** - the fifteen card types *delirium*'s own count is
  over, the same count `Unholy Heat`'s and `Violent Urge`'s delirium already
  use (`machines/layers.count_card_types`).

- **CR 613.5** - "The application of continuous effects as described by the
  layer system is continually and automatically performed by the game. All
  resulting changes to an object's characteristics are instantaneous." That
  is why the last test below can tap the copy for the *copied* object's mana
  ability: `Game.activated_abilities` reads the computed ability text through
  `machines/triggers.rewritten_ability_lines`, not the printed `Card`.
- **CR 605.3b** - a mana ability "doesn't use the stack ... it resolves
  immediately", so the copied `{T}: Add {C}{C}` is observable only in the
  pool.

**Remaining gap**: `machines/cost.py`'s own mana-source lookup still calls
`parse_mana_abilities(source.card, ...)` on the printed card, so a copy used
as a *payment* source (rather than activated directly) still offers its
printed mana ability. See `docs/engine-coverage.md`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from tests.scenarios.harness import Scenario


def test_mycosynth_gardens_becomes_a_copy_of_a_nontoken_artifact_you_control():
    """{X}, {T} with X=1, targeting a Sol Ring (mana value 1): the land's
    own computed characteristics become Sol Ring's - name, type, and rules
    text included - CR 707.2's own list of copiable values."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Mycosynth Gardens", "Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardens = scenario.find("The Mycosynth Gardens", Zone.BATTLEFIELD)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(gardens, forest, index=2, targets=[sol_ring], x_value=1)
    scenario.resolve_top()

    characteristics = scenario.game.characteristics_of(gardens)
    assert characteristics.name == "Sol Ring"
    assert characteristics.types == (Type.ARTIFACT,)
    assert "{T}: Add {C}{C}." in characteristics.abilities
    assert characteristics.mana_value == 1


def test_the_copy_is_indefinite_and_survives_the_turn():
    """No "until end of turn" on The Mycosynth Gardens' own clause - CR
    611.2a's default for a stated-no-duration resolution effect - so the
    copy is still Sol Ring after cleanup, unlike Shifting Woodland's own
    time-boxed version below."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Mycosynth Gardens", "Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardens = scenario.find("The Mycosynth Gardens", Zone.BATTLEFIELD)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(gardens, forest, index=2, targets=[sol_ring], x_value=1)
    scenario.resolve_top()

    scenario.game.continuous_effects.end_the_turn()

    assert scenario.game.characteristics_of(gardens).name == "Sol Ring"


def test_shifting_woodland_needs_delirium_to_activate_at_all():
    """ "Activate only if there are four or more card types among cards in
    your graveyard" (CR 602.5b) - with an empty graveyard, the activation is
    refused before the ability ever resolves."""
    scenario = Scenario().player("alice", battlefield=["Shifting Woodland", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    woodland = scenario.find("Shifting Woodland", Zone.BATTLEFIELD)

    reason = scenario.why_cannot_activate(woodland, 1)

    assert reason is not None
    assert "602.5b" in reason


def test_shifting_woodland_becomes_a_copy_of_a_graveyard_permanent_until_end_of_turn():
    """With delirium active (four card types in the graveyard: artifact,
    creature, land, instant) Shifting Woodland copies a permanent *card*
    sitting in the graveyard - Sol Ring - rather than one on the
    battlefield, and CR 611.2a's stated "until end of turn" makes the copy
    temporary."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shifting Woodland", "Forest", "Forest", "Forest", "Forest"],
            graveyard=["Sol Ring", "Grizzly Bears", "Lightning Bolt", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    woodland = scenario.find("Shifting Woodland", Zone.BATTLEFIELD)
    sol_ring = scenario.find("Sol Ring", Zone.GRAVEYARD)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    reason = scenario.why_cannot_activate(woodland, 1)
    assert reason is None, "delirium: artifact/creature/land/instant in the graveyard"

    scenario.activate(woodland, *forests, index=1, targets=[sol_ring])
    scenario.resolve_top()

    characteristics = scenario.game.characteristics_of(woodland)
    assert characteristics.name == "Sol Ring"
    assert characteristics.types == (Type.ARTIFACT,)

    scenario.game.continuous_effects.end_the_turn()

    reverted = scenario.game.characteristics_of(woodland)
    assert reverted.name == "Shifting Woodland"
    assert reverted.types == (Type.LAND,)


def test_the_copy_can_be_tapped_for_the_copied_permanents_own_mana_ability():
    """CR 613.5 has the layer system's changes to an object's characteristics
    apply instantly, and CR 707.2 puts the copied object's rules text (and so,
    by CR 707.2a, its abilities) among the copiable values acquired. The land is
    therefore tapped for Sol Ring's own `{T}: Add {C}{C}`, not for its own mana
    ability - the ability list `Game.activated_abilities` offers is read off the
    *computed* characteristics, not off the printed card."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Mycosynth Gardens", "Forest", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardens = scenario.find("The Mycosynth Gardens", Zone.BATTLEFIELD)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(gardens, forest, index=2, targets=[sol_ring], x_value=1)
    scenario.resolve_top()

    (ability,) = scenario.game.activated_abilities(gardens)
    assert ability.text == "{T}: Add {C}{C}."

    # CR 605.3b: a mana ability resolves immediately and never uses the stack,
    # so the pool is the whole of the observable result.
    assert scenario.game.activate_ability(gardens, 0) is None
    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS) == 2
    assert gardens.tapped
