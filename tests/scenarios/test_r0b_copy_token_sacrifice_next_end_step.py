"""Scenario: "Create a token that's a copy of target `<X>`[, except `<...>`].
[It|That token] gains haste[ until end of turn]. (Sacrifice|Exile) it at the
beginning of the next end step." - `_CREATE_TOKEN_COPY_OF_TARGET_RE` widened
past its bare one-sentence form (`_parse_create_token_copy_of_target_clause`).

The Fire Crystal's own activated ability - "{4}{R}{R}, {T}: Create a token
that's a copy of target creature you control. Sacrifice it at the beginning
of the next end step." - used to read only its first sentence, the second
falling to a fail-closed notice. Every trailing sentence is about the token
just made (CR 608.2c), never the targeted original.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 707.2** - the copy acquires the copiable values of the original's
  characteristics; other effects, status and counters are not copied.
- **CR 707.9b** - "Some copy effects modify a characteristic as part of the
  copying process" (Molten Duplication's "except it's an artifact in addition
  to its other types").
- **CR 603.7a** - a delayed triggered ability is created during the
  resolution and won't trigger until it has actually been created.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it from the
  battlefield to its owner's graveyard.
- **CR 608.2b** - a target that left its zone is illegal on resolution; with
  every target illegal the ability does nothing.
- **CR 601.2f** - cost reductions apply when the total cost is determined.

Generality (target the template, not the card): Cogwork Assembler (exile, not
sacrifice; "That token gains haste."; a bare "target artifact" any player
controls) and Molten Duplication (a spell; CR 707.9b's added card type; "It
gains haste until end of turn.") both carry the widened shape in different
words, neither in any `magic-cards-model-api/decks/*.txt`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

CRYSTAL = "The Fire Crystal"


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _tokens_named(scenario, name):
    return [p for p in scenario.game.battlefield if p.token and p.name == name]


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _resolve_everything(scenario)
        scenario.advance()
    _resolve_everything(scenario)


def _crystal_board(*, alice=(), bob=(), hand=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[CRYSTAL, *["Mountain"] * 6, *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def _activate_crystal(scenario, target):
    crystal = scenario.find(CRYSTAL, Zone.BATTLEFIELD, "alice")
    return scenario.activate(
        crystal, *scenario.untapped_sources(*["Mountain"] * 6), targets=[target]
    )


# -- The Fire Crystal: the activated ability --------------------------------


def test_fire_crystal_copies_the_target_and_sacrifices_the_token_at_end_step():
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _activate_crystal(scenario, bears)
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    assert token.id != bears.id, "a new object (CR 707.2), not the original"
    assert (token.power, token.toughness) == (2, 2)
    assert scenario.game.controller_of(token).username == "alice"
    assert scenario.find(CRYSTAL, Zone.BATTLEFIELD, "alice").tapped

    _to_end_step(scenario)

    assert _tokens_named(scenario, "Grizzly Bears") == []
    assert bears.zone is Zone.BATTLEFIELD, "the token is sacrificed, never the original"


def test_fire_crystal_token_survives_until_the_end_step():
    """CR 603.7a: the delayed trigger waits for the next end step - combat
    and the second main phase leave the token alone."""
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _activate_crystal(scenario, bears)
    _resolve_everything(scenario)
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        _resolve_everything(scenario)
        scenario.advance()

    assert len(_tokens_named(scenario, "Grizzly Bears")) == 1


def test_fire_crystal_token_has_haste_from_the_crystal_and_attacks():
    """The copy entered this turn, but "Creatures you control have haste"."""
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _activate_crystal(scenario, bears)
    _resolve_everything(scenario)
    (token,) = _tokens_named(scenario, "Grizzly Bears")

    assert "Haste" in _chars(scenario, token).abilities
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.advance()
    scenario.attack_with(token)
    assert token in scenario.attackers()


def test_fire_crystal_token_gone_before_end_step_sacrifices_nothing_else():
    """The delayed trigger names the token (CR 603.7a); once that token has
    left the battlefield there is nothing for it to sacrifice - not the
    original, not another copy."""
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _activate_crystal(scenario, bears)
    _resolve_everything(scenario)
    (token,) = _tokens_named(scenario, "Grizzly Bears")
    scenario.game.destroy(token)
    _resolve_everything(scenario)

    _to_end_step(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find(CRYSTAL, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_fire_crystal_copies_a_token_original_too():
    """CR 707.2 via a token's stated characteristics: copying a copy."""
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _activate_crystal(scenario, bears)
    _resolve_everything(scenario)
    (first,) = _tokens_named(scenario, "Grizzly Bears")
    crystal = scenario.find(CRYSTAL, Zone.BATTLEFIELD, "alice")
    crystal.tapped = False
    for mountain in scenario.game.permanents_controlled_by("alice"):
        if mountain.name == "Mountain":
            mountain.tapped = False

    _activate_crystal(scenario, first)
    _resolve_everything(scenario)
    assert len(_tokens_named(scenario, "Grizzly Bears")) == 2

    _to_end_step(scenario)
    assert _tokens_named(scenario, "Grizzly Bears") == []
    assert bears.zone is Zone.BATTLEFIELD


