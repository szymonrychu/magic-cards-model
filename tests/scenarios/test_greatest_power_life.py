"""A life total changed by an amount counted off a *target player's* board.

One mechanic: "Target player gains X life, where X is the greatest power
among creatures they control" (Inscription of Abundance's second mode) and
its proof printing's "Target opponent loses life equal to the number of
creatures they control" (Villainous Wrath). "They" is the targeted player,
not the spell's controller, so the count is taken off that player's
creatures - and it is taken as the instruction is carried out.

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- **CR 608.2h** - information from the game "is determined only once, when
  the effect is applied".
- **CR 608.2c** - the instructions are followed in the order written, so
  Villainous Wrath counts before it destroys, and Inscription's first mode
  has already put its counters on as the second reads power.
- **CR 700.2a** - the caster chooses the modes as the spell is cast;
  **CR 700.2d** - more than one mode may be chosen when the spell allows it,
  and each chosen mode is still followed in the order written (CR 608.2c).
- **CR 702.33d** - "If this spell was kicked" asks whether the kicker was
  paid.
- **CR 107.2** - a number that can't be determined (no creatures, so no
  "greatest power") is 0.
- **CR 208.5** - a creature's power is what the layers leave it at.

Proof printing: Villainous Wrath (Modern, Pioneer and Standard legal per
Scryfall, 2026-09-23; not in any api deck) - a different verb (loses), amount
wording ("life equal to") and count (creatures, not greatest power) with the
same "they control" referent. No other Modern/Pioneer/Standard printing
reads "the greatest power among creatures they control" as an amount; see
MEMORY.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

INSCRIPTION = "Inscription of Abundance"
WRATH = "Villainous Wrath"


def _inscription_board(*, alice: list[str], bob: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[INSCRIPTION], battlefield=["Forest"] * 6 + alice)
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: Scenario, modes: list[int], targets: list, *, kicked: bool = False):
    casting = scenario.cast(INSCRIPTION)
    if kicked:
        casting.pay_kicker()
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    spell = scenario.put_on_stack(casting)
    return spell


def test_target_player_gains_the_greatest_power_among_their_creatures():
    """Bob controls Craw Wurm (6) and Grizzly Bears (2): targeted, he gains 6."""
    scenario = _inscription_board(alice=[], bob=["Craw Wurm", "Grizzly Bears"])

    _cast(scenario, [2], ["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 26
    assert scenario.player("alice").life == 20


def test_they_is_the_targeted_player_not_the_caster():
    """Alice casts it at bob while controlling the bigger creature herself:
    bob's own board is what counts (Grizzly Bears, 2), not alice's Craw Wurm."""
    scenario = _inscription_board(alice=["Craw Wurm"], bob=["Grizzly Bears"])

    _cast(scenario, [2], ["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 22


def test_the_caster_may_target_themself():
    """Alice targets herself: her own Craw Wurm counts."""
    scenario = _inscription_board(alice=["Craw Wurm"], bob=["Grizzly Bears"])

    _cast(scenario, [2], ["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 26
    assert scenario.player("bob").life == 20


def test_a_player_with_no_creatures_gains_nothing():
    """CR 107.2: no creatures, no greatest power - X is 0."""
    scenario = _inscription_board(alice=["Craw Wurm"], bob=[])

    _cast(scenario, [2], ["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 20


def test_the_greatest_power_is_read_as_the_spell_resolves():
    """CR 608.2h: Craw Wurm leaving bob's battlefield while the spell waits on
    the stack leaves Grizzly Bears as the greatest power."""
    scenario = _inscription_board(alice=[], bob=["Craw Wurm", "Grizzly Bears"])
    _cast(scenario, [2], ["bob"])

    scenario.game.destroy(scenario.creature("Craw Wurm", "bob"))
    scenario.resolve_top()

    assert scenario.player("bob").life == 22


def test_kicked_every_mode_resolves_in_order_and_power_includes_the_new_counters():
    """Kicked (CR 702.33d), all three modes chosen (CR 700.2a, 700.2d). Mode 1 puts
    two +1/+1 counters on alice's Grizzly Bears before mode 2 reads power
    (CR 608.2c), so alice gains 4, not 2; mode 3 has the 4/4 Bears fight
    bob's Grizzly Bears."""
    scenario = _inscription_board(alice=["Grizzly Bears"], bob=["Grizzly Bears"])
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario, [1, 2, 3], [alice_bears, "alice", alice_bears, bob_bears], kicked=True)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert scenario.game.characteristics_of(alice_bears).power_toughness == (4, 4)
    assert scenario.player("alice").life == 24
    assert bob_bears.zone is Zone.GRAVEYARD
    assert alice_bears.damage == 2


def test_kicked_any_number_includes_just_the_life_mode():
    """ "Choose any number" is any number: kicked, the second mode alone is a
    legal choice too."""
    scenario = _inscription_board(alice=[], bob=["Craw Wurm"])

    _cast(scenario, [2], ["bob"], kicked=True)
    scenario.resolve_top()

    assert scenario.player("bob").life == 26


# --------------------------------------------------------------------------
# Villainous Wrath (proof printing)
# --------------------------------------------------------------------------


def _wrath_board(*, alice: list[str], bob: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[WRATH], battlefield=["Swamp"] * 5 + alice)
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_villainous_wrath_counts_the_targets_creatures_then_destroys_all():
    """Bob controls three creatures, alice two: bob loses 3, then every
    creature is destroyed."""
    scenario = _wrath_board(
        alice=["Grizzly Bears", "Craw Wurm"], bob=["Grizzly Bears", "Grizzly Bears", "Craw Wurm"]
    )

    scenario.cast_and_resolve(WRATH, auto=True, targets=["bob"])

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20
    assert not [p for p in scenario.game.battlefield if "Creature" in p.card.type_line]


def test_villainous_wrath_against_an_empty_board_costs_nothing():
    """No creatures under the target's control: 0 life lost (CR 107.2's
    empty count), and the destroy half still runs over alice's creatures."""
    scenario = _wrath_board(alice=["Grizzly Bears"], bob=[])

    scenario.cast_and_resolve(WRATH, auto=True, targets=["bob"])

    assert scenario.player("bob").life == 20
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
