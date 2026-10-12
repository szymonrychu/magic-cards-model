"""EP-01-R3 T7: branches of the new readers the first scenario file left untested.

No Modern/Pioneer/Standard printing in the engine's pool reaches these reader
branches (the spells with the look-at-top wording are read by another path;
Nine-Lives Familiar, Nacatl War-Pride, Protean Hydra and Foe-Razer Regent are
the "fewer", X and "it" shapes), so each is driven through the reader on its
printed-shape text, the clause run as a resolving ability of a real creature on
a real board:

- "Look at the top N cards... Put K of them into your hand and the rest on the
  bottom of your library" / "...and the rest back on top in any order"
- "Return it to the battlefield [tapped] with N <kind> counters on it at ..."
  (a fixed count; Nine-Lives Familiar only has the "fewer" shape)
- "Create N tokens that are copies of this <noun> and that are tapped and
  attacking." (a fixed count; Nacatl War-Pride is the X shape, with "it")
- "Put N <kind> counters on this <noun> at the beginning of the next end step."
  (Protean Hydra and Foe-Razer Regent are +1/+1 and say "it")

CR numbers read with `mise run rules:find`: 701.20e (look at a card), 603.7a
(delayed triggered abilities are created on resolution), 122.6 (counters put on
an object, including as it enters), 508.4 (put onto the battlefield attacking,
never "attacked").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.effects.counters import _parse_put_counters_on_self_at_step_clause
from magic_cards_model.machines.effects.library import _parse_look_top_put_some_into_zone_clause
from magic_cards_model.machines.effects.returns import (
    _parse_return_dead_self_with_counters_at_step_clause,
)
from magic_cards_model.machines.effects.tokens import _parse_create_copies_of_self_attacking_clause
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

#: Parsed once at import: the replay invariant reruns each test, and parsing
#: inside it would draw ids on the first run only.
_SOME_TRIGGERED_ABILITY = next(
    a for a in parse_abilities(card("Nacatl War-Pride")) if isinstance(a, TriggeredAbility)
)


def _board(
    *, alice=(), alice_graveyard=(), alice_hand=(), alice_library=("Island",) * 5, bob=()
) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            graveyard=list(alice_graveyard),
            hand=list(alice_hand),
            library=list(alice_library),
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _advance_into_end_step(scenario: PlayedScenario) -> None:
    while scenario.step is not Step.END_STEP:
        _resolve_all(scenario)
        scenario.advance()


def _resolve_clause(scenario: PlayedScenario, effect, source) -> None:
    """Resolve `effect` as an ability of `source`, the way the stack would."""
    with scenario.game._id_allocator_scope():  # noqa: SLF001 - what resolve_top opens
        effect(
            scenario.game,
            AbilityOnStack(
                kind=AbilityKind.TRIGGERED,
                ability=_SOME_TRIGGERED_ABILITY,
                source_id=source.id,
                source_name=source.name,
                controller="alice",
                source_stamp=source.zone_change_stamp,
            ),
        )


def _library(scenario: PlayedScenario) -> list[str]:
    return [state.name for state in scenario.game.player("alice").library]


# -- _parse_look_top_put_some_into_zone_clause ----------------------------------------


def test_look_at_top_four_put_one_into_hand_rest_on_the_bottom():
    """Hand destination, rest on the bottom (CR 701.20e: looked at, then split).
    The printings in the formats with this wording (Sleight of Hand, Anticipate)
    are spells read by another path, and the one ability printing (Sea Gate
    Oracle) is not in the pool; the reader is run on the printed-shape text."""
    scenario = _board(
        alice=["Grizzly Bears"],
        alice_library=["Forest", "Mountain", "Plains", "Swamp", "Wastes", "Wastes"],
    )
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.scry_bottoming(plains)
    effect = _parse_look_top_put_some_into_zone_clause(
        "Look at the top four cards of your library. "
        "Put one of them into your hand and the rest on the bottom of your library."
    )
    assert effect is not None
    _resolve_clause(scenario, effect, scenario.creature("Grizzly Bears", "alice"))
    assert plains.zone is Zone.HAND
    assert _library(scenario) == ["Wastes", "Wastes", "Forest", "Mountain", "Swamp"]


def test_look_at_top_three_put_one_into_hand_rest_back_on_top_in_the_chosen_order():
    """No printing in the formats says "back on top in any order" with a hand
    destination; the reader is run on the printed-shape text."""
    scenario = _board(
        alice=["Grizzly Bears"],
        alice_library=["Forest", "Mountain", "Plains", "Swamp"],
    )
    forest, mountain, plains = (
        scenario.find(name, Zone.LIBRARY, "alice") for name in ("Forest", "Mountain", "Plains")
    )
    scenario.scry_bottoming(mountain, top_order=[plains, forest])
    effect = _parse_look_top_put_some_into_zone_clause(
        "Look at the top three cards of your library. "
        "Put one of them into your hand and the rest back on top in any order."
    )
    assert effect is not None
    _resolve_clause(scenario, effect, scenario.creature("Grizzly Bears", "alice"))
    assert mountain.zone is Zone.HAND
    assert _library(scenario) == ["Plains", "Forest", "Swamp"]


# -- _parse_return_dead_self_with_counters_at_step_clause -----------------------------


def _returned(clause: str):
    scenario = _board(alice_graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    effect = _parse_return_dead_self_with_counters_at_step_clause(clause)
    assert effect is not None
    _resolve_clause(scenario, effect, bears)
    assert bears.zone is Zone.GRAVEYARD, "CR 603.7a: nothing returns until the step arrives"
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    return bears


def test_a_fixed_count_of_counters_comes_back_with_the_card_at_the_end_step():
    """No printing in the formats returns a card with a fixed count of counters
    (Nine-Lives Familiar is the "fewer" shape); CR 122.6 counts as it enters."""
    bears = _returned(
        "Return it to the battlefield with two charge counters on it "
        "at the beginning of the next end step."
    )
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counters["charge"] == 2
    assert not bears.tapped


def test_the_card_comes_back_tapped_when_the_clause_says_so():
    bears = _returned(
        "Return it to the battlefield tapped with a charge counter on it "
        "at the beginning of the next end step."
    )
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counters["charge"] == 1
    assert bears.tapped


# -- _parse_create_copies_of_self_attacking_clause ------------------------------------


def test_a_fixed_count_of_copies_of_this_creature_enter_tapped_and_attacking():
    """Nacatl War-Pride is the X shape and says "it"; no printing in the formats
    makes a fixed number of copies of "this creature". CR 508.4: attacking, but
    never declared as attackers."""
    scenario = _board(alice=["Grizzly Bears"], bob=["Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    effect = _parse_create_copies_of_self_attacking_clause(
        "Create two tokens that are copies of this creature and that are tapped and attacking.",
        for_spell=False,
    )
    assert effect is not None
    _resolve_clause(scenario, effect, bears)
    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears" and state.token
    ]
    assert len(copies) == 2
    assert all(copy.tapped for copy in copies)
    assert all(copy in scenario.attackers() for copy in copies)


# -- _parse_put_counters_on_self_at_step_clause ---------------------------------------


def test_counters_of_another_kind_land_on_this_creature_at_the_end_step():
    """Protean Hydra and Foe-Razer Regent put +1/+1 counters on "it"; no
    printing in the formats says "this creature" or another kind. CR 603.7a."""
    scenario = _board(alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    effect = _parse_put_counters_on_self_at_step_clause(
        "Put two charge counters on this creature at the beginning of the next end step."
    )
    assert effect is not None
    _resolve_clause(scenario, effect, bears)
    assert bears.counters["charge"] == 0
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert bears.counters["charge"] == 2
    assert bears.counters["+1/+1"] == 0