def test_fire_crystal_target_gone_on_resolution_makes_no_token():
    """CR 608.2b: the only target is illegal, so the ability does nothing -
    no token, and so no delayed trigger either."""
    scenario = _crystal_board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _activate_crystal(scenario, bears)
    scenario.game.destroy(bears)
    _resolve_everything(scenario)

    assert [p for p in scenario.game.battlefield if p.token] == []
    assert scenario.game.delayed_triggers.triggers == []


def test_fire_crystal_cannot_target_an_opponents_creature():
    scenario = _crystal_board(bob=["Watchwolf"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError):
        _activate_crystal(scenario, wolf)
    assert _tokens_named(scenario, "Watchwolf") == []


# -- The Fire Crystal: its two static abilities -----------------------------


def test_fire_crystal_reduces_a_red_spells_generic_cost_by_one():
    """CR 601.2f: Bonecrusher Giant's {2}{R} is determined as {1}{R}."""
    scenario = _crystal_board(hand=["Bonecrusher Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_fire_crystal_never_reduces_coloured_mana():
    """Only generic mana is reduced: Lightning Bolt's {R} stays {R}."""
    scenario = _crystal_board(hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_fire_crystal_leaves_a_nonred_spell_at_full_cost():
    scenario = _crystal_board(hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    assert casting.total_cost.mana == ManaCost.parse("{1}{G}")


def test_fire_crystal_gives_a_freshly_entered_creature_haste():
    scenario = _crystal_board(hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert "Haste" in _chars(scenario, bears).abilities
    scenario.advance()
    scenario.advance()
    assert scenario.can_attack(bears)


def test_fire_crystal_does_not_give_an_opponents_creature_haste():
    scenario = _crystal_board(bob=["Watchwolf"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    assert "Haste" not in _chars(scenario, wolf).abilities


# -- Cogwork Assembler: exile, "That token gains haste.", any artifact ------


def _assembler_board(*, bob=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Cogwork Assembler", *["Mountain"] * 7],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_cogwork_assembler_copies_an_opponents_artifact_with_haste_then_exiles_it():
    scenario = _assembler_board(bob=["Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    assembler = scenario.find("Cogwork Assembler", Zone.BATTLEFIELD, "alice")

    scenario.activate(assembler, *scenario.untapped_sources(*["Mountain"] * 7), targets=[thopter])
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Ornithopter")
    assert scenario.game.controller_of(token).username == "alice"
    assert "Haste" in _chars(scenario, token).abilities

    _to_end_step(scenario)

    assert _tokens_named(scenario, "Ornithopter") == []
    assert token.zone is not Zone.GRAVEYARD, "exiled, not sacrificed"
    assert thopter.zone is Zone.BATTLEFIELD


# -- Molten Duplication: a spell, CR 707.9b's added type, haste until EOT ---


def _duplication_board(*battlefield):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Molten Duplication"],
            battlefield=["Mountain", "Mountain", *battlefield],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def test_molten_duplication_copies_a_creature_as_an_artifact_with_haste():
    scenario = _duplication_board("Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Molten Duplication")
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    chars = _chars(scenario, token)
    assert Type.ARTIFACT in chars.types and Type.CREATURE in chars.types
    assert Type.ARTIFACT not in _chars(scenario, bears).types
    assert "Haste" in chars.abilities

    _to_end_step(scenario)
    assert _tokens_named(scenario, "Grizzly Bears") == []
    assert bears.zone is Zone.BATTLEFIELD


def test_molten_duplication_copies_an_artifact_it_is_already_an_artifact():
    scenario = _duplication_board("Mind Stone")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Molten Duplication")
    casting.choose_targets([stone])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Mind Stone")
    assert _chars(scenario, token).types.count(Type.ARTIFACT) == 1

    _to_end_step(scenario)
    assert _tokens_named(scenario, "Mind Stone") == []
