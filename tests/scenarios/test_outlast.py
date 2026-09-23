"""Scenario: Outlast (CR 702.107), a keyword-line activated ability.

Every rule below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 702.107a** - "Outlast is an activated ability. 'Outlast [cost]' means
  '[Cost], {T}: Put a +1/+1 counter on this creature. Activate only as a
  sorcery.'"
- **CR 602.5d** - "Activate only as a sorcery" means the CR 307.5 timing
  window (priority, own main phase, empty stack), not that the ability is a
  sorcery.
- **CR 602.5a / CR 302.6** - a creature with `{T}` in an activation cost
  cannot activate it unless it has been controlled since its controller's
  most recent turn began.

The keyword line itself never prints the ability - "Outlast {1}{W}" is one
line and the ability it means is another - so this goes through the same
synthetic `KeywordActivation` shape as equip and cycling
(`machines/keywords.outlast_activation`).

Ainok Bond-Kin (Outlast {1}{W}) is off-pool: it also prints "Each creature
you control with a +1/+1 counter on it has first strike," so its own
activation is proof both that outlast puts the counter and that the static
ability reading that counter already works end to end. Abzan Falconer
(Outlast {W}, the same static line granting flying instead) is the reported
card and is proven separately so nothing here is read off Ainok Bond-Kin's
own cost or grant.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import outlast_abilities, outlast_activation
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(creature: str, cost_sources: list[str], *extra: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[creature, *cost_sources, *extra])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def outlast(scenario, creature, sources, username="alice"):
    activation = outlast_activation(scenario.game, creature, username)
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


# --------------------------------------------------------------------------
# The keyword line itself (CR 702.107a)
# --------------------------------------------------------------------------


def test_outlast_expands_to_the_cr_702_107a_ability():
    (ability,) = outlast_abilities(card("Ainok Bond-Kin"))
    assert ability.cost == "{1}{W}"


# --------------------------------------------------------------------------
# Timing: sorcery speed only (CR 602.5d, CR 307.5)
# --------------------------------------------------------------------------


def test_outlast_can_only_be_activated_as_a_sorcery():
    scenario = board("Ainok Bond-Kin", ["Plains", "Plains"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)  # not alice's main phase
    ainok = scenario.creature("Ainok Bond-Kin")
    ainok.summoning_sick = False

    activation = outlast_activation(scenario.game, ainok, "alice")
    assert "only be activated as a sorcery" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        activation.begin_paying()


def test_outlast_is_refused_at_instant_speed_with_something_on_the_stack():
    """CR 307.5's own "stack must be empty" half of "as a sorcery" - alice's
    own main phase is not enough with a spell still on the stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Ainok Bond-Kin", "Plains", "Plains", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ainok = scenario.creature("Ainok Bond-Kin")
    ainok.summoning_sick = False
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])

    activation = outlast_activation(scenario.game, ainok, "alice")
    assert "only be activated as a sorcery" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        activation.begin_paying()


def test_outlast_is_refused_while_summoning_sick():
    """CR 602.5a, CR 302.6: `start_at` runs the untap step on its way in, which
    clears summoning sickness for anything controlled since before the game -
    so this creature has to actually arrive this turn, cast from hand exactly
    like `test_activated_abilities.py`'s own Llanowar Elves proof, rather than
    starting pre-placed on the battlefield."""
    scenario = (
        Scenario()
        .player("alice", hand=["Ainok Bond-Kin"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_sources = scenario.untapped_sources("Plains", "Plains")
    ainok = scenario.cast_and_resolve("Ainok Bond-Kin", *cast_sources)

    assert ainok.summoning_sick
    activation = outlast_activation(scenario.game, ainok, "alice")
    reason = activation.why_not()
    assert reason is not None and "most recent turn began" in reason
    with pytest.raises(ValueError, match="most recent turn began"):
        activation.begin_paying()


# --------------------------------------------------------------------------
# The effect: puts the counter, and the static ability that reads it
# --------------------------------------------------------------------------


def test_outlast_puts_a_plus_one_plus_one_counter_and_taps_the_creature():
    scenario = board("Ainok Bond-Kin", ["Plains", "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ainok = scenario.creature("Ainok Bond-Kin")
    ainok.summoning_sick = False
    sources = scenario.untapped_sources("Plains", "Plains")

    activation = outlast(scenario, ainok, sources)
    assert ainok.tapped, "CR 702.107a's own {T} half of the cost"
    assert ainok.counters[Counter.PLUS_ONE] == 0, "the ability is on the stack, not resolved yet"

    result = activation.resolve()
    assert result == 1
    assert ainok.counters[Counter.PLUS_ONE] == 1


def test_ainok_bond_kin_grants_first_strike_to_a_creature_carrying_the_counter():
    """Its own static line: "Each creature you control with a +1/+1 counter
    on it has first strike" - proven end to end, not just that the parser
    reads the sentence."""
    scenario = board("Ainok Bond-Kin", ["Plains", "Plains"], "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ainok = scenario.creature("Ainok Bond-Kin")
    bears = scenario.creature("Grizzly Bears")
    ainok.summoning_sick = False
    sources = scenario.untapped_sources("Plains", "Plains")

    assert not has_keyword(ainok, Keyword.FIRST_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)

    outlast(scenario, ainok, sources).resolve()

    assert has_keyword(ainok, Keyword.FIRST_STRIKE, scenario.game), "carries its own counter now"
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game), "no counter on this one"


def test_abzan_falconer_outlast_is_the_same_ability_at_a_different_cost():
    """The reported card: Outlast {W}, granting flying instead of first
    strike - proof the keyword expansion is not Ainok Bond-Kin's own text."""
    scenario = board("Abzan Falconer", ["Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    falconer = scenario.creature("Abzan Falconer")
    falconer.summoning_sick = False
    (plains,) = scenario.untapped_sources("Plains")

    (ability,) = outlast_abilities(card("Abzan Falconer"))
    assert ability.cost == "{W}"

    activation = outlast(scenario, falconer, [plains])
    activation.resolve()

    assert falconer.counters[Counter.PLUS_ONE] == 1
    assert has_keyword(falconer, Keyword.FLYING, scenario.game)
