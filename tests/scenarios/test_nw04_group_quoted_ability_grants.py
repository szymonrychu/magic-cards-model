"""Scenario: "Until end of turn, `<group>` gain [<keyword> and] "`<ability>`"."
- a one-shot grant of a quoted ability (and any keyword printed beside it) to a
whole group a player controls, with the duration printed first.

Reported cards (NW-04 T2):

- Lightning Volley - "creatures you control gain "{T}: This creature deals 1
  damage to any target.""
- Flame Fusillade - "permanents you control gain "{T}: This permanent deals 1
  damage to any target."" (a land gains it too).
- Gruesome Slaughter - "colorless creatures you control gain "{T}: This
  creature deals damage equal to its power to target creature."" (CR 105.2c:
  a colorless object has no color).
- Showstopper - a granted "When this creature dies, ..." trigger.
- Driven // Despair - "gain trample and "Whenever this creature deals combat
  damage to a player, draw a card."" and, cast from the graveyard with
  aftermath (CR 702.127a), "gain menace and "... that player discards a
  card.""

Second printings (legal in Modern, Pioneer or Standard, in no deck under
`magic-cards-model-api/decks/`): Arm with Aether (a granted damage trigger with
an optional targeted bounce), Vraska, Scheming Gorgon's -10 (a keyword and a
quote, from a loyalty ability) and Swarm Surge ("Colorless creatures you
control also gain first strike until end of turn.").

Every CR number below was looked up with `mise run rules:find`:

- **CR 105.2c** - a colorless object has no color.
- **CR 113.10** - an effect that adds an ability says the object "gains" it;
  **CR 113.10a** - an effect that grants an ability can describe the object
  the ability is granted to.
- **CR 302.6** - a creature's activated ability with {T} in its cost can't be
  activated unless it has been under its controller's control continuously
  since their most recent turn began.
- **CR 603.10a** - a leaves-the-battlefield trigger looks back in time.
- **CR 611.2a** - "until end of turn" lasts as stated; **CR 514.2** - it ends
  in the cleanup step.
- **CR 611.2c** - the set of objects a resolving effect changes is fixed as it
  begins; a permanent that enters later is not in it.
- **CR 613.1f** - layer 6, ability-adding effects.
- **CR 702.19a** - trample; **CR 702.111b** - menace.
- **CR 702.127a** - aftermath: cast only from the graveyard, then exiled.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

PING = "{T}: This creature deals 1 damage to any target."
PERMANENT_PING = "{T}: This permanent deals 1 damage to any target."
SLAUGHTER = "{T}: This creature deals damage equal to its power to target creature."
SHOWSTOPPER = "When this creature dies, it deals 2 damage to target creature an opponent controls."
DRIVEN = "Whenever this creature deals combat damage to a player, draw a card."
DESPAIR = "Whenever this creature deals combat damage to a player, that player discards a card."


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _index_of(scenario, permanent, effect_prefix: str) -> int:
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(permanent))
        if ability.effect.startswith(effect_prefix)
    ]
    return index


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Volley",
        "Flame Fusillade",
        "Gruesome Slaughter",
        "Showstopper",
        "Driven // Despair",
        "Arm with Aether",
        "Vraska, Scheming Gorgon",
        "Swarm Surge",
    ],
)
def test_every_card_is_handled(name: str) -> None:
    clauses = [c for c in classify_clauses(card(name)) if c.text]
    assert {c.category for c in clauses} == {HANDLED}, [(c.category, c.text) for c in clauses]


def _board(spell, *, lands, alice=("Grizzly Bears", "Savannah Lions"), bob=("Runeclaw Bear",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell, "Llanowar Elves", "Lightning Bolt"],
            battlefield=[*alice, *lands],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10, hand=["Forest"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    return scenario


# -- Lightning Volley: creatures you control ------------------------------------


def _volley():
    scenario = _board("Lightning Volley", lands=["Mountain"] * 5)
    scenario.cast_and_resolve("Lightning Volley", auto=True)
    return scenario


def test_lightning_volley_grants_every_creature_you_control_the_ping() -> None:
    scenario = _volley()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    board = computed(scenario)
    assert board.of(bears).has_ability(PING)
    assert board.of(lions).has_ability(PING)
    assert not board.of(runeclaw).has_ability(PING), "an opponent's creature is not in the group"
    assert notices(scenario) == []


def test_the_granted_ping_is_the_creature_s_own_damage() -> None:
    scenario = _volley()
    bears = scenario.creature("Grizzly Bears")

    scenario.activate(
        bears, index=_index_of(scenario, bears, "This creature deals"), targets=["bob"]
    )
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 19
    assert bears.tapped


def test_both_creatures_can_ping_once_each() -> None:
    scenario = _volley()
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")

    scenario.activate(
        bears, index=_index_of(scenario, bears, "This creature deals"), targets=[runeclaw]
    )
    scenario.activate(
        lions, index=_index_of(scenario, lions, "This creature deals"), targets=[runeclaw]
    )
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert runeclaw.zone is Zone.GRAVEYARD


def test_a_summoning_sick_creature_cannot_use_the_granted_tap_ability() -> None:
    """CR 302.6: the granted {T} ability is the creature's own."""
    scenario = _board("Lightning Volley", lands=["Mountain"] * 5)
    bears = scenario.creature("Grizzly Bears")
    bears.summoning_sick = True
    scenario.cast_and_resolve("Lightning Volley", auto=True)

    assert computed(scenario).of(bears).has_ability(PING)
    index = _index_of(scenario, bears, "This creature deals")
    assert scenario.why_cannot_activate(bears, index) is not None
    with pytest.raises(ValueError):
        scenario.activate(bears, index=index, targets=["bob"])


