"""Immaculate Magistrate's own "for each `<quality>` you control" multiplier
on a targeted counter placement.

"{T}: Put a +1/+1 counter on target creature for each Elf you control."
`_COUNTER_TARGET_RE`'s "phrase" group used to swallow the whole "target
creature for each Elf you control" tail whole, and the effect always used
the bare per-instance amount (1) regardless of how many Elves alice actually
controlled - the number sweep's own G2-1 finding, reassigned here since it
is one more "put counters" shape sharing `numbers.py` and `count_expression`
with the rest of the counters-on-self/group family rather than the
damage-target half of that shape (`_DAMAGE_TARGET_RE`'s own "for each",
still silent, is that family's business).

`_count_of_quality_you_control` is the new reader - "for each `<quality>`
you control" read through `count_expression`'s own "the number of
`<quality>` you control" vocabulary rather than a second copy of it, since a
for-each multiplier is that same phrase minus its "number of" lead-in.
Proven on Immaculate Magistrate (pool) and Go-Shintai of Boundless Vigor
(off-pool, a different quality and a different real count).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.1** - counters mark a permanent.
- **CR 205.2a, 205.3** - card types and subtypes, what "Elf"/"Shrine" are.
- **CR 611.2c** - a resolving ability's magnitude is fixed once, at
  resolution, not once per target.

This wave also found and fixed a name collision blocking both proofs above:
three separate `_singular_subtype`-named functions lived in `effects.py`
(one for `count_expression`'s own "the number of `<type>` you control"
family, one for `_parse_transform_all_subtype_clause`, one for `amass`), and
Python only ever bound the textually-last one at module scope - so
`count_expression`'s own subtype branch always ran the *amass* one instead
(neither lowercasing nor checking `subtype_vocabulary()`), and "the number
of Elf you control" silently came back 0 no matter how many Elves alice
controlled. The other two kept their own callers unchanged; only the
shadowed one - `count_expression`'s - was ever wrong.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import (
    _count_of_quality_you_control,
    _parse_targeted_clause,
)
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_immaculate_magistrates_counters_scale_with_elves_controlled():
    """Immaculate Magistrate is itself an Elf Shaman (CR 205.3), so alice's
    own three Elves - Immaculate Magistrate, Llanowar Elves, Elvish Mystic -
    put three +1/+1 counters on the target, not the bare "a" (1) the old
    swallowed-phrase reading always placed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Immaculate Magistrate",
                "Llanowar Elves",
                "Elvish Mystic",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    magistrate = scenario.creature("Immaculate Magistrate", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(magistrate, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.game.unreadable_counter_amount_notices == []


def test_go_shintais_for_each_shrine_is_a_different_quality_and_count():
    """Go-Shintai of Boundless Vigor (off-pool): "put a +1/+1 counter on
    target Shrine for each Shrine you control." Proves `_count_of_quality_
    you_control` generalises past "Elf" to a different subtype and a
    different real count (three Shrines), not a card-name-fitted reader.

    Driven directly against `_parse_targeted_clause` and the reader it wires
    up, rather than through a live activation: Go-Shintai's own trigger is
    "At the beginning of your end step, you may pay {1}. When you do, `<put
    counters clause>`" - a CR 603.12-style paid-cost reflexive trigger this
    engine has no generic reader for yet (unrelated to counter counts, and
    out of this family's scope). The counter clause itself - the only part
    this fix touches - is Go-Shintai's own unedited printed text, read the
    same way `test_mass_counter_placement.py`'s own `_parse_put_counters_on_
    group_clause` direct-call tests already do for an unreachable-live
    shape.
    """
    clause = "put a +1/+1 counter on target Shrine for each Shrine you control"
    match_effect = _parse_targeted_clause(clause, for_spell=False)
    assert match_effect is not None

    reader = _count_of_quality_you_control("Shrine you control")
    assert reader is not None

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Go-Shintai of Boundless Vigor",
                "Honden of Cleansing Fire",
                "Honden of Infinite Rage",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert reader(scenario.game, "alice") == 3


def test_grief_tyrants_for_each_counter_on_itself_is_not_this_shape():
    """Fails closed rather than silently using the bare per-instance amount:
    Grief Tyrant's real "put a -1/-1 counter on target creature for each
    -1/-1 counter on this creature" is a count of counters on the source, not
    a quality "you control" - a different expression `_count_of_quality_you_
    control` correctly declines, so the whole clause is refused rather than
    guessed at (CR 122.1)."""
    clause = "put a -1/-1 counter on target creature for each -1/-1 counter on this creature"
    assert _parse_targeted_clause(clause, for_spell=False) is None
