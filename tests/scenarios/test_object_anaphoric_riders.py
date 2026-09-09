"""Scenario: a rider sentence whose subject or object is the *thing* the
previous sentence acted on - "It ...", "They ...", "... on it".

CR 608.2c names this shape in as many words: "In some cases, later text on the
card may modify the meaning of earlier text (for example, 'Destroy target
creature. It can't be regenerated' ...). Don't just apply effects step by step
without thinking in these cases - read the whole text and apply the rules of
English to the text."

`_ANAPHORIC_SUBJECT_RE` (`machines/effects.py`) read only **player** anaphors -
"its controller", "that player" - so an *object* anaphor reached no parser at
all, the clause failed, and CR 608.2c's fail-closed guard correctly threw away
the readable half with it. Silently, and that silence is the defect: measured
before this file existed, both halves parse alone and the pair does not.

    Tap target creature.                                -> parses
    Put two stun counters on target creature.           -> parses
    Tap target creature. Put two stun counters on it.   -> None

Every CR number below was read out of the Comprehensive Rules on disk this
session with `mise run rules:find <number>`:

- **CR 608.2c** - the rule above, and the reason the rider is one instruction
  with its antecedent rather than two independent ones.
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence." What "it"
  refers to is the object as the antecedent found it, and a referent that has
  since changed zones is not that object any more.
- **CR 400.7j** - "If an effect causes an object to move to a public zone,
  other parts of that effect can find that object" - the one exception, and
  none of this wave's riders needs it: every one of them acts on a permanent
  that is still on the battlefield.
- **CR 608.2b** - "If all its targets ... are now illegal, the spell or
  ability doesn't resolve." An antecedent whose only target is gone takes the
  rider with it; the rider is never a second target of its own.
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen." "Up to one target creature" choosing none leaves the
  rider nothing to refer back to, and must **not** fall back to the ability's
  own source.
- **CR 122.1d** - "One or more stun counters on a permanent create a single
  replacement effect that stops the permanent from untapping. That effect is
  'If a permanent with a stun counter on it would become untapped, instead
  remove a stun counter from it.'"
- **CR 701.19a/701.19c** - regeneration is a replacement effect protecting a
  permanent "the next time it would be destroyed this turn", and "Effects that
  say that a permanent can't be regenerated ... cause regeneration shields to
  not be applied."
- **CR 613.4c** - +1/+1 counters apply in sublayer 7c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

STUN = "stun"


# -- Kaito's -2: the worked reproduction ------------------------------------


def test_kaitos_minus_two_taps_and_places_both_stun_counters():
    """`-2: Tap target creature. Put two stun counters on it.`

    "It" is the creature the first sentence tapped. Both halves run, and the
    count is two - a rider that placed one, or that placed them on the wrong
    object, would pass a test that only asserted "some counters exist".
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kaito, Bane of Nightmares"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD)

    scenario.activate(kaito, index=2, targets=[first])
    scenario.pass_until_resolved()

    assert first.tapped
    assert first.counters[STUN] == 2
    # The other Bears is untouched: "it" is one object, not "each creature".
    assert not second.tapped
    assert second.counters[STUN] == 0


def test_a_stun_counter_replaces_the_untap_instead_of_untapping():
    """CR 122.1d, which is what makes the counters mean anything at all: the
    stunned creature does not untap during its controller's untap step, and
    one counter is removed instead. Two counters, two untap steps skipped.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kaito, Bane of Nightmares"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD)
    scenario.activate(kaito, index=2, targets=[bears])
    scenario.pass_until_resolved()
    assert bears.tapped
    assert bears.counters[STUN] == 2

    bears.untap()
    assert bears.tapped
    assert bears.counters[STUN] == 1

    bears.untap()
    assert bears.tapped
    assert bears.counters[STUN] == 0

    bears.untap()
    assert not bears.tapped


def test_kaitos_minus_two_does_nothing_when_its_only_target_is_gone():
    """Danger 4, the referent-gone case, in its real form. CR 608.2b: the
    rider is never a target of its own, so when the antecedent's only target
    has left the battlefield the *whole* ability is removed from the stack -
    no tap, and no stun counters placed on some other object as a fallback.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kaito, Bane of Nightmares"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target, bystander = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD)
    scenario.activate(kaito, index=2, targets=[target])

    # The target leaves the battlefield with the ability still on the stack.
    scenario.game.put_into_graveyard(target)
    scenario.pass_until_resolved()

    assert target.zone is Zone.GRAVEYARD
    assert target.counters[STUN] == 0
    assert not bystander.tapped
    assert bystander.counters[STUN] == 0


