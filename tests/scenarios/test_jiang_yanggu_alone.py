"""Jiang Yanggu, Alone: "Whenever a creature you control attacks a player
alone, discard a card, then draw a card. Then put a +1/+1 counter on that
creature for each card you've discarded this turn."

The trigger condition itself (CR 506.6's "attacks a player alone") is
already proven in `test_attacks_alone_trigger.py`; this file is about the
effect body, previously wholly silent: "discard a card" and "draw a card"
were each already readable alone, but "put a +1/+1 counter on that creature
for each card you've discarded this turn" had no clause parser at all - a
`None` from `_parse_mixed_clauses` that took the whole three-clause
instruction down with it (CR 608.2c: no partial run).

`_parse_counter_on_trigger_subject_clause` (CR 400.7's "that creature"
anaphora back to `GameEvent.subject_id`, the identical referent `_parse_
untap_trigger_subject_clause` already reads for "untap it") plus
`_COUNT_CARDS_DISCARDED_THIS_TURN_RE`'s own count (proven off-set on Misty
Knight, Hero for Hire in `test_cards_discarded_this_turn_count.py`) close
the gap together.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 506.6** - "attacks a player alone" (the trigger condition, proven
  elsewhere).
- **CR 400.7** - an object leaving a zone becomes a new object with no
  memory of its previous existence; "that creature" names the object the
  trigger's own condition already identified, at the moment it is named.
- **CR 701.9a** - discarding.
- **CR 608.2h** - a magnitude ("for each ...") is locked in once, when the
  effect applies, not re-read partway through resolving it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _advance_until(scenario: Scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()


def test_jiang_yanggu_discards_draws_and_gets_one_counter_from_its_own_attack():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jiang Yanggu, Alone"],
            hand=["Lightning Bolt", "Lava Spike"],
            library=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    jiang = scenario.creature("Jiang Yanggu, Alone", "alice")
    alice = scenario.player("alice")

    scenario.attack_with(jiang, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(
        scenario.find("Lightning Bolt", Zone.HAND, "alice"), username="alice"
    )
    scenario.pass_until_resolved()

    assert "Lightning Bolt" not in [state.name for state in alice.hand]
    assert "Forest" in [state.name for state in alice.hand]
    assert jiang.counter_count("+1/+1") == 1
    characteristics = scenario.game.characteristics_of(jiang)
    assert (characteristics.power, characteristics.toughness) == (4 + 1, 4 + 1)
    assert scenario.game.cards_discarded_this_turn.get("alice") == 1


def test_jiang_yanggu_counts_a_discard_from_earlier_in_the_same_turn_too():
    """ "for each card you've discarded this turn" (CR 608.2h) is the whole
    turn's running total, not only the discard this trigger's own first
    clause just made - Misty Knight's own activation, resolved in the main
    phase before combat, already put one discard on the same turn's ledger,
    so Jiang's own discard (its trigger's first clause) brings the count to
    two by the time the counters are placed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Jiang Yanggu, Alone",
                "Misty Knight, Hero for Hire",
                "Mountain",
                "Mountain",
            ],
            hand=["Lightning Bolt", "Lava Spike", "Shock"],
            library=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    misty = scenario.creature("Misty Knight, Hero for Hire", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(misty, *sources, discarding=[bolt])
    scenario.resolve_top()
    assert scenario.game.cards_discarded_this_turn.get("alice") == 1

    _advance_until(scenario, lambda s: s.step is Step.DECLARE_ATTACKERS)
    jiang = scenario.creature("Jiang Yanggu, Alone", "alice")
    alice = scenario.player("alice")

    scenario.attack_with(jiang, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(scenario.find("Lava Spike", Zone.HAND, "alice"), username="alice")
    scenario.pass_until_resolved()

    assert "Lava Spike" not in [state.name for state in alice.hand]
    assert scenario.game.cards_discarded_this_turn.get("alice") == 2
    assert jiang.counter_count("+1/+1") == 2
    characteristics = scenario.game.characteristics_of(jiang)
    assert (characteristics.power, characteristics.toughness) == (4 + 2, 4 + 2)
