"""A permanent's static "creatures [with power <comparison>] can't attack [you]"
- an attack restriction on *other* creatures (CR 508.1c).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this file.

- **CR 508.1c** - "The active player checks each creature they control to see
  whether it's affected by any restrictions (effects that say a creature can't
  attack, or that it can't attack unless some condition is met). If any
  restrictions are being disobeyed, the declaration of attackers is illegal."
- **CR 508.1d** - requirements are only counted when they "could be obeyed
  without disobeying any restrictions", so a restricted "attacks each combat if
  able" creature carries no requirement.
- **CR 508.1** - an illegal declaration returns the game to the moment before
  it (CR 733): nothing is tapped, nothing is attacking.
- **CR 109.5** - "you"/"your" in a static ability is "the current controller
  of the object it's on": Ensnaring Bridge counts its *controller's* hand, and
  Reverence's "can't attack you" protects its controller, whoever is attacking.
- **CR 611.3a** - a static ability's effect "isn't 'locked in'; it applies at
  any given moment to whatever its text indicates": hand size and power are
  read at declaration, after pumps and draws.
- **CR 604.2** - the effect lasts only while the permanent is on the
  battlefield and has the ability.

The reported card is Ensnaring Bridge (live game 0cf08288: two 3/3s attacked
through a Bridge whose controller held 2 cards). Generality is proven by
Reverence ("Creatures with power 2 or less can't attack you." - a printed
number, the other comparison direction, and a defender scope) and Blazing
Archon ("Creatures can't attack you." - no power qualifier at all), neither in
any deck.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario

BRIDGE = "Ensnaring Bridge"


def _bridge_board(bob_hand: int, *alice: str, bob_library: int = 0) -> Scenario:
    """Alice (active) attacks; bob controls Ensnaring Bridge holding
    `bob_hand` Islands."""
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player(
            "bob",
            battlefield=[BRIDGE],
            hand=["Island"] * bob_hand,
            library=["Island"] * bob_library,
        )
    )


def _attacker_ids(scenario) -> set:
    return {
        action.card_id
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.DECLARE_ATTACKER
    }


# --------------------------------------------------------------------------
# Ensnaring Bridge - the reported card
# --------------------------------------------------------------------------


def test_a_creature_with_power_greater_than_the_bridge_controllers_hand_cannot_attack():
    """The live bug: a 3/3 against a Bridge with 2 cards in its controller's
    hand is refused, with the restriction named in the reason."""
    scenario = _bridge_board(2, "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")

    assert not scenario.can_attack(giant)
    reason = scenario.game.why_cannot_attack(giant, "bob")
    assert reason is not None and BRIDGE in reason and "CR 508.1c" in reason
    with pytest.raises(ValueError, match=BRIDGE):
        scenario.attack_with(giant)
    assert scenario.attackers() == []
    assert giant.untapped


def test_power_exactly_equal_to_the_hand_size_may_attack():
    """ "Greater than" is strict: a 2/2 against 2 cards attacks."""
    scenario = _bridge_board(2, "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")

    scenario.attack_with(bears)

    assert scenario.attackers() == [bears]


def test_a_declaration_naming_a_restricted_creature_declares_nothing():
    """CR 508.1: the whole declaration is illegal, so the legal Bears listed
    ahead of the restricted Giant is not left tapped and attacking."""
    scenario = _bridge_board(2, "Grizzly Bears", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")

    with pytest.raises(ValueError, match=BRIDGE):
        scenario.attack_with(bears, giant)

    assert scenario.attackers() == []
    assert bears.untapped and giant.untapped


def test_legal_actions_offer_only_the_creatures_the_bridge_allows():
    """The seat's attacker candidates agree with the declaration check."""
    scenario = _bridge_board(2, "Grizzly Bears", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")

    offered = _attacker_ids(scenario)

    assert bears.id in offered
    assert giant.id not in offered


def test_zero_cards_in_hand_stops_everything_with_positive_power():
    """An empty hand: a 1/1 cannot attack, a 0-power creature still can."""
    scenario = _bridge_board(0, "Memnite", "Ornithopter").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    memnite = scenario.creature("Memnite")
    thopter = scenario.creature("Ornithopter")

    assert not scenario.can_attack(memnite)
    scenario.attack_with(thopter)
    assert scenario.attackers() == [thopter]


def test_the_hand_is_counted_at_declaration_not_when_the_bridge_arrived():
    """CR 611.3a: the Bridge controller drawing a card before attackers are
    declared lets the 3/3 through."""
    scenario = _bridge_board(2, "Hill Giant", bob_library=1).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    assert not scenario.can_attack(giant)

    scenario.draw(1, "bob")

    assert scenario.can_attack(giant)
    scenario.attack_with(giant)
    assert scenario.attackers() == [giant]


def test_pumped_power_is_what_is_compared():
    """CR 611.3a with CR 613 layers: a Giant Growth on a 2/2 makes it a 5/5,
    and a 5/5 cannot attack through a 2-card Bridge."""
    scenario = (
        Scenario()
        .player("alice", hand=["Giant Growth"], battlefield=["Forest", "Grizzly Bears"])
        .player("bob", battlefield=[BRIDGE], hand=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()

    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError, match=BRIDGE):
        scenario.attack_with(bears)


def test_the_bridge_controllers_own_creatures_are_restricted_by_their_own_hand():
    """ "Creatures" is every creature, including its controller's: alice's own
    Bridge with alice holding one card stops her 2/2 but not her 1/1."""
    scenario = (
        Scenario()
        .player("alice", hand=["Island"], battlefield=[BRIDGE, "Grizzly Bears", "Memnite"])
        .player("bob", hand=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    memnite = scenario.creature("Memnite")

    assert not scenario.can_attack(bears)
    scenario.attack_with(memnite)
    assert scenario.attackers() == [memnite]


def test_casting_from_hand_before_combat_shrinks_the_count_for_the_bridge_controller():
    """Alice controls the Bridge and holds 3 cards; Giant Growth from her hand
    leaves 2, so her own 3/3 (3 > 2) can no longer attack, and the pumped
    Bears (5 > 2) cannot either - the hand drop and the pump both count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth", "Island", "Island"],
            battlefield=[BRIDGE, "Forest", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    assert scenario.can_attack(giant), "3 cards in hand: the 3/3 may attack"
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()

    assert len(scenario.player("alice").hand) == 2
    assert not scenario.can_attack(giant)
    assert not scenario.can_attack(bears)


def test_each_bridge_counts_its_own_controllers_hand():
    """CR 109.5: two Bridges, two controllers. Alice's own Bridge (alice holds
    5) allows her 3/3; bob's Bridge (bob holds 2) still stops it - every
    restriction must be obeyed (CR 508.1c)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Island"] * 5, battlefield=[BRIDGE, "Hill Giant", "Grizzly Bears"])
        .player("bob", battlefield=[BRIDGE], hand=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    bears = scenario.creature("Grizzly Bears")

    assert not scenario.can_attack(giant)
    scenario.attack_with(bears)
    assert scenario.attackers() == [bears]


def test_a_restricted_attacks_each_combat_creature_carries_no_requirement():
    """CR 508.1d: Juggernaut (5/3, "attacks each combat if able") under a
    2-card Bridge cannot attack, so declaring no attackers is legal."""
    scenario = _bridge_board(2, "Juggernaut").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    juggernaut = scenario.creature("Juggernaut")

    assert not scenario.can_attack(juggernaut)
    scenario.attack_with()
    assert scenario.attackers() == []


def test_the_restriction_ends_when_the_bridge_leaves():
    """CR 604.2: once the Bridge is gone, nothing restricts the 3/3."""
    scenario = _bridge_board(0, "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    bridge = scenario.find(BRIDGE, Zone.BATTLEFIELD, "bob")
    assert not scenario.can_attack(giant)

    scenario.game.destroy(bridge)

    assert scenario.can_attack(giant)


# --------------------------------------------------------------------------
# Reverence - a printed number, "or less", and "can't attack you"
# --------------------------------------------------------------------------


def test_reverence_stops_small_creatures_attacking_its_controller():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Reverence"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")

    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError, match="Reverence"):
        scenario.attack_with(bears)
    scenario.attack_with(giant)
    assert scenario.attackers() == [giant]


def test_reverence_does_not_stop_attacks_on_its_controllers_planeswalker():
    """ "Can't attack *you*" names the player, not the planeswalkers they
    control: the 2/2 may still attack bob's Jace Beleren."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Reverence", "Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    assert not scenario.can_attack(bears, defending="bob")
    scenario.attack_with(bears, defending=jace)
    assert scenario.attackers() == [bears]


def test_reverence_does_not_restrict_its_controllers_own_attacks():
    """CR 109.5: "you" is Reverence's controller, so alice's own Reverence
    says nothing about her 2/2 attacking bob."""
    scenario = (
        Scenario().player("alice", battlefield=["Reverence", "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")

    scenario.attack_with(bears)
    assert scenario.attackers() == [bears]


def test_bridge_and_reverence_together_leave_only_the_gap_between_them():
    """Two restrictions, both obeyed (CR 508.1c): bob holds 2 cards. Reverence
    stops power 2 or less, the Bridge stops power 3+ - nothing attacks bob."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Memnite"])
        .player("bob", battlefield=[BRIDGE, "Reverence"], hand=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert _attacker_ids(scenario) == set()
    for name in ("Grizzly Bears", "Hill Giant", "Memnite"):
        assert not scenario.can_attack(scenario.creature(name))


# --------------------------------------------------------------------------
# Blazing Archon - no power qualifier at all
# --------------------------------------------------------------------------


def test_blazing_archon_stops_every_creature_attacking_its_controller():
    """ "Creatures can't attack you." - no qualifier, so even a 0-power
    creature is stopped; nothing is offered against bob."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ornithopter", "Hill Giant"])
        .player("bob", battlefield=["Blazing Archon"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert _attacker_ids(scenario) == set()
    with pytest.raises(ValueError, match="Blazing Archon"):
        scenario.attack_with(scenario.creature("Ornithopter"))


def test_blazing_archon_leaves_its_controllers_planeswalker_attackable():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Blazing Archon", "Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    scenario.attack_with(giant, defending=jace)
    assert scenario.attackers() == [giant]


# --------------------------------------------------------------------------
# Composing with requirements across every defender (CR 508.1d)
# --------------------------------------------------------------------------


def _brigand_against_reverence(*bob: str) -> Scenario:
    """Alice's Goblin Brigand (2/2, "attacks each combat if able")
    against bob's Reverence, plus whatever else bob controls."""
    return (
        Scenario()
        .player("alice", battlefield=["Goblin Brigand"])
        .player("bob", battlefield=["Reverence", *bob])
    )


def test_a_must_attack_creature_restricted_from_the_player_must_attack_the_planeswalker():
    """CR 508.1d: Reverence stops the 2/2 attacking bob, but not bob's Jace
    Beleren, so attacking Jace is a requirement that can be obeyed, and
    declaring nobody obeys fewer requirements than possible."""
    scenario = _brigand_against_reverence("Jace Beleren").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    brigand = scenario.creature("Goblin Brigand")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    scenario.attack_with(brigand, defending=jace)
    assert scenario.attackers() == [brigand]


def test_an_unscripted_seat_sends_the_must_attack_creature_at_the_planeswalker():
    """The default declaration obeys the requirement through the one
    defender the restriction leaves open."""
    scenario = _brigand_against_reverence("Jace Beleren").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    brigand = scenario.creature("Goblin Brigand")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    scenario.game.declare_attackers_step()

    assert scenario.attackers() == [brigand]
    attack = scenario.game.combat.attack_by(brigand.id)
    assert attack is not None and attack.defender.card_id == jace.id


def test_with_no_planeswalker_the_restricted_must_attack_creature_may_stay_home():
    """Negative control: with nothing but bob to attack, Reverence leaves
    the requirement unobeyable, so declaring nobody is legal."""
    scenario = _brigand_against_reverence().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()
    assert scenario.attackers() == []


# --------------------------------------------------------------------------
# A declaration is judged whole (CR 508.1)
# --------------------------------------------------------------------------


def test_naming_the_same_creature_twice_declares_nothing():
    """CR 508.1a-b: each chosen creature attacks one player, planeswalker or
    battle, so naming one twice is illegal - and the whole declaration is,
    leaving the first copy neither tapped nor attacking."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Jace Beleren"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="more than once"):
        scenario.game.declare_attackers([(bears, "bob"), (bears, jace)])

    assert scenario.attackers() == []
    assert bears.untapped
