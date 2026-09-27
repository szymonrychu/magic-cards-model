"""Scenario: "Whenever you commit a crime, ..." (CR 700.13) as a real trigger
event, not only the intervening-if boolean `machines/conditions/history.
_committed_crime` already reads.

CR 700.13: "A player commits a crime as that player casts a spell, activates
an ability, or puts a triggered ability on the stack and that spell or
ability targets at least one opponent; at least one permanent, spell, or
ability an opponent controls; and/or at least one card in an opponent's
graveyard." `machines/conditions/history.record_crime` already records the
turn-scoped fact CR 700.13's intervening-if reads ("you've committed a crime
this turn"), but nothing raised a `GameEvent` a *trigger* could watch, so
"Whenever you commit a crime, [effect]" simply never fired: the ability
parsed, the effect parsed, and the condition was never checked at all.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Magda, the Hoardmaster**: "Whenever you commit a crime, create a tapped
  Treasure token. This ability triggers only once each turn." (CR 603.2h's
  own once-per-turn limiter, already read generically.)
- **Forsaken Miner** (a second printing, not in the api deck pool): "This
  creature can't block. Whenever you commit a crime, you may pay {B}. If you
  do, return this card from your graveyard to the battlefield." - proof that
  the new trigger composes with an ordinary CR 118.12 "if you do" reflexive
  reader already in place, not just with a plain token-creation effect.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

MAGDA = "Magda, the Hoardmaster"
MINER = "Forsaken Miner"


def _board(magda_battlefield: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=[*magda_battlefield, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bolt_bob_committing_a_crime(scenario: Scenario, *, target: str | object = "bob") -> None:
    """CR 601.2i/700.13: the crime is committed the instant the spell becomes
    cast - before it resolves - so a "whenever you commit a crime" trigger
    goes on the stack *above* the still-unresolved spell (CR 603.3) and
    resolves first."""
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[target])
    scenario.game.put_triggers_on_stack()


def _drain_stack(scenario: Scenario) -> None:
    while scenario.stack_names():
        scenario.resolve_top()


def test_magda_creates_a_tapped_treasure_when_you_commit_a_crime():
    scenario = _board([MAGDA])
    _bolt_bob_committing_a_crime(scenario)
    assert scenario.stack_names() == [
        "Lightning Bolt",
        f"{MAGDA}'s triggered ability",
    ], "the crime trigger resolves before the spell that committed it"
    _drain_stack(scenario)

    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Treasure Token"
    ]
    assert len(treasures) == 1
    assert treasures[0].tapped


def test_magda_does_not_trigger_when_nothing_targets_an_opponent():
    """Bolting your own creature is not a crime (CR 700.13): no opponent, no
    opposing permanent, no card in an opponent's graveyard is targeted."""
    scenario = _board([MAGDA, "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _bolt_bob_committing_a_crime(scenario, target=bears)

    assert scenario.stack_names() == ["Lightning Bolt"]


def test_magda_triggers_only_once_each_turn():
    """CR 603.2h: the ability's own limiter, already generic - a second crime
    the same turn creates no second Treasure."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Shock"],
            battlefield=[MAGDA, "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain_one, mountain_two) = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain_one, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    _drain_stack(scenario)
    scenario.cast_onto_stack("Shock", mountain_two, targets=["bob"])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Shock"], "no second crime trigger this turn"
    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Treasure Token"
    ]
    assert len(treasures) == 1


def test_forsaken_miner_reflexive_pay_returns_it_from_the_graveyard():
    """A second printing of the same trigger, composed with an ordinary
    CR 118.12 "if you do" reflexive already read."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            graveyard=[MINER],
            battlefield=["Mountain", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source=MINER)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Lightning Bolt", f"{MINER}'s triggered ability"]
    _drain_stack(scenario)

    miner = scenario.creature(MINER, "alice")
    assert miner.zone is Zone.BATTLEFIELD
