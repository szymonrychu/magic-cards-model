"""Scenario: three shapes of CR 305.2's "continuous effects may increase
this number" - a one-shot grant, a conditional static grant, and the same
one-shot grant reached through an Adventure (CR 715.3).

- **One-shot, resolved**: Till and Tend's own "You may play an additional
  land this turn." (Beorn, Reluctant Host's Adventure half) - the identical
  text and mechanism Way of the Paradox's own grant already reads
  (`machines/effects._ADDITIONAL_LAND_PLAY_RE`, `Game.extra_land_plays`);
  proven here reached through CR 715.3a's Adventure announcement rather than
  an ordinary sorcery, and again with Explore's own plain printing of the
  same sentence, off the deck pool.
- **Conditional, static**: Thranduil's Company's own "As long as you control
  another Elf, you may play an additional land on each of your turns." -
  `Game.land_allowance`'s new `conditional_additional_land_plays_of_line`
  reader, gated through `Game.condition_holds`'s own "another `<quality>`"
  self-exclusion (`_CONDITION_CONTROLS_ANOTHER`).

CR numbers verified this session with `mise run rules:find`: 305.2, 305.2a,
611.3d, 715.3a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_till_and_tend_grants_an_extra_land_play_as_an_adventure():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Beorn, Reluctant Host", "Forest", "Forest"],
            battlefield=["Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.land_allowance("alice") == 1

    casting = scenario.cast("Beorn, Reluctant Host")
    casting.cast_as_adventure()
    assert casting.face == "Till and Tend"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.land_allowance("alice") == 2

    first = scenario.play_land("Forest")
    second = scenario.play_land("Forest")
    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.BATTLEFIELD

    # Beorn himself went to exile (CR 715.3d), still castable later as the
    # creature - not this file's own business, `test_adventure.py` proves
    # that generically.
    assert scenario.zones_containing(casting.spell) == ["shared:exile"]


def test_the_extra_land_play_does_not_carry_over_to_the_next_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Beorn, Reluctant Host", "Forest"],
            battlefield=["Forest", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Beorn, Reluctant Host")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.game.land_allowance("alice") == 2

    turns_taken = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns_taken:
        scenario.advance()
    while scenario.turn.active_player != "alice":
        scenario.advance()

    assert scenario.game.land_allowance("alice") == 1, (
        "CR 611.2a: a one-turn grant, not a static one"
    )


def test_explore_grants_an_extra_land_play_off_the_pool():
    """Off-pool proof: the identical "You may play an additional land this
    turn." sentence, this time printed plainly (no Adventure) on a real
    Modern-legal card outside the deck pool."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Explore", "Forest", "Forest"],
            library=["Mountain"],
            battlefield=["Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.land_allowance("alice") == 1

    scenario.cast_and_resolve("Explore", *scenario.untapped_sources("Forest", "Forest"))

    assert scenario.game.land_allowance("alice") == 2
    first = scenario.play_land("Forest")
    second = scenario.play_land("Forest")
    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.BATTLEFIELD


def test_thranduils_company_grants_nothing_with_no_other_elf():
    scenario = Scenario().player("alice", battlefield=["Thranduil's Company"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.land_allowance("alice") == 1


def test_thranduils_company_grants_an_extra_land_with_another_elf_in_play():
    scenario = (
        Scenario().player("alice", battlefield=["Thranduil's Company", "Elvish Mystic"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.land_allowance("alice") == 2


def test_thranduils_company_does_not_count_itself_as_the_other_elf():
    """ "Another Elf" - Thranduil's Company is itself an Elf Soldier, and does
    not satisfy its own condition."""
    scenario = Scenario().player("alice", battlefield=["Thranduil's Company"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    company = scenario.creature("Thranduil's Company", "alice")
    assert "elf" in {subtype.lower() for subtype in company.subtypes}

    assert scenario.game.land_allowance("alice") == 1


def test_thranduils_company_grant_is_re_read_live_once_the_elf_leaves():
    """CR 611.3a: never locked in - the grant disappears the instant the
    other Elf does."""
    scenario = (
        Scenario().player("alice", battlefield=["Thranduil's Company", "Elvish Mystic"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.land_allowance("alice") == 2

    mystic = scenario.creature("Elvish Mystic", "alice")
    scenario.game.destroy(mystic)

    assert scenario.game.land_allowance("alice") == 1
