""" "`{cost}`, Sacrifice this artifact: `<A>`. `<B>`. `<C>`. `<D>`." - a
multi-part activated ability whose cost sacrifices its own source, resolving
several sentences (and a matching count of CR 115.1 targets) as one
instruction.

Everything Pizza: "{2}{W}{U}{B}{R}{G}, {T}, Sacrifice this artifact: Target
player gains 3 life and draws a card. Each of your opponents discards a card.
This artifact deals 3 damage to any target. Put three +1/+1 counters on up to
one target creature."

- **CR 602.2c/601.2h** - the cost is paid, sacrifice included, before the
  ability ever goes on the stack: by the time this resolves, the artifact is
  already in its owner's graveyard.
- **CR 608.2h** - "this artifact" is read through `AbilityOnStack.source_or_
  last_known` from then on, the identical last-known-information primitive
  Goblin Charbelcher's own "this artifact deals damage" already uses once it
  has been sacrificed as an additional cost.
- **CR 601.2c/602.2b** - all three targets (a player, "any target", and up
  to one target creature) are declared together as the ability is put on the
  stack, in the order the sentences name them.
- **CR 115.6** - "up to one target creature" makes the fourth sentence's own
  target optional; declining it (or having no legal creature at all) still
  lets the rest of the ability resolve.
- **CR 701.9a** - "each of your opponents discards a card" is not a target at
  all, so it always happens once per opponent regardless of what was
  targeted.

No second legal printing carries this exact four-sentence combined shape
(dated MEMORY.md line). The reader's own docstring documents the one
narrower thing this engine's own target architecture cannot fully recover -
a *targeted* player becoming illegal between announcement and resolution
mid-way through the three slots - which none of these scenarios exercises.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*, alice_creature: str = "Grizzly Bears", bob_creature: str = "Llanowar Elves"):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Everything Pizza",
                alice_creature,
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
                "Plains",
                "Plains",
            ],
            hand=["Opt"],
            library=["Forest"] * 10,
        )
        .player(
            "bob",
            battlefield=[bob_creature] if bob_creature else [],
            hand=["Counterspell"],
            library=["Island"] * 10,
        )
    )


def test_the_whole_ability_runs_against_its_own_last_known_information():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pizza = scenario.find("Everything Pizza", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources(
        "Plains", "Island", "Swamp", "Mountain", "Forest", "Plains", "Plains"
    )
    alice_life = scenario.player("alice").life
    bob_hand_before = len(scenario.player("bob").hand)

    scenario.activate(
        pizza,
        *sources,
        sacrificing=[pizza],
        # "any target" is offered a creature before the player pick, so this
        # engine's own greedy target-slot matcher (`TargetingProfile._fill_
        # slots`, order-dependent with no backtracking) does not misassign
        # the player to that ambiguous slot ahead of the mandatory "target
        # player" one - see the reader's own docstring for the same
        # positional-reading limitation this order sidesteps.
        targets=[elves, "alice", bears],
    )
    scenario.pass_until_resolved()

    assert pizza.zone is Zone.GRAVEYARD
    # Target player (alice) gains 3 life and draws a card.
    assert scenario.player("alice").life == alice_life + 3
    assert len(scenario.player("alice").hand) == 2  # Opt, plus the draw
    # Each opponent discards a card - not a target, always happens.
    assert len(scenario.player("bob").hand) == bob_hand_before - 1
    # Any target (Llanowar Elves) takes 3 damage and dies (0/1 base).
    assert elves.zone is Zone.GRAVEYARD
    # Up to one target creature (Grizzly Bears) gets three +1/+1 counters.
    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_declining_the_optional_creature_target_still_runs_the_rest():
    """CR 115.6: no legal creature to put counters on (Grizzly Bears is the
    only creature and it is the "any target" damage recipient this time, but
    the ability still only ever offers up to one *additional* creature) means
    the counters sentence simply does nothing."""
    scenario = _board(bob_creature="").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pizza = scenario.find("Everything Pizza", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources(
        "Plains", "Island", "Swamp", "Mountain", "Forest", "Plains", "Plains"
    )

    scenario.activate(
        pizza,
        *sources,
        sacrificing=[pizza],
        targets=[bears, "bob"],
    )
    scenario.pass_until_resolved()

    assert pizza.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 23
    assert bears.zone is Zone.GRAVEYARD  # took the 3 damage, died to it
    # bob is both the targeted player (draws a card) and alice's only
    # opponent (discards a card): Counterspell plus the draw, minus the
    # discard, is one card left.
    assert len(scenario.player("bob").hand) == 1
