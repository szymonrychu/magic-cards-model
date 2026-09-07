"""Property test: the flow solver and the brute-force oracle must never
disagree on whether a cost is payable, or on the plans each returns.

T8b replaced `_solve_auto_tap`'s exponential `combinations(candidates, size)`
search with a max-flow formulation (`_solve_auto_tap_flow`, in
`machines/cost.py`) and kept the old search as `_solve_auto_tap_brute_force` -
slow, but correct for a long time. The real risk in that replacement is not
"too slow", it is "silently wrong": the flow solver could report a cost
payable when it is not, or the reverse, and nothing downstream would notice
until a game desynced from what the rules actually allow.

This file is the mitigation the task asked for: generate a random board from
the real fixture printings and a random cost, run both solvers, and assert
they agree on whether *some* legal tapping plan exists - and, whenever the
flow solver finds one, that `pay()` actually accepts it, not merely that a
plan came back non-`None`. `_shrink` below gives a minimal reproducer for a
disagreement rather than a random 8-source board dump.

No mocks - every source is a real Scryfall printing from `tests/fixtures/cards`
(`docs/no-mocks-scenario-tests.md`), drawn from the real fixture pool and
filtered to cards the engine's own `parse_mana_abilities` says can produce
mana at all - a board of vanilla creatures tests nothing. Only the *cost*
being asked about, and one CR 106.6 restriction the pool is seeded with (see
`_FOREIGN_RESTRICTION` below), are built directly with `ManaCost`/
`ManaSymbol`/`ManaRestriction`, the same way `tests/test_mana.py`'s own unit
tests already parametrize costs that belong to no one particular printed
card.
"""

import random
from uuid import UUID

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.cost import (
    CostPayment,
    TotalCost,
    _solve_auto_tap,
    _solve_auto_tap_brute_force,
    _SpendContext,
    could_pay_mana_cost,
)
from magic_cards_model.models import Color
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.mana import (
    ManaCost,
    ManaRestriction,
    ManaSpend,
    ManaSymbol,
    RestrictedMana,
    SpendClause,
    SpendPurpose,
    SymbolKind,
)
from tests.cards import card
from tests.cards import pool as fixture_pool
from tests.scenarios.harness import PlayedScenario, Scenario


def _mana_producing_pool() -> list[str]:
    """Every real printing in `tests/fixtures/cards` with a genuine `{T}: Add
    ...` mana ability of its own - `machines.abilities.parse_mana_abilities`,
    the engine's own reading (CR 605.1a plus the CR 305.6 basic-land
    fallback), not a hand-picked guess at which names qualify. A board of
    vanilla creatures and non-mana permanents tests nothing, so this is what
    every board in this file is drawn from instead of a hand-written list.

    Deduplicated by the printing's own Scryfall id, since `tests.cards.pool`
    indexes a split/mdfc card under both its full and front-face name; the
    front-face name (`tests.cards.card`'s own lookup key for such a card) is
    what is kept.
    """
    seen: set[UUID] = set()
    names: list[str] = []
    for printing in fixture_pool().values():
        if printing.id in seen:
            continue
        seen.add(printing.id)
        if parse_mana_abilities(printing):
            names.append(printing.name.split("//")[0].strip())
    return sorted(names)


_MANA_POOL = _mana_producing_pool()

#: A CR 106.6 restriction that names nothing on this board (no printing in the
#: pool casts or activates as a Zombie) - seeded into every trial's pool so
#: `pool_registry` (`machines/cost.py::_solve_auto_tap_flow`) always already
#: holds one restriction before any source's own restriction is registered.
#: This is exactly the shape defect 1 lived in (`_chosen_alternative` used to
#: read a tapped source's restriction back through a registry it rebuilt from
#: empty, so a source's own slot was silently assumed to be 0): seeding it on
#: every trial means a regression here fails this property test generally,
#: not only the dedicated regression test below.
_FOREIGN_RESTRICTION = ManaRestriction(
    text="Spend this mana only to cast a Zombie spell.",
    clauses=(SpendClause(purpose=SpendPurpose.CAST_SPELL, subtypes=frozenset({"zombie"})),),
)


