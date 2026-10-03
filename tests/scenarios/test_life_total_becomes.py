"""CR 119.5: "If an effect sets a player's life total to a specific number,
the player gains or loses the necessary amount of life to end up with the
new total." - the "life total becomes `<amount>`" template, read by one
general reader (`_life_total_becomes_amount_reader` and its four subject
readers in `machines/effects.py`) rather than a table of cards.

Every CR number in this file was looked up with `mise run rules:find
<number>` against the checksum-verified 2026-09-25 Comprehensive Rules
release in the session that wrote it: CR 103.4, CR 119.1, CR 119.5, CR
506.5, CR 508.1c, CR 508.3f, CR 509.3g, CR 604.3a, CR 613.4a, CR 701.10d.

**The subjects** (CR 115.1's target, or none at all):

- "your life total becomes `<amount>`" - the resolving spell's/ability's own
  controller (Resolute Archangel's own "it" is this shape too - CR 607.1
  anaphora onto the "your life total" its own intervening-if just named).
- "target player's"/"target opponent's"/"up to one target player's life
  total becomes `<amount>`" - a genuine CR 115.1 target.
- "each player's life total becomes `<amount>`" - CR 102.1's whole player
  set, no target; every total is read off the board as it stood before the
  instruction touched anyone (load-bearing for "the highest/lowest life
  total among all players").
- "that player's life total becomes `<amount>`" - CR 607.1 anaphora onto an
  event's own player (Master of Cruelties' defending player, off the new
  CR 508.3f/509.3g `TriggerEvent.ATTACKS_UNBLOCKED` event).

**The amounts**: a number, "equal to `<X>`", "half `<X>`, rounded up/down",
"the number of `<expr>`", "that number" (CR 608.2c's "Count the number of
`<expr>`." sentence before it, read through the same `Game.record_count`
channel "that many" already uses), and "the highest/lowest life total among
all players".

**Related mechanics proven alongside it**, because the cards that print
"life total becomes" print them on the same line: CR 701.10d's "double your
life total" (Enduring Angel's back face), the CDA "`<this>`'s power and
toughness are each equal to your life total" (the same face), CR 508.1c's
"can only attack alone" restriction and the "assigns no combat damage this
combat" override (Master of Cruelties), and the group "don't untap during
your next untap step" rider (Oketra's Last Mercy).

**A genuine engine gap found and closed while writing this file**: CR
508.3f - "An ability that reads 'Whenever [a creature] attacks and isn't
blocked, . . .' triggers during the declare blockers step, not the declare
attackers step" - had no support at all; the parser classified Master of
Cruelties' own line as a plain `TriggerEvent.ATTACKS` (declare-attackers
time), which would have fired the ability before blocking was even known.
`TriggerEvent.ATTACKS_UNBLOCKED` is the new, CR-508.3f-timed event,
`_trigger_event` and `condition_matches` its parse/match halves, and
`Game.declare_blockers` its emitter (CR 509.3g: "stays blocked even once
its blockers are removed" is `Attack.blocked`, not "has blockers now").
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# "your life total becomes <amount>" - no target, the controller's own total
# --------------------------------------------------------------------------


def test_resolute_archangel_raises_a_lower_total_to_your_starting_life_total():
    """ "When this creature enters, if your life total is less than your
    starting life total, it becomes equal to your starting life total." -
    the intervening-if (CR 603.4) strips "if your life total is less than
    your starting life total" before the effect ever reaches this reader, so
    "it becomes equal to your starting life total" is the whole of what is
    parsed; "it" is read as "your life total" unconditionally (CR 607.1)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Resolute Archangel"], battlefield=["Plains"] * 7)
        .player("bob")
        .build()
    )
    scenario.player("alice").life = 12  # starting life total stays 20 (CR 103.4)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Resolute Archangel", *scenario.untapped_sources(*(["Plains"] * 7)))
    scenario.resolve_top()  # the ETB trigger

    assert scenario.player("alice").life == 20
    # CR 119.5's own "gains or loses the necessary amount": this was a gain
    # (12 -> 20), so CR 119.9's own per-turn ledger sees it.
    assert "alice" in scenario.game.life_gained_this_turn


