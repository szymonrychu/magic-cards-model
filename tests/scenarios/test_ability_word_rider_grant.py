"""Scenario: a targeted pump or grant, then an ability-word rider that grants
"that creature" something more only if a condition holds -
"<Ability word> — If <condition>, that creature gains <keyword> until end of
turn." or "<Ability word> — That creature also gains <keyword> until end of
turn if <condition>."

- **CR 207.2c** - an ability word has no rules meaning of its own; the rider
  is only the sentence printed after the dash.
- **CR 608.2c** - one resolving spell, its instructions in the order written;
  "that creature" is the object the first sentence acted on, not a new target.
- **CR 608.2h** - the condition is information from the game, determined once
  when the effect is applied - that is, on resolution, not on casting.
- **CR 611.2c** - the effect is fixed once it begins; losing the condition
  later does not take the grant back.
- **CR 613.1f** - the rider's keyword is a layer 6 grant; **CR 613.4c** - the
  first sentence's +1/+0 is sublayer 7c.
- **CR 608.2b** - a target illegal on resolution: the spell does nothing, the
  rider included.
- **CR 702.4b** / **CR 510.4** - double strike: a first-strike combat damage
  step, then a regular one.

Violent Urge is the reported card (Delirium, leading "If ..."). Temur Battle
Rage is the second printing: a different ability word (Ferocious), a trailing
"if", an "also", and a board-power condition rather than a graveyard count.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.layers import LAYER_EFFECTS
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

#: Four card types (CR 205.2a): creature, instant, sorcery, artifact.
FOUR_TYPES = ["Grizzly Bears", "Lightning Bolt", "Preordain", "Mishra's Bauble"]
THREE_TYPES = ["Lightning Bolt", "Preordain", "Mishra's Bauble"]


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario: Scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _urge(graveyard: list[str], **bob) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Violent Urge"],
            battlefield=["Mountain", "Grizzly Bears", "Memnite"],
            graveyard=graveyard,
        )
        .player("bob", **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_urge(scenario: Scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Violent Urge", mountain, targets=[bears])
    return bears


def test_violent_urge_has_no_card_name_row():
    """The rider is read off the template now, not a hand-built row."""
    assert "Violent Urge" not in LAYER_EFFECTS


def test_without_delirium_only_the_pump_and_first_strike():
    scenario = _urge(THREE_TYPES)
    bears = _cast_urge(scenario)

    board = computed(scenario).of(bears)
    assert board.power_toughness == (3, 2)
    assert has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert notices(scenario) == []


def test_with_delirium_that_creature_also_gains_double_strike():
    scenario = _urge(FOUR_TYPES)
    bears = _cast_urge(scenario)

    board = computed(scenario).of(bears)
    assert board.power_toughness == (3, 2)
    assert has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)
    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert notices(scenario) == []


def test_that_creature_is_the_target_not_another_creature():
    scenario = _urge(FOUR_TYPES)
    _cast_urge(scenario)
    memnite = scenario.creature("Memnite", "alice")

    assert not has_keyword(memnite, Keyword.DOUBLE_STRIKE, scenario.game)
    assert computed(scenario).of(memnite).power_toughness == (1, 1)


def test_delirium_is_checked_on_resolution_not_on_casting():
    """CR 608.2h: three types when cast; Bob's Lightning Bolt in response kills
    Memnite, an artifact creature, putting a fourth type (creature) into
    Alice's graveyard before Violent Urge resolves."""
    scenario = _urge(THREE_TYPES, hand=["Lightning Bolt"], battlefield=["Mountain"])
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Violent Urge", mountain, targets=[bears])

    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", bob_mountain, username="bob", targets=[memnite])
    scenario.pass_until_resolved()  # Bolt
    scenario.state_based_actions()
    assert memnite.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()  # Violent Urge

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_the_grant_is_not_taken_back_when_the_graveyard_empties():
    """CR 611.2c."""
    scenario = _urge(FOUR_TYPES)
    bears = _cast_urge(scenario)
    scenario.player("alice").zones[Zone.GRAVEYARD].clear()

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_an_illegal_target_gets_neither_the_pump_nor_the_rider():
    """CR 608.2b."""
    scenario = _urge(FOUR_TYPES)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Violent Urge", mountain, targets=[bears])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert scenario.game.continuous_effects.effects == []
    assert notices(scenario) == []


def test_the_granted_double_strike_deals_damage_twice():
    """CR 510.4: the 3/2 double striker deals 3 in the first-strike step and 3
    again in the regular one."""
    scenario = _urge(FOUR_TYPES, life=20)
    bears = _cast_urge(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()  # both steps (CR 510.4)

    assert scenario.player("bob").life == 14


# -- second printing: Temur Battle Rage ------------------------------------


def _rage(alice_battlefield: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Temur Battle Rage"],
            battlefield=["Mountain", "Mountain", *alice_battlefield],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_rage(scenario: Scenario, target_name: str):
    target = scenario.creature(target_name, "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Temur Battle Rage", *mountains, targets=[target])
    return target


def test_temur_battle_rage_without_ferocious_is_double_strike_alone():
    scenario = _rage(["Grizzly Bears"])
    bears = _cast_rage(scenario, "Grizzly Bears")

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert notices(scenario) == []


def test_temur_battle_rage_with_ferocious_also_grants_trample():
    """A 6-power Craw Wurm elsewhere on the board satisfies "you control a
    creature with power 4 or greater"; the Bears get the trample."""
    scenario = _rage(["Grizzly Bears", "Craw Wurm"])
    bears = _cast_rage(scenario, "Grizzly Bears")
    wurm = scenario.creature("Craw Wurm", "alice")

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(wurm, Keyword.TRAMPLE, scenario.game), "that creature only"
    assert notices(scenario) == []


def test_ferocious_counts_the_target_itself():
    scenario = _rage(["Craw Wurm"])
    wurm = _cast_rage(scenario, "Craw Wurm")

    assert has_keyword(wurm, Keyword.TRAMPLE, scenario.game)