def test_a_creature_entering_afterwards_does_not_gain_the_ping() -> None:
    """CR 611.2c."""
    scenario = _volley()
    elves = scenario.put_onto_battlefield("Llanowar Elves", "alice")

    assert not computed(scenario).of(elves).has_ability(PING)


def test_the_ping_ends_in_the_cleanup_step() -> None:
    scenario = _volley()
    bears = scenario.creature("Grizzly Bears")

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not computed(scenario).of(bears).has_ability(PING)


# -- Flame Fusillade: permanents you control ------------------------------------


def _fusillade():
    scenario = _board("Flame Fusillade", lands=["Mountain"] * 6)
    sources = scenario.untapped_sources(*["Mountain"] * 4, username="alice")
    scenario.cast_and_resolve("Flame Fusillade", *sources)
    return scenario


def test_flame_fusillade_grants_lands_and_creatures_alike() -> None:
    scenario = _fusillade()
    board = computed(scenario)
    for permanent in scenario.game.battlefield:
        if permanent.controller == "alice":
            assert board.of(permanent).has_ability(PERMANENT_PING), permanent.name
        else:
            assert not board.of(permanent).has_ability(PERMANENT_PING), permanent.name
    assert notices(scenario) == []


def test_an_untapped_land_pings_with_the_granted_ability() -> None:
    scenario = _fusillade()
    (mountain, _other) = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.activate(
        mountain, index=_index_of(scenario, mountain, "This permanent deals"), targets=["bob"]
    )
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 19
    assert mountain.tapped


def test_a_land_already_tapped_for_mana_cannot_ping() -> None:
    scenario = _fusillade()
    tapped = next(p for p in scenario.game.battlefield if p.name == "Mountain" and p.tapped)

    index = _index_of(scenario, tapped, "This permanent deals")
    with pytest.raises(ValueError, match="already tapped"):
        scenario.activate(tapped, index=index, targets=["bob"])
    assert scenario.player("bob").life == 20


# -- Gruesome Slaughter: colorless creatures you control ------------------------


def _slaughter():
    scenario = _board(
        "Gruesome Slaughter",
        lands=["Wastes"] * 6,
        alice=("Grizzly Bears", "Memnite", "Ornithopter"),
        bob=("Llanowar Elves", "Memnite"),
    )
    scenario.cast_and_resolve("Gruesome Slaughter", auto=True)
    return scenario


def test_only_colorless_creatures_you_control_gain_the_slaughter() -> None:
    scenario = _slaughter()
    board = computed(scenario)
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter")
    bears = scenario.creature("Grizzly Bears")
    bobs_memnite = scenario.creature("Memnite", "bob")

    assert board.of(memnite).has_ability(SLAUGHTER)
    assert board.of(thopter).has_ability(SLAUGHTER)
    assert not board.of(bears).has_ability(SLAUGHTER), "CR 105.2c: green is not colorless"
    assert not board.of(bobs_memnite).has_ability(SLAUGHTER)
    assert notices(scenario) == []