# -- The Wandering Emperor: danger 3, the layer-effect trap ----------------


def test_the_wandering_emperor_places_the_counter_and_grants_first_strike():
    """`+1: Put a +1/+1 counter on up to one target creature. It gains first
    strike until end of turn.`

    The trap this pins down: `_is_layer_effect_text` is an any-sentence test
    over the whole ability, so widening the layer parser's *subject* to accept
    "It" would route the entire ability to `create_continuous_effect_of_
    ability` - first strike granted, the +1/+1 counter never placed, and the
    card scored HANDLED. Both halves have to happen.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Wandering Emperor", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    emperor = scenario.find("The Wandering Emperor", Zone.BATTLEFIELD)

    scenario.activate(emperor, index=0, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.power_of(bears) == 3  # CR 613.4c
    assert has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)


def test_the_wandering_emperor_with_zero_targets_touches_nothing():
    """CR 115.6: "up to one target creature" may legally choose none. Neither
    half runs, and in particular the ability does **not** fall back to its own
    source - the exact bug Karn, the Great Creator's +1 had, where an empty
    target list animated Karn himself.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Wandering Emperor", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    emperor = scenario.find("The Wandering Emperor", Zone.BATTLEFIELD)

    scenario.activate(emperor, index=0, targets=[])
    scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 0
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)
    assert not has_keyword(emperor, Keyword.FIRST_STRIKE, scenario.game)


# -- Wrath of God: the rider that modifies its antecedent ------------------


def _regenerated_bears(sweeper: str, lands: list[str]) -> Scenario:
    """Bob regenerates his own Grizzly Bears with Asceticism's `{1}{G}`, so a
    real CR 701.19a shield is standing when Alice's sweeper resolves."""
    scenario = (
        Scenario()
        .player("alice", hand=[sweeper], battlefield=lands)
        .player("bob", battlefield=["Asceticism", "Grizzly Bears", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    asceticism = scenario.find("Asceticism", Zone.BATTLEFIELD)
    scenario.pass_priority()
    scenario.activate(
        asceticism,
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        index=0,
        targets=[bears],
        username="bob",
    )
    scenario.pass_until_resolved()
    return scenario


def test_regeneration_replaces_an_ordinary_destruction():
    """The control for the two tests below: without a "can't be regenerated"
    rider the shield does exactly what CR 701.19a says - the creature is not
    destroyed, damage is removed, and its controller taps it.
    """
    scenario = _regenerated_bears("Supreme Verdict", ["Plains", "Plains", "Plains", "Island"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Supreme Verdict", *scenario.untapped_sources("Plains", "Plains", "Plains", "Island")
    )

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.tapped


def test_wrath_of_god_beats_a_regeneration_shield():
    """`Destroy all creatures. They can't be regenerated.`

    CR 701.19c: "Effects that say that a permanent can't be regenerated don't
    preclude such abilities from being activated ...; rather, they cause
    regeneration shields to not be applied." The shield is standing and the
    Bears die anyway.

    This is also the sharpest form of the referent question: "They" are the
    creatures the *same sentence* is destroying, so the rider modifies the
    destruction rather than running after it (CR 608.2c's own worked example).
    """
    scenario = _regenerated_bears("Wrath of God", ["Plains"] * 4)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Wrath of God", *scenario.untapped_sources(*["Plains"] * 4))

    assert bears.zone is Zone.GRAVEYARD


def test_wrath_of_god_destroys_everything_with_no_shield_in_sight():
    """The plain case, and the one that was silent: with the rider unreadable
    the whole card did nothing at all - not "destroyed everything and forgot
    the regeneration clause", but a four-mana sorcery that resolved and left
    the board exactly as it was.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wrath of God"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")

    scenario.cast_and_resolve("Wrath of God", *scenario.untapped_sources(*["Plains"] * 4))

    assert first.zone is Zone.GRAVEYARD
    assert second.zone is Zone.GRAVEYARD
