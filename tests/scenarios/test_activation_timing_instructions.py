"""CR 602.1b: "Activate only during <when>" is an instruction the engine obeys.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 602.1b** - text after an activated ability's colon "may state which
  players can activate that ability, may restrict when a player can activate
  the ability ... It functions at all times."
- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated."
- **CR 602.5b** - "If an activated ability has a restriction on its use (for
  example, 'Activate only once each turn'), the restriction continues to apply
  to that object even if its controller changes."
- **CR 109.5** - "For an activated ability, this is the player who activated
  the ability": the "your" of "during your turn" is whoever activates it.
- **CR 506.1** - the combat phase's steps: beginning of combat, declare
  attackers, declare blockers, combat damage, end of combat.

Until this file, "Activate only during your turn" was parsed into
`ActivatedAbility.instructions` and then never read - every such ability was
activatable at any time (fail-open). Each timing form is proven on a printing
other than Sundial of the Infinite, the card that exposed it, and none is in
the api's deck pool.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _next_turn(scenario) -> None:
    """Run the rest of this turn out and begin the next one's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep


# -- "Activate only during your turn" -----------------------------------------


def test_during_your_turn_is_refused_on_an_opponents_turn_and_allowed_on_yours():
    """Sundial of the Infinite: "{1}, {T}: End the turn. Activate only during
    your turn." - the card that exposed the fail-open."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sundial of the Infinite", "Plains"])
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sundial = scenario.creature("Sundial of the Infinite", "alice")
    assert scenario.why_cannot_activate(sundial) is None

    _next_turn(scenario)  # bob's turn
    refusal = scenario.why_cannot_activate(sundial, username="alice")
    assert refusal is not None
    assert "during your turn" in refusal
    assert "CR 602.1b" in refusal


def test_during_your_turn_on_a_second_printing_resolves_when_met():
    """Disrupting Scepter: "{3}, {T}: Target player discards a card. Activate
    only during your turn." - refused on bob's turn, and on alice's it goes on
    the stack and resolves."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Disrupting Scepter", "Swamp", "Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scepter = scenario.creature("Disrupting Scepter", "alice")
    bob = scenario.player("bob")

    scenario.will_discard(*bob.hand)
    scenario.activate(scepter, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=[bob])
    scenario.pass_until_resolved()
    assert [card.name for card in bob.graveyard] == ["Grizzly Bears"]

    _next_turn(scenario)  # bob's turn
    refusal = scenario.why_cannot_activate(scepter, username="alice")
    assert refusal is not None and "during your turn" in refusal
    with pytest.raises(ValueError, match="during your turn"):
        scenario.activate(scepter, targets=[bob], username="alice")


# -- "Activate only during your upkeep" --------------------------------------


def test_during_your_upkeep_is_refused_in_the_main_phase_and_allowed_in_upkeep():
    """Hell's Caretaker: "{T}, Sacrifice a creature: Return target creature
    card from your graveyard to the battlefield. Activate only during your
    upkeep." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Hell's Caretaker", "Grizzly Bears"],
            graveyard=["Llanowar Elves"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    caretaker = scenario.creature("Hell's Caretaker", "alice")
    assert scenario.why_cannot_activate(caretaker) is None

    scenario.start_at(Step.PRECOMBAT_MAIN)
    refusal = scenario.why_cannot_activate(caretaker)
    assert refusal is not None and "during your upkeep" in refusal


def test_during_your_upkeep_follows_the_activating_player_after_a_control_change():
    """Hell's Caretaker again, taken by bob with Soul Ransom ("You control
    enchanted creature."): CR 602.5b keeps the restriction on the object and
    CR 109.5 makes its "your" bob's now - refused for bob in alice's upkeep,
    allowed in his own, and alice no longer controls it at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Hell's Caretaker", "Grizzly Bears"],
            library=["Plains"] * 6,
        )
        .player(
            "bob",
            hand=["Soul Ransom"],
            battlefield=["Island", "Island", "Swamp", "Swamp", "Llanowar Elves"],
            graveyard=["Grizzly Bears"],
            library=["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    caretaker = scenario.creature("Hell's Caretaker", "alice")
    assert scenario.why_cannot_activate(caretaker) is None

    _next_turn(scenario)  # bob's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Soul Ransom",
        *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="bob"),
        targets=[caretaker],
        username="bob",
    )
    assert scenario.game.controller_of(caretaker).username == "bob"
    assert scenario.why_cannot_activate(caretaker, username="alice") == (
        "alice does not control Hell's Caretaker"
    )

    _next_turn(scenario)  # alice's upkeep: bob controls it, but it is not his upkeep
    assert scenario.turn.active_player == "alice"
    refusal = scenario.why_cannot_activate(caretaker, username="bob")
    assert refusal is not None and "during your upkeep" in refusal

    _next_turn(scenario)  # bob's upkeep: he has controlled it since his turn began
    assert scenario.turn.active_player == "bob"
    assert scenario.why_cannot_activate(caretaker, username="bob") is None


def test_during_your_upkeep_on_a_second_printing_is_not_an_opponents_upkeep():
    """Augur of Skulls: "Sacrifice this creature: Target player
    discards two cards. Activate only during your upkeep." - bob's upkeep is
    not alice's, and on alice's own it resolves."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Augur of Skulls"], library=["Plains"] * 4)
        .player("bob", hand=["Grizzly Bears", "Llanowar Elves"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    augur = scenario.creature("Augur of Skulls", "alice")
    refusal = scenario.why_cannot_activate(augur, index=1)
    assert refusal is not None and "during your upkeep" in refusal
    # Its regeneration ability carries no instruction.
    assert scenario.why_cannot_activate(augur, index=0) is None

    _next_turn(scenario)  # bob's upkeep
    assert scenario.step is Step.UPKEEP
    refusal = scenario.why_cannot_activate(augur, index=1, username="alice")
    assert refusal is not None and "during your upkeep" in refusal

    _next_turn(scenario)  # alice's upkeep again
    assert scenario.turn.active_player == "alice"
    bob = scenario.player("bob")
    scenario.will_discard(*bob.hand)
    scenario.activate(augur, index=1, targets=[bob])
    scenario.pass_until_resolved()
    assert sorted(card.name for card in bob.graveyard) == ["Grizzly Bears", "Llanowar Elves"]


# -- combat, and its named steps ----------------------------------------------


def test_during_combat_is_any_step_of_the_combat_phase():
    """Jade Statue: "{2}: This artifact becomes a 3/6 Golem artifact creature
    until end of combat. Activate only during combat." (CR 506.1)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Jade Statue", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    statue = scenario.creature("Jade Statue", "alice")
    refusal = scenario.why_cannot_activate(statue)
    assert refusal is not None and "during combat" in refusal

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    assert scenario.why_cannot_activate(statue) is None
    on_stack = scenario.activate(statue, *scenario.untapped_sources("Plains", "Plains"))
    assert on_stack is not None and on_stack.source_name == "Jade Statue"
    scenario.pass_until_resolved()

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    refusal = scenario.why_cannot_activate(statue)
    assert refusal is not None and "during combat" in refusal