def _random_cost(rng: random.Random, *, max_generic: int, max_colored: int) -> ManaCost:
    """A random cost with generic, coloured, and occasionally snow, hybrid,
    monocoloured-hybrid, or Phyrexian symbols - every shape `ManaCost.parse`
    itself can produce off a real printed cost string (CR 107.4)."""
    symbols: list[ManaSymbol] = []
    generic = rng.randint(0, max_generic)
    if generic:
        symbols.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=generic))
    for _ in range(rng.randint(0, max_colored)):
        symbols.append(ManaSymbol(kind=SymbolKind.COLORED, colors=(rng.choice(list(Color)),)))
    roll = rng.random()
    if roll < 0.15:
        symbols.append(ManaSymbol(kind=SymbolKind.SNOW))
    elif roll < 0.30:
        first, second = rng.sample(list(Color), 2)
        symbols.append(ManaSymbol(kind=SymbolKind.HYBRID, colors=(first, second)))
    elif roll < 0.45:
        symbols.append(
            ManaSymbol(
                kind=SymbolKind.MONOCOLORED_HYBRID, amount=2, colors=(rng.choice(list(Color)),)
            )
        )
    elif roll < 0.55:
        symbols.append(ManaSymbol(kind=SymbolKind.PHYREXIAN, colors=(rng.choice(list(Color)),)))
    return ManaCost(symbols=tuple(symbols))


def _build_scenario(board: list[str], life: int) -> tuple[PlayedScenario, object]:
    """One board, built fresh - a `CardState` is not reusable across games -
    with the fixed-up choices some printings in the pool need to have a mana
    ability at all, and `_FOREIGN_RESTRICTION` seeded onto the player's own
    pool (see its own docstring) rather than passed as a bare parameter, so
    what the solvers are asked and what a real `CostPayment` would see stay
    the same object.
    """
    scenario = Scenario().player("alice", life=life, battlefield=board).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for state in scenario.game.battlefield:
        # Half the time (deterministically, off the board's own contents - no
        # extra randomness this function would have to thread through) let
        # its conditional clause hold too, so both the {C} and the any-colour
        # reading of Gemstone Caverns get exercised across the run.
        if (
            state.name == "Gemstone Caverns"
            and "luck" not in state.counters.counts
            and len(board) % 2 == 0
        ):
            state.counters.add("luck")
        if state.name == "Cavern of Souls":
            state.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")
    player = scenario.game.player("alice")
    player.mana_pool.add(Color.BLACK, 1, restriction=_FOREIGN_RESTRICTION)
    return scenario, player


def _solve_both(board: list[str], cost: ManaCost, life: int, spend: ManaSpend | None):
    """Run both solvers over the same freshly-built board, returning each
    plan (or `None`) plus the sources they were asked about - `sources`'
    `CardState`s belong to this one game and are never reused (both solves
    are pure, but the game's own ids would not survive a fresh rebuild - see
    `_assert_plan_is_payable`, which is what actually taps anything)."""
    scenario, player = _build_scenario(board, life)
    sources = scenario.game.permanents_controlled_by("alice")
    context = _SpendContext(game=scenario.game, payer="alice", spend=spend)
    base_floating = dict(player.mana_pool.floating)
    base_snow = dict(player.mana_pool.snow)
    base_restricted = [entry.model_copy(deep=True) for entry in player.mana_pool.restricted]
    brute_force = _solve_auto_tap_brute_force(
        context,
        sources,
        owed=cost,
        base_floating=base_floating,
        base_snow=base_snow,
        base_restricted=base_restricted,
        life_available=life,
    )
    flow = _solve_auto_tap(
        context,
        sources,
        owed=cost,
        base_floating=base_floating,
        base_snow=base_snow,
        base_restricted=base_restricted,
        life_available=life,
    )
    return brute_force, flow, sources


def _agree(
    board: list[str], cost: ManaCost, life: int, spend: ManaSpend | None
) -> tuple[bool, bool]:
    """Whether the brute-force oracle and the flow solver each say `cost` is
    payable off `board` - existence only, which is all `_shrink` needs to
    keep minimising towards."""
    brute_force, flow, _sources = _solve_both(board, cost, life, spend)
    return brute_force is not None, flow is not None


def _assert_plan_is_payable(
    board: list[str],
    cost: ManaCost,
    life: int,
    spend: ManaSpend | None,
    plan,
    original_sources: list,
    *,
    label: str,
) -> None:
    """Confirm `plan` - a real `_TapPlan`, either solver's - is one `pay()`
    actually accepts for `cost`, on a fresh, independently-built copy of the
    same board (so validating one solver's plan never taps a source the
    other solver's plan also wanted to use).

    This is the "at minimum" floor for plan equivalence: two different plans
    can both be correct ways to pay the same cost (a payer is free to spend
    a Steam Vents for `{R}` or a Mountain for it, and both are legal), so
    asserting the two plans are *equal* would reject a flow-solver answer
    that is merely different from the oracle's, not wrong. What both must
    still do, without exception, is actually pay - a plan `pay()` refuses
    is wrong regardless of what the other solver would have done instead.

    `plan`'s sources belong to `original_sources`' own game, minted with that
    game's own (randomly seeded) `game_uid`, so a fresh rebuild of the same
    board mints different ids for what is otherwise the identical battlefield
    - matched back up here by position (`Scenario.player`'s battlefield order
    is deterministic given the same board list), not by id.
    """
    indexes = [original_sources.index(source) for source, _colors, _restriction in plan]
    scenario, player = _build_scenario(board, life)
    fresh_sources = scenario.game.permanents_controlled_by("alice")
    total = TotalCost.of(cost)
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice", spend=spend)
    try:
        for index, (_source, colors, restriction) in zip(indexes, plan, strict=True):
            payment.tap_for_mana(fresh_sources[index], colors, restriction)
        payment.pay()
    except Exception as exc:  # noqa: BLE001 - re-raised as an AssertionError with full context
        raise AssertionError(
            f"{label} plan was not accepted by pay(): board={board} cost={cost} life={life} "
            f"spend={spend} plan={plan!r} error={exc!r}"
        ) from exc


