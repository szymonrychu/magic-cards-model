"""Shadow, an evasion ability that cuts both ways (CR 702.28).

Verified this session with `mise run rules:find 702.28`:

- CR 702.28a: "Shadow is an evasion ability."
- CR 702.28b: "A creature with shadow can't be blocked by creatures without
  shadow, and a creature without shadow can't be blocked by creatures with
  shadow."
- CR 702.28c: "Multiple instances of shadow on the same creature are
  redundant."

Dauthi Voidwalker exposed it; Dauthi Slayer (Time Spiral timeshifted, Modern
legal, in no deck) is the second printing. The refusal is the declare-blockers
check (CR 509.1b), asked through `Game.why_cannot_block`.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

VOIDWALKER = "Dauthi Voidwalker"
SLAYER = "Dauthi Slayer"


def _to_blocks(scenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.pass_until_resolved()
    scenario.turn.advance_to(Step.DECLARE_BLOCKERS)
    scenario.game.sync_priority_with_step()


def test_a_shadow_attacker_cannot_be_blocked_by_a_creature_without_shadow():
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 4, battlefield=[VOIDWALKER])
        .player("bob", library=["Swamp"] * 4, battlefield=["Grizzly Bears"])
        .build()
    )
    walker = scenario.creature(VOIDWALKER, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _to_blocks(scenario, walker)

    refusal = scenario.game.why_cannot_block(bears, walker)

    assert refusal is not None
    assert "shadow" in refusal.lower()
    assert "702.28b" in refusal


def test_a_shadow_creature_cannot_block_a_creature_without_shadow():
    """The other half of CR 702.28b - shadow is a drawback on defence."""
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 4, battlefield=["Grizzly Bears"])
        .player("bob", library=["Swamp"] * 4, battlefield=[SLAYER])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    slayer = scenario.creature(SLAYER, "bob")
    _to_blocks(scenario, bears)

    refusal = scenario.game.why_cannot_block(slayer, bears)

    assert refusal is not None
    assert "shadow" in refusal.lower()


def test_shadow_can_block_shadow():
    """Two shadow creatures meet each other normally."""
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 4, battlefield=[SLAYER])
        .player("bob", library=["Swamp"] * 4, battlefield=[VOIDWALKER])
        .build()
    )
    slayer = scenario.creature(SLAYER, "alice")
    walker = scenario.creature(VOIDWALKER, "bob")
    _to_blocks(scenario, slayer)

    assert scenario.game.why_cannot_block(walker, slayer) is None
    scenario.block(slayer, walker)
    assert walker in scenario.blockers()


def test_two_creatures_without_shadow_are_unaffected():
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 4, battlefield=["Grizzly Bears", VOIDWALKER])
        .player("bob", library=["Swamp"] * 4, battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    _to_blocks(scenario, bears)

    assert scenario.game.why_cannot_block(blocker, bears) is None


def test_an_unblocked_shadow_attacker_deals_its_damage():
    """The evasion in play: the only potential blocker is refused, so the
    Voidwalker connects for 3."""
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"] * 4, battlefield=[VOIDWALKER])
        .player("bob", library=["Swamp"] * 4, battlefield=["Grizzly Bears"])
        .build()
    )
    walker = scenario.creature(VOIDWALKER, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _to_blocks(scenario, walker)

    try:
        scenario.block(walker, bears)
        blocked = True
    except ValueError:
        blocked = False
    assert blocked is False
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17


def test_shadow_is_no_longer_an_ignored_keyword():
    from magic_cards_model.support import ignored_keywords
    from tests.cards import card

    assert "Shadow" not in ignored_keywords(card(VOIDWALKER))
    assert "Shadow" not in ignored_keywords(card(SLAYER))
