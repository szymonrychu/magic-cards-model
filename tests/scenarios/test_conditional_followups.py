"""Conditional follow-up templates: a resolution instruction whose second
half is gated on something the first half just determined - combat state,
what type the destroyed/exiled permanent turned out to be, its mana value,
or an intervening-if count check on the caster's own board.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 508.1i** - a creature is attacking once it has been declared as one.
- **CR 603.10a / 704.8** - a look-back trigger/instruction reads the
  permanent's last known information after it leaves the battlefield.
- **CR 700.4** - "dies" means put into a graveyard from the battlefield.
- **CR 603.4** - an intervening *if* is checked when the ability would
  trigger and again as it resolves (CR 608.2a).
- **CR 202.3** - mana value is a characteristic of an object.
- **CR 614.1a** - a replacement effect ("would die ... exile it instead").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_prophesied_end_lets_the_controller_draw_only_when_not_attacking() -> None:
    """ "Destroy target creature. If it wasn't attacking, its controller
    draws a card."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prophesied End"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_hand_before = len(scenario.game.player("bob").hand)

    scenario.cast_and_resolve(
        "Prophesied End", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.game.player("bob").hand) == bob_hand_before + 1


def test_budding_insurgent_draws_only_when_destroyed_permanent_was_legendary() -> None:
    """ "Sacrifice this creature: Destroy target artifact or enchantment. If
    that permanent was a legendary enchantment, draw a card." - the quality
    is checked against the permanent as it last existed, after it is
    already gone.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Budding Insurgent"], library=["Opt"])
        .player("bob", battlefield=["Oath of Jace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    insurgent = scenario.creature("Budding Insurgent", "alice")
    oath = scenario.find("Oath of Jace", Zone.BATTLEFIELD, "bob")
    alice_hand_before = len(scenario.game.player("alice").hand)

    scenario.activate(insurgent, sacrificing=[insurgent], targets=[oath])
    scenario.resolve_top()

    assert insurgent.zone is Zone.GRAVEYARD
    assert oath.zone is Zone.GRAVEYARD
    assert len(scenario.game.player("alice").hand) == alice_hand_before + 1


def test_lilianas_defeat_off_set_reads_the_same_quality_check_with_a_life_loss_consequence() -> (
    None
):
    """Liliana's Defeat (not in this pool, not the reported card): "Destroy
    target black creature or black planeswalker. If that permanent was a
    Liliana planeswalker, her controller loses 3 life." - the identical
    "if that permanent was a `<quality>`" gate, generalized this session to
    a second consequence (a life loss on the destroyed permanent's own last
    known controller) beyond Budding Insurgent's/Nissa's Defeat's "draw a
    card".
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Liliana's Defeat"], battlefield=["Swamp"])
        .player("bob", battlefield=["Liliana of the Veil"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    bob_life_before = scenario.game.player("bob").life

    scenario.cast_and_resolve(
        "Liliana's Defeat", *scenario.untapped_sources("Swamp"), targets=[liliana]
    )

    assert liliana.zone is Zone.GRAVEYARD
    assert scenario.game.player("bob").life == bob_life_before - 3


def test_vindictive_triumph_returns_a_cheap_permanent_then_re_exiles_it_at_end_step() -> None:
    """ "Exile target creature or planeswalker. If that permanent's mana
    value was 3 or less, return it to the battlefield tapped under your
    control. Exile it at the beginning of the next end step." - Grizzly
    Bears (mana value 2) comes back under alice's control, tapped, then a
    delayed trigger exiles it again.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Vindictive Triumph"], battlefield=["Swamp", "Plains", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Vindictive Triumph",
        *scenario.untapped_sources("Swamp", "Plains", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.tapped
    assert scenario.game.controller_of(bears).username == "alice"

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.resolve_top()  # the delayed re-exile trigger

    assert bears.zone is Zone.EXILE


def test_vraska_destroys_and_gives_a_treasure_only_when_controlling_six_or_more_lands() -> None:
    """ "When Vraska, the Cutting Glare enters, if you control six or more
    lands, destroy target permanent an opponent controls. They create a
    Treasure token." - CR 603.4's intervening *if*, generalized this
    session to also read the "N or more" suffix form (`_CONTROLLED_
    SUBTYPE_COUNT`'s own widening) alongside the pre-existing "at least N"
    prefix form.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Vraska, the Cutting Glare"],
            battlefield=["Swamp"] * 6 + ["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Vraska, the Cutting Glare", [bears])

    scenario.cast_and_resolve(
        "Vraska, the Cutting Glare",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Forest"),
    )
    scenario.resolve_top()  # the enters trigger

    assert bears.zone is Zone.GRAVEYARD
    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if state.name == "Treasure Token"
    ]
    assert len(treasures) == 1


def test_vraska_does_nothing_with_fewer_than_six_lands() -> None:
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Vraska, the Cutting Glare"], battlefield=["Swamp", "Swamp", "Forest"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Vraska, the Cutting Glare", *scenario.untapped_sources("Swamp", "Swamp", "Forest")
    )
    scenario.game._before_priority()

    assert bears.zone is Zone.BATTLEFIELD
    assert not scenario.game.stack


def test_essence_burn_exiles_a_lethally_damaged_creature_instead_of_letting_it_die() -> None:
    """ "Essence Burn deals 5 damage to target black or green creature or
    planeswalker. If that permanent would die this turn, exile it instead."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Essence Burn"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Essence Burn", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )

    assert bears.zone is Zone.EXILE


def test_bleed_dry_off_set_reads_the_same_die_to_exile_replacement_from_a_pump_kill() -> None:
    """Bleed Dry (not in this pool, not the reported card): "Target creature
    gets -13/-13 until end of turn. If that creature would die this turn,
    exile it instead." - the identical replacement, proven this time off a
    stat-reduction kill rather than a damage one.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Bleed Dry"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Bleed Dry", *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"), targets=[bears]
    )

    assert bears.zone is Zone.EXILE