def test_during_the_end_of_combat_step_only():
    """Desert: "{T}: This land deals 1 damage to target attacking creature.
    Activate only during the end of combat step." (CR 511)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Desert"])
        .player("bob")
        .build()
    )
    desert = scenario.creature("Desert", "alice")
    for step in (Step.PRECOMBAT_MAIN, Step.DECLARE_ATTACKERS, Step.COMBAT_DAMAGE):
        scenario.start_at(step)
        refusal = scenario.why_cannot_activate(desert, index=1)
        assert refusal is not None and "during the end of combat step" in refusal
    scenario.start_at(Step.END_OF_COMBAT)
    assert scenario.why_cannot_activate(desert, index=1) is None
    # Its mana ability carries no instruction at all.
    assert scenario.why_cannot_activate(desert, index=0) is None


def test_during_the_declare_blockers_step_only():
    """Balduvian Warlord: "... Activate only during the declare blockers
    step." (CR 509)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Balduvian Warlord"])
        .player("bob")
        .build()
    )
    warlord = scenario.creature("Balduvian Warlord", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    refusal = scenario.why_cannot_activate(warlord)
    assert refusal is not None and "during the declare blockers step" in refusal
    scenario.start_at(Step.DECLARE_BLOCKERS)
    assert scenario.why_cannot_activate(warlord) is None
    scenario.start_at(Step.COMBAT_DAMAGE)
    assert scenario.why_cannot_activate(warlord) is not None


# -- compounds: "... and only once each turn" / "... and only if ..." ---------


def test_during_your_turn_and_only_once_each_turn():
    """Snowslope Hunter: "Sacrifice another creature or artifact: Exile the
    top card of your library. You may play it until the end of your next
    turn. Activate only during your turn and only once each turn." - both
    halves read: the second activation this turn is refused, and bob's turn
    refuses it outright."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Snowslope Hunter", "Grizzly Bears", "Llanowar Elves"],
            library=["Plains"] * 6,
        )
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hunter = scenario.creature("Snowslope Hunter", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(hunter, sacrificing=[bears])
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(hunter) == (
        "Snowslope Hunter's ability has already been activated this turn"
    )

    _next_turn(scenario)
    refusal = scenario.why_cannot_activate(hunter, username="alice")
    assert refusal is not None and "during your turn" in refusal


def test_a_mana_ability_reads_its_instructions_too():
    """Vivi Ornitier: "{0}: Add X mana in any combination of {U} and/or {R},
    where X is Vivi Ornitier's power. Activate only during your turn and only
    once each turn." - a mana ability (CR 605.1a) is still an activated
    ability with instructions."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vivi Ornitier"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.creature("Vivi Ornitier", "alice")
    assert scenario.why_cannot_activate(vivi) is None
    _next_turn(scenario)
    refusal = scenario.why_cannot_activate(vivi, username="alice")
    assert refusal is not None and "during your turn" in refusal


def test_during_your_upkeep_and_only_if_off_the_battlefield():
    """Kuldotha Phoenix: "Metalcraft - {4}: Return this card from your
    graveyard to the battlefield. Activate only during your upkeep and only
    if you control three or more artifacts." - both halves, from the
    graveyard."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Kuldotha Phoenix"],
            hand=["Jade Statue"],
            battlefield=["Sundial of the Infinite", "Disrupting Scepter", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    phoenix = scenario.find("Kuldotha Phoenix", Zone.GRAVEYARD, "alice")
    refusal = off_battlefield_activation(scenario.game, phoenix, "alice").why_not()
    assert refusal == "Kuldotha Phoenix's activation restriction is not met (CR 602.5b)"

    scenario.put_onto_battlefield("Jade Statue", "alice")
    assert off_battlefield_activation(scenario.game, phoenix, "alice").why_not() is None

    scenario.start_at(Step.PRECOMBAT_MAIN)
    refusal = off_battlefield_activation(scenario.game, phoenix, "alice").why_not()
    assert refusal is not None and "during your upkeep" in refusal


# -- "Activate only once": never reset ----------------------------------------


def test_activate_only_once_is_not_reset_by_a_new_turn():
    """In the Trenches: "{5}{W}: Exile target nonland permanent you don't
    control until this enchantment leaves the battlefield. Activate only as a
    sorcery and only once." - unlike "once each turn", the next turn does not
    free it (CR 602.5b)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["In the Trenches"] + ["Plains"] * 6,
            library=["Plains"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears", "Llanowar Elves"], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trenches = scenario.creature("In the Trenches", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(trenches, *scenario.untapped_sources(*["Plains"] * 6), targets=[bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE
    refusal = scenario.why_cannot_activate(trenches)
    assert refusal is not None and "only once" in refusal

    _next_turn(scenario)
    _next_turn(scenario)  # alice's next turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    refusal = scenario.why_cannot_activate(trenches)
    assert refusal is not None and "only once" in refusal


# -- "... and only if <condition>": the condition halves ----------------------


def _gutterbones_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Gutterbones"],
            hand=["Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Mountain"],
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_during_your_turn_and_only_if_an_opponent_lost_life():
    """Gutterbones: "{1}{B}: Return this card from your graveyard to your
    hand. Activate only during your turn and only if an opponent lost life
    this turn." - the timing half met, the condition not; then bob loses
    life (CR 120.3a) and it returns."""
    scenario = _gutterbones_board()
    gutterbones = scenario.find("Gutterbones", Zone.GRAVEYARD, "alice")
    refusal = off_battlefield_activation(scenario.game, gutterbones, "alice").why_not()
    assert refusal == "Gutterbones's activation restriction is not met (CR 602.5b)"

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    activation = off_battlefield_activation(scenario.game, gutterbones, "alice")
    assert activation.why_not() is None
    scenario.pay_with(activation.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp"))
    activation.activate()
    scenario.pass_until_resolved()
    assert gutterbones.zone is Zone.HAND


def test_an_opponent_lost_life_on_a_second_printing():
    """Falkenrath Pit Fighter: "{1}{R}, Discard a card, Sacrifice a Vampire:
    Draw two cards. Activate only if an opponent lost life this turn." - it
    sacrifices itself, a Vampire, once bob has lost life."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Falkenrath Pit Fighter", "Mountain", "Mountain", "Mountain"],
            hand=["Lightning Bolt", "Forest"],
            library=["Plains"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fighter = scenario.creature("Falkenrath Pit Fighter", "alice")
    assert scenario.why_cannot_activate(fighter) == (
        "Falkenrath Pit Fighter's activation restriction is not met (CR 602.5b)"
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.why_cannot_activate(fighter) is None
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.activate(
        fighter,
        *scenario.untapped_sources("Mountain", "Mountain"),
        discarding=[forest],
        sacrificing=[fighter],
    )
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 2


def test_during_your_turn_and_only_if_a_card_left_your_graveyard():
    """Essence Anchor: "{T}: Create a 2/2 black Zombie Druid creature token.
    Activate only during your turn and only if a card left your graveyard
    this turn." (CR 603.10a's graveyard departure, counted per graveyard)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Essence Anchor"],
            graveyard=["Grizzly Bears"],
            library=["Plains"] * 4,
        )
        .player("bob", graveyard=["Llanowar Elves"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anchor = scenario.creature("Essence Anchor", "alice")
    assert scenario.why_cannot_activate(anchor) == (
        "Essence Anchor's activation restriction is not met (CR 602.5b)"
    )
    # A card leaving bob's graveyard is not one leaving alice's.
    scenario.game.exile_cards([scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob")])
    assert scenario.why_cannot_activate(anchor) is not None

    scenario.game.exile_cards([scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")])
    scenario.activate(anchor)
    scenario.pass_until_resolved()
    assert "Zombie Druid Token" in [s.name for s in scenario.game.permanents_controlled_by("alice")]

    _next_turn(scenario)
    _next_turn(scenario)  # alice's next turn: nothing has left her graveyard
    assert scenario.why_cannot_activate(anchor) == (
        "Essence Anchor's activation restriction is not met (CR 602.5b)"
    )


def test_a_card_left_your_graveyard_on_a_second_printing():
    """Living History: "Whenever you attack, if a card left your graveyard
    this turn, target attacking creature gets +2/+0 until end of turn." - the
    same condition as an intervening "if" (CR 603.4)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Living History", "Grizzly Bears"],
            graveyard=["Llanowar Elves"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_a_card_left_your_graveyard_triggers_the_attack_ability():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Living History", "Grizzly Bears"],
            graveyard=["Llanowar Elves"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.exile_cards([scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears, source="Living History")
    scenario.attack_with(bears)
    assert scenario.stack_names() == ["Living History's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.power_of(bears) == 4
