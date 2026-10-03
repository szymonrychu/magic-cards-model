"""R0b T2: painlands and a painland-artifact, through the engine.

Llanowar Wastes, Caves of Koilos (`{T}: Add {C}.` / `{T}: Add <X> or <Y>. This
land deals 1 damage to you.`) and Talisman of Curiosity (the same on an
artifact). Rules verified with `mise run rules:find`:

- **CR 605.1a** - the coloured ability has no target and adds mana, so it is a
  mana ability: it never uses the stack.
- **CR 405.6c** - the mana is produced and the other effect happens
  immediately, as part of the same ability.
- **CR 120.1** - the permanent is the source of the damage, so a prevention
  effect or protection can see it.
- **CR 106.12** - tapping for mana is activating a mana ability with {T}.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

W, U, B, R, G, C = (
    Color.WHITE,
    Color.BLUE,
    Color.BLACK,
    Color.RED,
    Color.GREEN,
    Color.COLORLESS,
)

# card, the two colours its pain ability offers, a one-mana spell of the first
PAINLANDS = [
    ("Llanowar Wastes", B, G, "Dark Ritual"),
    ("Caves of Koilos", W, B, "Dark Ritual"),
    ("Talisman of Curiosity", G, U, "Opt"),
]
IDS = [row[0] for row in PAINLANDS]


def _board(name, hand=None):
    scenario = (
        Scenario()
        .player("alice", battlefield=[name], hand=hand or [], library=["Plains"] * 6)
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find(name, Zone.BATTLEFIELD)


@pytest.mark.parametrize("name,one,two,spell", PAINLANDS, ids=IDS)
def test_the_colourless_ability_is_free(name, one, two, spell):
    scenario, source = _board(name)
    scenario.activate(source, index=0)
    assert scenario.player("alice").mana_pool.floating == {C: 1}
    assert scenario.player("alice").life == 20
    assert scenario.game.damage_dealt_this_turn == []
    assert not scenario.game.stack


@pytest.mark.parametrize("name,one,two,spell", PAINLANDS, ids=IDS)
@pytest.mark.parametrize("pick", [0, 1])
def test_either_coloured_choice_deals_1_to_you_from_the_permanent_without_the_stack(
    name, one, two, spell, pick
):
    colour = (one, two)[pick]
    scenario, source = _board(name)
    result = scenario.activate(source, index=1, color=colour)
    assert result is None, "a mana ability never goes on the stack (CR 605.3b)"
    assert not scenario.game.stack
    assert scenario.player("alice").mana_pool.floating == {colour: 1}
    assert scenario.player("alice").life == 19
    (hit,) = scenario.game.damage_dealt_this_turn
    assert hit.source_id == source.id, "the land/artifact is the damage source (CR 120.1)"
    assert hit.recipient_player == "alice"
    assert hit.amount == 1
    assert source.tapped


@pytest.mark.parametrize("name,one,two,spell", PAINLANDS, ids=IDS)
def test_a_colour_outside_the_offered_pair_is_refused_with_no_damage(name, one, two, spell):
    scenario, source = _board(name)
    with pytest.raises(ValueError):
        scenario.activate(source, index=1, color=R if R not in (one, two) else Color.WHITE)
    assert scenario.player("alice").life == 20
    assert scenario.player("alice").mana_pool.floating == {}


@pytest.mark.parametrize("name,one,two,spell", PAINLANDS, ids=IDS)
def test_paying_a_coloured_cost_by_hand_pays_the_pain_once(name, one, two, spell):
    spell_colour = B if spell == "Dark Ritual" else U
    scenario, source = _board(name, hand=[spell])
    casting = scenario.cast(spell, username="alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(source, [spell_colour])
    payment.pay()
    scenario.put_on_stack(casting)
    assert scenario.player("alice").life == 19
    assert [hit.source_id for hit in scenario.game.damage_dealt_this_turn] == [source.id]


@pytest.mark.parametrize("name,one,two,spell", PAINLANDS, ids=IDS)
def test_the_auto_payer_pays_the_pain_for_a_coloured_cost(name, one, two, spell):
    scenario, source = _board(name, hand=[spell])
    scenario.cast_onto_stack(spell, username="alice", auto=True)
    assert source.tapped
    assert scenario.player("alice").life == 19


def test_the_auto_payer_takes_the_free_colourless_ability_for_a_generic_cost():
    scenario, source = _board("Llanowar Wastes", hand=["Sol Ring"])
    scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)
    assert source.tapped
    assert scenario.player("alice").life == 20, "{1} is paid with {C}, no pain"
    assert scenario.game.damage_dealt_this_turn == []


def test_a_prevention_shield_stops_the_rider_damage():
    from magic_cards_model.models.game import PreventionShield, ShieldKind

    scenario, source = _board("Caves of Koilos")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage to alice this turn",
            controller="alice",
            player="alice",
        )
    )
    scenario.activate(source, index=1, color=W)
    assert scenario.player("alice").mana_pool.floating == {W: 1}
    assert scenario.player("alice").life == 20


def test_a_second_printing_of_the_template_also_prefers_its_free_ability():
    """Karplusan Forest (not a listed card): a generic cost is paid with
    `{T}: Add {C}.`, a coloured one with the damaging ability."""
    scenario, source = _board("Karplusan Forest", hand=["Sol Ring"])
    scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)
    assert scenario.player("alice").life == 20

    scenario, source = _board("Karplusan Forest", hand=["Lightning Bolt"])
    scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=["bob"], auto=True)
    assert scenario.player("alice").life == 19
