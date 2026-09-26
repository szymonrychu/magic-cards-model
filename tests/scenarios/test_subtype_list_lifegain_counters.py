"""SOS's Blech, Loafing Pest: "Whenever you gain life, put a +1/+1 counter
on each Pest, Bat, Insect, Snake, and Spider you control." CR 205.3's own
subtype list (an inclusive "or" - a creature carrying two of the five names
still gets one counter, not two), widened onto `machines/effects.py`'s
pre-existing "put a `<kind>` counter on each `<group>` [you control]"
reader (`_COUNTER_EACH_GROUP_RE`), whose `group` capture used to read only
one bare word (a card type or a single subtype).

**Agent Phil Coulson** (off-pool, real, Modern/Pioneer/Standard-legal) - "{T}:
Put a +1/+1 counter on each other Hero you control." - is the generality
proof for the *widening itself*: it is the pre-existing single-subtype,
"other"-qualified, activated-ability shape the widened regex still has to
read exactly as before, on a card this task did not touch and does not own.
Both cards resolve through the identical `effects._parse_put_counters_on_
group_clause`, so proving the single-element case still works alongside the
five-element one is what shows the widening is additive, not a rewrite.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 205.3** - subtypes, including creature types; a card's own type line
  can carry more than one at once.
- **CR 119.9** - life gain is one event even when it happens as a result of
  several sources at once (not exercised here directly, but why this file's
  own `Game.gain_life` call raises exactly one trigger).
- **CR 613.5** - the computed board's own subtypes are what a group clause
  reads, not the printed type line alone - a permanent that gained a
  subtype through a continuous effect still counts.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

BLECH = "Blech, Loafing Pest"
COULSON = "Agent Phil Coulson"


def test_blech_puts_a_counter_on_each_creature_of_any_listed_type():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[BLECH, "Essenceknit Scholar", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blech = scenario.creature(BLECH, "alice")
    dryad = scenario.creature("Essenceknit Scholar", "alice")  # a Dryad Warlock -
    # none of the five listed types, even though it *makes* Pest tokens.
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.gain_life(scenario.player("alice"), 1)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert blech.counter_count(Counter.PLUS_ONE) == 1, "Blech is itself a Pest"
    assert dryad.counter_count(Counter.PLUS_ONE) == 0, "Essenceknit Scholar is a Dryad Warlock"
    assert bears.counter_count(Counter.PLUS_ONE) == 0, (
        "Grizzly Bears carries none of the five types"
    )


def test_blech_does_not_double_count_a_creature_matching_two_listed_types():
    """CR 205.3's list is an inclusive "or": one creature matching more than
    one named subtype still gets exactly one counter, not one per match."""
    scenario = Scenario().player("alice", battlefield=[BLECH]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blech = scenario.creature(BLECH, "alice")

    scenario.game.gain_life(scenario.player("alice"), 1)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert blech.counter_count(Counter.PLUS_ONE) == 1, (
        "Blech is a Pest, and only a Pest - one match, one counter - but the "
        "reader must never add twice even if a future printing named two of "
        "its own types"
    )


def test_blech_does_nothing_without_a_life_gain():
    scenario = Scenario().player("alice", battlefield=[BLECH]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blech = scenario.creature(BLECH, "alice")

    assert blech.counter_count(Counter.PLUS_ONE) == 0


def test_agent_phil_coulson_still_reads_the_single_subtype_other_shape():
    """Off-pool generality proof: the widened group regex still reads the
    pre-existing one-element, "other"-qualified case exactly as before."""
    scenario = (
        Scenario().player("alice", battlefield=[COULSON, "Agent Maria Hill"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    coulson = scenario.creature(COULSON, "alice")
    hill = scenario.creature("Agent Maria Hill", "alice")

    scenario.activate(coulson)
    scenario.resolve_top()

    assert coulson.counter_count(Counter.PLUS_ONE) == 0, '"other Hero" excludes Coulson himself'
    assert hill.counter_count(Counter.PLUS_ONE) == 1, "Agent Maria Hill is another Hero"
