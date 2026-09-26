"""Scenario: a card name chosen by a triggered ability as the permanent enters
- "When this land enters, choose a land card name." - read back by the same
permanent's static abilities: "Activated abilities of sources with the chosen
name can't be activated unless they're mana abilities." and "Lands with the
chosen name have "{T}: Add {C}."" (Petrified Hamlet).

The choice is made as the trigger resolves (CR 603.3, CR 608.2), not as the
land enters - unlike Pithing Needle's CR 614.12a "As this enters" choice - so
until the trigger resolves no name is chosen and neither static ability picks
anything. It lands on `CardState.choice`, the same record the "as enters"
choice fills, so both static readers are the ones Pithing Needle and Alpine
Moon already use.

No other printing legal in Modern, Pioneer or Standard carries a *triggered*
"choose a ... card name" or "with the chosen name have" (Scryfall oracle
search, 2026-09-26; see MEMORY.md). The chosen-name grant is one branch of the
group quoted-grant reader proved on Resonating Lute and Cryptolith Rite in
`test_granted_mana_abilities.py`; the corner cases below are on Petrified
Hamlet itself, against several real lands.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 201.4** / **CR 201.4a** - choosing a card name, and one "with certain
  characteristics": the Oracle text must match them.
- **CR 603.2** - a triggered ability triggers when its trigger event happens.
- **CR 603.3** - it is put on the stack the next time a player would receive
  priority.
- **CR 608.2** - it resolves in steps; its instructions are followed then.
- **CR 113.10** - "have" grants an ability.
- **CR 613.1f** - layer 6: ability-adding effects.
- **CR 611.3a** - a static ability's effect is not locked in.
- **CR 604.2** - it lasts only while its permanent is on the battlefield.
- **CR 602.5** - a rule or effect can prohibit activating an ability.
- **CR 605.1a** - what makes an activated ability a mana ability.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import ChoiceKind
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

COLORLESS = "{T}: Add {C}."


def _land(scenario, name: str, username: str = "alice"):
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return state


def _board(*, alice=(), bob=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Petrified Hamlet"], battlefield=list(alice))
        .player("bob", battlefield=list(bob), hand=["Lotus Field"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_and_choose(scenario, name: str):
    scenario.will_choose(name, username="alice", source="Petrified Hamlet")
    scenario.play_land("Petrified Hamlet")
    scenario.resolve_top()
    return _land(scenario, "Petrified Hamlet")


def test_every_line_is_handled() -> None:
    clauses = [c for c in classify_clauses(card("Petrified Hamlet")) if c.text]

    assert {c.category for c in clauses} == {HANDLED}


def test_the_name_is_chosen_as_the_trigger_resolves() -> None:
    scenario = _board()
    scenario.play_land("Petrified Hamlet")
    hamlet = _land(scenario, "Petrified Hamlet")

    assert hamlet.choice is None
    assert scenario.stack_names() == ["Petrified Hamlet's triggered ability"]

    scenario.will_choose("Mishra's Factory", username="alice", source="Petrified Hamlet")
    scenario.resolve_top()

    assert hamlet.choice is not None
    assert hamlet.choice.kind is ChoiceKind.CARD_NAME
    assert hamlet.choice.value == "Mishra's Factory"


def test_a_nonland_name_is_refused() -> None:
    """CR 201.4a: "a land card name" - Lightning Bolt is not one."""
    scenario = _board()
    scenario.will_choose("Lightning Bolt", username="alice", source="Petrified Hamlet")
    scenario.play_land("Petrified Hamlet")

    with pytest.raises(ValueError, match=r"CR 201\.4a"):
        scenario.resolve_top()


def test_a_land_with_the_chosen_name_has_the_colorless_ability() -> None:
    scenario = _board(bob=["Lotus Field"])
    _enter_and_choose(scenario, "Lotus Field")

    chars = scenario.game.characteristics_of(_land(scenario, "Lotus Field", "bob"))

    assert COLORLESS in chars.abilities


def test_any_player_s_land_with_the_name_is_caught() -> None:
    """No "you control": the grant reaches every player's lands."""
    scenario = _board(alice=["Lotus Field"], bob=["Lotus Field"])
    _enter_and_choose(scenario, "Lotus Field")

    for username in ("alice", "bob"):
        chars = scenario.game.characteristics_of(_land(scenario, "Lotus Field", username))
        assert COLORLESS in chars.abilities, username


def test_the_granted_ability_taps_for_colorless() -> None:
    scenario = _board(alice=["Lotus Field"])
    _enter_and_choose(scenario, "Lotus Field")
    field = _land(scenario, "Lotus Field")
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(field))
        if (ability.cost, ability.effect) == ("{T}", "Add {C}.")
    ]

    scenario.activate(field, index=index)

    assert field.tapped
    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}


def test_a_land_with_another_name_is_untouched() -> None:
    scenario = _board(bob=["Lotus Field", "Tolaria West"])
    _enter_and_choose(scenario, "Lotus Field")

    chars = scenario.game.characteristics_of(_land(scenario, "Tolaria West", "bob"))

    assert COLORLESS not in chars.abilities


def test_nothing_is_granted_before_the_trigger_resolves() -> None:
    scenario = _board(bob=["Lotus Field"])
    scenario.play_land("Petrified Hamlet")

    chars = scenario.game.characteristics_of(_land(scenario, "Lotus Field", "bob"))

    assert COLORLESS not in chars.abilities


def test_a_land_with_the_name_that_enters_later_has_it() -> None:
    """CR 611.3a."""
    scenario = _board()
    _enter_and_choose(scenario, "Lotus Field")

    field = scenario.put_onto_battlefield("Lotus Field", "bob")

    assert COLORLESS in scenario.game.characteristics_of(field).abilities


def test_the_grant_ends_when_the_hamlet_leaves() -> None:
    """CR 604.2."""
    scenario = _board(bob=["Lotus Field"])
    hamlet = _enter_and_choose(scenario, "Lotus Field")

    scenario.game.put_into_graveyard(hamlet)

    chars = scenario.game.characteristics_of(_land(scenario, "Lotus Field", "bob"))
    assert COLORLESS not in chars.abilities


def test_the_named_source_s_non_mana_abilities_cannot_be_activated() -> None:
    """CR 602.5 / CR 605.1a: Mishra's Factory's "{1}: ... becomes a 2/2
    Assembly-Worker artifact creature" is not a mana ability, so it is
    refused; its "{T}: Add {C}." still works."""
    scenario = _board(bob=["Mishra's Factory", "Wastes"])
    _enter_and_choose(scenario, "Mishra's Factory")
    factory = _land(scenario, "Mishra's Factory", "bob")

    assert scenario.why_cannot_activate(factory, 1, "bob") is not None
    assert scenario.why_cannot_activate(factory, 0, "bob") is None


def test_the_hamlet_s_own_ability_still_taps_for_colorless() -> None:
    scenario = _board()
    hamlet = _enter_and_choose(scenario, "Lotus Field")

    scenario.activate(hamlet)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}
