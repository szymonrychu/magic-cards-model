""" "Target spell or `<permanent type>` with `<comparison>`" keeps its own
trailing restriction on *both* halves of the disjunction (CR 115.1, CR
601.2c).

Divide by Zero: "Return target spell or permanent with mana value 1 or
greater to its owner's hand." `TargetRequirement.or_any_spell`'s early return
in `_rejects_card` - "nothing further to check: the phrase named no type for
this half" - was true of the *card-type and zone* check (a spell on the stack
is never in `self.zones`, and the phrase names no card type for the spell
half), but not of a *shared* trailing clause like "with mana value 1 or
greater": that comparison is not part of either noun's own type restriction,
it modifies the whole compound noun, so it has to bind both halves. The old
early return let it through unchecked for every spell, accepting a
mana-value-0 spell the card's own words refuse.

`_rejects_card` now skips only the zone and card-type checks for the "or any
spell" half; a *shared, trailing* restriction (comparison, colors) still
runs - proven here by mana value specifically (Divide by Zero's own reported
gap) and by color (Aether Gust's own "target spell or permanent that's red
or green", real, off-set, not the reported card, proving the fix reads the
shape rather than one specific restriction kind).

A supertype/subtype restriction is not a trailing, whole-compound clause the
way those two are: Icy Reception's own "target creature or **legendary**
spell" reads "legendary" as the second item's own leading adjective, with
nothing recording which disjunct it belonged to by the time `_rejects_card`
runs - so it stays exempt from the spell half exactly as it always was,
which `test_icy_reception_still_counters_a_non_legendary_creature_spell`
guards: fixing Divide by Zero's gap must not regress a card that was never
broken.

CR numbers verified with `mise run rules:find` in the session that wrote this
file: CR 115.1 ("The targets are object(s) and/or player(s)..."), CR 112.1
("A spell is a card on the stack"), CR 601.2c (target announcement),
CR 205.4a (supertypes).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_divide_by_zero_refuses_a_mana_value_zero_spell():
    """The reported gap: a mana-value-0 spell (Mishra's Bauble, {0}) is not a
    legal target for "target spell or permanent with mana value 1 or
    greater", but the old `or_any_spell` early return accepted it anyway."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Mishra's Bauble"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (artifact_source,) = scenario.untapped_sources("Island")
    bauble = scenario.cast_onto_stack("Mishra's Bauble", artifact_source, username="alice")

    casting = scenario.cast("Divide by Zero", username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([bauble])


def test_divide_by_zero_bounces_a_qualifying_spell():
    """`or_any_spell` still lets a spell meeting the comparison through - the
    fix must not have refused every spell outright."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Lightning Bolt"],
            battlefield=["Island", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    casting = scenario.cast("Divide by Zero", username="alice")
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    # Divide by Zero also prints "Learn." (CR 701.48a) - decline its own
    # discard-to-draw so it does not immediately discard the very card the
    # bounce just put back into alice's hand; that keyword is not this fix's
    # business (see `tests/scenarios/test_learn.py`).
    scenario.will_take_the_may(False, source="Divide by Zero")
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND


def test_aether_gust_refuses_a_spell_of_the_wrong_color():
    """Aether Gust: real, off-set, non-reported - "target spell or permanent
    that's red or green." The color disjunction is the shared clause here
    rather than a mana-value comparison, proving the fix reads the general
    shape (keep everything past the zone/type check) and not a mana-value
    special case."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aether Gust", "Opt"], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    blue_spell = scenario.cast_onto_stack("Opt", island, username="alice")

    casting = scenario.cast("Aether Gust", username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([blue_spell])


def test_aether_gust_accepts_a_spell_of_the_right_color():
    """The other side of the same fix: a genuinely red spell still satisfies
    the disjunction, so the fix did not turn the whole requirement closed."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aether Gust", "Lightning Bolt"], battlefield=["Island", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    casting = scenario.cast("Aether Gust", username="alice")
    casting.choose_targets([bolt])


def test_icy_reception_still_counters_a_non_legendary_creature_spell():
    """Regression guard: Icy Reception's own "target creature or legendary
    spell" must not start demanding every targeted *creature* spell be
    legendary too - "legendary" is the second item's own adjective, not a
    shared restriction on the whole compound."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Icy Reception"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_casting = scenario.cast("Grizzly Bears", username="bob")
    bob_payment = bob_casting.begin_paying()
    scenario.pay_with(bob_payment, *scenario.untapped_sources("Forest", "Forest", username="bob"))
    bears_on_stack = scenario.put_on_stack(bob_casting)
    scenario.pass_priority()

    casting = scenario.cast("Icy Reception", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bears_on_stack])
