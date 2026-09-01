"""Modal spells, cast for real: CR 700.2 and CR 601.2b.

A modal spell chooses its modes as it is announced (CR 700.2a), before it
chooses targets, and only the chosen modes ask for targets (CR 700.2c). These
scenarios drive that by hand rather than through `cast_and_resolve`, because
the harness announces targets straight away and a modal spell has to announce
its modes first.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with red and white mana up; Bob with a bear, a Sol Ring, a
    Memnite (mana value 0), and an Elvish Mystic (mana value 1) - the last two
    for Kozilek's Command's X-bounded exile mode. Both players carry a small
    library of Forests, so a mode that scries or draws has something to find -
    library defaults to empty otherwise, which used to make "the draw did
    nothing" indistinguishable from "the draw never ran"."""
    return (
        Scenario()
        .player(
            "alice",
            hand=[
                "Abrade",
                "Thraben Charm",
                "Cryptic Command",
                "Kozilek's Command",
                "Kozilek's Command",
                "Mystic Confluence",
                "Blessed Alliance",
                "Tooth and Nail",
                "Lightning Bolt",
            ],
            library=["Forest"] * 10,
            battlefield=[
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Plains",
                "Island",
                "Island",
                "Island",
                "Eldrazi Temple",
                "Eldrazi Temple",
                "Eldrazi Temple",
                "Eldrazi Temple",
            ],
        )
        .player(
            "bob",
            library=["Forest"] * 5,
            battlefield=["Grizzly Bears", "Sol Ring", "Memnite", "Elvish Mystic"],
        )
    )


def test_a_modal_spell_reaches_the_stack_carrying_its_mode_s_target():
    """Abrade's first mode deals damage to target creature (CR 700.2c)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Abrade")
    casting.choose_modes([1])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    on_stack = scenario.put_on_stack(casting)

    assert on_stack.zone is Zone.STACK
    assert on_stack.targets[0].card_id == bears.id
    assert casting.chosen_modes == ["Abrade deals 3 damage to target creature."]


def test_the_mode_that_was_not_chosen_does_not_get_to_pick_the_target():
    """Abrade's other mode destroys target artifact, and a bear is not one."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Abrade")
    casting.choose_modes([2])

    with pytest.raises(ValueError, match="needs a artifact"):
        casting.choose_targets([bears])


def test_the_artifact_mode_takes_the_artifact():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Abrade")
    casting.choose_modes(["Destroy target artifact"])
    casting.choose_targets([sol_ring])

    assert casting.targets[0].card_id == sol_ring.id


def test_a_modal_spell_cannot_announce_targets_before_its_modes():
    """CR 601.2b: modes come first, and CR 700.2c is why it matters."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="modes must be announced"):
        scenario.cast("Abrade", targets=[bears])


def test_choosing_two_modes_where_only_one_of_them_targets():
    """Cryptic Command: return target permanent, and draw a card."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Cryptic Command")
    casting.choose_modes([2, 4])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island", "Mountain"))
    on_stack = scenario.put_on_stack(casting)

    assert on_stack.zone is Zone.STACK
    assert len(on_stack.targets) == 1


def test_two_non_targeting_modes_leave_the_spell_with_no_targets():
    """Tapping every opposing creature and drawing a card target nothing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Cryptic Command")
    casting.choose_modes([3, 4])

    with pytest.raises(ValueError, match="too many targets"):
        casting.choose_targets([bears])


def test_a_charm_mode_targeting_an_enchantment_refuses_a_creature():
    """Thraben Charm's second mode destroys target enchantment."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Thraben Charm")
    casting.choose_modes([2])

    with pytest.raises(ValueError, match="needs a enchantment"):
        casting.choose_targets([bears])


def test_a_charm_mode_taking_any_number_of_players_takes_as_many_as_it_likes():
    """Exiling "any number of target players' graveyards" targets the players.

    CR 107.1c: "any number" is any positive number or zero, so this mode is the
    one in the pool with no maximum, and none of the players chosen has to be
    an opponent.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Thraben Charm")
    casting.choose_modes([3])

    assert casting.targeting.max_targets is None
    casting.choose_targets(["bob", "alice"])

    assert [str(target) for target in casting.targets] == ["bob", "alice"]


def test_the_graveyard_mode_still_refuses_a_permanent():
    """Unbounded is not unchecked: a bear is not a player (CR 601.2c)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Thraben Charm")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="illegal target"):
        casting.choose_targets([bears])


