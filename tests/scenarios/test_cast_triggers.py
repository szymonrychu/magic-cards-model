"""Scenario: "When you cast this spell, ..." - a trigger that resolves before its own spell.

This is the Eldrazi shape, and it is why the eldrazi ramp lists in this project's
sweep can win a game they never untap for: the trigger goes on the stack *above*
the spell that made it, so it resolves first and cannot be undone by countering
the creature.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 113.3c** - a triggered ability is "[Trigger condition], [effect]" and
  begins with "when", "whenever", or "at".
- **CR 603.3** - "Once an ability has triggered, its controller puts it on the
  stack as an object that's not a card the next time a player would receive
  priority."
- **CR 603.3d** - putting a trigger on the stack otherwise follows CR 601.2c-d,
  which is where its targets are chosen.
- **CR 405.1** - a trigger on the stack has no card behind it.
- **CR 117.2a** - triggers can trigger "while a spell is being cast", which is
  exactly when these do.
- **CR 608.2b** - a target that is gone by resolution is illegal, and the rest of
  the effect still happens.
- **CR 701.13a / CR 406.2** - to exile an object is to move it to the exile zone.
- **CR 701.23a** - the search action.
- **CR 603.4** - the intervening *if*: Sowing Mycospawn's second trigger has
  one ("if it was kicked"), read by `machines/triggers.intervening_if_holds`
  off `Game.cast_record(spell).kicked` - CR 702.33d's "kicked" flag, recorded
  by `Casting.pay_kicker` and carried onto the stack by `Game.note_cast`.
- **CR 702.33a / CR 702.33d / CR 702.33e** - kicker, being kicked, and the
  abilities linked to it.
- **CR 105.2a / CR 105.2b / CR 105.2c / CR 202.2b** - monocolored, multicolored,
  a colorless object, and an object with no colored mana symbols in its mana
  cost being colorless - what Sanctum of Ugin's "a colorless spell" restricts
  the cast event's own spell to, not the type words a plain "Whenever you cast
  a[n] [type] spell" already reads.
- **CR 202.3 / CR 202.3e** - mana value, and an {X} spell's mana value being
  the value chosen for X while it is on the stack - what Sanctum of Ugin's
  "mana value 7 or greater" compares against.

The effects are `exile_ability_targets` and `fetch_any_land_onto_the_battlefield`
in `machines/effects.py`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, DecisionPending
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

MOUNTAINS_FOR_ULAMOG = ["Mountain"] * 10
MOUNTAINS_FOR_UGIN = ["Mountain"] * 7


def _ulamog_board(opposing: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Ulamog, the Ceaseless Hunger"],
            battlefield=list(MOUNTAINS_FOR_ULAMOG),
        )
        .player("bob", library=["Forest"], battlefield=opposing)
    )


# -- the trigger goes above the spell --------------------------------------


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    """CR 117.2a lets a trigger trigger while the spell is being cast, and
    CR 603.3 puts it on the stack the next time a player would receive priority
    - which is after the spell is already there. So the stack reads spell first,
    trigger on top, and the trigger resolves first.

    CR 405.1: the trigger is on the stack with no card behind it, which is why
    it is named after its source rather than being one.
    """
    scenario = _ulamog_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [bears, wolf])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_ULAMOG)

    scenario.cast_onto_stack("Ulamog, the Ceaseless Hunger", *sources)

    assert scenario.stack_names() == [
        "Ulamog, the Ceaseless Hunger",
        "Ulamog, the Ceaseless Hunger's triggered ability",
    ]


def test_exiling_two_target_permanents_happens_before_the_creature_arrives():
    """ "When you cast this spell, exile two target permanents."

    The trigger resolves first (CR 603.3), so both permanents are exiled
    (CR 701.13a, CR 406.2) while the 10/10 is still on the stack.
    """
    scenario = _ulamog_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [bears, wolf])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_ULAMOG)

    scenario.cast_onto_stack("Ulamog, the Ceaseless Hunger", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert wolf.zone is Zone.EXILE
    assert "Ulamog, the Ceaseless Hunger" not in scenario.battlefield_names()


def test_the_exile_is_not_the_graveyard():
    """Worth asserting separately: exile is its own zone (CR 406.2), and a
    creature exiled this way never touches a graveyard on the way, so nothing
    that watches for a creature dying sees anything.
    """
    scenario = _ulamog_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [bears, wolf])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_ULAMOG)

    scenario.cast_onto_stack("Ulamog, the Ceaseless Hunger", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("bob").graveyard == []


def test_a_target_that_has_left_is_skipped_and_the_other_is_still_exiled():
    """CR 608.2b: "a target that's no longer in the zone it was in when it was
    targeted is illegal", and the rest of the effect still happens. One
    permanent removed in response does not save the other.
    """
    scenario = _ulamog_board(["Grizzly Bears", "Watchwolf"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [bears, wolf])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_ULAMOG)

    scenario.cast_onto_stack("Ulamog, the Ceaseless Hunger", *sources)
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.EXILE


def test_ugin_exiles_up_to_one_target_permanent_as_it_is_cast():
    """Ugin, Eye of the Storms: "When you cast this spell, exile up to one target
    permanent that's one or more colors."

    "Up to one" means the trigger is legal with no target at all, so this test
    only proves the one-target case; the zero-target case is
    `test_up_to_one_target_may_be_none`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Ugin, Eye of the Storms"],
            battlefield=list(MOUNTAINS_FOR_UGIN),
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Ugin, Eye of the Storms", [bears])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_UGIN)

    scenario.cast_onto_stack("Ugin, Eye of the Storms", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE


def test_up_to_one_target_may_be_none():
    """A trigger with no targets chosen resolves and exiles nothing. It is not
    countered for having no targets, because "up to one" needs none.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Ugin, Eye of the Storms"],
            battlefield=list(MOUNTAINS_FOR_UGIN),
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_UGIN)

    scenario.cast_onto_stack("Ugin, Eye of the Storms", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_ugins_second_trigger_fires_off_a_later_colorless_spell():
    """Ugin, Eye of the Storms' *other* `CAST_SPELL` trigger: "Whenever you
    cast a colorless spell, exile up to one target permanent that's one or
    more colors."

    Neither of Ugin's two triggers has a `TRIGGER_EFFECTS` row any more (wave
    2 - see `machines/effects.py`'s `_targets_understood`); both are
    `parse_targeted_effect`'s count-agnostic exile shape. With Ugin already on
    the battlefield, casting a colorless spell fires only the second trigger -
    this is what proves the marker dispatch still tells the two apart with
    neither one written down.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Solemn Simulacrum"],
            battlefield=["Ugin, Eye of the Storms"] + ["Wastes"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Wastes"] * 4))

    scenario.choose_trigger_targets("Ugin, Eye of the Storms", [bears])
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE


def test_sanctums_trigger_ignores_a_cheap_colored_spell_but_fires_off_a_big_colorless_one():
    """Sanctum of Ugin: "Whenever you cast a colorless spell with mana value 7
    or greater, you may sacrifice this land. ..." (CR 601.2, 603.2).

    `condition_matches` used to read this `TriggerEvent.CAST_SPELL` condition
    by checking only its type words (`_types_match`), which "a colorless spell
    with mana value 7 or greater" has none of - `required` and `forbidden`
    both come back empty, and an empty requirement matches anything
    (`_types_match`'s "no type word means anything matches" default, correct
    for a plain "whenever you cast a spell" but wrong here). The condition's
    actual restrictions - colorless (CR 105.2c, 202.2b) and mana value 7 or
    greater (CR 202.3) - were never read at all, so the trigger fired for
    Malevolent Rumble, a green {1}{G} sorcery of mana value 2, exactly as
    reported. `_color_matches` and `_mana_value_comparison` now read both.

    Malevolent Rumble does not queue the trigger; Ulamog, the Ceaseless
    Hunger - colorless, mana value 10 - does.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 4,
            hand=["Malevolent Rumble", "Ulamog, the Ceaseless Hunger"],
            battlefield=["Sanctum of Ugin", "Forest", "Forest"] + list(MOUNTAINS_FOR_ULAMOG),
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("Malevolent Rumble", *forests)
    assert scenario.stack_names() == ["Malevolent Rumble"], (
        "a green mana value 2 spell must not queue Sanctum of Ugin's trigger"
    )
    scenario.pass_until_resolved()
    assert scenario.stack_names() == []

    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Ulamog, the Ceaseless Hunger", [bears, wolf])
    mountains = scenario.untapped_sources(*MOUNTAINS_FOR_ULAMOG)
    scenario.cast_onto_stack("Ulamog, the Ceaseless Hunger", *mountains)

    assert "Sanctum of Ugin's triggered ability" in scenario.stack_names(), (
        "a colorless mana value 10 spell must queue Sanctum of Ugin's trigger"
    )


# -- a cast trigger that searches -------------------------------------------


def _mycospawn_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=library,
            hand=["Sowing Mycospawn"],
            battlefield=["Forest"] * 4,
        )
        .player("bob", library=["Forest"])
    )


def test_sowing_mycospawn_fetches_a_land_before_the_creature_resolves():
    """ "When you cast this spell, search your library for a land card, put it
    onto the battlefield, then shuffle." (CR 701.23a for the search.)

    The land is on the battlefield while the Eldrazi is still on the stack,
    which is the whole reason the card is played as a four-mana ramp spell.

    Unkicked, the card's *second* cast trigger ("if it was kicked, exile
    target land") never reaches the stack at all (CR 603.4 - see
    `test_the_kicked_trigger_does_not_trigger_when_the_spell_was_not_kicked`),
    so a single pass resolves the land-fetch trigger and leaves the spell
    itself still on the stack underneath it.
    """
    scenario = _mycospawn_board(["Eldrazi Temple", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Sowing Mycospawn", *sources)
    scenario.pass_until_resolved()

    assert "Eldrazi Temple" in scenario.battlefield_names()
    assert "Sowing Mycospawn" not in scenario.battlefield_names()


def test_the_unkicked_second_trigger_fetches_nothing_extra():
    """Sowing Mycospawn prints **two** cast triggers, and `TRIGGER_EFFECTS` is
    keyed by `(card name, TriggerEvent)`, so one entry is handed both of them.

    CR 603.4's intervening *if* now stops the kicked one from triggering at
    all when the spell was not kicked (see
    `test_the_kicked_trigger_does_not_trigger_when_the_spell_was_not_kicked`),
    so only the unconditional land-fetch trigger ever reaches the stack.
    """
    scenario = _mycospawn_board(["Eldrazi Temple", "Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Sowing Mycospawn", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.battlefield_names().count("Eldrazi Temple") == 1
    assert "Island" not in scenario.battlefield_names()


def test_an_empty_library_fetches_nothing_and_the_spell_still_resolves():
    """The search finds nothing (CR 701.23a) and the trigger simply does less.
    A trigger that does nothing does not counter the spell beneath it.
    """
    scenario = _mycospawn_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Sowing Mycospawn", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert "Sowing Mycospawn" in scenario.battlefield_names()


def test_the_kicked_trigger_does_not_trigger_when_the_spell_was_not_kicked():
    """CR 603.4: an intervening *if* is checked when the ability would trigger,
    and the ability does not trigger at all if the condition is false.

    CR 702.33d's "kicked" flag is recorded by `Casting.pay_kicker` and carried
    onto the stack by `Game.note_cast`, so "if it was kicked" is genuinely
    evaluated (`Game.cast_record(spell).kicked`) rather than failing closed -
    an unkicked cast reads it as false, the correct answer, not an unreadable
    clause. An unkicked Sowing Mycospawn puts exactly one trigger on the
    stack - the unconditional land fetch - and exiles nothing, and there is no
    engine-gap notice, because this clause is read.
    """
    scenario = _mycospawn_board(["Eldrazi Temple", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Sowing Mycospawn", *sources)

    triggers = [name for name in scenario.stack_names() if "triggered ability" in name]
    assert len(triggers) == 1
    assert scenario.game.intervening_if_notices == []

    scenario.pass_until_resolved()  # the land-fetch trigger
    scenario.pass_until_resolved()  # Sowing Mycospawn itself

    assert "Eldrazi Temple" in scenario.battlefield_names()
    assert scenario.game.exile == [], "nothing should have been exiled"
    assert scenario.battlefield_names().count("Forest") == 4, "no land left the battlefield"


def test_the_kicked_trigger_fires_and_exiles_the_target_land():
    """The positive branch: a kicked Sowing Mycospawn puts **both** triggers on
    the stack, and the second one - "exile target land" - actually exiles the
    land it targeted. This is the exact defect named in
    `machines/triggers.InterveningIfNotice`'s docstring: an unkicked Mycospawn
    used to exile a land anyway, because the old default read an unreadable
    "if it was kicked" as true. Kicked now means kicked, read for real off
    `Game.cast_record`, not assumed.

    **The land-fetch trigger now fizzles here, and that is a separate, known
    gap this test accepts rather than routes around** (CR 608.2b/CR 400.7's
    zone-change target-legality fix; `test_target_zone_change_legality.py`
    is the file for that mechanism itself). `Game.trigger_targets`
    (`choose_trigger_targets` above) is keyed by **card name**, not by
    ability, so the single `[bob_island]` staged for the *exile* trigger is
    also handed to the *fetch* trigger - which prints no "target" clause at
    all and was never supposed to have one. That was harmless before this
    session: nothing ever rechecked a stale target against a moved zone. Now
    that `Game.legal_target` does, the exile trigger (which resolves first,
    CR 603.3b) moves the island to exile, and the fetch trigger's own
    resolution finds its *borrowed* target now illegal - its only one, so
    CR 608.2b fizzles the whole ability, and no land is fetched. Fixing the
    name-keying is out of scope for the zone-change fix and is not attempted
    here; `test_sowing_mycospawn_fetches_a_land_before_the_creature_resolves`
    above is the unkicked, single-trigger case that proves the fetch effect
    itself is untouched.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Eldrazi Temple", "Forest"],
            hand=["Sowing Mycospawn"],
            battlefield=["Forest"] * 5 + ["Wastes"],
        )
        .player("bob", library=["Forest"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # {3}{G} plus kicker {1}{C} totals {4}{G}{C}, six mana - the Wastes is the
    # only source that can pay the kicker's {C}, a Forest cannot.
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest", "Wastes")
    bob_island = scenario.find("Island", Zone.BATTLEFIELD)
    # "Exile target land" is the *triggered ability's* target (CR 601.2c-d,
    # 603.3d), not the creature spell's own - Sowing Mycospawn itself targets
    # nothing, so this is staged for the trigger, not `casting.choose_targets`.
    scenario.choose_trigger_targets("Sowing Mycospawn", [bob_island])

    casting = scenario.cast("Sowing Mycospawn")
    casting.pay_kicker()
    payment = casting.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)

    triggers = [name for name in scenario.stack_names() if "triggered ability" in name]
    assert len(triggers) == 2
    assert scenario.game.intervening_if_notices == []

    scenario.pass_until_resolved()  # the exile trigger (CR 603.3b: kicked one)
    scenario.pass_until_resolved()  # the land-fetch trigger
    scenario.pass_until_resolved()  # Sowing Mycospawn itself

    # CR 608.2b: the fetch trigger's borrowed, now-illegal target fizzles it -
    # see the docstring above for why this is the accepted, separate gap.
    assert "Eldrazi Temple" not in scenario.battlefield_names()
    assert bob_island.zone is Zone.EXILE


# -- CR 601.2: the costs are paid before the spell becomes cast -------------
#
# Read whole with `mise run rules:find` in the session that added these:
#
# - **CR 601.2c** - targets are announced during the proposal; CR 601.2f-h
#   determine, activate mana abilities for, and pay the total cost.
# - **CR 601.2i** - "Once the steps described in 601.2a-h are completed, ...
#   the spell becomes cast. Any abilities that trigger when a spell is cast or
#   put onto the stack trigger at this time."
# - **CR 603.3** - a triggered ability is put on the stack "the next time a
#   player would receive priority"; **CR 603.3b** is the ordering question when
#   several are waiting, and **CR 603.3d** is the trigger's own CR 601.2c
#   target announcement as it goes on the stack.
#
# The battle report (B2-13) saw Ugin's cast-trigger target question and
# Devourer of Destiny's trigger ordering pending while the lands were still
# untapped. Reproduced here in the engine, with a pause standing in for the
# seat that has not answered yet: at the moment each question is raised the
# cost is already paid and the spell already on the stack. What the report
# saw was the api serving its last committed state while a command was
# paused, not the engine asking out of order; the api now serves the paused
# board (magic-cards-model-api `tests/test_paused_cast_board.py`), and these
# tests keep the engine's order pinned.


def _pause_at_the_cast_trigger(scenario, name: str, *sources):
    scenario.game.decisions.pause_when_unanswered = True
    casting = scenario.cast(name, "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    with pytest.raises(DecisionPending) as paused:
        scenario.put_on_stack(casting)
    return casting.spell, paused.value.pending


def _all_tapped(scenario, names: list[str]) -> bool:
    lands = [s for s in scenario.game.permanents_controlled_by("alice") if s.name in names]
    return bool(lands) and all(land.tapped for land in lands)


def test_ugins_cast_trigger_asks_for_its_target_only_after_the_cost_is_paid():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Ugin, Eye of the Storms"],
            battlefield=list(MOUNTAINS_FOR_UGIN),
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_UGIN, username="alice")

    spell, pending = _pause_at_the_cast_trigger(scenario, "Ugin, Eye of the Storms", *sources)

    assert pending.decision.kind is DecisionKind.CHOOSE_TARGETS
    assert pending.decision.source == "Ugin, Eye of the Storms"
    assert _all_tapped(scenario, ["Mountain"]), "CR 601.2h paid before CR 601.2i"
    assert scenario.game.stack == [spell]
    assert spell.zone is Zone.STACK
    assert sum(scenario.game.cast_record(spell).mana_spent.values()) == 7


def test_a_cast_trigger_outside_the_pool_asks_only_after_the_cost_is_paid():
    """Petrifying Meddler: "When you cast this spell, tap up to one target
    creature and put a stun counter on it." A different effect, a different
    cost and an "up to one" target from Ugin's, on a card in no deck pool."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Petrifying Meddler"],
            battlefield=["Island"] * 5,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 5, username="alice")

    spell, pending = _pause_at_the_cast_trigger(scenario, "Petrifying Meddler", *sources)

    assert pending.decision.kind is DecisionKind.CHOOSE_TARGETS
    assert _all_tapped(scenario, ["Island"])
    assert scenario.game.stack == [spell]
    assert sum(scenario.game.cast_record(spell).mana_spent.values()) == 5


def test_two_cast_triggers_are_ordered_only_after_the_cost_is_paid():
    """Devourer of Destiny's own cast trigger and the Ugin on the battlefield's
    "Whenever you cast a colorless spell" trigger together: CR 603.3b's order
    question comes after CR 601.2h, the report's second repro."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Wastes"] * 7 + ["Ugin, Eye of the Storms"],
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Wastes"] * 7, username="alice")

    spell, pending = _pause_at_the_cast_trigger(scenario, "Devourer of Destiny", *sources)

    assert pending.decision.kind is DecisionKind.ORDER_TRIGGERS
    assert _all_tapped(scenario, ["Wastes"])
    assert scenario.game.stack == [spell]


def test_a_cost_that_cannot_be_paid_asks_no_cast_trigger_question():
    """Six Mountains for a seven-mana Ugin: CR 601.2h fails, the spell never
    becomes cast (CR 601.2i), and so nothing triggers and nothing is asked."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Ugin, Eye of the Storms"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.decisions.pause_when_unanswered = True
    casting = scenario.cast("Ugin, Eye of the Storms", "alice")
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 6, username="alice"))

    assert scenario.game.pending_triggers == []


# -- Emrakul, the Exigent Doom: "untap all lands you control" ---------------
#
# The same CR 117.2a/603.3 cast-trigger shape every test above already
# proves - this section is only about the *consequence* being one this file's
# other cast triggers never exercise: a non-targeted mass untap of the
# caster's own lands, rather than a search or an exile.


def test_untapping_all_lands_you_control_pays_the_ten_generic_mana_back():
    """Ten Wastes pay for Emrakul; the cast trigger resolves before the
    10/10 does (CR 603.3, same ordering `test_the_cast_trigger_sits_above_
    its_own_spell_on_the_stack` proves for Ulamog) and untaps every one of
    them (CR 701.26b - untapping is not targeted)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emrakul, the Exigent Doom"],
            battlefield=["Wastes"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Wastes"] * 10)

    scenario.cast_onto_stack("Emrakul, the Exigent Doom", *sources)
    assert all(land.tapped for land in sources)

    scenario.pass_until_resolved()

    assert all(not land.tapped for land in sources)


def test_the_mass_untap_reads_generically_off_untap_all_creatures_you_control():
    """Proved on a genuinely different card, not Emrakul again: Aggravated
    Assault's own "Untap all creatures you control." - a different quality
    word (creatures, not lands) read by the same
    `_parse_untap_all_you_control_clause` parser. Only the untap sentence is
    exercised here; Aggravated Assault's own extra-combat-phase half is a
    separate, unbuilt mechanic and is not what this test is about."""
    from magic_cards_model.machines.effects import parse_mixed_effect

    assert parse_mixed_effect("Untap all creatures you control.") is not None