def _shrink(board: list[str], cost: ManaCost, life: int, spend: ManaSpend | None) -> list[str]:
    """A minimal sub-board that still disagrees, dropping one source at a
    time - so a failure names the smallest reproducer rather than the whole
    random board it was first found on."""
    current = list(board)
    changed = True
    while changed and len(current) > 1:
        changed = False
        for index in range(len(current)):
            candidate = current[:index] + current[index + 1 :]
            oracle, flow = _agree(candidate, cost, life, spend)
            if oracle != flow:
                current = candidate
                changed = True
                break
    return current


def _assert_agree(board: list[str], cost: ManaCost, life: int, spend: ManaSpend | None) -> None:
    brute_force, flow, sources = _solve_both(board, cost, life, spend)
    oracle_found, flow_found = brute_force is not None, flow is not None
    if oracle_found != flow_found:
        minimal = _shrink(board, cost, life, spend)
        raise AssertionError(
            f"flow solver disagrees with the brute-force oracle on payability: board={minimal} "
            f"cost={cost} life={life} spend={spend} oracle_says_payable={oracle_found} "
            f"flow_says_payable={flow_found}"
        )
    if not flow_found:
        return
    # Both found a plan (or both found the empty "already payable" plan).
    # Neither being non-None is not the claim being made here - each plan
    # must itself be one `pay()` accepts, checked independently so tapping
    # one plan's sources never interferes with checking the other's.
    _assert_plan_is_payable(board, cost, life, spend, flow, sources, label="flow solver's")
    _assert_plan_is_payable(
        board, cost, life, spend, brute_force, sources, label="brute-force oracle's"
    )


def test_flow_solver_agrees_with_brute_force_on_random_simple_boards():
    """100 random boards drawn from every real mana-producing printing in the
    fixture pool, random costs including snow/hybrid/monocoloured-hybrid/
    Phyrexian symbols, `spend=None` (the common "could legal-action-
    enumeration afford this" question) - the dominant case this task
    targets. Every trial's pool also carries `_FOREIGN_RESTRICTION`, so this
    is also defect 1's own regression, run 100 times over instead of once.

    Verified once at 2000 trials (zero disagreements, ~4m45s alongside the
    exotic test's own 1000) before being turned back down to a count that
    keeps the suite fast; see the defect-fix report for that run's output."""
    rng = random.Random(20260907)
    for _ in range(100):
        size = rng.randint(1, 8)
        board = rng.choices(_MANA_POOL, k=size)
        cost = _random_cost(rng, max_generic=3, max_colored=2)
        life = rng.randint(0, 6)
        _assert_agree(board, cost, life, None)


# --------------------------------------------------------------------------
# The exotic case: boards that include a permanent whose choice is between
# alternatives of more than one mana (Shang-Chi), or a permanent with two
# `{T}`-only abilities that a broken flow network could sum instead of
# choosing between (Eldrazi Temple), with the restriction actually unlocked
# often enough that both of those abilities are genuinely in play. Forced
# onto every board below so the exotic branch stays reliably exercised - the
# rest of each board is still drawn at random from the real fixture pool.
# --------------------------------------------------------------------------

_FORCED_EXOTIC_SOURCES = ["Eldrazi Temple", "Shang-Chi, Master of Kung Fu", "Cavern of Souls"]


