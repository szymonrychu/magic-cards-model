"""Unearth: returning a card from the graveyard, briefly, with haste
(CR 702.84).

CR 702.84a: "Unearth is an activated ability that functions while the card
with unearth is in a graveyard. 'Unearth [cost]' means '[Cost]: Return this
card from your graveyard to the battlefield. It gains haste. Exile it at the
beginning of the next end step. If it would leave the battlefield, exile it
instead of putting it anywhere else. Activate only as a sorcery.'"

The card never prints that sentence - only "Unearth [cost]" - so the
activation is built from the rule's own wording the same way cycling's is
(`machines/keywords.cycling_activation`/`_synthetic_ability`,
`tests/scenarios/test_cycling.py`), and it functions off the battlefield, so
it joins `off_zone_abilities`'s single index space (CR 113.6j/113.6m)
alongside cycling and any printed off-battlefield ability.

CR 702.84a's replacement clause, "If it would leave the battlefield, exile
it instead of putting it anywhere else", is `machines/replacement.
exile_instead_of_leaving`'s replacement bound to the unearthed object; its
own corner cases (destroyed, bounced, sacrificed, the source gone) are in
`test_returned_creature_exiled_instead_of_leaving.py`, shared with Geth,
Thane of Contracts and Whip of Erebos. Below is the primary half: it
returns, it has haste, and it is exiled at the next end step if nothing else
happened to it first. See `docs/engine-coverage.md`.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.

Cityscape Leveler (Unearth {8}) is the assigned card. Fatestitcher (Unearth
{U}) is not in the deck pool and not named in the brief - cheap, blue, and a
much smaller creature - and proves `unearth_activation`/`_unearth_effect`
read any unearth cost rather than Cityscape Leveler's own {8}.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    KeywordActivation,
    off_zone_abilities,
    off_zone_activation,
    unearth_abilities,
    unearth_activation,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(**kwargs) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **kwargs)
        .player("bob", battlefield=["Mountain"])
    )


def pay_with(*sources):
    def hook(payment):
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))

    return hook


def test_the_unearth_ability_is_read_off_the_printed_line():
    (leveler,) = unearth_abilities(card("Cityscape Leveler"))
    assert leveler.cost == "{8}"
    assert leveler.cost_is_mana


def test_unearth_returns_the_card_with_haste():
    scenario = board(
        graveyard=["Cityscape Leveler"],
        battlefield=["Mountain"] * 8,
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*(["Mountain"] * 8))
    activation = unearth_activation(scenario.game, leveler, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    entered = activation.resolve()

    assert entered.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(entered).abilities
    assert entered.summoning_sick, "a returned permanent is a new object (CR 302.6)"


def test_unearth_is_exiled_at_the_next_end_step():
    scenario = board(graveyard=["Cityscape Leveler"], battlefield=["Mountain"] * 8).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(*(["Mountain"] * 8))
    activation = unearth_activation(scenario.game, leveler, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    entered = activation.resolve()

    while scenario.step is not Step.END_STEP:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert entered.zone is Zone.EXILE


def test_unearth_only_functions_in_the_graveyard():
    """CR 602.5/CR 702.84a: not the battlefield, not the hand."""
    scenario = board(battlefield=["Cityscape Leveler"] + ["Mountain"] * 8).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    leveler = scenario.creature("Cityscape Leveler")
    activation = unearth_activation(scenario.game, leveler, "alice")

    assert "functions in the graveyard" in (activation.why_not() or "")


def test_unearth_is_a_sorcery_speed_activation():
    """CR 702.84a's own "Activate only as a sorcery" clause."""
    scenario = board(graveyard=["Cityscape Leveler"], battlefield=["Mountain"] * 8).build()
    scenario.start_at(Step.END_STEP)

    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    activation = unearth_activation(scenario.game, leveler, "alice")

    assert "sorcery" in (activation.why_not() or "")


def test_off_zone_abilities_lists_unearth():
    """`ACTIVATE_OFF_ZONE`'s own single index space (CR 113.6j) - the same
    seat-facing path cycling already reaches through."""
    entries = off_zone_abilities(card("Cityscape Leveler"))
    assert [entry.family for entry in entries] == ["unearth"]

    scenario = board(graveyard=["Cityscape Leveler"], battlefield=["Mountain"] * 8).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    activation = off_zone_activation(scenario.game, leveler, "alice", 0)
    assert isinstance(activation, KeywordActivation)
    assert activation.keyword.lower() == "unearth"


# -- generality: a second, un-named unearth printing -------------------------


def test_fatestitcher_reads_its_own_differently_shaped_unearth_cost():
    (ability,) = unearth_abilities(card("Fatestitcher"))
    assert ability.cost == "{U}"


def test_fatestitcher_unearths_for_its_own_cost():
    scenario = board(graveyard=["Fatestitcher"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    stitcher = scenario.find("Fatestitcher", Zone.GRAVEYARD, "alice")
    (island,) = scenario.untapped_sources("Island")
    activation = unearth_activation(scenario.game, stitcher, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(island, mana_from(island))
    payment.pay()
    activation.activate()
    entered = activation.resolve()

    assert entered.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(entered).abilities