def test_a_resolved_mode_does_what_it_says():
    """Abrade's first mode deals 3 damage - now dispatched by `resolve_modal_spell`."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Abrade")
    casting.choose_modes([1])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD


# -- CR 700.2a / 601.2b: a modal spell refuses to complete with no modes ----
#
# The reported defect: `Casting` used to let a modal spell reach the stack
# with zero modes chosen. Choosing modes is part of announcing the spell
# (CR 700.2a), so a caster who never announces any has not completed a legal
# announcement - CR 601.2e/601.6 make that cast illegal outright, not a cast
# that quietly resolves and does nothing. The only place this used to be
# checked was inside `choose_targets`, which a caller can skip entirely by
# never calling it (exactly what happened with `--x 2` and no `--modes`) -
# so the guard has to live somewhere every casting path reaches, which is why
# it is enforced in `Casting.cast()` itself.


def _cast_with_no_modes(scenario, name: str, x_value: int | None = None):
    """Drive a cast all the way to `cast()` without ever calling `choose_modes`.

    This is exactly the shape of the reported bug: the API only calls
    `casting.choose_modes(...)` when `req.modes` is truthy, so a request with
    an empty mode list skips the call altogether and `chosen_mode_numbers`
    never leaves its empty default.
    """
    casting = scenario.cast(name)
    payment = casting.determine_cost(x_value=x_value)
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    return casting


def test_kozileks_command_cast_with_no_modes_is_refused():
    """The reported case: `--x 2`, no `--modes`, used to resolve and do nothing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = _cast_with_no_modes(scenario, "Kozilek's Command", x_value=2)

    with pytest.raises(ValueError, match=r"requires exactly 2 mode\(s\)") as excinfo:
        casting.cast()
    # The refusal must name the numbered modes so a player can retry correctly.
    message = str(excinfo.value)
    assert "1." in message and "2." in message and "3." in message and "4." in message


def test_kozileks_command_with_one_mode_is_refused():
    """One mode where the card requires exactly two (CR 700.2).

    `choose_modes` already refuses this immediately, via `ModalProfile.resolve`
    - the announcement is never even completed, so the cast-time guard added
    for the reported bug never has to fire here.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")
    with pytest.raises(ValueError, match="too few modes"):
        casting.choose_modes([3], x_value=2)


def test_kozileks_command_with_exactly_two_modes_is_accepted():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Kozilek's Command")
    # X has to reach Grizzly Bears' mana value (2): mode 3 is "Exile target
    # creature with mana value X or less", and X=1 would make Bears an
    # illegal target now that the comparison is actually enforced.
    casting.choose_modes([3, 1], x_value=2)
    casting.choose_targets([bears, "alice"])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    on_stack = casting.cast()

    assert on_stack.zone is Zone.STACK


def test_kozileks_command_with_too_many_modes_is_refused():
    """`choose_modes` itself already refuses this (CR 700.2), but confirm it holds."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")
    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2, 3], x_value=1)


def test_kozileks_command_duplicate_mode_is_refused():
    """CR 700.2d: Kozilek's Command does not say a mode may repeat."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")
    with pytest.raises(ValueError, match="chosen twice"):
        casting.choose_modes([1, 1], x_value=1)


def test_mystic_confluence_allows_a_repeated_mode():
    """Mystic Confluence explicitly allows the same mode more than once."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Mystic Confluence")
    casting.choose_modes([3, 3, 2])
    casting.choose_targets([bears])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    on_stack = casting.cast()

    assert on_stack.zone is Zone.STACK


def test_mystic_confluence_cast_with_no_modes_is_still_refused():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = _cast_with_no_modes(scenario, "Mystic Confluence")

    with pytest.raises(ValueError, match=r"requires exactly 3 mode\(s\)"):
        casting.cast()


def test_kozileks_command_out_of_range_mode_number_is_refused():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")
    with pytest.raises(ValueError, match="there is no mode 5"):
        casting.choose_modes([1, 5], x_value=1)