def test_flow_solver_agrees_with_brute_force_when_exotic_sources_are_in_play():
    """50 boards that always include Eldrazi Temple, Shang-Chi, and Cavern
    of Souls, filled out with a random draw from the same real fixture pool
    `_MANA_POOL` (rather than a second hand-picked list) - `spend` rotates
    across trials between nothing, casting a colourless Eldrazi spell,
    activating a creature's ability, and casting a creature spell of
    Cavern's chosen type, so the exotic branch in `_solve_auto_tap_flow` is
    actually exercised, not just present in the candidate list and then
    filtered out."""
    rng = random.Random(8675309)
    glaring_fleshraker = card("Glaring Fleshraker")
    basking_rootwalla = card("Basking Rootwalla")
    llanowar_elves = card("Llanowar Elves")
    spends: list[ManaSpend | None] = [
        None,
        ManaSpend.casting(glaring_fleshraker),
        ManaSpend.activating(basking_rootwalla),
        ManaSpend.casting(llanowar_elves),
    ]
    for _ in range(50):
        filler_size = rng.randint(0, 5)
        board = [*_FORCED_EXOTIC_SOURCES, *rng.choices(_MANA_POOL, k=filler_size)]
        rng.shuffle(board)
        cost = _random_cost(rng, max_generic=4, max_colored=2)
        spend = rng.choice(spends)
        _assert_agree(board, cost, 0, spend)


# --------------------------------------------------------------------------
# Regression: a restriction already floating in the payer's pool must not
# shift the bucket slot the flow solver reads a tapped source's own
# restriction back from - see `_chosen_alternative` in `machines/cost.py`.
# The property tests above now seed this on every trial too (see
# `_FOREIGN_RESTRICTION`); this is kept as its own sharply-worded, non-random
# reproducer of the exact case the whole-diff review found.
# --------------------------------------------------------------------------


def test_flow_solver_finds_a_plan_when_pool_already_holds_a_different_restriction():
    """Cavern of Souls, naming Goblin, is the only source on the board;
    `{R}` is owed for a Goblin spell. `base_restricted` already carries one
    entry for an *unrelated* restriction (a Zombie-only clause the pool
    happens to hold), which registers slot 0 before Cavern's own restriction
    is ever seen, so Cavern's restriction lands in slot 1 when the buckets
    are built.

    `_chosen_alternative` used to read the plan back through a registry it
    rebuilt from empty, so it looked for Cavern's restriction in slot 0 -
    found nothing there, and silently dropped Cavern from the read-back plan.
    The flow network itself still finds a legal assignment (it uses the real,
    shared registry), so `_best_flow_plan` returned `[]` - "already payable,
    nothing to tap" - rather than `None` or the one-source plan the oracle
    finds. `[]` is worse than either: `could_pay_mana_cost` reports the cost
    payable (correctly), but `auto_tap` then taps nothing at all, and `pay()`
    fails outright - the exact predicate/payment disagreement the flow-solver
    split exists to make impossible.

    Asserting only `is not None` (as `_agree` in this file used to) cannot
    catch this: `[]` is "not None" too. This asserts the plan's actual
    content agrees, and separately drives the whole real payment path
    (`could_pay_mana_cost` -> `CostPayment.auto_tap` -> `.pay()`) the way a
    live cast would."""
    scenario = Scenario().player("alice", battlefield=["Cavern of Souls"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (cavern,) = scenario.game.battlefield
    cavern.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Goblin")
    sources = scenario.game.permanents_controlled_by("alice")

    goblin_guide = card("Goblin Guide")
    spend = ManaSpend.casting(goblin_guide)
    cost = ManaCost.parse("{R}")

    unrelated_restriction = ManaRestriction(
        text="Spend this mana only to cast a Zombie spell.",
        clauses=(SpendClause(purpose=SpendPurpose.CAST_SPELL, subtypes=frozenset({"zombie"})),),
    )
    base_restricted = [RestrictedMana(restriction=unrelated_restriction, amounts={Color.BLACK: 1})]

    context = _SpendContext(game=scenario.game, payer="alice", spend=spend)
    brute_force = _solve_auto_tap_brute_force(
        context,
        sources,
        owed=cost,
        base_floating={},
        base_snow={},
        base_restricted=base_restricted,
        life_available=0,
    )
    flow = _solve_auto_tap(
        context,
        sources,
        owed=cost,
        base_floating={},
        base_snow={},
        base_restricted=base_restricted,
        life_available=0,
    )
    assert brute_force, "oracle should find a nonempty plan: nothing floats red mana already"
    assert flow, (
        "flow solver returned an empty ('already payable') plan instead of tapping Cavern of "
        f"Souls, disagreeing with the oracle's plan {brute_force!r}: flow={flow!r}"
    )

    # Drive the real payment path end to end, restriction seeded on the
    # player's actual mana pool rather than passed as a bare parameter.
    player = scenario.game.player("alice")
    player.mana_pool.add(Color.BLACK, 1, restriction=unrelated_restriction)

    assert could_pay_mana_cost(cost, sources, game=scenario.game, payer="alice", spend=spend), (
        "could_pay_mana_cost should say {R} is payable: Cavern of Souls can tap for it"
    )

    total = TotalCost.of("{R}")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice", spend=spend)
    payment.auto_tap(sources)
    payment.pay()
    assert cavern.tapped, "auto_tap should have tapped Cavern of Souls to cover {R}"
