"""Scenario: Endure (CR 701.63), a keyword action read generally off the
ability's own printed text, not pinned to one card.

CR 701.63a (verified with `mise run rules:find 701.63` in this session):
"Certain abilities instruct a permanent to endure N. To do so, that
permanent's controller creates an N/N white Spirit creature token unless
they put N +1/+1 counters on that permanent." CR 701.63b: "If a permanent is
instructed to endure 0, nothing happens. No counters are put on that
permanent and no tokens are created."

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Krumar Initiate** (the follow-up's own named card): "{X}{B}, {T}, Pay X
  life: This creature endures X. Activate only as a sorcery." An activated
  ability, X announced at activation (CR 107.3a).
- **Fortress Kin-Guard** (off-pool, proves the parser generalises rather than
  reading Krumar Initiate's own sentence): "When this creature enters, it
  endures 1." A triggered ability with a fixed amount and the pronoun "it"
  rather than "this creature", and no activation cost or X at all.

Both readings share `_ENDURE_RE`/`_parse_endure_clause` in
`machines/effects.py`; the choice between the two outcomes is
`DecisionKind.MAY` (CR 608.2d), the same primitive every other "unless"/"you
may instead" clause in the module already uses.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_krumar_initiate_endures_x_by_creating_a_spirit_when_the_may_is_declined():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Krumar Initiate"] + ["Swamp"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)  # decline "put counters instead"
    krumar = scenario.find("Krumar Initiate", Zone.BATTLEFIELD, "alice")

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.activate(krumar, *sources, x_value=2)
    scenario.pass_until_resolved()

    assert krumar.zone is Zone.BATTLEFIELD
    assert krumar.counters[Counter.PLUS_ONE] == 0
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Spirit" in (state.card.type_line or "")
    ]
    assert len(spirits) == 1
    spirit = spirits[0]
    assert spirit.power == 2
    assert spirit.toughness == 2


def test_krumar_initiate_endures_x_by_putting_counters_when_the_may_is_taken():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Krumar Initiate"] + ["Swamp"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)  # accept "put counters instead"
    krumar = scenario.find("Krumar Initiate", Zone.BATTLEFIELD, "alice")

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.activate(krumar, *sources, x_value=2)
    scenario.pass_until_resolved()

    assert krumar.zone is Zone.BATTLEFIELD
    assert krumar.counters[Counter.PLUS_ONE] == 2
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Spirit" in (state.card.type_line or "")
    ]
    assert spirits == []


def test_endure_0_does_nothing():
    """CR 701.63b."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Krumar Initiate"] + ["Swamp"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    krumar = scenario.find("Krumar Initiate", Zone.BATTLEFIELD, "alice")

    (swamp1,) = scenario.untapped_sources("Swamp")
    scenario.activate(krumar, swamp1, x_value=0)
    scenario.pass_until_resolved()

    assert krumar.zone is Zone.BATTLEFIELD
    assert krumar.counters[Counter.PLUS_ONE] == 0
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Spirit" in (state.card.type_line or "")
    ]
    assert spirits == []


def test_off_pool_fortress_kin_guard_endures_1_on_its_own_etb_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Fortress Kin-Guard"], battlefield=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)  # decline -> create the Spirit
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Fortress Kin-Guard", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    guard = scenario.find("Fortress Kin-Guard", Zone.BATTLEFIELD, "alice")
    assert guard.counters[Counter.PLUS_ONE] == 0
    spirits = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Spirit" in (state.card.type_line or "")
    ]
    assert len(spirits) == 1
    assert spirits[0].power == 1
    assert spirits[0].toughness == 1
