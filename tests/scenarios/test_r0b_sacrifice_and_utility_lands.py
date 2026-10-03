"""Utility, sacrifice and search lands, and the land-search sorcery:
Horizon Canopy, Fountainport, Escape Tunnel, Promising Vein, Mistveil Plains,
Emeria, the Sky Ruin and Glimpse the Core.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 119.4** - life may be paid only up to the life total; paying subtracts
  it. Losing at 0 is CR 704.5a.
- **CR 602.2** - the whole cost, a sacrifice included, is paid on activation.
- **CR 701.23a / CR 701.24a** - search, then shuffle. A search for a quality
  need not find (CR 701.23b).
- **CR 305.6** - a land with a basic land type has that type's mana ability.
- **CR 603.4** - an intervening "if" is checked when the trigger event occurs
  and again on resolution.
- **CR 700.2** - a modal spell announces its mode(s) on casting.
- **CR 111.10a** - a Treasure token.
- **CR 509.1b** - "can't be blocked" is a restriction checked when blockers
  are declared.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario, mana_from


def _ready(scenario, name: str, username: str = "alice"):
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    permanent.summoning_sick = False
    return permanent


def _names(cards) -> list[str]:
    return [card.name for card in cards]


# -- Horizon Canopy -----------------------------------------------------------


def _canopy_board(life: int = 20, extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            battlefield=["Horizon Canopy", *(extra or [])],
            library=["Forest", "Island", "Plains"],
        )
        .player("bob", library=["Forest"] * 3)
    )


@pytest.mark.parametrize("colour", [Color.GREEN, Color.WHITE])
def test_canopy_taps_for_green_or_white_and_costs_one_life(colour):
    scenario = _canopy_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    canopy = _ready(scenario, "Horizon Canopy")

    scenario.activate(canopy, index=0, color=colour)

    assert scenario.player("alice").mana_pool.floating == {colour: 1}
    assert scenario.player("alice").life == 19
    assert canopy.tapped


def test_canopy_refuses_a_colour_it_does_not_make():
    scenario = _canopy_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    canopy = _ready(scenario, "Horizon Canopy")

    with pytest.raises(ValueError):
        scenario.activate(canopy, index=0, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {}


def test_canopy_can_pay_its_last_life_point_and_the_player_then_loses():
    """CR 119.4: a payment equal to the life total is allowed; CR 704.5a then
    makes the player lose as a state-based action."""
    scenario = _canopy_board(life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    canopy = _ready(scenario, "Horizon Canopy")

    scenario.activate(canopy, index=0, color=Color.GREEN)
    scenario.state_based_actions()

    assert scenario.player("alice").life == 0
    assert "alice" not in [player.username for player in scenario.game.players_in_game]


def test_canopy_sacrifice_ability_draws_a_card_and_pays_everything_up_front():
    scenario = _canopy_board(extra=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    canopy = _ready(scenario, "Horizon Canopy")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(canopy, forest, index=1, sacrificing=[canopy])

    assert canopy.zone is Zone.GRAVEYARD, "CR 602.2: the sacrifice is a cost"
    assert forest.tapped
    assert scenario.stack_names() == ["Horizon Canopy's activated ability"]
    assert scenario.player("alice").life == 20, "the draw ability pays no life"
    scenario.pass_until_resolved()
    assert _names(scenario.player("alice").hand) == ["Forest"]


def test_canopy_sacrifice_ability_needs_its_generic_mana():
    scenario = _canopy_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    canopy = _ready(scenario, "Horizon Canopy")

    with pytest.raises(ValueError):
        scenario.activate(canopy, index=1, sacrificing=[canopy])

    assert canopy.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").hand == []


# -- Fountainport -------------------------------------------------------------


def _fountainport_board(*, fountainports: int = 1, lands: int = 8, life: int = 20) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            battlefield=["Fountainport"] * fountainports + ["Forest"] * lands + ["Sol Ring"],
            library=["Island", "Plains", "Swamp"],
        )
        .player("bob", library=["Forest"] * 3)
    )


def _tokens(scenario, username: str = "alice"):
    return [s for s in scenario.game.permanents_controlled_by(username) if is_token(s)]


def test_fountainport_taps_for_colourless():
    scenario = _fountainport_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")

    scenario.activate(port, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


def test_fountainport_makes_a_treasure_for_four_mana_and_a_tap():
    scenario = _fountainport_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")

    scenario.activate(port, *scenario.untapped_sources(*["Forest"] * 4), index=3)
    scenario.pass_until_resolved()

    (treasure,) = _tokens(scenario)
    assert "Treasure" in scenario.game.computed_board().of(treasure).subtypes
    assert Type.ARTIFACT in scenario.game.computed_board().of(treasure).types
    assert port.tapped


def test_fountainport_makes_a_one_one_blue_fish_for_three_mana_a_tap_and_one_life():
    scenario = _fountainport_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")

    scenario.activate(port, *scenario.untapped_sources(*["Forest"] * 3), index=2)
    assert scenario.player("alice").life == 19, "CR 119.4: the life is paid on activation"
    scenario.pass_until_resolved()

    (fish,) = _tokens(scenario)
    computed = scenario.game.computed_board().of(fish)
    assert computed.is_creature
    assert (computed.power, computed.toughness) == (1, 1)
    assert computed.colors == (Color.BLUE,)
    assert "Fish" in computed.subtypes


def test_fountainport_fish_ability_can_take_the_last_life_point():
    scenario = _fountainport_board(life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")

    scenario.activate(port, *scenario.untapped_sources(*["Forest"] * 3), index=2)

    assert scenario.player("alice").life == 0


def test_fountainport_sacrifices_a_token_to_draw_a_card():
    scenario = _fountainport_board(fountainports=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [
        s for s in scenario.game.permanents_controlled_by("alice") if s.card.name == "Fountainport"
    ]
    first.summoning_sick = second.summoning_sick = False
    scenario.activate(first, *scenario.untapped_sources(*["Forest"] * 4), index=3)
    scenario.pass_until_resolved()
    (treasure,) = _tokens(scenario)

    scenario.activate(
        second, *scenario.untapped_sources("Forest", "Forest"), index=1, sacrificing=[treasure]
    )
    assert treasure.zone is not Zone.BATTLEFIELD, "CR 602.2: the sacrifice is a cost"
    scenario.pass_until_resolved()

    assert _names(scenario.player("alice").hand) == ["Island"]


def test_fountainport_cannot_sacrifice_a_nontoken_permanent():
    scenario = _fountainport_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.activate(
            port, *scenario.untapped_sources("Forest", "Forest"), index=1, sacrificing=[ring]
        )

    assert ring.zone is Zone.BATTLEFIELD
    assert not port.tapped


def test_fountainport_draw_ability_needs_a_token_to_sacrifice():
    scenario = _fountainport_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    port = _ready(scenario, "Fountainport")

    with pytest.raises(ValueError):
        scenario.activate(port, *scenario.untapped_sources("Forest", "Forest"), index=1)

    assert scenario.player("alice").hand == []


# -- Escape Tunnel ------------------------------------------------------------


def _tunnel_board(library: list[str] | None = None, bob_battlefield=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Escape Tunnel", "Hill Giant", "Grizzly Bears"],
            library=library if library is not None else ["Hallowed Fountain", "Island", "Forest"],
        )
        .player("bob", battlefield=bob_battlefield or ["Grizzly Bears"], library=["Forest"] * 3)
    )


def test_tunnel_fetches_a_basic_land_tapped_and_ignores_nonbasic_lands():
    scenario = _tunnel_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")
    before = len(scenario.player("alice").library)

    scenario.activate(tunnel, index=0, sacrificing=[tunnel])
    assert tunnel.zone is Zone.GRAVEYARD, "CR 602.2: sacrificed as a cost"
    scenario.pass_until_resolved()

    found = [s for s in scenario.game.permanents_controlled_by("alice") if s.card.name == "Island"]
    assert len(found) == 1
    assert found[0].tapped, "'put it onto the battlefield tapped'"
    assert "Hallowed Fountain" in _names(scenario.player("alice").library), "not basic"
    assert len(scenario.player("alice").library) == before - 1


def test_tunnel_search_may_find_nothing_when_no_basic_land_remains():
    """CR 701.23b: failing to find is always a legal outcome."""
    scenario = _tunnel_board(library=["Hallowed Fountain", "Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")

    scenario.activate(tunnel, index=0, sacrificing=[tunnel])
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").library) == 2
    assert tunnel.zone is Zone.GRAVEYARD


def test_tunnel_makes_a_small_creature_unblockable_for_the_turn():
    scenario = _tunnel_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")
    bears = _ready(scenario, "Grizzly Bears")

    scenario.activate(tunnel, index=1, sacrificing=[tunnel], targets=[bears])
    scenario.pass_until_resolved()
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    blocker = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.block(bears, blocker)


def test_a_creature_that_was_not_targeted_stays_blockable():
    scenario = _tunnel_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")
    bears = _ready(scenario, "Grizzly Bears")
    giant = _ready(scenario, "Hill Giant")

    scenario.activate(tunnel, index=1, sacrificing=[tunnel], targets=[bears])
    scenario.pass_until_resolved()
    scenario.advance()
    scenario.advance()
    scenario.attack_with(giant)
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.block(giant, blocker)

    assert scenario.blockers() == [blocker]


def test_tunnel_cannot_target_a_creature_with_power_three():
    """'Power 2 or less': Hill Giant is a 3/3, so it is not a legal target."""
    scenario = _tunnel_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")
    giant = _ready(scenario, "Hill Giant")

    with pytest.raises(ValueError):
        scenario.activate(tunnel, index=1, sacrificing=[tunnel], targets=[giant])

    assert tunnel.zone is Zone.BATTLEFIELD


def test_tunnel_may_target_an_opponents_small_creature():
    scenario = _tunnel_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tunnel = _ready(scenario, "Escape Tunnel")
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(tunnel, index=1, sacrificing=[tunnel], targets=[theirs])

    assert scenario.stack_names() == ["Escape Tunnel's activated ability"]


# -- Promising Vein -----------------------------------------------------------


def _vein_board(library: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Promising Vein", "Forest"],
            library=library if library is not None else ["Hallowed Fountain", "Swamp", "Island"],
        )
        .player("bob", library=["Forest"] * 3)
    )


def test_vein_is_a_cave_that_taps_for_colourless():
    scenario = _vein_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vein = _ready(scenario, "Promising Vein")

    assert "Cave" in scenario.game.computed_board().of(vein).subtypes
    scenario.activate(vein, index=0)
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


def test_vein_fetches_any_basic_land_tapped():
    scenario = _vein_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vein = _ready(scenario, "Promising Vein")
    (forest,) = scenario.untapped_sources("Forest")
    before = len(scenario.player("alice").library)

    scenario.activate(vein, forest, index=1, sacrificing=[vein])
    assert vein.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    found = [s for s in scenario.game.permanents_controlled_by("alice") if s.card.name == "Swamp"]
    assert len(found) == 1 and found[0].tapped
    assert len(scenario.player("alice").library) == before - 1
    assert "Hallowed Fountain" in _names(scenario.player("alice").library)


def test_vein_needs_its_one_generic_mana():
    scenario = _vein_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vein = _ready(scenario, "Promising Vein")

    with pytest.raises(ValueError):
        scenario.activate(vein, index=1, sacrificing=[vein])

    assert vein.zone is Zone.BATTLEFIELD


def test_vein_with_no_basic_land_in_the_library_finds_nothing():
    scenario = _vein_board(library=["Hallowed Fountain", "Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vein = _ready(scenario, "Promising Vein")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(vein, forest, index=1, sacrificing=[vein])
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").library) == 2


# -- Mistveil Plains ----------------------------------------------------------


def _mistveil_board(*, white: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Mistveil Plains", "Plains", *white],
            graveyard=graveyard if graveyard is not None else ["Grizzly Bears"],
            library=["Forest"] * 3,
        )
        .player("bob", graveyard=["Memnite"], library=["Forest"] * 3)
    )


def test_mistveil_is_a_plains_that_enters_tapped():
    scenario = (
        Scenario()
        .player("alice", hand=["Mistveil Plains"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    plains = scenario.play_land("Mistveil Plains")

    assert plains.tapped
    assert "Plains" in scenario.game.computed_board().of(plains).subtypes


def test_mistveil_taps_for_white_through_its_plains_type():
    """CR 305.6: the basic land type brings `{T}: Add {W}` along."""
    scenario = _mistveil_board(white=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _ready(scenario, "Mistveil Plains")

    (source,) = scenario.untapped_sources("Mistveil Plains")
    assert scenario.player("alice").mana_pool.floating == {}
    assert Color.WHITE in mana_from(source)


def test_mistveil_puts_a_graveyard_card_on_the_bottom_with_two_white_permanents():
    scenario = _mistveil_board(white=["Serra Angel", "Wall of Omens"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")
    (plains,) = scenario.untapped_sources("Plains")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.why_cannot_activate(mistveil, 0) is None

    scenario.activate(mistveil, plains, index=0, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-1] is bears, "the bottom of the library"
    assert scenario.player("alice").graveyard == []


def test_mistveil_is_refused_with_only_one_white_permanent():
    scenario = _mistveil_board(white=["Serra Angel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")

    refusal = scenario.why_cannot_activate(mistveil, 0)

    assert refusal is not None
    assert "activation restriction is not met" in refusal


def test_mistveil_does_not_count_itself_or_colourless_permanents():
    scenario = _mistveil_board(white=["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")

    assert scenario.why_cannot_activate(mistveil, 0) is not None


def test_mistveil_does_not_count_an_opponents_white_permanents():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mistveil Plains", "Plains", "Serra Angel"],
            graveyard=["Grizzly Bears"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Wall of Omens", "Serra Angel"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")

    assert scenario.why_cannot_activate(mistveil, 0) is not None


def test_mistveil_cannot_target_the_opponents_graveyard():
    scenario = _mistveil_board(white=["Serra Angel", "Wall of Omens"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")
    (plains,) = scenario.untapped_sources("Plains")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "bob")

    with pytest.raises(ValueError):
        scenario.activate(mistveil, plains, index=0, targets=[memnite])

    assert memnite.zone is Zone.GRAVEYARD


def test_mistveil_activation_needs_a_card_in_the_graveyard():
    scenario = _mistveil_board(white=["Serra Angel", "Wall of Omens"], graveyard=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mistveil = _ready(scenario, "Mistveil Plains")
    (plains,) = scenario.untapped_sources("Plains")

    with pytest.raises(ValueError):
        scenario.activate(mistveil, plains, index=0)


# -- Emeria, the Sky Ruin -----------------------------------------------------


def _emeria_board(plains: int, graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Emeria, the Sky Ruin", *["Plains"] * plains],
            graveyard=graveyard if graveyard is not None else ["Grizzly Bears", "Opt"],
            library=["Forest"] * 6,
        )
        .player("bob", graveyard=["Memnite"], library=["Forest"] * 6)
    )


def _alices_next_upkeep(scenario) -> None:
    """Run alice's turn and bob's out, and stop in alice's next upkeep."""
    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()  # untap
        scenario.advance()  # upkeep
    assert scenario.turn.active_player == "alice"


def test_emeria_enters_tapped_and_taps_for_white():
    scenario = (
        Scenario()
        .player("alice", hand=["Emeria, the Sky Ruin"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emeria = scenario.play_land("Emeria, the Sky Ruin")
    assert emeria.tapped
    emeria.tapped = False
    emeria.summoning_sick = False

    scenario.activate(emeria, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1}


def test_emeria_returns_a_creature_card_with_seven_plains():
    scenario = _emeria_board(7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Emeria, the Sky Ruin", [bears])
    scenario.will_take_the_may(True)
    _alices_next_upkeep(scenario)
    assert scenario.stack_names() == ["Emeria, the Sky Ruin's triggered ability"]

    scenario.pass_until_resolved()

    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_emeria_does_not_trigger_with_six_plains():
    """CR 603.4: the intervening 'if' is false when the upkeep begins."""
    scenario = _emeria_board(6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alices_next_upkeep(scenario)

    assert scenario.stack_names() == []
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_emeria_itself_is_not_a_plains():
    """Six Plains and Emeria is still six Plains."""
    scenario = _emeria_board(6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emeria = scenario.find("Emeria, the Sky Ruin", Zone.BATTLEFIELD, "alice")

    assert "Plains" not in scenario.game.computed_board().of(emeria).subtypes
    _alices_next_upkeep(scenario)
    assert scenario.stack_names() == []


def test_emeria_may_decline_to_return_the_creature():
    scenario = _emeria_board(7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Emeria, the Sky Ruin", [bears])
    scenario.will_take_the_may(False)
    _alices_next_upkeep(scenario)

    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_emeria_rechecks_the_plains_count_on_resolution():
    """CR 603.4: the 'if' is checked again as the ability resolves."""
    scenario = _emeria_board(7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Emeria, the Sky Ruin", [bears])
    scenario.will_take_the_may(True)
    _alices_next_upkeep(scenario)
    assert scenario.stack_names() == ["Emeria, the Sky Ruin's triggered ability"]
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(plains)

    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "six Plains on resolution: the ability does nothing"


def test_emeria_cannot_return_a_noncreature_card_or_an_opponents_creature():
    scenario = _emeria_board(7, graveyard=["Opt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError, match="needs a creature"):
        scenario.choose_trigger_targets("Emeria, the Sky Ruin", [opt])
    with pytest.raises(ValueError, match="alice controls"):
        scenario.choose_trigger_targets("Emeria, the Sky Ruin", [memnite])

    assert opt.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.GRAVEYARD, "your graveyard only"


# -- Glimpse the Core ---------------------------------------------------------


def _glimpse_board(
    *, library: list[str] | None = None, graveyard: list[str] | None = None
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Glimpse the Core"],
            battlefield=["Forest", "Forest"],
            graveyard=graveyard if graveyard is not None else ["Promising Vein"],
            library=library if library is not None else ["Island", "Forest", "Hallowed Fountain"],
        )
        .player("bob", library=["Forest"] * 3)
    )


def _cast_glimpse(scenario, mode: int, targets=None) -> None:
    casting = scenario.cast("Glimpse the Core", username="alice")
    casting.choose_modes([mode])
    if targets:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def test_glimpse_mode_one_puts_a_basic_forest_onto_the_battlefield_tapped():
    scenario = _glimpse_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = len(scenario.player("alice").library)

    _cast_glimpse(scenario, 1)

    forests = [
        s
        for s in scenario.game.permanents_controlled_by("alice")
        if s.card.name == "Forest" and s.tapped and s.zone is Zone.BATTLEFIELD
    ]
    assert len(forests) == 3, "the two that paid, and the new tapped one"
    assert len(scenario.player("alice").library) == before - 1
    assert "Island" in _names(scenario.player("alice").library)
    assert scenario.find("Glimpse the Core", Zone.GRAVEYARD, "alice")


def test_glimpse_mode_one_finds_nothing_without_a_basic_forest():
    scenario = _glimpse_board(library=["Island", "Hallowed Fountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_glimpse(scenario, 1)

    assert len(scenario.player("alice").library) == 2
    assert "Hallowed Fountain" in _names(scenario.player("alice").library)


def test_glimpse_mode_one_does_not_fetch_a_nonbasic_forest_typed_land():
    """'Basic Forest card': Breeding Pool is a Forest but not basic."""
    scenario = _glimpse_board(library=["Breeding Pool", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_glimpse(scenario, 1)

    assert "Breeding Pool" in _names(scenario.player("alice").library)


def test_glimpse_mode_two_returns_a_cave_from_the_graveyard_tapped():
    scenario = _glimpse_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vein = scenario.find("Promising Vein", Zone.GRAVEYARD, "alice")

    _cast_glimpse(scenario, 2, [vein])

    assert vein.zone is Zone.BATTLEFIELD
    assert vein.tapped


def test_glimpse_mode_two_cannot_return_a_non_cave():
    scenario = _glimpse_board(graveyard=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Glimpse the Core", username="alice")
    casting.choose_modes([2])

    with pytest.raises(ValueError):
        casting.choose_targets([forest])


# -- "Sacrifice a token", on a second printing ---------------------------------


def _tactician_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Hardened Tactician", "Sol Ring", "Forest"],
            library=["Island", "Plains"],
        )
        .player("bob", library=["Forest"] * 3)
    )


def test_hardened_tactician_sacrifices_a_token_to_draw():
    from magic_cards_model.models.token import PREDEFINED, create_tokens

    scenario = _tactician_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tactician = _ready(scenario, "Hardened Tactician")
    (token,) = create_tokens(scenario.game, PREDEFINED["Treasure"], "alice")

    scenario.activate(tactician, *scenario.untapped_sources("Forest"), index=0, sacrificing=[token])
    scenario.pass_until_resolved()

    assert _names(scenario.player("alice").hand) == ["Island"]


def test_hardened_tactician_refuses_a_nontoken_sacrifice():
    scenario = _tactician_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tactician = _ready(scenario, "Hardened Tactician")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="not a token"):
        scenario.activate(
            tactician, *scenario.untapped_sources("Forest"), index=0, sacrificing=[ring]
        )

    assert ring.zone is Zone.BATTLEFIELD


def test_a_nontoken_quality_reads_the_opposite_way():
    from magic_cards_model.machines.cost import cost_component_for_phrase

    component = cost_component_for_phrase("Sacrifice a nontoken creature", payer="alice")

    assert component is not None
    assert component.requirement.token is False
    assert Type.CREATURE in component.requirement.types


# -- "if you control N or more Plains", on a second printing -------------------


def test_duergar_hedge_mage_counts_plains_for_its_own_intervening_if():
    """The `s$` of the count reader strips the s from "Plains" too; the second
    printing of the clause shape is Duergar Hedge-Mage's Plains half."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Duergar Hedge-Mage"],
            battlefield=["Plains", "Plains", "Plains", "Mountain"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Pacifism"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Duergar Hedge-Mage", [pacifism])
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve(
        "Duergar Hedge-Mage", *scenario.untapped_sources("Plains", "Plains", "Mountain")
    )
    assert scenario.stack_names() == ["Duergar Hedge-Mage's triggered ability"]
    scenario.pass_until_resolved()

    assert pacifism.zone is Zone.GRAVEYARD


def test_duergar_hedge_mage_with_one_plains_has_no_trigger():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Duergar Hedge-Mage"],
            battlefield=["Plains", "Mountain", "Swamp"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Pacifism"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Duergar Hedge-Mage", *scenario.untapped_sources("Plains", "Mountain", "Swamp")
    )

    assert scenario.stack_names() == []
