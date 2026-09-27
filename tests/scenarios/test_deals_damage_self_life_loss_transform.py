"""Scenario: Cecil, Dark Knight // Cecil, Redeemed Paladin's ability-word
triggers (CR 207.2c: an ability word has no rules meaning of its own, so
"Darkness — "/"Protect — " are labels, not part of the condition).

Trigger *recognition* already worked before this file - `TriggerEvent.
DEALS_DAMAGE` reads a bare "Cecil deals damage" self-reference and
`TriggerEvent.ATTACKS` reads "Cecil attacks" the same way, ability word
stripped, per `machines/abilities.py`'s own parsing pipeline. What was
missing was the *effect* on each side:

- **Darkness** — "Whenever Cecil deals damage, you lose that much life.
  Then if your life total is less than or equal to half your starting life
  total, untap Cecil and transform it." "That much" is the damage amount
  (CR 120.1's own `GameEvent.amount`); the transform is CR 701.27a's
  ordinary self one.
- **Protect** — "Whenever Cecil attacks, other attacking creatures gain
  indestructible until end of turn." - the keyword-grant twin of the
  already-generic "each other attacking creature gets +N/+N" mass pump.

No second, off-pool printing was found for either exact shape in a
Modern/Pioneer/Standard-legal card (recorded rather than asserted, in
`docs/engine-coverage.md` and a dated `MEMORY.md` line) - both readers are
still shape-matched (the card's own name normalized to "this permanent"
before either pattern is tried, `machines/abilities.self_normalized_
effect_text`), never gated on Cecil's name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword

from .harness import Scenario

CECIL = "Cecil, Dark Knight"
CECIL_BACK = "Cecil, Redeemed Paladin"


def test_darkness_loses_life_equal_to_damage_dealt_no_transform_above_half():
    scenario = Scenario().player("alice", battlefield=[CECIL]).player("bob", battlefield=[]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cecil = scenario.creature(CECIL, "alice")
    scenario.player("alice").life = 20

    scenario.attack_with(cecil)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CECIL}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").life == 18, "2 damage dealt, 2 life lost"
    assert cecil.name == CECIL, "life total (9) is above half of 20 - no transform"
    assert cecil.tapped, "not untapped either, since the transform never happened"


def test_darkness_untaps_and_transforms_at_or_below_half_starting_life():
    scenario = Scenario().player("alice", battlefield=[CECIL]).player("bob", battlefield=[]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cecil = scenario.creature(CECIL, "alice")
    scenario.player("alice").life = 11

    scenario.attack_with(cecil)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CECIL}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").life == 9
    assert cecil.name == CECIL_BACK, "9 <= half of 20 (10) - transforms"
    assert not cecil.tapped, "CR 701.27a's own untap, part of the same effect"


def test_protect_grants_indestructible_to_other_attackers_only():
    scenario = (
        Scenario()
        .player("alice", battlefield=[CECIL, "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cecil = scenario.creature(CECIL, "alice")
    cecil.transform()  # CR 701.27a: now Cecil, Redeemed Paladin - "Protect" is its face
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.attack_with(cecil, bears)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CECIL_BACK}'s triggered ability"]
    scenario.resolve_top()

    assert has_keyword(bears, "indestructible", scenario.game)
    assert not has_keyword(cecil, "indestructible", scenario.game), "other, not itself"
    assert not has_keyword(giant, "indestructible", scenario.game), "not a defender"
