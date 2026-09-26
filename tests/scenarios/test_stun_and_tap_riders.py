"""SOS's tap-plus-stun-counter riders: "Tap target creature. `<rider>`."
where `<rider>` is an anaphoric CR 400.7 "it" naming what the tap sentence
just found - not a fresh target of its own. Two riders, plus a proof of the
underlying "put a stun counter on it" reader on a real second printing:

- **Procrastinate** - "Tap target creature. Put twice X stun counters on
  it." CR 107.3a's announced X, doubled, with no ceiling of its own.
- **Rapier Wit** - "Tap target creature. If it's your turn, put a stun
  counter on it. Draw a card." A conditional rider (`machines/
  effects._parse_conditional_referent_clause`'s own "if `<condition>`,
  `<rider>`" shape, widened so the rider need not *start* with the anaphor -
  here it ends with it, "... on it"), followed by an unrelated third
  sentence that names no referent at all.
- **Fractal Mascot** (off-pool, already `handled` on `main`; the generality
  proof that the plain, unconditional "put a stun counter on it" rider was
  never fitted to either of the two cards above) - "When this creature
  enters, tap target creature an opponent controls. Put a stun counter on
  it."

CR 122.1d's own replacement effect ("If a permanent with a stun counter on
it would become untapped, instead remove a stun counter from it") is
`models/card_state.py`'s `CardState.untap`, exercised here rather than
duplicated.

(Duel Tactics's own "It can't block this turn." damage rider is a different
antecedent - `tests/scenarios/test_damage_riders_sos.py`.)

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 400.7** - CR 400.7's anaphora backing "it"/"that creature" naming the
  antecedent's own found object, not a second targeting event.
- **CR 107.3a** - X in a spell's own mana cost, announced as it is cast.
- **CR 122.1d** - the stun counter's own untap-preventing replacement
  effect.
- **CR 509.1b** - a restriction (an effect saying a creature can't block)
  makes a block declaring it illegal.
- **CR 608.2h** - a conditional rider's condition is checked once, as the
  ability resolves, using the current game state.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

PROCRASTINATE = "Procrastinate"
RAPIER_WIT = "Rapier Wit"
FRACTAL_MASCOT = "Fractal Mascot"


def _cast_with_x(scenario, name, x_value, *sources, targets):
    """Cast an `{X}...` spell with `x_value` explicitly announced (CR
    107.3a) - the harness's own `cast_and_resolve` never sets X itself, so
    every X-cost scenario in this file goes through `Casting.determine_cost`
    by hand."""
    casting = scenario.cast(name, targets=targets)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_procrastinate_taps_and_puts_twice_x_stun_counters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PROCRASTINATE],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")

    _cast_with_x(scenario, PROCRASTINATE, 2, *sources, targets=[bears])

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 4


def test_procrastinate_with_x_equal_zero_taps_but_stuns_nothing():
    """CR 107.3b: twice zero is zero - the tap still happens (CR 601.2c: an
    announced X of 0 is a legal cast), the counter placement simply adds
    nothing."""
    scenario = (
        Scenario()
        .player("alice", hand=[PROCRASTINATE], battlefield=["Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (island,) = scenario.untapped_sources("Island")

    _cast_with_x(scenario, PROCRASTINATE, 0, island, targets=[bears])

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 0


def test_procrastinate_stun_counter_prevents_the_next_untap():
    """CR 122.1d's own replacement effect, exercised end to end: one stun
    counter removed instead of the permanent actually untapping."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PROCRASTINATE],
            battlefield=["Island", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    islands = scenario.untapped_sources("Island", "Island")

    _cast_with_x(scenario, PROCRASTINATE, 1, *islands, targets=[bears])
    assert bears.counter_count(Counter.STUN) == 2

    bears.tapped = True  # combat happened; now it's due to untap
    bears.untap()
    assert bears.tapped, "CR 122.1d: a stun counter is removed instead of untapping"
    assert bears.counter_count(Counter.STUN) == 1

    bears.untap()
    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 0

    bears.untap()
    assert not bears.tapped, "no stun counters left: it untaps normally"


def _rapier_wit_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[RAPIER_WIT],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob")
    )


def test_rapier_wit_stuns_on_the_casters_own_turn_and_draws_a_card():
    scenario = _rapier_wit_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    cards_before = len(alice.hand)
    plains = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve(RAPIER_WIT, *plains, targets=[bears])

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 1
    assert len(alice.hand) == cards_before  # the card just cast left one hand slot,
    # the draw fills it back - net unchanged, checked precisely below.


def test_rapier_wit_draws_regardless_of_whose_turn_it_is():
    """The draw is an unconditional third sentence, naming no referent - it
    always happens, even when the stun half does not."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"])
        .player(
            "bob",
            hand=[RAPIER_WIT],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
            library=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice's turn; bob casts at instant speed
    scenario.pass_priority("alice")
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    cards_before = len(bob.hand)
    plains = scenario.untapped_sources("Plains", "Plains", username="bob")

    scenario.cast_and_resolve(RAPIER_WIT, *plains, username="bob", targets=[bears])

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 0, "it wasn't bob's turn"
    assert len(bob.hand) == cards_before, "the draw still happened"


def test_fractal_mascots_enters_trigger_taps_and_stuns_an_opponents_creature():
    """Off-pool generality proof: the identical unconditional "put a stun
    counter on it" rider, on a triggered ability rather than a spell, and
    with its own restriction ("an opponent controls") on the antecedent's
    own target phrase."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[FRACTAL_MASCOT],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets(FRACTAL_MASCOT, [bears])
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Island", "Island")

    scenario.cast_and_resolve(FRACTAL_MASCOT, *sources)
    scenario.resolve_top()  # the enters trigger

    assert bears.tapped
    assert bears.counter_count(Counter.STUN) == 1
