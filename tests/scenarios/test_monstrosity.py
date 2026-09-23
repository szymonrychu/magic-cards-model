"""Scenario: Monstrosity (CR 701.37a-c), a keyword action read generally off
an activated ability's own printed text, not pinned to one card.

CR 701.37a (verified with `mise run rules:find 701.37` in this session):
"'Monstrosity N' means 'If this permanent isn't monstrous, put N +1/+1
counters on it and it becomes monstrous.'"

CR 701.37b: "Monstrous is a designation that has no rules meaning other than
to act as a marker that the monstrosity action and other spells and abilities
can identify. Only permanents can be or become monstrous. Once a permanent
becomes monstrous, it stays monstrous until it leaves the battlefield.
Monstrous is neither an ability nor part of the permanent's copiable
values."

CR 701.37c: "If a permanent's ability instructs a player to 'monstrosity X,'
other abilities of that permanent may also refer to X. The value of X in
those abilities is equal to the value of X as that permanent became
monstrous."

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Polukranos, World Eater** (reported card): "{X}{X}{G}: Monstrosity X."
  plus "When Polukranos becomes monstrous, it deals X damage divided as you
  choose among any number of target creatures your opponents control. Each
  of those creatures deals damage equal to its power to Polukranos." - the
  activated X-cost action, CR 701.37c's own X plumbed to a second ability,
  and CR 601.2d divided damage combined with CR 701.14a's own retaliation.
- **Nessian Asp** (off-pool, proves the action generalises past the reported
  card): "{6}{G}: Monstrosity 4." with no trigger at all - a fixed N and a
  bare designation, nothing else.
- **Fleecemane Lion** (off-pool): "{3}{G}{W}: Monstrosity 1." plus "As long
  as this creature is monstrous, it has hexproof and indestructible." - the
  "as long as ... is monstrous" condition reader for statics.
- **Arbor Colossus** (off-pool): "{3}{G}{G}{G}: Monstrosity 3." plus "When
  this creature becomes monstrous, destroy target creature with flying an
  opponent controls." - a plain single-target trigger, no X involved.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

# --------------------------------------------------------------------------
# Nessian Asp - {6}{G}: Monstrosity 4. No trigger at all - the bare action.
# --------------------------------------------------------------------------


def test_nessian_asp_monstrosity_puts_counters_and_becomes_monstrous():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nessian Asp"] + ["Forest"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    asp = scenario.creature("Nessian Asp", "alice")
    assert asp.monstrous is False
    sources = scenario.untapped_sources(*(["Forest"] * 7), username="alice")

    scenario.activate(asp, *sources)
    scenario.pass_until_resolved()

    assert asp.monstrous is True
    assert asp.monstrous_x == 4
    assert asp.counter_count(Counter.PLUS_ONE) == 4
    assert scenario.game.power_of(asp) == 8  # printed 4/5, +4/+4
    assert scenario.game.toughness_of(asp) == 9


def test_nessian_asp_second_activation_adds_no_counters_and_does_not_trigger():
    """CR 701.37a's own second refusal: "a permanent can't gain this
    designation if the permanent already has it." The activation itself
    stays legal - CR 701.37a is the effect, not a cost - it simply does
    nothing the second time."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nessian Asp"] + ["Forest"] * 14)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    asp = scenario.creature("Nessian Asp", "alice")
    sources = scenario.untapped_sources(*(["Forest"] * 7), username="alice")
    scenario.activate(asp, *sources)
    scenario.pass_until_resolved()
    assert asp.counter_count(Counter.PLUS_ONE) == 4

    more_sources = scenario.untapped_sources(*(["Forest"] * 7), username="alice")
    ability = scenario.activate(asp, *more_sources)
    assert isinstance(ability, AbilityOnStack), "the activation itself is still legal"
    scenario.pass_until_resolved()

    assert asp.counter_count(Counter.PLUS_ONE) == 4, "no second set of counters"
    assert asp.monstrous is True
    assert asp.monstrous_x == 4, "the X it first became monstrous with is unchanged"
    assert scenario.game.stack_is_empty, "no second BECOMES_MONSTROUS trigger fired"


# --------------------------------------------------------------------------
# Fleecemane Lion - {3}{G}{W}: Monstrosity 1. "As long as this creature is
# monstrous, it has hexproof and indestructible." - the static condition.
# --------------------------------------------------------------------------


