"""Scenario: a mass pump or grant followed by "Put `<n>` `<kind>` counter(s)
on each of them." - an additive instruction (CR 608.2c), not a CR 614.1a
"instead" swap, whose "them" is the exact group the leading sentence's own
antecedent already found.

Summon: Knights of Round chapter V (reported): "Other creatures you control
get +2/+2 until end of turn. Put an indestructible counter on each of them."
`_parse_mass_pump_clause` used to read only the pump and drop the whole
counter sentence as an unparsed remainder - the group was pumped for the
turn but never got the lasting indestructible counters.

Age of Ultron chapter III is the off-pool generality proof: the identical
"pump-or-grant, then counter on each of them" shape with a narrower subject
("Artifact creatures you control", not "Other creatures you control"), a
keyword grant rather than a P/T pump, and a +1/+1 counter rather than a
keyword one - proving `_parse_mass_pump_counter_on_each` reads the rider
generically rather than fitted to "indestructible". (Age of Ultron is not
itself legal in Modern/Pioneer/Standard - it is used here only as a genuine
second Scryfall printing of the identical mechanic, per `CLAUDE.md`'s own
"add a card with `scripts/add_card.py`" rule, not as a target-format card.)

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 122.1b** - a keyword counter (indestructible among them) grants that
  keyword to the object it is on.
- **CR 611.2/611.2a** - the pump/grant itself, lasting until end of turn.
- **CR 122.1a** - a +1/+1 counter is a different, lasting object from a
  temporary pump.
- **CR 608.2c** - the controller follows every instruction in order; the
  counter placement is a further instruction, not a replacement of the pump.
- **CR 714.3/714.4** - a Saga's lore counters and chapter abilities.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _next_chapter(scenario: Scenario, saga) -> None:
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)


def test_knights_of_round_chapter_five_pumps_and_grants_indestructible():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summon: Knights of Round"],
            battlefield=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    saga = scenario.put_onto_battlefield("Summon: Knights of Round", "alice")
    _resolve_everything(scenario)  # the intrinsic lore counter, chapter I

    for _ in range(4):  # chapters II, III, IV, V
        _next_chapter(scenario, saga)

    knights = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Knight Token"
    ]
    assert len(knights) == 12, "four resolved token chapters, three tokens each"

    # "Other creatures you control" - the Saga creature itself is excluded
    # (and CR 714.4/704.5s has already sacrificed it as a state-based action,
    # so there is no board left to compute it on).
    assert saga.counter_count("indestructible") == 0

    assert bears.counter_count("indestructible") == 1
    assert has_keyword(bears, "indestructible", scenario.game)
    assert computed(scenario).of(bears).power_toughness == (4, 4), "a 2/2 plus a temporary +2/+2"
    for knight in knights:
        assert knight.counter_count("indestructible") == 1
        assert has_keyword(knight, "indestructible", scenario.game)


def test_age_of_ultron_chapter_three_grants_deathtouch_and_a_plus_one_counter_off_pool():
    """Off-pool generality proof: Age of Ultron's own chapter III prints the
    identical "pump-or-grant, then counter on each of them" shape with a
    narrower subject (artifact creatures only), a keyword grant instead of a
    P/T pump, and a +1/+1 counter instead of a keyword one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Age of Ultron"],
            battlefield=["Ornithopter", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ornithopter = scenario.creature("Ornithopter", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    saga = scenario.put_onto_battlefield("Age of Ultron", "alice")
    _resolve_everything(scenario)  # the intrinsic lore counter, chapter I

    for _ in range(2):  # chapters II, III
        _next_chapter(scenario, saga)

    # "Artifact creatures you control" - Grizzly Bears is not one.
    assert has_keyword(ornithopter, "deathtouch", scenario.game)
    assert ornithopter.counter_count(Counter.PLUS_ONE) == 1
    assert not has_keyword(bears, "deathtouch", scenario.game)
    assert bears.counter_count(Counter.PLUS_ONE) == 0