def test_a_non_modal_spell_is_unaffected():
    """Lightning Bolt has no modes at all, and the guard must not touch it.

    `Game.resolve_top` branches on `cast_record(spell).modes`, so an empty
    list has to keep reaching the ordinary `effect_for` path rather than
    `resolve_modal_spell` - proven by the damage actually landing, not just
    by the spell reaching the stack.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.game.player("bob")
    life_before = bob.life

    on_stack = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert on_stack.zone is Zone.STACK

    scenario.resolve_top()

    assert bob.life == life_before - 3


def test_elder_gargaroth_can_still_be_cast_normally():
    """Elder Gargaroth's modal *triggered* ability must not block casting it.

    `is_modal()` returns True for the card (its attack/block trigger has its
    own bulleted "choose one"), but that profile's `understood` is False,
    because the instruction line ("Whenever this creature attacks or blocks,
    choose one -") does not begin with "Choose" the way `ModalProfile`
    requires to trust a count. The cast-time guard must not fire on an
    unreadable profile, or a genuinely castable creature would be refused.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Elder Gargaroth"], battlefield=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    on_stack = scenario.cast_onto_stack(
        "Elder Gargaroth", *scenario.untapped_sources(*["Forest"] * 5)
    )

    assert on_stack.zone is Zone.STACK


def test_escalate_spell_still_casts_with_its_modes_chosen():
    """Blessed Alliance (escalate) is unaffected by the new guard, and both of
    its escalated modes actually happen on resolution: "Target player gains 4
    life." and "Untap up to two target creatures."
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    bob = scenario.game.player("bob")
    life_before = bob.life

    casting = scenario.cast("Blessed Alliance")
    casting.choose_modes([1, 2])
    casting.pay_escalate()
    casting.choose_targets(["bob", bears])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    on_stack = scenario.put_on_stack(casting)
    assert on_stack.zone is Zone.STACK

    scenario.resolve_top()

    assert bob.life == life_before + 4
    assert not bears.tapped
    assert scenario.game.mode_notices == []


def test_entwine_spell_still_casts_with_all_modes_entwined():
    """Tooth and Nail entwined chooses both modes at once (CR 702.42a).

    Both modes are read now, so no `ModeNotice` is recorded: the first is a
    search to hand and the second puts creature cards from hand onto the
    battlefield. With an empty hand and a library of nothing but Forests
    neither finds a creature, so the observable result is only that the cast
    and the resolution complete - which is what this test is about. CR 701.23b
    makes "find nothing" a legal answer, and CR 608.2d never asks a question
    with no legal option, so the empty hand is silently skipped rather than
    refused. `test_entwine.py` drives the version with creatures to find.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Tooth and Nail"], battlefield=["Forest"] * 9)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1, 2], entwined=True)
    casting.choose_targets([])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    on_stack = scenario.put_on_stack(casting)
    assert on_stack.zone is Zone.STACK

    scenario.resolve_top()

    assert scenario.game.mode_notices == [], "both modes are read now"
    assert on_stack.zone is Zone.GRAVEYARD


# -- The reported defect: Kozilek's Command, modes 1 and 3, X=1 ------------


def test_kozileks_command_modes_one_and_three_do_exactly_what_they_say():
    """The reported case: `--modes 1,3 --x 1`, a player and a mana-value-0-or-
    less creature targeted. Before this dispatch existed, the spell was
    allowed, resolved, and did nothing at all - no token, no exile.

    Memnite (mana value 0) stands in for the reported Cat Token: the pool's
    own mana-value-1-or-less permanent on bob's side.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")  # mana value 2: untouched
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "bob")  # mana value 0

    casting = scenario.cast("Kozilek's Command")
    casting.choose_modes([1, 3], x_value=1)
    casting.choose_targets(["alice", memnite])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    spawn_tokens = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if "Spawn" in permanent.card.subtypes
    ]
    assert len(spawn_tokens) == 1, "mode 1: target player creates X (1) Eldrazi Spawn token(s)"
    token = spawn_tokens[0]
    assert (token.card.power, token.card.toughness) == ("0", "1")
    assert token.card.oracle_text == "Sacrifice this token: Add {C}."

    assert memnite.zone is Zone.EXILE, "mode 3: mana value 0 is within X (1) or less"
    assert bears.zone is Zone.BATTLEFIELD, "the untargeted bears are untouched"
    assert scenario.game.mode_notices == [], "both chosen modes were fully understood"


def test_kozileks_command_mode_three_respects_the_x_bound():
    """Mode 3's comparison is enforced at announcement (`_rejects_comparison`),
    which is where "X reached the comparison" is actually provable: a creature
    one mana value *above* X is refused as an illegal target outright, and one
    *at* the bound is exiled on resolution.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elvish_mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "bob")  # mana value 1
    bears = scenario.creature("Grizzly Bears", "bob")  # mana value 2

    over_the_bound = scenario.cast("Kozilek's Command")
    over_the_bound.choose_modes([3, 2], x_value=1)
    with pytest.raises(ValueError, match="illegal target"):
        over_the_bound.choose_targets([bears, "alice"])

    at_the_bound = scenario.cast("Kozilek's Command")
    at_the_bound.choose_modes([3, 2], x_value=1)
    at_the_bound.choose_targets([elvish_mystic, "alice"])
    payment = at_the_bound.determine_cost()
    scenario.auto_pay(payment, username=at_the_bound.caster)
    at_the_bound.begin_paying()
    scenario.put_on_stack(at_the_bound)
    scenario.resolve_top()

    assert elvish_mystic.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD


