""" "Return/exile target `<X>`, ... with a `<kind>` counter on it." never
restricts the *target* by a counter the effect is about to place on it
(CR 608.2c, CR 115.2, CR 122.1).

Both reported cards read the whole rest of their own sentence - "from your
graveyard to the battlefield with a `<kind>` counter on it" (Persist), "then
return that card to the battlefield under its owner's control with a
`<kind>` counter on it" (Daydream) - as the *target's own noun phrase*, so
`targeting._extract_required_counter_kind` spliced "with a `<kind>` counter
on it" out and treated it as a restriction the target must already satisfy.
CR 608.2c: "read the whole text and apply the rules of English to the text" -
the counter clause here belongs to what the ability *does* once its target
resolves, the same distinction `_TARGET_CLAUSE_VERB_RE`'s own docstring
already draws for "gains"/"gets"/"becomes"/"loses". A card that returns
something "to the battlefield" is squarely on the *doing* side of that line,
never the target's own description, so a "with a `<kind>` counter on it"
clause reached only after "to"/"onto the battlefield" is never a target
restriction - `_before_target_clause_verb`'s cutoff now reads that boundary
too, not only the four verbs.

Persist could never be targeted at all - no card sits in a graveyard with a
-1/-1 counter already on it, since counters do not survive a zone change
(CR 122.2). Daydream's own battlefield creature had the identical problem in
miniature: a permanent with no +1/+1 counter on it yet was refused as a
target for the very spell that was about to give it one.

Both cards' own effect halves needed the identical widening on the
*effects.py* side once targeting was no longer the blocker:
`_RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_WITH_COUNTER_RE` only read
Generous Revival's own "with an additional `<kind>` counter on it"; Persist's
plain "with a `<kind>` counter on it" (no "additional") is the same CR 122.1
counter-placed-as-it-arrives shape with one fewer word, so "additional" is
now optional there. `_RETURN_TO_BATTLEFIELD_RE` (Ephemerate's own blink
return) read no trailing counter rider at all; Daydream's is the identical
rider on the identical "return ... to the battlefield under its owner's/your
control" shape, so the rider is now read there too.

Unbreakable Bond is the off-set proof: a real, non-pool, non-reported
printing carrying a differently-named counter (a "lifelink" counter, not
either power/toughness spelling) on the identical "return target creature
card from your graveyard to the battlefield with a `<kind>` counter on it"
template, proving the fix reads the shape rather than either reported card's
own exact words.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_persist_targets_and_reanimates_a_graveyard_creature_with_no_counters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Persist"],
            battlefield=["Swamp", "Swamp"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.counter_count(Counter.MINUS_ONE) == 0

    casting = scenario.cast("Persist", username="alice")
    # CR 115.2/CR 601.2c: the graveyard creature - carrying no -1/-1 counter,
    # since counters do not survive the zone change it is about to make - is
    # a legal target right now, not refused for a counter it does not have.
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.counter_count(Counter.MINUS_ONE) == 1


def test_daydream_targets_and_returns_its_own_creature_with_a_fresh_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Daydream"],
            battlefield=["Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert bears.counter_count(Counter.PLUS_ONE) == 0

    casting = scenario.cast("Daydream", username="alice")
    # The battlefield creature Daydream is about to give its first +1/+1
    # counter to is a legal target right now, precisely because it does not
    # have one yet.
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    reentered = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert reentered.controller == "alice"
    assert reentered.counter_count(Counter.PLUS_ONE) == 1


def test_unbreakable_bond_reads_the_general_reanimate_with_a_counter_template():
    """Unbreakable Bond: real, off-set, non-fra, not the reported card -
    "Return target creature card from your graveyard to the battlefield with
    a lifelink counter on it." A counter kind that is neither power/toughness
    spelling, proving the fix reads the shape, not either reported card's own
    counter word.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unbreakable Bond"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Unbreakable Bond", username="alice")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.counter_count("lifelink") == 1
