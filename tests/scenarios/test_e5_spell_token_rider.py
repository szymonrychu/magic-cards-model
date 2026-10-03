"""Essence Feed: "Target player loses 3 life. You gain 3 life and create three
0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token:
Add {C}.""

The last sentence is part of the tokens' definition (CR 111.3, CR 608.2c), so
each created Spawn has the mana ability and can be sacrificed for {C}.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _cast():
    scenario = (
        Scenario()
        .player("alice", hand=["Essence Feed"], battlefield=["Swamp"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Essence Feed", *scenario.untapped_sources(*["Swamp"] * 6), targets=["bob"])
    return scenario


def test_life_swing_and_three_spawn_tokens():
    scenario = _cast()
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    spawn = [s for s in scenario.game.battlefield if s.name == "Eldrazi Spawn Token"]
    assert len(spawn) == 3
    for token in spawn:
        assert (token.power, token.toughness) == (0, 1)


def test_each_spawn_token_has_the_sacrifice_for_mana_ability():
    scenario = _cast()
    spawn = [s for s in scenario.game.battlefield if s.name == "Eldrazi Spawn Token"]
    assert all(t.card.oracle_text == "Sacrifice this token: Add {C}." for t in spawn)
    scenario.activate(spawn[0])
    assert spawn[0].zone is not Zone.BATTLEFIELD, "sacrificed as the cost"
    assert scenario.player("alice").mana_pool.total == 1


def test_the_support_oracle_scores_the_rider_as_read():
    """The ablation probe compared a token definition carrying the granted
    ability equal to one without it (a freed temporary's id reused in
    `same_closure`'s visited set) and called the sentence ignored."""
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    assert card_support(card("Essence Feed")).status == HANDLED
