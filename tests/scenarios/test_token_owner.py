"""Every token has an owner: the player who created it.

- **CR 111.2** (read in full with `mise run rules:find` in the session that
  wrote this file) - "The player who creates a token is its owner. The token
  enters the battlefield under that player's control."

Each token path is exercised through a real printing: a stated token (Spectral
Procession), a predefined Treasure (Ragavan, Nimble Pilferer), a token created
by a targeted player (Kozilek's Command), a replacement effect's extra token
(Stridehangar Automaton), and a token copy (`token_copy_of`, CR 707.2). The
owner is read again after a JSON round trip, which is what a seat's view is
built from.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from magic_cards_model.models.token import is_token, token_copy_of
from tests.scenarios.harness import Scenario


def _round_trip(game: Game) -> Game:
    return Game.model_validate(game.model_dump(mode="json"))


def _tokens(game: Game, name: str):
    return [state for state in game.battlefield if is_token(state) and state.name == name]


def test_stated_tokens_are_owned_by_their_creator():
    scenario = (
        Scenario()
        .player("alice", hand=["Spectral Procession"], battlefield=["Plains"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    spirits = _tokens(scenario.game, "Spirit Token")
    assert len(spirits) == 3
    assert {spirit.owner for spirit in spirits} == {"alice"}

    decoded = _round_trip(scenario.game)
    assert {decoded.find_by_id(spirit.id).owner for spirit in spirits} == {"alice"}


def _ragavan_connects(battlefield: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=battlefield)
        .player("bob", library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    ragavan.summoning_sick = False
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    return scenario


def test_a_treasure_token_is_owned_by_its_creator_and_survives_a_round_trip():
    scenario = _ragavan_connects(["Ragavan, Nimble Pilferer"])

    (treasure,) = _tokens(scenario.game, "Treasure Token")
    assert treasure.owner == "alice"
    assert treasure.controller == "alice"

    decoded = _round_trip(scenario.game).find_by_id(treasure.id)
    assert decoded.owner == "alice"
    assert decoded.zone is Zone.BATTLEFIELD


def test_a_replacement_effects_extra_token_is_owned_by_the_creator():
    scenario = _ragavan_connects(["Ragavan, Nimble Pilferer", "Stridehangar Automaton"])

    created = _tokens(scenario.game, "Treasure Token") + _tokens(scenario.game, "Thopter Token")
    assert len(created) >= 2
    assert {state.owner for state in created} == {"alice"}


def test_tokens_a_targeted_player_creates_are_that_players():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kozilek's Command"],
            battlefield=["Eldrazi Temple", "Eldrazi Temple", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Kozilek's Command", username="alice")
    casting.choose_modes([1, 2], x_value=3)
    casting.choose_targets(["bob", "bob"])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment,
        *scenario.untapped_sources(
            "Eldrazi Temple", "Eldrazi Temple", "Forest", "Forest", "Forest", username="alice"
        ),
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    spawn = _tokens(scenario.game, "Eldrazi Spawn Token")
    assert spawn
    assert {state.owner for state in spawn} == {"bob"}


def test_a_token_copy_is_owned_by_its_creator_not_the_originals_owner():
    scenario = Scenario().player("alice").player("bob", battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (copy,) = token_copy_of(scenario.game, bears, "alice")

    assert copy.owner == "alice"
    assert _round_trip(scenario.game).find_by_id(copy.id).owner == "alice"
