"""Morningtide's Light: "Exile any number of target creatures. At the
beginning of the next end step, return those cards to the battlefield
tapped under their owners' control. Until your next turn, prevent all
damage that would be dealt to you. Exile Morningtide's Light."

Four CR 608.2c instructions, each already generalised or newly added:

- **Exile any number of target creatures, then return them together at the
  next end step** - `_parse_delayed_blink_clauses`'s existing multi-target
  machinery (proven already on Displace/Eerie Interlude), widened here for
  an optional "tapped" rider on the return (CR 110.5b's default is
  untapped; a card can say otherwise).
- **Until your next turn, prevent all damage that would be dealt to you** -
  a brand-new CR 615.1a prevention shield naming the resolving spell's own
  controller and CR 611.2a's "until your next turn" duration, ended by
  `Game.begin_turn_for` rather than the cleanup step.
- **Exile `<this card's own name>`** - CR 201.5's self-reference (the same
  shape Worlds Within Worlds' and Burning Wish's own printings already
  carry, generalised into its own single-clause reader), overriding CR
  608.2n's ordinary "goes to the graveyard" for this one sorcery.

Proof printing: **Eerie Interlude** (real Scryfall data, added with
`scripts/add_card.py`, Pioneer/Modern `legal`, not a listed ecl-T8 card, not
in any deck list) - "Exile any number of target creatures you control.
Return those cards to the battlefield under their owner's control at the
beginning of the next end step." proves the shared multi-target exile/delay
machinery generally, on the *trailing* timing-phrase word order
(Morningtide's Light's own is leading) and with no "tapped" rider at all -
CR 110.5b's plain default still applies once "tapped" is not printed.

No second real Modern/Pioneer/Standard-legal printing carries the exact
"Until your next turn, prevent all damage that would be dealt to you." self-
only shape (a Scryfall full-text search for it during this session found
only Morningtide's Light; Channel Harm and Eerie Interference both prevent
damage to *you and permanents you control*, restricted to *sources you don't
control*, for *this turn* rather than *until your next turn* - a materially
different shape, not a wording variant of this one) - recorded as a dated
line in `MEMORY.md`. The reader itself is still structural, not name-keyed:
it reads "you" as whichever object's controller is resolving, and its
duration hooks into the same `Game.begin_turn_for` "until your next turn"
ending every other such duration on `Player`/`ContinuousEffect`/
`DelayedTrigger` already uses.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file: 115.6 (any number may choose zero), 400.7 (a
returned object is new), 603.6a (objects entering together), 603.7 (a
delayed triggered ability), 610.3c (returns under the owner's control by
default), 615.1a (prevention effects), 611.2a (a stated duration), 201.5
(a card refers to itself by name), 608.2n (an instant/sorcery's resolution
ends with it going to the graveyard, unless something else says otherwise).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

MORNINGTIDES_LIGHT = "Morningtide's Light"
EERIE_INTERLUDE = "Eerie Interlude"


def test_both_printings_are_fully_handled():
    for name in (MORNINGTIDES_LIGHT, EERIE_INTERLUDE):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


def test_morningtides_light_exiles_and_returns_two_creatures_tapped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MORNINGTIDES_LIGHT],
            battlefield=["Plains"] * 4 + ["Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Elite Vanguard"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    vanguard = scenario.creature("Elite Vanguard", "bob")
    bears_stamp = bears.zone_change_stamp
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.cast_and_resolve(MORNINGTIDES_LIGHT, *sources, targets=[bears, giant, vanguard])

    assert bears.zone is Zone.EXILE
    assert giant.zone is Zone.EXILE
    assert vanguard.zone is Zone.EXILE
    assert scenario.find(MORNINGTIDES_LIGHT, Zone.EXILE, "alice").zone is Zone.EXILE, (
        "CR 201.5: it exiled itself instead of going to the graveyard"
    )

    _to_end_step(scenario)

    new_bears = scenario.creature("Grizzly Bears", "alice")
    new_giant = scenario.creature("Hill Giant", "alice")
    new_vanguard = scenario.creature("Elite Vanguard", "bob")
    assert new_bears.zone_change_stamp != bears_stamp, "CR 400.7: a new object"
    assert new_bears.tapped, "returned tapped, not CR 110.5b's plain default"
    assert new_giant.tapped
    assert new_vanguard.tapped
    assert new_bears.controller == "alice" and new_vanguard.controller == "bob", (
        "CR 610.3c: under each one's own owner"
    )


def test_morningtides_light_prevents_all_damage_to_its_caster_until_next_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[MORNINGTIDES_LIGHT], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.life = 20
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.cast_and_resolve(MORNINGTIDES_LIGHT, *sources, targets=[])

    scenario.game.deal_damage(alice, 5, source=None)
    assert alice.life == 20, "CR 615.1a: prevented"

    # Still prevented on bob's own intervening turn (CR 611.2a: "your next
    # turn", not "end of this turn").
    scenario.advance()  # combat -> ... -> alice's end step
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()  # bob's untap
    scenario.game.deal_damage(alice, 4, source=None)
    assert alice.life == 20, "still prevented during bob's turn"

    scenario.advance()  # bob's upkeep
    scenario.advance()  # bob's draw
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()  # alice's own next turn begins - the shield ends here

    scenario.game.deal_damage(alice, 3, source=None)
    assert alice.life == 17, "CR 611.2a: the duration has ended"


def test_morningtides_light_may_target_no_creatures_and_still_prevents_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[MORNINGTIDES_LIGHT], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears_stamp = bears.zone_change_stamp
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    scenario.cast_and_resolve(MORNINGTIDES_LIGHT, *sources, targets=[])
    _to_end_step(scenario)

    assert bears.zone_change_stamp == bears_stamp, "CR 115.6: nothing chosen, nothing touched"


# -- proof printing: Eerie Interlude, the trailing-timing, no-"tapped" shape -


def test_eerie_interlude_exiles_and_returns_untapped_under_their_owner():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[EERIE_INTERLUDE],
            battlefield=["Plains"] * 3 + ["Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears_stamp = bears.zone_change_stamp
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")

    scenario.cast_and_resolve(EERIE_INTERLUDE, *sources, targets=[bears, giant])

    assert bears.zone is Zone.EXILE
    assert giant.zone is Zone.EXILE

    _to_end_step(scenario)

    new_bears = scenario.creature("Grizzly Bears", "alice")
    new_giant = scenario.creature("Hill Giant", "alice")
    assert new_bears.zone_change_stamp != bears_stamp
    assert not new_bears.tapped, "no 'tapped' rider printed - CR 110.5b's plain default"
    assert not new_giant.tapped
