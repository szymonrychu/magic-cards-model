"""Modal spells, cast for real: CR 700.2 and CR 601.2b.

A modal spell chooses its modes as it is announced (CR 700.2a), before it
chooses targets, and only the chosen modes ask for targets (CR 700.2c). These
scenarios drive that by hand rather than through `cast_and_resolve`, because
the harness announces targets straight away and a modal spell has to announce
its modes first.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import parse_mode_effect
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from magic_cards_model.support import in_target_formats
from tests.cards import pool
from tests.scenarios.harness import Scenario
from tests.scenarios.test_unread_spell_text_fails_closed import _lands_paying


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

    with pytest.raises(ValueError, match="needs an artifact"):
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

    with pytest.raises(ValueError, match="needs an enchantment"):
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


def _a_modal_spell_with_an_unread_mode() -> tuple[str, list[str], int, int]:
    """The first (by name) out-of-format, single-faced modal instant or
    sorcery in the pool that may choose two modes, one untargeted mode
    `parse_mode_effect` reads and one it does not, with the lands that pay
    for it: `(name, lands, read_mode, unread_mode)`.

    Chosen, not named. Cryptic Command stood here until S18 read its "Tap all
    creatures your opponents control."; the owner rule (every Modern, Pioneer
    and Standard card fully supported) means any in-format vehicle is only
    waiting its turn, so this picks from cards legal in none of the three."""
    seen: set[str] = set()
    for _, printing in sorted(pool().items()):
        if printing.name in seen:
            continue
        seen.add(printing.name)
        if in_target_formats(printing) or printing.card_faces:
            continue
        if not {"Instant", "Sorcery"} & set(printing.type_line.split()):
            continue
        modal = modal_profile(printing)
        if modal is None or not modal.understood or modal.maximum < 2:
            continue
        untargeted = [mode for mode in modal.modes if "target" not in mode.text.lower()]
        read = [mode.number for mode in untargeted if parse_mode_effect(mode, 0) is not None]
        unread = [mode.number for mode in untargeted if parse_mode_effect(mode, 0) is None]
        lands = _lands_paying(printing.mana_cost or "")
        if read and unread and lands is not None:
            return printing.name, lands, read[0], unread[0]
    pytest.fail(
        "no out-of-format modal spell in the pool has both a read and an unread "
        "untargeted mode: add a real printing of one with scripts/add_card.py"
    )


def _cast_modes(name: str, lands: list[str], modes: list[int]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[name],
            library=["Forest"] * 3,
            graveyard=["Forest"],
            battlefield=[*lands, "Grizzly Bears"],
        )
        .player("bob", library=["Forest"] * 3, graveyard=["Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast(name)
    casting.choose_modes(sorted(modes))
    casting.choose_targets([])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def _board(scenario: Scenario) -> list[object]:
    """Every card's name and zone, and each life total - what a mode changes."""
    players = [
        (
            player.username,
            player.life,
            [
                sorted(card.name for card in player.cards_in(zone))
                for zone in (Zone.HAND, Zone.LIBRARY, Zone.GRAVEYARD)
            ],
        )
        for player in scenario.game.players
    ]
    shared = [
        sorted((card.name, card.owner) for card in scenario.game.battlefield),
        sorted((card.name, card.owner) for card in scenario.game.exile),
    ]
    return [players, shared]


def test_a_mode_this_wave_cannot_read_is_recorded_as_a_notice_and_the_other_still_happens():
    """A modal spell cast with one mode this engine reads and one it does not:
    per-mode fail-closed (CR 702.42b: each mode is followed on its own) means
    the read mode still happens - the board ends exactly as it does when that
    mode is chosen alone - and the unread mode's absence is loud, not silent.
    """
    name, lands, read_mode, unread_mode = _a_modal_spell_with_an_unread_mode()

    alone = _cast_modes(name, lands, [read_mode])
    both = _cast_modes(name, lands, [read_mode, unread_mode])

    assert alone.game.mode_notices == []
    assert _board(both) == _board(alone), "the read mode happened as it does on its own"
    assert [(n.source_name, n.mode_number) for n in both.game.mode_notices] == [(name, unread_mode)]


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


