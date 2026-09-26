"""Scenario: three spells whose own effect reads CR 601.2h's "amount of mana
spent to cast" a spell - Mana Sculpt (the *countered* spell's amount, at a
delayed main phase), Molten Note (*this* spell's own amount, including a
flashback recast's cost), and Burrog Barrage (a conditional pump keyed off
"you've cast another instant or sorcery spell this turn", then an
unconditional bite for whatever power that pump left the creature at).

Mana Sculpt: "Counter target spell. If you control a Wizard, add an amount
of {C} equal to the amount of mana spent to cast that spell at the beginning
of your next main phase." The mana amount is captured off the *countered*
spell's own `CastRecord` while it still exists on the stack (CR 608.2b: it
is gone the instant `Game.counter` moves it), carried as a plain integer on
a new delayed triggered ability (`machines/delayed.AddManaAmountForController`)
that waits for either of the controller's own main phases
(`DelayedTrigger.any_main_phase`, CR 505.1). "You control a Wizard" gates
whether the delayed trigger is even created, checked once as Mana Sculpt
itself resolves - not itself a delayed condition.

Molten Note: "Molten Note deals damage to target creature equal to the
amount of mana spent to cast this spell. Untap all creatures you control."
"This spell" is CR 700.7's self-reference (`machines/effects._amount_term`'s
own new "the amount of mana spent to cast this spell" term, reused by
`amount_expression` wherever a spell's own resolution reads an `<expr>`) -
verified here on both a plain cast and a flashback recast (CR 702.34a: the
flashback cost *is* what CR 601.2h pays, so a flashback-cast Molten Note's
own damage is the flashback cost's total, not the printed mana cost's).

Burrog Barrage: "Target creature you control gets +1/+0 until end of turn
if you've cast another instant or sorcery spell this turn. Then it deals
damage equal to its power to up to one target creature an opponent
controls." The "another" exclusion
(`machines/conditions/history._cast_a_spell`, widened this task) counts
Burrog Barrage's own cast as not "another" - only a *different* instant or
sorcery already cast earlier this turn satisfies it. The bite half always
runs, off whatever power the creature has by then, reusing `_resolve_bite_
damage` outright (shared with Rabid Bite's own identical "deals damage equal
to its power to" shape, exercised standalone below as the proof printing).

Rabid Bite ({1}{G}, "Target creature you control deals damage equal to its
power to target creature you don't control.", Modern/Pioneer/Standard-legal)
is the proof printing for the "deals damage equal to its power to" reader
Burrog Barrage's own rider shares - a genuinely different card, not in this
round and not in any deck pool, already fully handled before this task.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.turn import MAIN_PHASES
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color

from .harness import PlayedScenario, Scenario


def resolve_everything(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def advance_to_next_main_phase_of(scenario: PlayedScenario, owner: str) -> None:
    """Walk the real turn machine to `owner`'s next main phase (either one,
    CR 505.1), resolving whatever is on the stack on the way."""
    scenario.advance()
    while not (scenario.step in MAIN_PHASES and scenario.turn.active_player == owner):
        resolve_everything(scenario)
        scenario.advance()


# -- Mana Sculpt ----------------------------------------------------------------


def _mana_sculpt_board(with_wizard: bool):
    battlefield = ["Island", "Island", "Island"]
    if with_wizard:
        battlefield.append("Augur of Bolas")
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Mana Sculpt"], battlefield=battlefield, library=["Island"] * 10)
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"],
            library=["Mountain"] * 10,
        )
    )


def test_mana_sculpt_adds_mana_equal_to_the_countered_spells_cost_with_a_wizard():
    scenario = _mana_sculpt_board(with_wizard=True).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    # Bob casts in response, during Alice's own main phase (CR 117.3c
    # returns priority to the active player, Alice, right after) - so the
    # whole exchange stays inside Alice's turn 1, and "your next main
    # phase" is simply this same turn's postcombat main.
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.pass_priority("bob")
    scenario.cast_and_resolve(
        "Mana Sculpt", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bolt]
    )

    assert bolt.zone is Zone.GRAVEYARD  # countered
    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS, 0) == 0

    advance_to_next_main_phase_of(scenario, "alice")
    resolve_everything(scenario)

    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS, 0) == 1


def test_mana_sculpt_adds_no_mana_without_a_wizard():
    scenario = _mana_sculpt_board(with_wizard=False).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.pass_priority("bob")
    scenario.cast_and_resolve(
        "Mana Sculpt", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bolt]
    )

    assert bolt.zone is Zone.GRAVEYARD  # still countered

    advance_to_next_main_phase_of(scenario, "alice")
    resolve_everything(scenario)

    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS, 0) == 0


# -- Molten Note ------------------------------------------------------------------


def test_molten_note_deals_damage_equal_to_mana_spent_and_untaps_creatures():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Molten Note"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Plains",
                "Plains",
                "Grizzly Bears",
            ],
        )
        .player("bob", battlefield=["Indomitable Ancients"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    victim = scenario.creature("Indomitable Ancients", "bob")
    bears.tapped = True

    card = scenario.find("Molten Note", Zone.HAND, "alice")
    scenario.game.cast(
        card,
        "alice",
        x_value=1,
        targets=[victim],
        mana_sources=scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains"),
    )
    scenario.resolve_top()

    # {X}{R}{W} at X=1 is 3 mana spent.
    assert victim.damage == 3
    assert not bears.tapped


def test_molten_note_flashback_counts_the_flashback_cost_as_mana_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Molten Note"],
            battlefield=["Mountain"] * 4 + ["Plains"] * 4,
        )
        .player("bob", battlefield=["Indomitable Ancients"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    victim = scenario.creature("Indomitable Ancients", "bob")

    card = scenario.find("Molten Note", Zone.GRAVEYARD, "alice")
    scenario.game.cast(
        card,
        "alice",
        keyword="Flashback",
        targets=[victim],
        mana_sources=scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Plains", "Plains", "Plains"
        ),
    )
    scenario.resolve_top()

    # Flashback {6}{R}{W}: 8 mana spent, not the printed {X}{R}{W} (X=0).
    assert victim.damage == 8
    assert card.zone is Zone.EXILE  # CR 702.34a


# -- Burrog Barrage --------------------------------------------------------------


def test_burrog_barrage_pumps_after_another_instant_or_sorcery_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Burrog Barrage"],
            battlefield=["Mountain", "Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Indomitable Ancients"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    victim = scenario.creature("Indomitable Ancients", "bob")
    printed_power = scenario.game.power_of(bears)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.cast_and_resolve(
        "Burrog Barrage", *scenario.untapped_sources("Forest", "Forest"), targets=[bears, victim]
    )

    assert victim.damage == printed_power + 1  # pumped, then bit for the pumped power


def test_burrog_barrage_still_bites_without_another_spell_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Burrog Barrage"],
            battlefield=["Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Indomitable Ancients"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    victim = scenario.creature("Indomitable Ancients", "bob")
    printed_power = scenario.game.power_of(bears)

    scenario.cast_and_resolve(
        "Burrog Barrage", *scenario.untapped_sources("Forest", "Forest"), targets=[bears, victim]
    )

    assert victim.damage == printed_power  # no pump - Burrog Barrage is the first spell


# -- Off-pool proof: Rabid Bite --------------------------------------------------


def test_off_pool_rabid_bite_deals_damage_equal_to_its_power():
    scenario = (
        Scenario()
        .player("alice", hand=["Rabid Bite"], battlefield=["Forest", "Forest", "Grizzly Bears"])
        .player("bob", battlefield=["Indomitable Ancients"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    victim = scenario.creature("Indomitable Ancients", "bob")
    printed_power = scenario.game.power_of(bears)

    scenario.cast_and_resolve(
        "Rabid Bite", *scenario.untapped_sources("Forest", "Forest"), targets=[bears, victim]
    )

    assert victim.damage == printed_power
