"""Affordability of a spell with {X} in its mana cost.

X is announced as the spell is cast, so before the cast nobody has chosen it.
The question `legal_actions` answers is whether the spell can be cast at all,
and the cheapest legal announcement decides that: if X=0 is payable the cast
is affordable, and since a larger X only adds generic mana, a mana cost that
is unpayable at X=0 is unpayable at every X.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 107.3a** - the controller "chooses and announces the value of X as part
  of casting the spell".
- **CR 107.1b / 107.1c** - a chosen number is a positive number or zero, so 0
  is always a legal choice unless a card says otherwise.
- **CR 601.2b** - X is announced at CR 601.2b, before the total cost is
  determined and paid.

No card in the pool prints a minimum for X on its mana cost ("X can't be 0"
appears only on a suspend cost there), and the engine does not read such a
minimum, so the minimum is always 0 here. `docs/engine-coverage.md` records
that gap.
"""

from magic_cards_model.machines import Step, legal_actions, payability
from magic_cards_model.models import ActionKind, Affordability, Zone
from tests.scenarios.harness import Scenario


def _board(hand, battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_row(scenario, name):
    card = scenario.find(name, Zone.HAND, "alice")
    (row,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == card.id and action.kind is ActionKind.CAST
    ]
    return row


def test_walking_ballista_is_affordable_for_x_equal_zero():
    scenario = _board(["Walking Ballista"], battlefield=["Island", "Island"])

    row = _cast_row(scenario, "Walking Ballista")

    assert row.affordable is Affordability.YES
    assert row.x_range == (0, None)
    assert payability(
        scenario.game, "alice", scenario.find("Walking Ballista", Zone.HAND, "alice")
    ).payable


def test_the_cast_agrees_that_x_equal_zero_is_legal():
    scenario = _board(["Walking Ballista"], battlefield=["Island", "Island"])
    ballista = scenario.find("Walking Ballista", Zone.HAND, "alice")

    scenario.game.cast(ballista, "alice", x_value=0)

    assert ballista.zone is Zone.STACK


def test_the_colored_part_still_has_to_be_paid():
    """Green Sun's Zenith is {X}{G}: X=0 still costs {G}."""
    islands = _board(["Green Sun's Zenith"], battlefield=["Island", "Island"])
    forest = _board(["Green Sun's Zenith"], battlefield=["Forest"])

    assert _cast_row(islands, "Green Sun's Zenith").affordable is Affordability.NO
    assert _cast_row(forest, "Green Sun's Zenith").affordable is Affordability.YES


def test_an_x_spell_with_a_plan_pays_with_the_x_equal_zero_plan():
    scenario = _board(["Green Sun's Zenith"], battlefield=["Forest", "Forest"])

    row = _cast_row(scenario, "Green Sun's Zenith")

    assert row.affordable is Affordability.YES
    assert [entry.name for entry in row.pays_with] == ["Forest"]


def test_an_x_in_an_additional_cost_is_announced_at_its_minimum_too():
    """CR 107.3a names additional costs as well: Toxic Deluge's "pay X life"
    is paid for the X announced, and X=0 pays 0 life (CR 119.4b)."""
    scenario = _board(["Toxic Deluge"], battlefield=["Swamp", "Swamp", "Swamp"])

    row = _cast_row(scenario, "Toxic Deluge")

    assert row.affordable is Affordability.YES, row.unaffordable_reason
    assert row.x_range == (0, None)


def test_an_x_in_an_additional_cost_does_not_pay_the_mana():
    scenario = _board(["Toxic Deluge"], battlefield=["Swamp"])

    assert _cast_row(scenario, "Toxic Deluge").affordable is Affordability.NO


# ---------------------------------------------------------------------------
# The row's displayed cost keeps X unresolved - CR 107.3a says nobody has
# announced a value yet, so folding the X=0 stand-in used to judge
# affordability into `Action.cost`/`mana_cost` would show a number nobody
# chose. Only the affordability *verdict* is judged at X=0 (CR 107.1b); the
# strings a caller reads keep the printed X, mandatory additional costs
# included when they do not themselves depend on the unannounced X.
# ---------------------------------------------------------------------------


def test_a_pure_x_mana_cost_keeps_x_in_both_strings():
    """Walking Ballista and Chalice of the Void both print {X}{X}: the
    displayed cost is the printed cost, not the X=0 total it is judged by."""
    for name in ("Walking Ballista", "Chalice of the Void"):
        scenario = _board([name], battlefield=["Island", "Island"])

        row = _cast_row(scenario, name)

        assert row.affordable is Affordability.YES, (name, row.unaffordable_reason)
        assert row.cost == "{X}{X}", name
        assert row.mana_cost == "{X}{X}", name


def test_a_single_x_mana_cost_keeps_x_in_both_strings():
    """Engineered Explosives prints a lone {X}."""
    scenario = _board(["Engineered Explosives"], battlefield=["Island"])

    row = _cast_row(scenario, "Engineered Explosives")

    assert row.affordable is Affordability.YES, row.unaffordable_reason
    assert row.cost == "{X}"
    assert row.mana_cost == "{X}"


def test_a_colored_x_mana_cost_keeps_x_in_both_strings():
    """Meltdown proves this on a card outside the four the regression named,
    with a different mana-cost shape ({X}{R} rather than a bare {X} or a
    doubled {X}{X})."""
    scenario = _board(["Meltdown"], battlefield=["Mountain"])

    row = _cast_row(scenario, "Meltdown")

    assert row.affordable is Affordability.YES, row.unaffordable_reason
    assert row.cost == "{X}{R}"
    assert row.mana_cost == "{X}{R}"


def test_an_x_mana_cost_alongside_colored_pips_keeps_x_in_mana_cost():
    """Disrupting Shoal is {X}{U}{U}: the row that pays with mana (as opposed
    to the row that exiles a blue card instead, CR 118.9) must not drop the X
    the way it did while affordability judged the X=0 total directly."""
    scenario = _board(["Disrupting Shoal"], battlefield=["Island", "Island", "Island"])
    shoal = scenario.find("Disrupting Shoal", Zone.HAND, "alice")
    (row,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == shoal.id
        and action.kind is ActionKind.CAST
        and action.alternative_cost is None
    ]

    assert row.affordable is Affordability.YES, row.unaffordable_reason
    assert row.cost == "{X}{U}{U}"
    assert row.mana_cost == "{X}{U}{U}"


def test_an_x_in_an_additional_cost_is_dropped_from_the_displayed_extra():
    """Toxic Deluge's mana cost, {2}{B}, has no X in it - only its printed
    additional cost ("pay X life") does, and that cannot be shown resolved
    to the X=0 stand-in (that would claim the spell always costs 0 life) nor
    literally as "X" (a life payment carries only a concrete amount). The
    honest, smallest choice is to leave the unresolved extra out of the
    string, matching what the cost showed before this row counted mandatory
    additional costs at all."""
    scenario = _board(["Toxic Deluge"], battlefield=["Swamp", "Swamp", "Swamp"])

    row = _cast_row(scenario, "Toxic Deluge")

    assert row.affordable is Affordability.YES, row.unaffordable_reason
    assert row.cost == "{2}{B}"
    assert row.mana_cost == "{2}{B}"