# --------------------------------------------------------------------------
# "Choose one. If <condition>, [you may] choose <N> instead." - the second
# sentence of the instruction raises the number of modes when its condition
# holds as the spell is cast (CR 601.2b, CR 700.2a) or as the ability is put
# on the stack (CR 700.2b). The alternative count is read like any other
# instruction count; the condition is read by the same board reader
# "Activate only if" uses, and one it cannot read keeps the printed count and
# records a notice.
# --------------------------------------------------------------------------


def _flame_board(*, wizard: bool) -> "Scenario":
    battlefield = ["Island", "Mountain", "Mountain"]
    if wizard:
        battlefield.append("Rootwater Mystic")
    return (
        Scenario()
        .player("alice", hand=["Flame of Anor"], battlefield=battlefield, library=["Forest"] * 3)
        .player("bob", battlefield=["Sol Ring"], library=["Forest"] * 3)
        .build()
    )


def test_flame_of_anor_without_a_wizard_takes_one_mode():
    scenario = _flame_board(wizard=False)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Flame of Anor")
    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2])


def test_flame_of_anor_with_a_wizard_may_take_two_modes():
    scenario = _flame_board(wizard=True)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, username="bob")

    casting = scenario.cast("Flame of Anor")
    casting.choose_modes([1, 2])
    casting.choose_targets(["bob", sol_ring])
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username="alice")
    casting.begin_paying()
    casting.cast()
    scenario.pass_until_resolved()

    assert sol_ring.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 2


def test_flame_of_anor_with_a_wizard_still_takes_one_mode_if_asked():
    """ "You may choose two instead" - one mode stays legal."""
    scenario = _flame_board(wizard=True)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Flame of Anor")
    casting.choose_modes([2])


def test_flame_of_anor_with_a_wizard_is_capped_at_two():
    scenario = _flame_board(wizard=True)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Flame of Anor")
    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2, 3])


def _titan_board(graveyard: list[str]) -> "Scenario":
    return (
        Scenario()
        .player(
            "alice",
            hand=["Prophetic Titan"],
            graveyard=graveyard,
            battlefield=["Mountain"] * 6,
            library=["Forest"] * 6,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )


def _mode_questions(scenario):
    from magic_cards_model.machines.decisions import DecisionKind

    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_A_MODE]


