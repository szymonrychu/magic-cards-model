"""Scenario: Ferocious's own payoff shape, "Whenever this creature attacks
while you control a creature with power `<n>` or greater, until end of
turn, this creature gets `<P>`/`<T>` and creatures you control gain
`<keyword>`." - Wargling's own "Ferocious — Whenever this creature attacks
while you control a creature with power 4 or greater, until end of turn,
this creature gets +1/+0 and creatures you control gain trample."

Ferocious itself (CR 207.2c: an ability word, "no special rules meaning" -
just a printed label on the intervening *if*) and the "while you control a
creature with power N or greater" condition are both pre-existing, general
machinery: `machines/abilities._CONDITION_WHILE_CLAUSE` already splits any
"attacks while ..." condition into the ATTACKS event plus an intervening
*if* (CR 603.4), and `Game.condition_holds`'s own "you control a creature
with power N or greater" reading is the identical clause dozens of real
Khans-block Ferocious cards already exercise - nothing here is new.

What this session adds is the *effect* reader,
`machines/effects._merge_self_pump_and_group_keyword_grant_clauses`: a self
pump and a mass keyword grant sharing one printed duration, split into two
raw clauses by the clause splitter's bare "and" (`_CLAUSE_SEPARATOR`) before
either reaches `_parse_mixed_clause`. No other legal printing, real or in
this session's Scryfall snapshot (checked both `oracle-cards.jsonl` and a
live Scryfall search for `o:"this creature gets" o:"creatures you control
gain"`), carries this exact combined sentence - recorded, not asserted
around, in the dated MEMORY.md line. The reader's own generality is instead
exercised here across the axis that does vary card to card - the granted
keyword and the pump's own magnitude are read out of the sentence, not
hard-coded to trample/+1/+0 - and the pre-existing Ferocious condition is
proven separately, both holding and failing, the same way every other
intervening-*if* test in this suite does.

CR 207.2c and CR 603.4 were verified with `mise run rules:find` in the
session that wrote this file - see `machines/abilities.py`'s own docstring
for `_CONDITION_WHILE_CLAUSE`, which already cites the identical wording.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario


def board(*extra: str) -> Scenario:
    return Scenario().player("alice", battlefield=["Wargling", *extra]).player("bob")


def test_ferocious_holds_pumps_wargling_and_grants_the_team_trample():
    scenario = board("Wurmcoil Engine", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wargling = scenario.creature("Wargling")
    bears = scenario.creature("Grizzly Bears")
    assert scenario.game.power_of(scenario.creature("Wurmcoil Engine")) >= 4

    scenario.attack_with(wargling)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(wargling).power_toughness == (3, 2), "base 2/2, +1/+0"
    assert has_keyword(wargling, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game), (
        "creatures you control, not just self"
    )


def test_ferocious_fails_with_nothing_at_power_4_or_greater():
    scenario = board("Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wargling = scenario.creature("Wargling")
    bears = scenario.creature("Grizzly Bears")

    scenario.attack_with(wargling)

    assert scenario.game.stack == [], "CR 603.4: an unmet intervening if never triggers at all"
    assert scenario.game.characteristics_of(wargling).power_toughness == (2, 2)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)


def test_the_pump_and_grant_expire_at_the_end_of_turn():
    scenario = board("Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wargling = scenario.creature("Wargling")

    scenario.attack_with(wargling)
    scenario.resolve_top()
    assert has_keyword(wargling, Keyword.TRAMPLE, scenario.game)

    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert scenario.game.characteristics_of(wargling).power_toughness == (2, 2)
    assert not has_keyword(wargling, Keyword.TRAMPLE, scenario.game)
