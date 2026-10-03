"""The intervening *if* "you've cast both a creature spell and a noncreature
spell this turn" (CR 603.4) - Eshki Dragonclaw's beginning-of-combat trigger
and Fae Offering's each-end-step trigger.

"Both" asks for two different spells cast this turn (CR 601.2i, `Game.
spells_cast_this_turn`), one of each quality - CR 205.2a's card types of the
spell as it was cast. Before this, both triggers recorded an
`InterveningIfNotice` and never triggered.

The fact only accumulates within a turn, so CR 603.4's recheck on
resolution reads the same answer the trigger did. Fae Offering's "each end
step" asks about *its controller's* casts even on the opponent's turn.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 603.4, CR 601.2i, CR 205.2a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

ESHKI = "Eshki Dragonclaw"
FAE = "Fae Offering"


def _scenario(permanent: str, *, hand=("Grizzly Bears", "Shock")) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[permanent, "Forest", "Forest", "Mountain", "Mountain"],
            hand=list(hand),
            library=["Forest"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _cast_bears(scenario: PlayedScenario) -> None:
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))


def _cast_shock(scenario: PlayedScenario) -> None:
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])


def _to_combat(scenario: PlayedScenario) -> None:
    scenario.advance()  # beginning of combat
    _resolve_all(scenario)


def _to_end_step(scenario: PlayedScenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    _resolve_all(scenario)


def _tokens(scenario: PlayedScenario) -> list[str]:
    return sorted(
        sub
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.token
        for sub in permanent.subtypes
    )


def test_eshki_draws_and_grows_after_a_creature_and_a_noncreature_spell():
    scenario = _scenario(ESHKI)
    _cast_bears(scenario)
    _cast_shock(scenario)
    hand = len(scenario.player("alice").hand)

    _to_combat(scenario)

    eshki = scenario.find(ESHKI, Zone.BATTLEFIELD, "alice")
    assert eshki.counter_count("+1/+1") == 2
    assert len(scenario.player("alice").hand) == hand + 1
    assert scenario.game.intervening_if_notices == []


def test_eshki_does_nothing_after_only_a_creature_spell():
    scenario = _scenario(ESHKI)
    _cast_bears(scenario)

    _to_combat(scenario)

    assert scenario.find(ESHKI, Zone.BATTLEFIELD, "alice").counter_count("+1/+1") == 0
    assert scenario.game.intervening_if_notices == []


def test_two_noncreature_spells_are_not_both():
    scenario = _scenario(ESHKI, hand=("Shock", "Shock"))
    _cast_shock(scenario)
    _cast_shock(scenario)

    _to_combat(scenario)

    assert scenario.find(ESHKI, Zone.BATTLEFIELD, "alice").counter_count("+1/+1") == 0


def test_an_opponents_spells_do_not_count_for_you():
    scenario = _scenario(ESHKI, hand=())
    scenario.game.spells_cast_this_turn["bob"] = [
        scenario.find("Island", Zone.LIBRARY, "bob")
    ]

    _to_combat(scenario)

    assert scenario.find(ESHKI, Zone.BATTLEFIELD, "alice").counter_count("+1/+1") == 0


def test_fae_offering_makes_a_clue_a_food_and_a_treasure():
    scenario = _scenario(FAE)
    _cast_shock(scenario)
    _cast_bears(scenario)

    _to_end_step(scenario)

    assert _tokens(scenario) == ["Clue", "Food", "Treasure"]
    assert scenario.game.intervening_if_notices == []


def test_fae_offering_makes_nothing_after_only_a_noncreature_spell():
    scenario = _scenario(FAE)
    _cast_shock(scenario)

    _to_end_step(scenario)

    assert _tokens(scenario) == []
    assert scenario.game.intervening_if_notices == []


def test_fae_offering_makes_nothing_on_a_quiet_turn():
    scenario = _scenario(FAE, hand=())

    _to_end_step(scenario)

    assert _tokens(scenario) == []
    assert scenario.game.intervening_if_notices == []
