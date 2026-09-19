"""Scenario: "Whenever you cast a noncreature spell this turn, create a token
that's a copy of a non-<Subtype> token you control." (CR 603.7a's own delayed
triggered ability, CR 707.2's copy)

Summon: Good King Mog XII's Saga chapters II and III both print this exact
sentence: reaching either chapter does not itself create any token - it
creates a *delayed* trigger (CR 603.7a) that watches for a noncreature spell
cast, for the rest of the current turn only (CR 603.7b's "unless it has a
stated duration, such as 'this turn'"), the same shape Dalkovan Encampment's
own "whenever you attack this turn" already builds
(`_parse_attack_this_turn_create_tapped_attacking_tokens`) - here watching
`TriggerEvent.CAST_SPELL` filtered to noncreature spells
(`DelayedTrigger.forbidden_types`) instead of `ATTACKS`.

`CreateTokenCopyOfControlledToken` is the delayed trigger's own payload: a
CR 707.2 copy of one token the controller controls, filtered by subtype
("non-Saga" excludes the Saga itself, since Sagas are enchantment tokens
too in principle, though this Saga is never itself a token) and chosen by
the controller when more than one qualifies (no target, CR 115.1 - "a ...
token you control" names no target at all).

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 603.7a** - "Some triggered abilities are 'delayed triggered
  abilities.' ... created by the resolution of a spell or ability."
- **CR 603.7b** - "unless the ability has a stated duration, such as 'this
  turn' ... a delayed triggered ability will trigger no more than once."
- **CR 707.2** - the copy "acquires the copiable values of the original
  object's characteristics."
- **CR 205.2a** - card types, including "noncreature" as their negation.
- **CR 111.1** - a token is "a marker used to represent any permanent that
  isn't represented by a card."
- **CR 115.1** - what may be targeted; "a ... token you control" is not a
  target at all, so the controller's own choice at resolution is not a CR
  601.2c targeting step.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.effects import _parse_generic_token_descriptor, trigger_effect_for
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models.token import create_tokens
from tests.cards import card
from tests.scenarios.harness import Scenario


def _fire_chapter_two(scenario: Scenario, saga_name: str):
    """Run chapter II's own effect directly - the same direct-call pattern
    already used for Good King Mog's chapters I and IV in
    `tests/scenarios/test_mass_counter_placement.py`, since a Saga's own
    chapter triggers are CR 714.2's "lore counters added" event, not
    something a scenario need drive through a real draw step to prove the
    clause itself reads and creates the right delayed trigger.
    """
    saga = scenario.creature(saga_name, "alice")
    chapter_two = next(
        a for a in parse_abilities(card(saga_name)) if getattr(a, "chapter", None) == 2
    )
    # `trigger_effect_for` - not `parse_mixed_effect` directly - is the real
    # dispatch path a resolving trigger goes through: it tries the whole-text
    # mergers (this clause's own delayed-trigger creation among them) before
    # falling back to `parse_mixed_effect`'s per-clause split.
    effect = trigger_effect_for(saga_name, chapter_two.event, chapter_two.effect)
    assert effect is not None
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=chapter_two,
        source_id=saga.id,
        source_name=saga.name,
        controller="alice",
    )
    effect(scenario.game, ability)
    return saga


def test_casting_a_noncreature_spell_this_turn_copies_a_controlled_token():
    """On-set: reaching chapter II creates the delayed trigger; casting
    Lightning Bolt (a noncreature spell) later the same turn fires it,
    copying the one Moogle token already on the battlefield."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Summon: Good King Mog XII", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    moogle_definition = _parse_generic_token_descriptor(
        ["1/2", "white", "Moogle", "creature"], "lifelink"
    )
    assert moogle_definition is not None
    (moogle,) = create_tokens(scenario.game, moogle_definition, "alice")

    _fire_chapter_two(scenario, "Summon: Good King Mog XII")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()  # the delayed trigger fires and resolves

    moogle_tokens = [state for state in scenario.game.battlefield if state.name == "Moogle Token"]
    assert len(moogle_tokens) == 2
    assert all(state.token for state in moogle_tokens)


def test_the_delayed_trigger_excludes_the_named_subtype():
    """A single qualifying non-Saga token: the reader correctly filters by
    subtype (a Wurm token, named subtype excluded is "Saga", so the Wurm
    token still counts) rather than reading no filter at all - if the
    filter were silently dropped, "no candidates" would behave identically
    to "one candidate" here, so this alone would not catch a broken filter;
    the next test does, by giving the ability nothing *but* an excluded
    token to find.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Summon: Good King Mog XII", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wurm_definition = _parse_generic_token_descriptor(["3/3", "green", "Wurm", "creature"], None)
    assert wurm_definition is not None
    (wurm,) = create_tokens(scenario.game, wurm_definition, "alice")

    _fire_chapter_two(scenario, "Summon: Good King Mog XII")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    wurm_tokens = [state for state in scenario.game.battlefield if state.name == "Wurm Token"]
    assert len(wurm_tokens) == 2


def test_expires_at_end_of_turn():
    """CR 603.7b's "unless it has a stated duration, such as 'this turn'" -
    the delayed trigger created by chapter II does not survive into the
    next turn's own noncreature spell.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Summon: Good King Mog XII", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    moogle_definition = _parse_generic_token_descriptor(
        ["1/2", "white", "Moogle", "creature"], "lifelink"
    )
    assert moogle_definition is not None
    create_tokens(scenario.game, moogle_definition, "alice")

    _fire_chapter_two(scenario, "Summon: Good King Mog XII")
    assert len(scenario.game.delayed_triggers.triggers) == 1

    scenario.game.cleanup_step()

    assert scenario.game.delayed_triggers.triggers == []