def test_kozileks_command_different_mode_pairs_produce_different_outcomes():
    """Modes [1, 3] make a token and exile; modes [2, 4] scry-and-draw for
    the target and touch no graveyard at X=0 - two casts of the same card,
    chosen differently, must not converge on the same board state.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "bob")
    alice = scenario.game.player("alice")

    tokens_and_exile = scenario.cast("Kozilek's Command")
    tokens_and_exile.choose_modes([1, 3], x_value=1)
    tokens_and_exile.choose_targets(["alice", memnite])
    payment = tokens_and_exile.determine_cost()
    scenario.auto_pay(payment, username=tokens_and_exile.caster)
    tokens_and_exile.begin_paying()
    scenario.put_on_stack(tokens_and_exile)
    scenario.resolve_top()

    assert any("Spawn" in p.card.subtypes for p in scenario.game.permanents_controlled_by("alice"))
    assert memnite.zone is Zone.EXILE

    hand_before = len(alice.hand)
    scry_and_draw = scenario.cast("Kozilek's Command")
    scry_and_draw.choose_modes([2, 4], x_value=0)
    scry_and_draw.choose_targets(["alice"])
    payment = scry_and_draw.determine_cost()
    scenario.auto_pay(payment, username=scry_and_draw.caster)
    scry_and_draw.begin_paying()
    scenario.put_on_stack(scry_and_draw)
    scenario.resolve_top()

    # hand_before still counts the second Kozilek's Command itself: casting
    # removes it (-1) and mode 2's single draw adds one (+1), net unchanged.
    # Mode 4 with X=0 exiles nothing, so no second Eldrazi Spawn token
    # appears either.
    assert len(alice.hand) == hand_before
    spawn_tokens = [
        p for p in scenario.game.permanents_controlled_by("alice") if "Spawn" in p.card.subtypes
    ]
    assert len(spawn_tokens) == 1, "modes [2, 4] make no token, unlike the first cast"


def test_kozileks_command_per_mode_targets_are_not_swapped():
    """Modes [1, 2] both name "target player", each their own player: mode 1
    ("target player creates tokens") for alice, mode 2 ("target player
    scries, then draws") for bob. If `Casting.choose_targets`'s per-mode
    slicing assigned targets to the wrong mode - or, as before this wave,
    handed every mode the whole flat target list - both players would get
    both effects instead of one each.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.game.player("bob")
    bob_hand_before = len(bob.hand)

    casting = scenario.cast("Kozilek's Command")
    casting.choose_modes([1, 2], x_value=1)
    casting.choose_targets(["alice", "bob"])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    alice_spawns = [
        p for p in scenario.game.permanents_controlled_by("alice") if "Spawn" in p.card.subtypes
    ]
    bob_spawns = [
        p for p in scenario.game.permanents_controlled_by("bob") if "Spawn" in p.card.subtypes
    ]
    assert len(alice_spawns) == 1, "mode 1's target (alice) gets the Eldrazi Spawn"
    assert len(bob_spawns) == 0, "mode 1's target was alice, not bob"
    assert len(bob.hand) == bob_hand_before + 1, "mode 2's target (bob) drew a card"


def test_mystic_confluence_repeated_mode_runs_twice():
    """`choose_modes([3, 3, 2])` draws twice and returns Grizzly Bears once -
    the repeated "Draw a card." mode must actually run twice, not once."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice = scenario.game.player("alice")
    hand_before = len(alice.hand)

    casting = scenario.cast("Mystic Confluence")
    casting.choose_modes([3, 3, 2])
    casting.choose_targets([bears])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # hand_before still counts Mystic Confluence itself: casting removes it
    # (-1) and two draws add two (+2), a net +1 - proof the "Draw a card."
    # mode ran twice and not once (which would net to 0).
    assert len(alice.hand) == hand_before + 1, "drew a card is chosen twice (CR 700.2d)"
    assert bears.zone is Zone.HAND, "return target creature to its owner's hand, chosen once"
    assert scenario.game.mode_notices == []


def test_a_mode_this_wave_cannot_read_is_recorded_as_a_notice_and_the_other_still_happens():
    """Cryptic Command modes [1, 3]: mode 1 ("Counter target spell.") is a
    shape this wave reads; mode 3 ("Tap all creatures your opponents
    control.") is not, since it names no target at all. Per-mode fail-closed
    (CR 702.42b: each mode is followed on its own) means mode 1 still
    counters the targeted spell even though mode 3 could not be performed -
    and mode 3's absence is loud, not silent.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt_casting = scenario.cast("Lightning Bolt", targets=["bob"])
    bolt_payment = bolt_casting.begin_paying()
    scenario.pay_with(bolt_payment, *scenario.untapped_sources("Mountain"))
    bolt_on_stack = scenario.put_on_stack(bolt_casting)
    assert bolt_on_stack.zone is Zone.STACK

    casting = scenario.cast("Cryptic Command")
    casting.choose_modes([1, 3])
    casting.choose_targets([bolt_on_stack])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Cryptic Command is on top; resolving it counters the bolt.

    assert bolt_on_stack.zone is Zone.GRAVEYARD, "mode 1: the targeted spell was countered"
    assert len(scenario.game.mode_notices) == 1
    notice = scenario.game.mode_notices[0]
    assert notice.mode_number == 3
    assert notice.source_name == "Cryptic Command"


def test_x_value_must_agree_between_targets_and_cost():
    """CR 107.3a: X is fixed once for the whole spell. `choose_modes` and
    `determine_cost` are two independent setters of `Casting.x_value` - a
    caller that announces targets under one X and then changes it before
    `cast()` must be refused loudly, not silently counted against whichever
    X happened to be in force when `choose_targets` ran.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Kozilek's Command")
    casting.choose_modes([3, 2])  # no x_value announced here - defaults to 0
    casting.choose_targets([memnite, "alice"])  # announced while X was still 0
    payment = casting.determine_cost(x_value=1)  # X changes after targets were chosen
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()

    with pytest.raises(ValueError, match="X was 0 when targets were chosen but is now 1"):
        casting.cast()


def test_a_modal_x_spell_asks_for_no_targets_before_its_modes_are_chosen():
    """CR 700.2c: "if a spell or ability targets one or more targets only if a
    particular mode is chosen for it, its controller will need to choose those
    targets only if they chose that mode".

    So a modal spell announced with no modes yet requires NOTHING, and its
    profile says `understood=False` - the question "what does this target" has
    no answer until CR 700.2a's mode choice has been made.

    The regression this pins: the branch that substitutes X into a spell's own
    text before reading its targets (Postmortem Lunge's "mana value X") did not
    exclude modal cards, and Kozilek's Command is `{X}{C}{C}`. Its four bullets
    were read whole, as one non-modal blob, so the profile demanded three
    targets up front - one for each bullet that says "target" - for a card that
    chooses two modes and will need at most two. CR 601.2c enforcement then
    refused the cast for "too few targets" before the caster was ever asked
    which modes they wanted, which is how it reached a player as "I cannot cast
    Kozilek's Command and target creatures with it at all".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")

    assert not casting.targeting.understood, (
        "which targets a modal spell needs depends on modes nobody has chosen yet"
    )
    assert casting.targeting.min_targets == 0, "a mode-less modal spell requires no target"

    # And the same spell, once its modes ARE announced, asks for exactly the
    # one target its single targeting mode needs - not three.
    # "Choose two", so two it is: mode 3 ("Exile target creature with mana
    # value X or less") requires one, and mode 4 ("Exile UP TO X target cards
    # from graveyards") requires none. One required target for the pair, where
    # reading all four bullets as one blob demanded three.
    casting.choose_modes([3, 4], x_value=1)
    assert casting.targeting.understood
    assert casting.targeting.min_targets == 1, "only the chosen modes target (CR 700.2c)"
