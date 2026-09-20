""" "As [this] enters, [you may] sacrifice any number of `<description>`.
[If you do, ]it enters with [twice] that many `<kind>` counters on it." (CR
614.1c, CR 614.12, CR 614.12a) - Shimatsu the Bloodcloaked and Devouring
Hellion.

Both cards used to come back `static_unaudited` from `scripts/sweep_pool.py`:
`machines/replacement.py`'s `_try_enters_with`/`_read_counters` split "that
many"/"twice that many" into an unknown count word, and the honest
"unreadable count" path (`_amount_of` deliberately refuses "that many" as a
guessed CR 107.3m X - see its own docstring) made the whole `ENTERS_WITH`
sentence come back `UNPARSED` rather than a made-up amount. The sacrifice
sentence in front of it (`AS_ENTERS`, "sacrifice any number of `<permanents>`"
/ "you may sacrifice any number of `<creatures and/or planeswalkers>`") had no
consumer at all in `_self_enters_modifiers` - unlike the shockland's "you may
pay N life. If you don't, it enters tapped." pairing, which is the one other
two-sentence CR 614.12a choice that module already performs.

This file covers the general shape - not the two named cards' own text, since
nothing in the fix reads a card name - built out of `_read_counters` learning
"[`<multiplier>`] that many `<kind>` counters" (`that_many_multiplier` on
`ReplacementEffect`) and `_self_enters_modifiers` pairing an `AS_ENTERS`
"[you may ]sacrifice any number of `<description>`" clause with a following
`ENTERS_WITH` clause carrying that marker, the same way it already pairs the
shockland's two sentences.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 614.1c** - "Effects that read '[This permanent] enters with . . . ,'
  'As [this permanent] enters . . . ,' or '[This permanent] enters as . . .'
  are replacement effects."
- **CR 614.12** - "Some replacement effects modify how a permanent enters the
  battlefield... Such effects may come from the permanent itself if they
  affect only that permanent."
- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield" - which is why the candidates below never
  include the entering permanent itself: it is not on the battlefield yet
  when the choice is made.
- **CR 107.1c** - "If a rule or ability instructs a player to choose 'any
  number,' that player may choose any positive number or zero" - the reason
  Devouring Hellion's "you may" and Shimatsu's bare "sacrifice any number of"
  both permit choosing none, with no separate yes/no asked first.
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard... Sacrificing a
  permanent doesn't destroy it."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

SHIMATSU = "Shimatsu the Bloodcloaked"
HELLION = "Devouring Hellion"


# --------------------------------------------------------------------------
# Shimatsu the Bloodcloaked: mandatory "sacrifice any number of permanents",
# bare "that many" (multiplier 1)
# --------------------------------------------------------------------------


def test_shimatsu_cast_sacrificing_two_permanents_enters_with_two_counters():
    """Cast for real, off four Mountains: two permanents chosen, two counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SHIMATSU],
            battlefield=[
                "Grizzly Bears",
                "Swamp",
                "Island",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.will_choose_cards(bears, swamp, source=SHIMATSU)

    shimatsu = scenario.cast_and_resolve(SHIMATSU, *mountains)

    assert shimatsu.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert swamp.zone is Zone.GRAVEYARD
    assert island.zone is Zone.BATTLEFIELD
    assert shimatsu.counters[Counter.PLUS_ONE] == 2


def test_shimatsu_sacrificing_none_enters_with_no_counters():
    """CR 107.1c: choosing zero is legal on its own, no "you may" printed."""
    scenario = (
        Scenario().player("alice", hand=[SHIMATSU], battlefield=["Swamp"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(source=SHIMATSU)

    shimatsu = scenario.put_onto_battlefield(SHIMATSU, "alice")

    assert shimatsu.zone is Zone.BATTLEFIELD
    assert swamp.zone is Zone.BATTLEFIELD
    assert shimatsu.counters[Counter.PLUS_ONE] == 0


def test_shimatsu_itself_is_never_offered_as_a_permanent_to_sacrifice():
    """CR 614.12a: the choice is made before Shimatsu is on the battlefield,
    so its own id is never among the candidates - only the Swamp is offered."""
    scenario = (
        Scenario().player("alice", hand=[SHIMATSU], battlefield=["Swamp"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(swamp, source=SHIMATSU)

    shimatsu = scenario.put_onto_battlefield(SHIMATSU, "alice")

    (asked,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == SHIMATSU
    ]
    assert set(asked.cards) == {swamp.id}
    assert shimatsu.id not in asked.cards
    assert swamp.zone is Zone.GRAVEYARD
    assert shimatsu.counters[Counter.PLUS_ONE] == 1


# --------------------------------------------------------------------------
# Devouring Hellion: optional "you may sacrifice any number of creatures
# and/or planeswalkers", "twice that many" (multiplier 2)
# --------------------------------------------------------------------------


def test_devouring_hellion_sacrificing_a_creature_and_a_planeswalker_enters_with_four_counters():
    """Two sacrificed, doubled: four +1/+1 counters. The Swamp - neither a
    creature nor a planeswalker - is never touched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HELLION],
            battlefield=["Grizzly Bears", "Karn, the Great Creator", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    karn = scenario.find("Karn, the Great Creator", Zone.BATTLEFIELD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, karn, source=HELLION)

    hellion = scenario.put_onto_battlefield(HELLION, "alice")

    assert hellion.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert karn.zone is Zone.GRAVEYARD
    assert swamp.zone is Zone.BATTLEFIELD
    assert hellion.counters[Counter.PLUS_ONE] == 4


def test_devouring_hellion_declining_enters_with_no_counters():
    """CR 107.1c again: "any number of" already permits zero without a
    separate yes/no gate, so declining just means choosing none."""
    scenario = (
        Scenario()
        .player("alice", hand=[HELLION], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(source=HELLION)

    hellion = scenario.put_onto_battlefield(HELLION, "alice")

    assert hellion.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD
    assert hellion.counters[Counter.PLUS_ONE] == 0


def test_devouring_hellion_cannot_be_offered_a_land_that_does_not_fit_the_description():
    """The Swamp is not a creature or planeswalker, so it is never among the
    candidates `Decision.cards` lists - only the Bears is offered."""
    scenario = (
        Scenario()
        .player("alice", hand=[HELLION], battlefield=["Grizzly Bears", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(bears, source=HELLION)

    hellion = scenario.put_onto_battlefield(HELLION, "alice")

    (asked,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == HELLION
    ]
    assert set(asked.cards) == {bears.id}
    assert swamp.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert hellion.counters[Counter.PLUS_ONE] == 2