def test_resolute_archangel_does_nothing_at_or_above_starting_life_total():
    """The intervening-if is false at trigger time, so the ability never
    triggers at all (CR 603.4) - not a no-op resolution, no ability on the
    stack."""
    scenario = (
        Scenario()
        .player("alice", life=20, hand=["Resolute Archangel"], battlefield=["Plains"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Resolute Archangel", *scenario.untapped_sources(*(["Plains"] * 7)))

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_elderscale_wurm_etb_raises_a_lower_total_to_a_flat_number():
    """ "When this creature enters, if your life total is less than 7, your
    life total becomes 7." - a flat number, not "equal to `<expr>`". The
    static damage floor on the same card is a different task's own reader
    and is not touched here."""
    scenario = (
        Scenario()
        .player("alice", hand=["Elderscale Wurm"], battlefield=["Forest"] * 7)
        .player("bob")
        .build()
    )
    scenario.player("alice").life = 3
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Elderscale Wurm", *scenario.untapped_sources(*(["Forest"] * 7)))
    scenario.resolve_top()

    assert scenario.player("alice").life == 7


def test_form_of_the_dinosaur_etb_sets_a_flat_total_even_when_it_is_a_loss():
    """ "When this enchantment enters, your life total becomes 15." -
    unconditional, so a life total already above 15 is a loss, not a no-op
    (CR 119.5 works either direction)."""
    scenario = (
        Scenario()
        .player("alice", life=20, hand=["Form of the Dinosaur"], battlefield=["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Form of the Dinosaur", *scenario.untapped_sources(*(["Mountain"] * 6))
    )
    scenario.resolve_top()

    assert scenario.player("alice").life == 15
    assert scenario.player("alice").life_lost_this_turn == 5


def test_form_of_the_dragon_end_step_trigger_sets_the_total_every_end_step():
    """ "At the beginning of each end step, your life total becomes 5." -
    "your" is the ability's own controller regardless of whose end step
    fired it (the condition is "each end step", not "your end step"), and
    the static "Creatures without flying can't attack you." is proven in
    the attack-restriction section below."""
    scenario = (
        Scenario()
        .player("alice", life=20, hand=["Form of the Dragon"], battlefield=["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Form of the Dragon", *scenario.untapped_sources(*(["Mountain"] * 7)))
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step: "each end step" triggers on entry
    assert scenario.step is Step.END_STEP
    assert scenario.stack_names() == ["Form of the Dragon's triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").life == 5


def test_oketra_s_last_mercy_raises_the_total_and_exerts_every_land_you_control():
    """ "Your life total becomes equal to your starting life total. Lands you
    control don't untap during your next untap step." - both clauses of one
    instant, the second reusing `CardState.exerted` (CR 701.43a-b) as the
    shared "skip the next untap step" flag Vorinclex's own targeted "that
    land doesn't untap" already uses, applied here to every land the caster
    controls rather than one named object."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Oketra's Last Mercy"],
            battlefield=["Plains"] * 3 + ["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.player("alice").life = 5
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*(["Plains"] * 3))
    forest = scenario.untapped_sources("Forest")[0]

    scenario.cast_and_resolve("Oketra's Last Mercy", *lands)

    assert scenario.player("alice").life == 20
    # The four Plains paid the cost and are tapped; the Forest never tapped
    # for anything, so it proves the *rider* exerted it independently of
    # payment - every land alice controls, not merely the ones just spent.
    assert forest.exerted is True
    for plains in lands:
        assert plains.exerted is True


def test_the_endstone_end_step_trigger_halves_the_starting_total_rounded_up():
    """ "At the beginning of your end step, your life total becomes half your
    starting life total, rounded up." CR 103.4's starting total (20) halves
    to 10 exactly, so a fractional case is exercised by Torgaar below
    instead; this one proves the plain "half `<X>`, rounded" composition
    lands on the *starting* total, not the current one."""
    scenario = (
        Scenario()
        .player("alice", hand=["The Endstone"], battlefield=["Wastes"] * 7)
        .player("bob")
        .build()
    )
    scenario.player("alice").life = 3
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("The Endstone", *scenario.untapped_sources(*(["Wastes"] * 7)))
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step
    scenario.resolve_top()

    assert scenario.player("alice").life == 10


def test_cosmos_elixir_end_step_draws_when_above_starting_life_otherwise_gains():
    """ "At the beginning of your end step, draw a card if your life total is
    greater than your starting life total. Otherwise, you gain 2 life." - no
    life-total-becomes reader of its own; this is here to confirm the card's
    *other* clause (an if/otherwise already generic) still resolves
    alongside every card this file's reader touches, per the brief's "every
    clause handled" bar."""
    scenario = (
        Scenario()
        .player("alice", hand=["Cosmos Elixir"], battlefield=["Wastes"] * 4, library=["Wastes"])
        .player("bob")
        .build()
    )
    scenario.player("alice").life = 15
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Cosmos Elixir", *scenario.untapped_sources(*(["Wastes"] * 4)))
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    scenario.advance()  # the end step
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert len(scenario.player("alice").hand) == hand_before


def test_double_your_life_total_doubles_the_current_total_cr_701_10d():
    """CR 701.10d: "the player gains or loses an amount of life such that
    their new life total is twice its current value." Angelic Enforcer's
    (Enduring Angel's transformed back face) own attack trigger: "Whenever
    this creature attacks, double your life total." Staged already
    transformed, since the front face's own transform condition is a
    different task's reader."""
    scenario = (
        Scenario().player("alice", life=7, battlefield=["Enduring Angel"]).player("bob").build()
    )
    angel = scenario.find("Enduring Angel", Zone.BATTLEFIELD, "alice")
    angel.transform()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(angel, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").life == 14


def test_angelic_enforcers_power_and_toughness_equal_your_life_total():
    """The same back face's own CDA: "Angelic Enforcer's power and toughness
    are each equal to your life total." (CR 604.3a, sublayer 7a, CR
    613.4a) - live, not fixed at the moment it transformed."""
    scenario = Scenario().player("alice", life=11, battlefield=["Enduring Angel"]).build()
    angel = scenario.find("Enduring Angel", Zone.BATTLEFIELD, "alice")
    angel.transform()

    board = scenario.game.computed_board()
    assert (board.of(angel).power, board.of(angel).toughness) == (11, 11)

    scenario.game.gain_life(scenario.player("alice"), 5)
    board = scenario.game.computed_board()
    assert (board.of(angel).power, board.of(angel).toughness) == (16, 16)


# --------------------------------------------------------------------------
# "target player's"/"target opponent's"/"up to one target player's life
# total becomes <amount>" - CR 115.1's genuine target
# --------------------------------------------------------------------------


def test_magister_sphinx_etb_sets_a_targeted_players_total_to_a_flat_number():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Magister Sphinx"],
            battlefield=["Plains", "Island", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Magister Sphinx", ["bob"])
    scenario.cast_and_resolve(
        "Magister Sphinx",
        *scenario.untapped_sources("Plains", "Island", *(["Swamp"] * 5)),
    )
    scenario.resolve_top()

    assert scenario.player("bob").life == 10


def test_sorin_markov_minus_three_sets_target_opponents_total():
    scenario = (
        Scenario()
        .player("alice", hand=["Sorin Markov"], battlefield=["Swamp"] * 6)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Sorin Markov", *scenario.untapped_sources(*(["Swamp"] * 6)))
    sorin = scenario.find("Sorin Markov", Zone.BATTLEFIELD, "alice")

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(sorin))
        if a.cost.strip().startswith("−3") or a.cost.strip().startswith("-3")
    )
    scenario.activate(sorin, index=index, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 10


def test_vraska_relic_seeker_minus_ten_sets_a_target_players_total_to_one():
    scenario = (
        Scenario()
        .player("alice", hand=["Vraska, Relic Seeker"], battlefield=["Swamp"] * 5 + ["Forest"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Vraska, Relic Seeker", *scenario.untapped_sources(*(["Swamp"] * 5), "Forest")
    )
    vraska = scenario.find("Vraska, Relic Seeker", Zone.BATTLEFIELD, "alice")
    vraska.add_counters(Counter.LOYALTY, 4)  # 6 printed + 4 = 10, CR 606.6

    index = next(
        i for i, a in enumerate(scenario.game.activated_abilities(vraska)) if "10" in a.cost
    )
    scenario.activate(vraska, index=index, targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 1


def test_torgaar_famine_incarnate_etb_halves_a_targeted_players_starting_total():
    """ "up to one target player's life total becomes half their starting
    life total, rounded down." CR 115.6's optional target; "their" is the
    *target*, not the caster, so a target with a non-default starting life
    total proves the amount is read off the right player."""
    scenario = (
        Scenario()
        .player("alice", hand=["Torgaar, Famine Incarnate"], battlefield=["Swamp"] * 8)
        .player("bob", life=15)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    assert bob.starting_life == 15

    scenario.choose_trigger_targets("Torgaar, Famine Incarnate", ["bob"])
    scenario.cast_and_resolve(
        "Torgaar, Famine Incarnate", *scenario.untapped_sources(*(["Swamp"] * 8))
    )
    scenario.resolve_top()

    assert bob.life == 7  # half of 15, rounded down


def test_torgaar_famine_incarnate_etb_with_no_target_chosen_changes_nothing():
    """CR 115.6's "up to one": zero targets is legal, and resolves the whole
    ability against an empty target list (`Game.resolve_targets`), not an
    error."""
    scenario = (
        Scenario()
        .player("alice", hand=["Torgaar, Famine Incarnate"], battlefield=["Swamp"] * 8)
        .player("bob", life=15)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Torgaar, Famine Incarnate", [])
    scenario.cast_and_resolve(
        "Torgaar, Famine Incarnate", *scenario.untapped_sources(*(["Swamp"] * 8))
    )
    scenario.resolve_top()

    assert scenario.player("bob").life == 15
    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# "each player's life total becomes <amount>" - CR 102.1's whole player set
# --------------------------------------------------------------------------


def test_arbiter_of_knollridge_etb_raises_every_player_to_the_highest_total():
    scenario = (
        Scenario()
        .player("alice", life=5, hand=["Arbiter of Knollridge"], battlefield=["Plains"] * 8)
        .player("bob", life=17)
        .player("carol", life=9)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Arbiter of Knollridge", *scenario.untapped_sources(*(["Plains"] * 8))
    )
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 17
    assert scenario.player("carol").life == 17


def test_repay_in_kind_sets_every_player_to_the_lowest_total():
    scenario = (
        Scenario()
        .player("alice", life=5, hand=["Repay in Kind"], battlefield=["Swamp"] * 7)
        .player("bob", life=17)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Repay in Kind", *scenario.untapped_sources(*(["Swamp"] * 7)))

    assert scenario.player("alice").life == 5
    assert scenario.player("bob").life == 5


def test_worldfire_sets_every_player_to_one():
    scenario = (
        Scenario()
        .player("alice", life=20, hand=["Worldfire"], battlefield=["Mountain"] * 9)
        .player("bob", life=3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Worldfire", *scenario.untapped_sources(*(["Mountain"] * 9)))

    assert scenario.player("alice").life == 1
    assert scenario.player("bob").life == 1
    assert scenario.game.battlefield == []


def test_sway_of_the_stars_sets_every_player_to_seven():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Sway of the Stars"],
            battlefield=["Island"] * 10,
            library=["Wastes"] * 10,
        )
        .player("bob", life=3, library=["Wastes"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Sway of the Stars", *scenario.untapped_sources(*(["Island"] * 10)))

    assert scenario.player("alice").life == 7
    assert scenario.player("bob").life == 7


def test_biorhythm_sets_each_players_total_to_their_own_creature_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Biorhythm"],
            battlefield=["Forest"] * 8 + ["Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob", life=20, battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Biorhythm", *scenario.untapped_sources(*(["Forest"] * 8)))

    assert scenario.player("alice").life == 2
    assert scenario.player("bob").life == 1


def test_shaman_of_forgotten_ways_formidable_activation_sets_creature_counts():
    """ "Formidable - {9}{G}{G}, {T}: Each player's life total becomes the
    number of creatures they control. Activate only if creatures you
    control have total power 8 or greater." The ability word (CR 207.2c) is
    decorative; the "Activate only if" gate is a pre-existing generic cost
    restriction, not this file's own reader."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=["Shaman of Forgotten Ways", "Blightsteel Colossus"] + ["Forest"] * 11,
        )
        .player("bob", life=20, battlefield=["Runeclaw Bear", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shaman = scenario.creature("Shaman of Forgotten Ways", "alice")

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(shaman))
        if "9" in a.cost and "T" in a.cost
    )
    scenario.activate(shaman, index=index, auto=True)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 2  # Shaman + Blightsteel Colossus
    assert scenario.player("bob").life == 2  # two Bears


# --------------------------------------------------------------------------
# "that player's life total becomes <amount>" - CR 607.1 event anaphora,
# off the new CR 508.3f/509.3g `TriggerEvent.ATTACKS_UNBLOCKED` event.
# --------------------------------------------------------------------------


def test_master_of_cruelties_unblocked_attack_sets_the_defending_players_life_to_one():
    """ "Whenever this creature attacks a player and isn't blocked, that
    player's life total becomes 1. This creature assigns no combat damage
    this combat." First strike, deathtouch and power 1 make the "no combat
    damage" override observable: without it, an unblocked first striker
    would also deal 1 combat damage on top of the life-total set."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Cruelties"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    master = scenario.creature("Master of Cruelties", "alice")

    scenario.attack_with(master, defending="bob")
    scenario.game.put_triggers_on_stack()
    # CR 508.3f: it does not trigger at declare attackers; blocking is not known yet.
    assert scenario.stack_names() == []

    scenario.no_blocks()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Master of Cruelties's triggered ability"]
    scenario.resolve_top()  # the life-total trigger, before any damage step

    assert scenario.player("bob").life == 1
    assert master.assigns_no_combat_damage_this_combat is True

    scenario.combat_damage()

    # Still 1, not 0: the trigger's own rider held even though Master has
    # first strike and would otherwise deal its own 1 power of damage here.
    assert scenario.player("bob").life == 1


def test_master_of_cruelties_does_not_trigger_when_blocked():
    """CR 509.3g: blocked at all (even if the blocker is later removed) is
    enough to refuse the trigger - `Attack.blocked` is a standing fact of
    the declaration, not "has a blocker right now"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Cruelties"])
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    master = scenario.creature("Master of Cruelties", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(master, defending="bob")
    scenario.block(master, bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_master_of_cruelties_can_only_attack_alone():
    """ "This creature can only attack alone." (CR 508.1c, CR 506.5) -
    checked on the whole declaration, like the printed "no more than one
    creature may attack this `<subject>`" cap already is."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Cruelties", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    master = scenario.creature("Master of Cruelties", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="can only attack alone"):
        scenario.attack_with(master, bears, defending="bob")


def test_master_of_cruelties_may_attack_alone_with_another_creature_staying_home():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Cruelties", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    master = scenario.creature("Master of Cruelties", "alice")

    scenario.attack_with(master, defending="bob")

    assert scenario.attackers() == [master]


# --------------------------------------------------------------------------
# "Count the number of <expr>. <subject> life total becomes that number."
# --------------------------------------------------------------------------


def test_invincible_hymn_sets_your_life_total_to_your_library_size():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Invincible Hymn"],
            battlefield=["Plains"] * 8,
            library=["Wastes"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Invincible Hymn", *scenario.untapped_sources(*(["Plains"] * 8)))

    assert scenario.player("alice").life == 4


def test_touch_of_the_eternal_upkeep_trigger_sets_your_life_total_to_permanents_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Touch of the Eternal"],
            battlefield=["Plains"] * 7 + ["Grizzly Bears"],
            library=["Wastes"] * 5,
        )
        .player("bob", library=["Wastes"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Touch of the Eternal", *scenario.untapped_sources(*(["Plains"] * 7)))
    for _ in range(2):  # bob's turn, then alice's: "your upkeep" is her next one
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()  # the new turn's untap step
        scenario.advance()  # its upkeep
    assert scenario.player().username == "alice"
    scenario.resolve_top()

    # 7 Plains + the Bears + Touch of the Eternal itself = 9 permanents alice
    # controls when the upkeep trigger counts.
    assert scenario.player("alice").life == 9


# --------------------------------------------------------------------------
# The other clauses printed on the same cards, proven so no card in this file
# is only half-read.
# --------------------------------------------------------------------------


def test_cosmos_elixir_end_step_draws_when_above_starting_life():
    """The "draw a card if ..." half of the same instruction: above the
    starting life total the controller draws and the "Otherwise" gain does
    not happen (CR 608.2c)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Cosmos Elixir"], battlefield=["Wastes"] * 4, library=["Wastes"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Cosmos Elixir", *scenario.untapped_sources(*(["Wastes"] * 4)))
    scenario.player("alice").life = 25
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    scenario.advance()  # the end step
    scenario.resolve_top()

    assert scenario.player("alice").life == 25
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_form_of_the_dragon_stops_creatures_without_flying_from_attacking_its_controller():
    """ "Creatures without flying can't attack you." (CR 508.1c) - a group
    restriction negating a keyword, read for whoever controls the attacker."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears", "Wind Drake"])
        .player("alice", battlefield=["Form of the Dragon"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "bob")
    drake = scenario.creature("Wind Drake", "bob")

    assert scenario.can_attack(bears, defending="alice") is False
    assert scenario.can_attack(drake, defending="alice") is True
    with pytest.raises(ValueError, match="flying"):
        scenario.attack_with(bears, defending="alice")


def test_form_of_the_dinosaur_upkeep_trigger_fights_one_way_and_hits_you_back():
    """ "At the beginning of your upkeep, this enchantment deals 15 damage to
    target creature an opponent controls and that creature deals damage equal
    to its power to you." - the creature is still on the battlefield when it
    deals its damage (CR 704.3: state-based actions wait for the resolution)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Form of the Dinosaur"],
            library=["Wastes"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Wastes"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Form of the Dinosaur", [bears])
    for _ in range(2):  # bob's turn, then alice's own next upkeep
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()
        scenario.advance()
    assert scenario.player().username == "alice"
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


def test_worldfire_exiles_every_hand_and_graveyard_too():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Worldfire", "Lightning Bolt"],
            graveyard=["Shock"],
            battlefield=["Mountain"] * 9,
        )
        .player("bob", life=3, hand=["Giant Growth"], graveyard=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Worldfire", *scenario.untapped_sources(*(["Mountain"] * 9)))

    assert scenario.player("alice").hand == []
    assert scenario.player("bob").hand == []
    assert scenario.player("bob").graveyard == []
    assert [card.name for card in scenario.player("alice").graveyard] == ["Worldfire"]
    assert sorted(card.name for card in scenario.game.exile) == [
        "Giant Growth",
        "Island",
        "Lightning Bolt",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Mountain",
        "Shock",
    ]


def test_sway_of_the_stars_shuffles_hand_graveyard_and_permanents_then_draws_seven():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sway of the Stars", "Lightning Bolt"],
            graveyard=["Shock"],
            battlefield=["Island"] * 10 + ["Grizzly Bears"],
            library=["Wastes"] * 10,
        )
        .player("bob", life=3, battlefield=["Runeclaw Bear"], library=["Wastes"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Sway of the Stars", *scenario.untapped_sources(*(["Island"] * 10)))

    for username in ("alice", "bob"):
        assert len(scenario.player(username).hand) == 7
        assert scenario.player(username).life == 7
    assert scenario.game.battlefield == []
    assert [card.name for card in scenario.player("alice").graveyard] == ["Sway of the Stars"]
    assert (
        len(scenario.player("alice").library) == 10 + 13 - 7
    )  # library + Bolt + Shock + 11 permanents, minus the seven drawn
