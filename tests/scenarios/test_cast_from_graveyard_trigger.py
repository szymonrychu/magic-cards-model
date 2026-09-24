"""Abilities that trigger on casting a spell *from a graveyard*, and the
ability Rivaz of the Claw's trigger hands the spell.

- **Rivaz of the Claw** - "Whenever you cast a Dragon creature spell from your
  graveyard, it gains "When this creature dies, exile it.""
- **Secrets of the Dead** (second printing - Modern legal on Scryfall, in no
  deck list) - "Whenever you cast a spell from your graveyard, draw a card."

Both sit on the battlefield. "From your graveyard" in the trigger condition
says where the *spell* came from, not where the ability works: an ability
that names its own zone (CR 113.6b) is one whose *source* is described
there ("this card is in your graveyard"), and neither of these is.

No other legal printing grants a quoted ability to the spell whose casting
triggered it (Scryfall full-text search, recorded in MEMORY.md), so the grant
is proven on Rivaz with both a spell that should and one that should not
receive it.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 113.6b** - "An ability that states which zones it functions in
  functions only from those zones."
- **CR 603.2** - the ability triggers whenever the game event matches.
- **CR 400.7a** - "Effects from spells, activated abilities, and triggered
  abilities that change the characteristics or controller of a permanent
  spell on the stack continue to apply to the permanent that spell becomes."
- **CR 400.7** - once that permanent leaves the battlefield it is a new
  object; a card bounced and recast has nothing Rivaz gave the old one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_from_graveyard(scenario, card, caster="alice", *, targets=()):
    casting = Casting(spell=card, caster=caster, origin_zone=Zone.GRAVEYARD, game=scenario.game)
    casting.use_keyword(CAST_PERMISSION)
    if targets:
        casting.choose_targets(list(targets))
    scenario.auto_pay(casting.begin_paying(), username=caster)
    return scenario.put_on_stack(casting)


def _rivaz(*, hand=(), graveyard=("Slumbering Dragon",), extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Rivaz of the Claw", *extra] + ["Mountain"] * 5,
            graveyard=list(graveyard),
            library=["Mountain"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


EXILE_ON_DEATH = "When this creature dies, exile it."


def test_a_dragon_cast_from_the_graveyard_is_exiled_when_it_dies():
    scenario = _rivaz()
    dragon = scenario.find("Slumbering Dragon", Zone.GRAVEYARD, "alice")
    dragon = _cast_from_graveyard(scenario, dragon)
    _resolve_everything(scenario)
    assert dragon.zone is Zone.BATTLEFIELD
    assert EXILE_ON_DEATH in dragon.granted_ability_texts

    scenario.game.destroy(dragon)
    _resolve_everything(scenario)

    assert dragon.zone is Zone.EXILE


def test_a_dragon_cast_from_hand_gets_nothing_and_dies_to_the_graveyard():
    scenario = _rivaz(hand=("Slumbering Dragon",), graveyard=())
    dragon = scenario.cast_onto_stack("Slumbering Dragon", auto=True)
    _resolve_everything(scenario)
    assert EXILE_ON_DEATH not in dragon.granted_ability_texts

    scenario.game.destroy(dragon)
    _resolve_everything(scenario)

    assert dragon.zone is Zone.GRAVEYARD


def test_a_non_dragon_spell_cast_from_the_graveyard_does_not_trigger_rivaz():
    scenario = _rivaz(graveyard=("Lightning Bolt",), extra=("Kess, Dissident Mage",))
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _cast_from_graveyard(scenario, bolt, targets=[scenario.player("bob")])
    scenario.game.put_triggers_on_stack()
    assert [item.name for item in scenario.game.stack] == ["Lightning Bolt"]


def test_the_gained_ability_does_not_follow_the_card_to_a_new_object():
    """CR 400.7: bounced and recast from hand, the Dragon is a new object
    Rivaz never touched, so it dies to the graveyard."""
    scenario = _rivaz()
    dragon = scenario.find("Slumbering Dragon", Zone.GRAVEYARD, "alice")
    dragon = _cast_from_graveyard(scenario, dragon)
    _resolve_everything(scenario)
    scenario.game.return_to_hand(dragon)
    assert dragon.zone is Zone.HAND

    dragon = scenario.cast_onto_stack("Slumbering Dragon", auto=True)
    _resolve_everything(scenario)
    scenario.game.destroy(dragon)
    _resolve_everything(scenario)

    assert dragon.zone is Zone.GRAVEYARD


# -- Secrets of the Dead: the same condition, a different effect -----------


def _secrets(*, hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Secrets of the Dead", "Kess, Dissident Mage", "Mountain", "Mountain"],
            graveyard=["Lightning Bolt"],
            library=["Mountain"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_secrets_of_the_dead_draws_when_a_spell_is_cast_from_the_graveyard():
    scenario = _secrets()
    hand_before = len(scenario.player("alice").hand)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _cast_from_graveyard(scenario, bolt, targets=[scenario.player("bob")])
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_secrets_of_the_dead_ignores_a_spell_cast_from_hand():
    scenario = _secrets(hand=("Shock",))
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_onto_stack("Shock", auto=True, targets=[scenario.player("bob")])
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == hand_before - 1