def test_fleecemane_lion_gains_hexproof_and_indestructible_once_monstrous():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fleecemane Lion", "Forest", "Forest", "Forest", "Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lion = scenario.creature("Fleecemane Lion", "alice")
    assert has_keyword(lion, "Hexproof", scenario.game) is False
    assert has_keyword(lion, "Indestructible", scenario.game) is False

    sources = [
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice"),
        *scenario.untapped_sources("Plains", username="alice"),
    ]
    scenario.activate(lion, *sources)
    scenario.pass_until_resolved()

    assert lion.monstrous is True
    assert lion.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(lion, "Hexproof", scenario.game) is True
    assert has_keyword(lion, "Indestructible", scenario.game) is True


# --------------------------------------------------------------------------
# Arbor Colossus - {3}{G}{G}{G}: Monstrosity 3. "When this creature becomes
# monstrous, destroy target creature with flying an opponent controls."
# --------------------------------------------------------------------------

ARBOR = "Arbor Colossus"


def test_arbor_colossus_destroys_a_flier_when_it_becomes_monstrous():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ARBOR] + ["Forest"] * 6)
        .player("bob", battlefield=["Wind Drake"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colossus = scenario.creature(ARBOR, "alice")
    drake = scenario.creature("Wind Drake", "bob")
    scenario.choose_trigger_targets(ARBOR, [drake])
    sources = scenario.untapped_sources(*(["Forest"] * 6), username="alice")

    scenario.activate(colossus, *sources)
    scenario.pass_until_resolved()  # the Monstrosity activation itself
    scenario.game.put_triggers_on_stack()

    assert colossus.monstrous is True
    assert scenario.stack_names() == [f"{ARBOR}'s triggered ability"]

    scenario.pass_until_resolved()  # the "becomes monstrous" trigger

    assert drake.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Polukranos, World Eater - {X}{X}{G}: Monstrosity X. "When Polukranos
# becomes monstrous, it deals X damage divided as you choose among any
# number of target creatures your opponents control. Each of those creatures
# deals damage equal to its power to Polukranos." - CR 701.37c's own X,
# plumbed from the activation to the trigger, plus CR 701.14a's retaliation.
# --------------------------------------------------------------------------

POLUKRANOS = "Polukranos, World Eater"


def test_polukranos_monstrosity_x_divides_damage_and_takes_retaliation():
    scenario = (
        Scenario()
        .player("alice", battlefield=[POLUKRANOS] + ["Forest"] * 5)
        .player("bob", battlefield=["Grizzly Bears", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    polukranos = scenario.creature(POLUKRANOS, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")
    # CR 603.3d: the trigger's own targets are announced as it goes on the
    # stack, after the activated ability has already resolved - scripted
    # ahead of time, the same way `test_activated_ability_effects.py` scripts
    # Agatha's Soul Cauldron's reflexive target.
    scenario.choose_trigger_targets(POLUKRANOS, [bears, memnite])
    sources = scenario.untapped_sources(*(["Forest"] * 5), username="alice")

    ability = scenario.activate(polukranos, *sources, x_value=2)
    assert isinstance(ability, AbilityOnStack)
    assert ability.x_value == 2
    scenario.pass_until_resolved()  # {X}{X}{G}: Monstrosity X
    scenario.game.put_triggers_on_stack()

    assert polukranos.monstrous is True
    assert polukranos.monstrous_x == 2
    assert polukranos.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.stack_names() == [f"{POLUKRANOS}'s triggered ability"]

    scenario.pass_until_resolved()  # the "becomes monstrous" trigger

    # 2 damage divided with no announced division falls back to an even
    # split, 1 each, over the two targets (CR 601.2d). Memnite is a 1/1, so
    # its share is lethal and CR 704.5g's state-based action destroys it -
    # its own `.damage` reads 0 once in the graveyard (CR 400.7's "new
    # object", the same reset a zone change already gives every permanent's
    # marked damage), so the graveyard arrival is the proof the 1 landed.
    assert bears.damage == 1
    assert memnite.zone is Zone.GRAVEYARD
    # CR 701.14a: each of those creatures deals damage equal to its own
    # power back to Polukranos - Grizzly Bears' 2 plus Memnite's 1 - and
    # CR 704.3 never checks state-based actions mid-resolution, so Memnite's
    # own retaliation still happened before it died.
    assert polukranos.damage == 3


def test_polukranos_activation_with_no_legal_opponent_creature_still_becomes_monstrous():
    """CR 601.2d's divided damage asks for "any number of target creatures" -
    zero is legal (CR 115.6) - so an empty board still lets the permanent
    become monstrous even though the trigger's own damage clause has nothing
    to divide among."""
    scenario = (
        Scenario().player("alice", battlefield=[POLUKRANOS] + ["Forest"] * 3).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    polukranos = scenario.creature(POLUKRANOS, "alice")
    sources = scenario.untapped_sources(*(["Forest"] * 3), username="alice")

    scenario.activate(polukranos, *sources, x_value=1)
    scenario.pass_until_resolved()  # {X}{X}{G}: Monstrosity X

    assert polukranos.monstrous is True
    assert polukranos.monstrous_x == 1
    assert polukranos.counter_count(Counter.PLUS_ONE) == 1


# --------------------------------------------------------------------------
# Corners: leaving the battlefield, and copies.
# --------------------------------------------------------------------------


def test_blinked_monstrous_creature_is_no_longer_monstrous():
    """CR 701.37b: "Once a permanent becomes monstrous, it stays monstrous
    until it leaves the battlefield." Ephemerate's exile-then-return is CR
    400.7's "new object with no memory of ... its previous existence" -
    Nessian Asp returns as a fresh, unmonstrous permanent with no counters."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ephemerate"],
            battlefield=["Nessian Asp"] + ["Forest"] * 7 + ["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    asp = scenario.creature("Nessian Asp", "alice")
    forests = scenario.untapped_sources(*(["Forest"] * 7), username="alice")
    scenario.activate(asp, *forests)
    scenario.pass_until_resolved()
    assert asp.monstrous is True
    assert asp.counter_count(Counter.PLUS_ONE) == 4

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Ephemerate", plains, targets=[asp])

    blinked = scenario.creature("Nessian Asp", "alice")
    assert blinked.monstrous is False
    assert blinked.monstrous_x is None
    assert blinked.counter_count(Counter.PLUS_ONE) == 0


def test_a_token_copy_of_a_monstrous_creature_is_not_monstrous():
    """CR 701.37b: "Monstrous is ... neither an ability nor part of the
    permanent's copiable values." Clone entering as a copy of a monstrous
    Fleecemane Lion copies its power, toughness and ability lines - not the
    designation, and not the hexproof/indestructible the static grants only
    while `monstrous` actually holds."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fleecemane Lion", "Forest", "Forest", "Forest", "Forest", "Plains"],
        )
        .player("bob", hand=["Clone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lion = scenario.creature("Fleecemane Lion", "alice")
    sources = [
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice"),
        *scenario.untapped_sources("Plains", username="alice"),
    ]
    scenario.activate(lion, *sources)
    scenario.pass_until_resolved()
    assert lion.monstrous is True

    # `Fleecemane Lion` is the only creature on the battlefield, so `Clone`'s
    # own "you may have this creature enter as a copy of any creature on the
    # battlefield" has exactly one candidate - the same unscripted-decision
    # shape `test_replacement_effects.py`'s own Clone/Grizzly Bears proof
    # uses, with no explicit `choose_trigger_targets`-style scripting needed.
    scenario.put_onto_battlefield("Clone", "bob")

    clone = scenario.creature("Clone", "bob")
    # `CardState.name` reads the printing, not the computed copy (a
    # documented gap `test_replacement_effects.py`'s own Clone proof already
    # notes) - `characteristics_of` is what actually shows the copy landed.
    assert scenario.game.characteristics_of(clone).name == "Fleecemane Lion"
    assert clone.monstrous is False
    assert clone.monstrous_x is None
    assert has_keyword(clone, "Hexproof", scenario.game) is False
    assert has_keyword(clone, "Indestructible", scenario.game) is False
    # The original is unaffected by the copy - still monstrous, still
    # hexproof and indestructible.
    assert lion.monstrous is True
    assert has_keyword(lion, "Hexproof", scenario.game) is True