def test_prophetic_titan_with_delirium_chooses_both_modes():
    """ "If there are four or more card types among cards in your graveyard,
    choose both instead." - not optional: both modes are chosen."""
    scenario = _titan_board(["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", username="alice")

    scenario.put_onto_battlefield("Prophetic Titan")
    scenario.pass_until_resolved()

    assert len(_mode_questions(scenario)) == 2
    assert scenario.player("bob").life == 16


def test_prophetic_titan_without_delirium_chooses_one_mode():
    scenario = _titan_board(["Lightning Bolt", "Grizzly Bears", "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", username="alice")

    scenario.put_onto_battlefield("Prophetic Titan")
    scenario.pass_until_resolved()

    (question,) = _mode_questions(scenario)
    assert len(question.options) == 2


def test_molten_collapse_without_descending_still_refuses_both_modes():
    """Molten Collapse's "If you descended this turn, you may choose both
    instead." (CR 700.11, `Game.descended`) reads as a real False when alice
    has not descended this turn - "too many modes" is refused for the
    genuine reason now, not because the condition is unread, so no
    `ConditionalClauseNotice` is recorded for it either."""
    scenario = (
        Scenario()
        .player("alice", hand=["Molten Collapse"], battlefield=["Swamp", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert not scenario.game.descended("alice")

    casting = scenario.cast("Molten Collapse")
    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2])

    notices = [notice.text for notice in scenario.game.conditional_clause_notices]
    assert not any("descended this turn" in text for text in notices)


def test_molten_collapse_after_descending_may_choose_both_modes():
    """ "You may choose both instead" is optional (CR 700.2), not mandatory -
    the range widens from exactly one to one-or-two, the same way Flame of
    Anor's own "you may choose two instead" already does."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Molten Collapse", "Grizzly Bears"],
            battlefield=["Swamp", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bears])
    assert scenario.game.descended("alice")

    casting = scenario.cast("Molten Collapse")
    casting.choose_modes([1, 2])  # no longer refused
    assert casting.chosen_mode_numbers == [1, 2]


def test_off_pool_inscription_of_abundance_unkicked_takes_exactly_one_mode():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Inscription of Abundance"],
            battlefield=["Forest"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Inscription of Abundance")
    with pytest.raises(ValueError, match="too many modes"):
        casting.choose_modes([1, 2])
    casting.choose_modes([1])
    assert casting.chosen_mode_numbers == [1]


def test_off_pool_inscription_of_ruin_kicked_may_choose_any_number():
    """ "If this spell was kicked, choose any number instead." (CR 601.4,
    CR 702.33d) - zero to every mode, read from `Casting.kicked` live, before
    the kicker cost itself is even paid onto the stack."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Inscription of Ruin"],
            battlefield=["Swamp"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Inscription of Ruin")
    casting.pay_kicker()
    casting.choose_modes([1, 2, 3])  # all three: refused before this fix
    assert casting.chosen_mode_numbers == [1, 2, 3]


# --------------------------------------------------------------------------
# R0a-T7: Get Out (CR 700.2, CR 701.6a - counter; CR 401 - return) and
# Frontline Rush (CR 111.1 - tokens; CR 107.3c - a self-defined X pump)
# --------------------------------------------------------------------------


def test_get_out_counters_a_creature_spell():
    """Get Out's own first mode: "Counter target creature or enchantment
    spell." (CR 701.6a)."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Get Out"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_spell = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_priority("bob")

    casting = scenario.cast("Get Out", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bears_spell])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", username="alice"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears_spell.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_get_out_returns_two_owned_permanents_to_hand():
    """Get Out's own second mode: "Return one or two target creatures
    and/or enchantments you own to your hand." - one of each, both owned by
    the caster."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Get Out"],
            battlefield=["Island", "Island", "Grizzly Bears", "Pacifism"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "bob")
    pacifism.attach_to(angel)  # CR 704.5m: an unattached Aura would be an SBA, not this test

    casting = scenario.cast("Get Out")
    casting.choose_modes([2])
    casting.choose_targets([bears, pacifism])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert pacifism.zone is Zone.HAND
    assert scenario.game.mode_notices == []


def test_get_out_return_mode_refuses_an_unowned_creature():
    """ "you own" (CR 109.5) refuses bob's own Serra Angel for the return
    mode - only the counter mode's own target may be anyone's."""
    scenario = (
        Scenario()
        .player("alice", hand=["Get Out"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast("Get Out")
    casting.choose_modes([2])
    try:
        casting.choose_targets([angel])
    except ValueError:
        pass
    else:
        raise AssertionError("bob's own creature should not be a legal target for 'you own'")


def test_frontline_rush_creates_two_goblin_tokens():
    """Frontline Rush's own first mode: "Create two 1/1 red Goblin creature
    tokens." (CR 111.1)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Frontline Rush"], battlefield=["Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Frontline Rush")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    goblins = [
        state for state in scenario.game.battlefield if state.token and "Goblin" in state.name
    ]
    assert len(goblins) == 2
    assert all(state.power == 1 and state.toughness == 1 for state in goblins)
    assert scenario.game.mode_notices == []


def test_frontline_rush_pumps_by_the_number_of_creatures_controlled():
    """Frontline Rush's own second mode: "Target creature gets +X/+X until
    end of turn, where X is the number of creatures you control." (CR
    107.3c: X is fixed once, at resolution) - alice controls three
    creatures, so the target gets +3/+3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Frontline Rush"],
            battlefield=["Mountain", "Plains", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Frontline Rush")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.power_of(bears) == 2 + 3
    assert scenario.game.toughness_of(bears) == 2 + 3
    assert scenario.game.mode_notices == []
