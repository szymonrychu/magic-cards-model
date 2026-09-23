"""Scenario: "Exile any number of target players' graveyards."

Thraben Charm's third mode and The Death of Gwen Stacy's chapter III print
the same sentence. The targets are players (CR 115.1: "The targets are
object(s) and/or player(s)"), any number of them including none (CR 107.1c:
"that player may choose any positive number or zero"), and each chosen
player's graveyard is exiled (CR 406.2: exile moves an object from whatever
zone it is in). The singular reader already read Bojuka Bog's "exile target
player's graveyard"; it is widened here to the plural, count-agnostic phrase,
on the spell side (a mode) and the ability side (a Saga chapter) alike.

The rest of Thraben Charm - its damage mode and its enchantment mode - is
covered at the end, so every mode of the card is proven resolving on its
own.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.1c** - "any number" includes zero.
- **CR 115.1** - a target may be a player.
- **CR 406.2** - to exile an object is to put it into exile from whatever
  zone it is in.
- **CR 608.2b** - targets are rechecked on resolution.
- **CR 701.8a** - destroy moves a permanent to its owner's graveyard.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _charm_board(bob_battlefield: tuple[str, ...] = ("Serra Angel",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Thraben Charm"],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Grizzly Bears"],
            graveyard=["Lightning Bolt", "Island"],
        )
        .player(
            "bob",
            battlefield=list(bob_battlefield),
            graveyard=["Counterspell", "Mountain", "Memnite"],
        )
    )


def _cast_charm(scenario, mode: int, targets: list) -> object:
    casting = scenario.cast("Thraben Charm")
    casting.choose_modes([mode])
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Plains"))
    spell = scenario.put_on_stack(casting)
    _resolve_all(scenario)
    return spell


def test_one_target_player_loses_their_whole_graveyard():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_cards = list(scenario.player("bob").graveyard)

    _cast_charm(scenario, 3, ["bob"])

    assert scenario.player("bob").graveyard == []
    assert all(state.zone is Zone.EXILE for state in bob_cards)
    assert {c.name for c in scenario.player("alice").graveyard} == {
        "Lightning Bolt",
        "Island",
        "Thraben Charm",
    }, "the untargeted graveyard is untouched; the charm itself lands there after"
    assert not scenario.game.mode_notices


def test_two_target_players_both_lose_their_graveyards():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_charm(scenario, 3, ["bob", "alice"])

    assert scenario.player("bob").graveyard == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Thraben Charm"], (
        "alice's own graveyard was exiled while the charm was still on the stack"
    )
    assert {c.name for c in scenario.game.exile} >= {
        "Lightning Bolt",
        "Island",
        "Counterspell",
        "Mountain",
        "Memnite",
    }


def test_zero_target_players_is_a_legal_choice_that_exiles_nothing():
    """CR 107.1c: zero is "any number". The mode resolves, does nothing, and
    records no notice - it did everything it was asked to."""
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = _cast_charm(scenario, 3, [])

    assert spell.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").graveyard) == 3
    assert not scenario.game.mode_notices


def test_your_own_graveyard_alone_may_be_the_target():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_charm(scenario, 3, ["alice"])

    assert [c.name for c in scenario.player("alice").graveyard] == ["Thraben Charm"]
    assert len(scenario.player("bob").graveyard) == 3


def test_an_empty_graveyard_is_still_a_legal_target():
    """Nothing in CR 115 conditions a player target on what their zones
    hold."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thraben Charm"], battlefield=["Plains", "Plains"])
        .player("bob", graveyard=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_charm(scenario, 3, ["alice", "bob"])

    assert scenario.player("bob").graveyard == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Thraben Charm"]


def test_the_singular_template_still_reads():
    """Bojuka Bog's "exile target player's graveyard" is the sentence the
    widened reader grew from; it keeps working."""
    scenario = (
        Scenario()
        .player("alice", hand=["Bojuka Bog"])
        .player("bob", graveyard=["Mountain", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Bojuka Bog", ["bob"])
    scenario.play_land("Bojuka Bog")
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert scenario.player("bob").graveyard == []


# -- The Death of Gwen Stacy, chapter III: the ability side -----------------


def _gwen_stacy_at_chapter_two() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Death of Gwen Stacy"],
            graveyard=["Lightning Bolt", "Island"],
        )
        .player("bob", graveyard=["Counterspell", "Mountain"])
        .player("carol", graveyard=["Memnite"])
        .build()
    )
    saga = scenario.find("The Death of Gwen Stacy", Zone.BATTLEFIELD, "alice")
    saga.add_counters(Counter.LORE, 1)
    return scenario


def test_chapter_three_exiles_every_targeted_players_graveyard():
    scenario = _gwen_stacy_at_chapter_two()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("The Death of Gwen Stacy", ["bob", "carol"])
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert scenario.player("bob").graveyard == []
    assert scenario.player("carol").graveyard == []
    assert {"Lightning Bolt", "Island"} <= {c.name for c in scenario.player("alice").graveyard}


def test_chapter_three_with_no_targets_exiles_nothing():
    scenario = _gwen_stacy_at_chapter_two()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("The Death of Gwen Stacy", [])
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert len(scenario.player("bob").graveyard) == 2
    assert len(scenario.player("carol").graveyard) == 1


# -- Thraben Charm's other two modes ---------------------------------------


def test_the_damage_mode_deals_twice_the_number_of_your_creatures():
    """Two Grizzly Bears: 4 damage kills Bob's 4/4 Serra Angel."""
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_charm(scenario, 1, [angel])

    assert angel.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices


def test_the_damage_mode_counts_on_resolution_not_on_cast():
    """One of the two Bears leaves before the charm resolves: 2 damage, and
    the 4/4 Angel survives it."""
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Thraben Charm")
    casting.choose_modes([1])
    casting.choose_targets([angel])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(bears)
    _resolve_all(scenario)

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_the_enchantment_mode_destroys_target_enchantment():
    scenario = _charm_board(("Serra Angel", "Glorious Anthem")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "bob")

    _cast_charm(scenario, 2, [anthem])

    assert anthem.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices
