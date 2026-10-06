"""Scenario: damage a resolving spell redirects (CR 614.9) or doubles (CR
614.1a, CR 701.10g) for the rest of the turn, and the turn's "Damage can't be
prevented" beside it (CR 615.12).

Rules, each read in full with `mise run rules:find`:

- CR 614.9 - "Some effects replace damage dealt to one battle, creature,
  planeswalker, or player with the same damage dealt to another battle,
  creature, planeswalker, or player; such effects are called redirection
  effects. If one of those permanents is no longer on the battlefield when the
  damage would be redirected, or is no longer a battle, creature, or
  planeswalker when the damage would be redirected, the effect does nothing."
- CR 609.7a - "If an effect requires a player to choose a source of damage,
  they may choose a permanent; a spell on the stack ... The source is chosen
  when the effect is created."
- CR 614.1a - "Effects that use the word "instead" are replacement effects."
- CR 615.12 - unpreventable damage: prevention effects prevent none of it.

Printings: Kor Dirge, Turn the Tables, Insult // Injury (listed); Carom (proof:
"The next 1 damage ... is dealt to another target creature instead.", with a
"Draw a card." after it), Razia, Boros Archangel (proof: the same redirection
from an activated ability), Gratuitous Violence (proof: "If a creature you
control would deal damage to a permanent or player, it deals double that
damage instead." - the widened doubling reader on a permanent).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def test_every_listed_and_proof_card_is_handled():
    for name in (
        "Kor Dirge",
        "Turn the Tables",
        "Insult // Injury",
        "Carom",
        "Razia, Boros Archangel",
        "Gratuitous Violence",
    ):
        outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
        assert outcomes == {"handled"}, (name, outcomes)


# -- Kor Dirge: all damage from a chosen source, to another creature -----------


def _bob_attacks(alice_hand, alice_lands, *, attackers, alice_creatures=(), bob_extra=()):
    scenario = (
        Scenario()
        .player("bob", battlefield=[*attackers, *bob_extra], library=["Island"] * 5)
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*alice_lands, *alice_creatures],
            library=["Plains"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _alice_casts(scenario, name, *sources, targets=None):
    """Cast in bob's turn: bob, the active player, passes priority first."""
    if scenario.priority_holder == "bob":
        scenario.pass_priority("bob")
    return scenario.cast_and_resolve(name, *sources, username="alice", targets=targets)


def test_kor_dirge_redirects_the_chosen_sources_damage():
    scenario = _bob_attacks(
        ["Kor Dirge"],
        ["Swamp"] * 3,
        attackers=["Hill Giant"],
        alice_creatures=["Grizzly Bears"],
        bob_extra=["Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(giant, defending="alice")
    scenario.block(giant, bears)

    scenario.will_choose_cards(giant)
    _alice_casts(
        scenario,
        "Kor Dirge",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[bears, lions],
    )
    scenario.combat_damage()
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is not Zone.BATTLEFIELD  # the Giant's 3 went to the Lions
    assert giant.damage == 2  # the Bears' own damage is untouched


def test_kor_dirge_leaves_another_sources_damage_alone():
    scenario = _bob_attacks(
        ["Kor Dirge"],
        ["Swamp"] * 3,
        attackers=["Hill Giant", "Raging Goblin"],
        alice_creatures=["Grizzly Bears"],
        bob_extra=["Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    goblin = scenario.creature("Raging Goblin", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(goblin, defending="alice")
    scenario.block(goblin, bears)

    scenario.will_choose_cards(giant)
    _alice_casts(
        scenario,
        "Kor Dirge",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[bears, lions],
    )
    scenario.combat_damage()

    assert bears.damage == 1
    assert lions.damage == 0


def test_kor_dirge_does_nothing_once_the_other_creature_is_gone():
    """CR 614.9: the redirect target has left - the damage is dealt where it
    was going."""
    scenario = _bob_attacks(
        ["Kor Dirge", "Lightning Bolt"],
        ["Swamp"] * 3 + ["Mountain"],
        attackers=["Hill Giant"],
        alice_creatures=["Grizzly Bears"],
        bob_extra=["Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(giant, defending="alice")
    scenario.block(giant, bears)
    scenario.will_choose_cards(giant)
    _alice_casts(
        scenario,
        "Kor Dirge",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[bears, lions],
    )
    _alice_casts(
        scenario,
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        targets=[lions],
    )
    scenario.state_based_actions()

    scenario.combat_damage()
    scenario.state_based_actions()

    assert bears.zone is not Zone.BATTLEFIELD


# -- Turn the Tables: all combat damage to you, to an attacker ------------------


def test_turn_the_tables_sends_all_combat_damage_to_the_attacker():
    scenario = _bob_attacks(
        ["Turn the Tables"], ["Plains"] * 5, attackers=["Hill Giant", "Grizzly Bears"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.attack_with(bears, defending="alice")
    scenario.no_blocks()

    _alice_casts(
        scenario,
        "Turn the Tables",
        *scenario.untapped_sources(*["Plains"] * 5, username="alice"),
        targets=[giant],
    )
    scenario.combat_damage()
    scenario.state_based_actions()

    assert scenario.player("alice").life == 20
    assert giant.zone is not Zone.BATTLEFIELD  # 3 + 2 damage on a 3/3


def test_turn_the_tables_attacker_gone_damage_is_dealt_to_you():
    scenario = _bob_attacks(
        ["Turn the Tables", "Lightning Bolt"],
        ["Plains"] * 5 + ["Mountain"],
        attackers=["Hill Giant", "Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.attack_with(bears, defending="alice")
    scenario.no_blocks()
    _alice_casts(
        scenario,
        "Turn the Tables",
        *scenario.untapped_sources(*["Plains"] * 5, username="alice"),
        targets=[bears],
    )
    _alice_casts(
        scenario,
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        targets=[bears],
    )
    scenario.state_based_actions()

    scenario.combat_damage()

    assert scenario.player("alice").life == 17


def test_turn_the_tables_leaves_noncombat_damage_alone():
    scenario = _bob_attacks(
        ["Turn the Tables"], ["Plains"] * 5, attackers=["Hill Giant"], bob_extra=["Mogg Fanatic"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    fanatic = scenario.creature("Mogg Fanatic", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.no_blocks()
    _alice_casts(
        scenario,
        "Turn the Tables",
        *scenario.untapped_sources(*["Plains"] * 5, username="alice"),
        targets=[giant],
    )

    scenario.activate(fanatic, username="bob", sacrificing=[fanatic], targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 19
    assert giant.damage == 0


# -- Carom and Razia: the next N damage ------------------------------------------


def test_carom_redirects_only_the_next_one_damage_and_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Carom", "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Mountain"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Carom", *scenario.untapped_sources("Plains", "Plains"), targets=[giant, bears]
    )
    assert len(scenario.player("alice").hand) == hand_before  # Carom left, a card came
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )

    assert giant.damage == 2
    assert bears.damage == 1


def test_razia_redirects_from_an_activated_ability():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Razia, Boros Archangel", "Grizzly Bears", "Mountain"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    razia = scenario.creature("Razia, Boros Archangel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(razia, targets=[bears, giant])
    scenario.resolve_top()
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD
    assert giant.zone is not Zone.BATTLEFIELD


# -- Insult: double damage from your sources, and none of it prevented ----------


def _insult_board(**extra):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Insult // Injury", *extra.get("hand", [])],
            battlefield=["Mountain"] * 4 + extra.get("battlefield", []),
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=extra.get("bob_hand", []),
            battlefield=extra.get("bob_battlefield", []),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Insult")
    casting.cast_as_split_half("Insult")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_insult_doubles_a_spell_you_control():
    scenario = _insult_board(hand=["Lightning Bolt"])

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert scenario.player("bob").life == 14


def test_insult_doubles_your_creatures_combat_damage():
    scenario = _insult_board(battlefield=["Savannah Lions"])
    lions = scenario.creature("Savannah Lions", "alice")

    scenario.attack_with(lions, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16


def test_insult_does_not_double_an_opponents_source():
    scenario = _insult_board(battlefield=["Hill Giant"], bob_battlefield=["Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, bears)
    scenario.combat_damage()

    assert giant.damage == 2  # bob's Bears are not "a source you control"
    assert bears.damage == 6 or bears.zone is not Zone.BATTLEFIELD


def test_insult_damage_cannot_be_prevented_by_fog():
    scenario = _insult_board(
        battlefield=["Savannah Lions"], bob_hand=["Fog"], bob_battlefield=["Forest"]
    )
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(lions, defending="bob")
    scenario.no_blocks()
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Fog", *scenario.untapped_sources("Forest", username="bob"), username="bob"
    )

    scenario.combat_damage()

    assert scenario.player("bob").life == 16


def test_insult_ends_with_the_turn():
    scenario = _insult_board()
    assert scenario.game.created_replacements

    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()

    assert scenario.game.created_replacements == []


# -- Gratuitous Violence: the static doubling, by creatures only --------------------


def test_gratuitous_violence_doubles_creature_damage_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Gratuitous Violence", "Savannah Lions", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.player("bob").life == 17  # a spell is not a creature

    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(lions, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 13