def test_the_slaughter_deals_the_creature_s_power() -> None:
    scenario = _slaughter()
    memnite = scenario.creature("Memnite", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.activate(
        memnite, index=_index_of(scenario, memnite, "This creature deals"), targets=[elves]
    )
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD


def test_a_zero_power_creature_slaughters_for_nothing() -> None:
    scenario = _slaughter()
    thopter = scenario.creature("Ornithopter")
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.activate(
        thopter, index=_index_of(scenario, thopter, "This creature deals"), targets=[elves]
    )
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert elves.zone is Zone.BATTLEFIELD


# -- Swarm Surge: "Colorless creatures you control also gain first strike" -------


def test_swarm_surge_gives_first_strike_only_to_colorless_creatures() -> None:
    scenario = _board("Swarm Surge", lands=["Swamp"] * 3, alice=("Grizzly Bears", "Memnite"))
    scenario.cast_and_resolve("Swarm Surge", auto=True)
    bears = scenario.creature("Grizzly Bears")
    memnite = scenario.creature("Memnite")

    board = computed(scenario)
    assert (board.of(bears).power, board.of(memnite).power) == (4, 3)
    assert has_keyword(memnite, Keyword.FIRST_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)
    assert notices(scenario) == []


# -- Showstopper: a granted dies trigger ----------------------------------------


def test_a_creature_dying_with_showstopper_s_grant_deals_two() -> None:
    """CR 603.10a: the dies trigger looks back at the creature as it died."""
    scenario = _board("Showstopper", lands=["Swamp", "Mountain", "Mountain", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Showstopper", *sources)
    bears = scenario.creature("Grizzly Bears")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    assert computed(scenario).of(bears).has_ability(SHOWSTOPPER)
    assert notices(scenario) == []

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    scenario.state_based_actions()
    scenario.choose_trigger_targets("Grizzly Bears", [runeclaw])
    _resolve_stack(scenario)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert runeclaw.zone is Zone.GRAVEYARD


def test_a_creature_without_the_grant_triggers_nothing_when_it_dies() -> None:
    scenario = _board("Showstopper", lands=["Swamp", "Mountain", "Mountain", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Showstopper", *sources)
    elves = scenario.put_onto_battlefield("Llanowar Elves", "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[elves])
    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD
    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty


# -- Driven // Despair ----------------------------------------------------------


def _attack_unblocked(scenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)


def test_driven_grants_trample_and_a_card_per_connecting_creature() -> None:
    scenario = _board("Driven // Despair", lands=["Forest", "Forest"])
    scenario.cast_and_resolve("Driven", auto=True)
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert computed(scenario).of(lions).has_ability(DRIVEN)
    assert notices(scenario) == []
    hand_before = len(scenario.player().hand)

    _attack_unblocked(scenario, bears, lions)

    assert scenario.player("bob").life == 16
    assert len(scenario.player().hand) == hand_before + 2


def test_driven_s_trample_assigns_the_excess_through_a_blocker() -> None:
    """CR 702.19a."""
    scenario = _board("Driven // Despair", lands=["Forest", "Forest"], bob=("Llanowar Elves",))
    scenario.cast_and_resolve("Driven", auto=True)
    bears = scenario.creature("Grizzly Bears")
    elves = scenario.creature("Llanowar Elves", "bob")
    hand_before = len(scenario.player().hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, elves)
    scenario.will_assign_combat_damage((elves, 1), ("bob", 1))
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 19
    assert len(scenario.player().hand) == hand_before + 1


def test_despair_from_the_graveyard_grants_menace_and_a_discard() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Driven // Despair"],
            battlefield=["Grizzly Bears", "Swamp", "Swamp"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Runeclaw Bear"], hand=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    bears.summoning_sick = False
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    casting = scenario.cast("Driven", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Aftermath")
    casting.cast_as_split_half("Despair")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert has_keyword(bears, Keyword.MENACE, scenario.game)
    assert computed(scenario).of(bears).has_ability(DESPAIR)
    assert scenario.find("Driven", Zone.EXILE, "alice").zone is Zone.EXILE
    assert notices(scenario) == []

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    with pytest.raises(ValueError):
        scenario.block(bears, runeclaw)  # CR 702.111b
    scenario.no_blocks()
    island = scenario.find("Island", Zone.HAND, "bob")
    scenario.will_discard(island, username="bob")
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 18
    assert len(scenario.player("bob").hand) == 1


# -- Arm with Aether: a granted damage trigger with an optional bounce ----------


def test_arm_with_aether_bounces_a_creature_of_the_damaged_opponent() -> None:
    scenario = _board(
        "Arm with Aether", lands=["Island"] * 3, bob=("Runeclaw Bear", "Llanowar Elves")
    )
    scenario.cast_and_resolve("Arm with Aether", auto=True)
    bears = scenario.creature("Grizzly Bears")
    elves = scenario.creature("Llanowar Elves", "bob")
    assert notices(scenario) == []

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Grizzly Bears", [elves])
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 18
    assert elves.zone is Zone.HAND


# -- Vraska, Scheming Gorgon's -10: a keyword and a quote from a loyalty ability -


def test_vraska_s_ultimate_grants_deathtouch_and_the_game_loss() -> None:
    scenario = _board("Vraska, Scheming Gorgon", lands=[], alice=("Grizzly Bears",))
    vraska = scenario.put_onto_battlefield("Vraska, Scheming Gorgon", "alice")
    scenario.game.add_counters(vraska, Counter.LOYALTY, 10 - vraska.counters[Counter.LOYALTY])
    bears = scenario.creature("Grizzly Bears")

    scenario.activate(vraska, index=_index_of(scenario, vraska, "Until end of turn"))
    _resolve_stack(scenario)

    assert has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)
    assert (
        computed(scenario)
        .of(bears)
        .has_ability(
            "Whenever this creature deals damage to an opponent, that player loses the game."
        )
    )
    assert notices(scenario) == []

    _attack_unblocked(scenario, bears)

    scenario.state_based_actions()
    assert "bob" in scenario.game.losers
