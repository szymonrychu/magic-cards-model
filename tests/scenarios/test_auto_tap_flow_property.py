"""Property test: the flow solver and the brute-force oracle must never
disagree on whether a cost is payable.

T8b replaced `_solve_auto_tap`'s exponential `combinations(candidates, size)`
search with a max-flow formulation (`_solve_auto_tap_flow`, in
`machines/cost.py`) and kept the old search as `_solve_auto_tap_brute_force` -
slow, but correct for a long time. The real risk in that replacement is not
"too slow", it is "silently wrong": the flow solver could report a cost
payable when it is not, or the reverse, and nothing downstream would notice
until a game desynced from what the rules actually allow.

This file is the mitigation the task asked for: generate a random board from
the real fixture printings and a random cost, run both solvers, and assert
they agree on whether *some* legal tapping plan exists. Disagreement is a bug
in one of the two, and `_shrink` below gives a minimal reproducer for it
rather than a random 8-source board dump.

No mocks - every source is a real Scryfall printing from `tests/fixtures/cards`
via the `Scenario` harness (`docs/no-mocks-scenario-tests.md`); only the
*cost* being asked about is built directly with `ManaCost`/`ManaSymbol`, the
same way `tests/test_mana.py`'s own unit tests already parametrize costs that
belong to no one particular printed card.
"""

import random

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import (
    _solve_auto_tap,
    _solve_auto_tap_brute_force,
    _SpendContext,
)
from magic_cards_model.models import Color
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.mana import ManaCost, ManaSpend, ManaSymbol, SymbolKind
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# The dominant case: bare-{T} sources with no CR 106.6 restriction in play at
# all - duals, shocks, any-colour rocks, snow basics, boosted Tron pieces.
# This is the shape the task calls the "majority" case, and where the
# combinatorial search used to be exponential.
# --------------------------------------------------------------------------

_SIMPLE_POOL = [
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Steam Vents",
    "Breeding Pool",
    "Hallowed Fountain",
    "Godless Shrine",
    "Watery Grave",
    "Sacred Foundry",
    "Overgrown Tomb",
    "Exotic Orchard",
    "Reflecting Pool",
    "Karplusan Forest",
    "Birds of Paradise",
    "Llanowar Elves",
    "Urza's Mine",
    "Urza's Power Plant",
    "Urza's Tower",
    "Snow-Covered Forest",
    "Gemstone Caverns",
]


def _random_simple_cost(rng: random.Random) -> ManaCost:
    """A random cost with generic, coloured, and occasionally snow, hybrid,
    monocoloured-hybrid, or Phyrexian symbols - every shape `ManaCost.parse`
    itself can produce off a real printed cost string (CR 107.4)."""
    symbols: list[ManaSymbol] = []
    generic = rng.randint(0, 3)
    if generic:
        symbols.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=generic))
    for _ in range(rng.randint(0, 2)):
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


def _agree(
    board: list[str], cost: ManaCost, life: int, spend: ManaSpend | None
) -> tuple[bool, bool]:
    """Whether the brute-force oracle and the flow solver each say `cost` is
    payable off `board` - built fresh as a real `Scenario` battlefield every
    time, since a `CardState` is not reusable across games."""
    scenario = Scenario().player("alice", battlefield=board).build()
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
    sources = scenario.game.permanents_controlled_by("alice")
    context = _SpendContext(game=scenario.game, payer="alice", spend=spend)
    brute_force = _solve_auto_tap_brute_force(
        context,
        sources,
        owed=cost,
        base_floating={},
        base_snow={},
        base_restricted=[],
        life_available=life,
    )
    flow = _solve_auto_tap(
        context,
        sources,
        owed=cost,
        base_floating={},
        base_snow={},
        base_restricted=[],
        life_available=life,
    )
    return brute_force is not None, flow is not None


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
    oracle, flow = _agree(board, cost, life, spend)
    if oracle == flow:
        return
    minimal = _shrink(board, cost, life, spend)
    raise AssertionError(
        f"flow solver disagrees with the brute-force oracle: board={minimal} cost={cost} "
        f"life={life} spend={spend} oracle_says_payable={oracle} flow_says_payable={flow}"
    )


def test_flow_solver_agrees_with_brute_force_on_random_simple_boards():
    """300 random boards drawn from the simple pool, random costs including
    snow/hybrid/monocoloured-hybrid/Phyrexian symbols, `spend=None` (the
    common "could legal-action-enumeration afford this" question) - the
    dominant case this task targets."""
    rng = random.Random(20260907)
    for _ in range(300):
        size = rng.randint(1, 8)
        board = rng.choices(_SIMPLE_POOL, k=size)
        cost = _random_simple_cost(rng)
        life = rng.randint(0, 6)
        _assert_agree(board, cost, life, None)


# --------------------------------------------------------------------------
# The exotic case: boards that include a permanent whose choice is between
# alternatives of more than one mana (Shang-Chi), or a permanent with two
# `{T}`-only abilities that a broken flow network could sum instead of
# choosing between (Eldrazi Temple), with the restriction actually unlocked
# often enough that both of those abilities are genuinely in play.
# --------------------------------------------------------------------------

_EXOTIC_POOL = [
    "Plains",
    "Island",
    "Swamp",
    "Mountain",
    "Forest",
    "Steam Vents",
    "Birds of Paradise",
    "Urza's Mine",
    "Urza's Tower",
    "Eldrazi Temple",
    "Shang-Chi, Master of Kung Fu",
    "Cavern of Souls",
]


def _random_exotic_cost(rng: random.Random) -> ManaCost:
    symbols: list[ManaSymbol] = []
    generic = rng.randint(0, 4)
    if generic:
        symbols.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=generic))
    for _ in range(rng.randint(0, 2)):
        symbols.append(ManaSymbol(kind=SymbolKind.COLORED, colors=(rng.choice(list(Color)),)))
    return ManaCost(symbols=tuple(symbols))


def test_flow_solver_agrees_with_brute_force_when_exotic_sources_are_in_play():
    """150 random boards drawn from a pool that always makes Eldrazi Temple's
    and Shang-Chi's restricted abilities *available* - `spend` rotates across
    trials between nothing, casting a colourless Eldrazi spell, activating a
    creature's ability, and casting a creature spell of Cavern's chosen type -
    so the exotic branch in `_solve_auto_tap_flow` is actually exercised, not
    just present in the candidate list and then filtered out."""
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
    for _ in range(150):
        size = rng.randint(1, 6)
        board = rng.choices(_EXOTIC_POOL, k=size)
        cost = _random_exotic_cost(rng)
        spend = rng.choice(spends)
        _assert_agree(board, cost, 0, spend)
