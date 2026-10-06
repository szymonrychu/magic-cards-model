"""The predefined Shard token (CR 111.10e), created by Niko Aris.

- **Niko Aris** - "When Niko Aris enters, create X Shard tokens." and
  "-1: Create a Shard token." The reminder text names the token's one
  ability: "{2}, Sacrifice this token: Scry 1, then draw a card."

Niko Aris is the proof printing of NW01-T7's "Whenever that creature ...
this turn" reader (test_nw01_chosen_creature_delayed_triggers.py); these are
its two other clauses, closed here so the proof card carries no silent
clause.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 111.10e** - "A Shard token is a colorless Shard enchantment token
  with '{2}, Sacrifice this token: Scry 1, then draw a card.'"
- **CR 107.3a** - X in the mana cost is the value announced on casting; the
  enters trigger's X is that same value, and 0 when none was announced.
- **CR 701.22a** - scry: look at the top card, put it on the bottom or keep
  it on top.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from tests.scenarios.harness import Scenario


def _shards(scenario: Scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.card.subtypes == ["Shard"] and state.controller == username
    ]


def _cast_niko(scenario: Scenario, x_value: int) -> None:
    sources = scenario.untapped_sources(
        "Plains", "Island", "Island", *["Island"] * x_value, username="alice"
    )
    casting = scenario.cast("Niko Aris")
    casting.determine_cost(x_value=x_value)
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _niko_scenario(extra_islands: int) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Niko Aris"],
            battlefield=["Plains", "Island", "Island", *["Island"] * extra_islands],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_niko_aris_enters_creating_x_shard_tokens():
    scenario = _niko_scenario(extra_islands=2)
    _cast_niko(scenario, x_value=2)

    shards = _shards(scenario)
    assert len(shards) == 2
    shard = shards[0]
    assert shard.card.types == [Type.ENCHANTMENT]
    assert shard.card.colors == []
    assert "Scry 1, then draw a card" in (shard.card.oracle_text or "")


def test_niko_aris_cast_for_x_zero_creates_no_shard():
    scenario = _niko_scenario(extra_islands=0)
    _cast_niko(scenario, x_value=0)

    assert scenario.find("Niko Aris", Zone.BATTLEFIELD, "alice") is not None
    assert _shards(scenario) == []


def test_niko_aris_minus_one_creates_one_shard_token():
    scenario = Scenario().player("alice", battlefield=["Niko Aris"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    niko = scenario.find("Niko Aris", Zone.BATTLEFIELD, "alice")
    loyalty = niko.loyalty

    scenario.activate(niko, index=2)
    scenario.pass_until_resolved()

    assert len(_shards(scenario)) == 1
    assert niko.loyalty == loyalty - 1, "CR 606.4: the -1 loyalty cost"


def test_shard_token_scries_one_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Niko Aris", "Island", "Island"],
            library=["Grizzly Bears", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    niko = scenario.find("Niko Aris", Zone.BATTLEFIELD, "alice")
    scenario.activate(niko, index=2)
    scenario.pass_until_resolved()
    (shard,) = _shards(scenario)

    bears, mountain = alice.library[0], alice.library[1]
    scenario.scry_bottoming(bears, username="alice")
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(shard, *islands, index=0, sacrificing=[shard])
    assert shard not in scenario.game.battlefield, "sacrificed as a cost"
    scenario.pass_until_resolved()

    assert mountain in alice.hand, "the card under the scried-away one is drawn"
    assert alice.library[-1] is bears
    assert _shards(scenario) == []
