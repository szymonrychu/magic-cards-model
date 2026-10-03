"""R0b proofs: sacrifice-an-artifact and discard payoffs - Biotech Specialist,
Cryogen Relic, Iron-Shield Elf and Monument to Endurance.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 701.21a** - to sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard; only your own permanents.
- **CR 603.6a** - enters-the-battlefield abilities trigger on entry.
- **CR 603.10a** - leaves-the-battlefield abilities look back in time, so a
  permanent that is gone still triggers its own "leaves" ability.
- **CR 122.1d** - a stun counter replaces the next untap with its removal.
- **CR 700.2d** - a modal ability's mode can't be chosen twice unless the text
  says so ("choose one that hasn't been chosen this turn").
- **CR 702.12b** - an indestructible permanent can't be destroyed; it is not
  protected from exile or from toughness 0.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario

BIOTECH = "Biotech Specialist"
RELIC = "Cryogen Relic"
ELF = "Iron-Shield Elf"
MONUMENT = "Monument to Endurance"
POLLINATOR = "Gene Pollinator"


def _bob_life(scenario):
    return scenario.player("bob").life


# -- Biotech Specialist ------------------------------------------------------


def test_biotech_enters_and_makes_a_lander_token():
    scenario = (
        Scenario()
        .player("alice", hand=[BIOTECH], battlefield=["Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(BIOTECH, *scenario.untapped_sources("Mountain", "Forest"))
    scenario.pass_until_resolved()

    lander = scenario.find("Lander Token", Zone.BATTLEFIELD, "alice")
    assert "Lander" in lander.card.subtypes
    assert [t.value for t in lander.card.types] == ["artifact"]
    assert _bob_life(scenario) == 20, "creating the token sacrifices nothing"


def test_biotech_lander_sacrifice_searches_a_basic_and_deals_two():
    """The Lander's own sacrifice-search ability works, and sacrificing it
    to pay the cost is a sacrifice (CR 701.21a) that Biotech sees."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BIOTECH],
            battlefield=["Mountain", "Forest", "Island", "Island"],
            library=["Plains", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(BIOTECH, *scenario.untapped_sources("Mountain", "Forest"))
    scenario.pass_until_resolved()
    lander = scenario.find("Lander Token", Zone.BATTLEFIELD, "alice")
    islands = scenario.untapped_sources("Island", "Island")

    scenario.activate(lander, *islands)
    scenario.pass_until_resolved()  # the search
    scenario.pass_until_resolved()  # Biotech's trigger, queued by the sacrifice

    assert lander.zone is not Zone.BATTLEFIELD
    assert _bob_life(scenario) == 18
    lands = [c for c in scenario.game.battlefield if c.name in {"Plains", "Forest"}]
    assert any(c.name == "Plains" or c.tapped for c in lands), "a basic came from the library"


def _treasure_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BIOTECH, "Goblin Bombardment", "Grizzly Bears", POLLINATOR])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_biotech_sacrificed_treasure_deals_two():
    scenario = _treasure_board()
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")

    scenario.activate(treasure, color=Color.GREEN)
    scenario.pass_until_resolved()

    assert _bob_life(scenario) == 18


def test_biotech_sacrificed_artifact_creature_counts_as_an_artifact():
    scenario = _treasure_board()
    pollinator = scenario.creature(POLLINATOR, "alice")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")

    scenario.activate(bombardment, sacrificing=[pollinator], targets=["bob"])
    scenario.pass_until_resolved()  # Bombardment's 1 damage or Biotech's trigger
    scenario.pass_until_resolved()

    assert _bob_life(scenario) == 20 - 1 - 2, "Bombardment's 1 plus Biotech's 2"


def test_biotech_ignores_a_sacrificed_nonartifact_creature():
    scenario = _treasure_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")

    scenario.activate(bombardment, sacrificing=[bears], targets=["bob"])
    scenario.pass_until_resolved()

    assert _bob_life(scenario) == 19, "only Bombardment's own point"


def test_biotech_ignores_an_opponents_sacrificed_artifact():
    """'Whenever you sacrifice' - bob's Treasure does nothing for alice."""
    scenario = _treasure_board()
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "bob")

    scenario.pass_priority("alice")
    scenario.activate(treasure, color=Color.RED, username="bob")
    scenario.pass_until_resolved()

    assert _bob_life(scenario) == 20
    assert scenario.player("alice").life == 20


def test_biotech_triggers_once_per_artifact_sacrificed():
    scenario = _treasure_board()
    (first,) = create_predefined_tokens(scenario.game, "Treasure", "alice")
    (second,) = create_predefined_tokens(scenario.game, "Treasure", "alice")

    scenario.activate(first, color=Color.RED)
    scenario.pass_until_resolved()
    scenario.activate(second, color=Color.RED)
    scenario.pass_until_resolved()

    assert _bob_life(scenario) == 16


def test_a_lander_from_a_second_printing_is_a_lander_artifact():
    """CR 111.10u via a differently worded printing (Sami's Curiosity: a
    spell, not an enters trigger) - the token carries the Lander artifact
    type (CR 205.3g) and the sacrifice-search ability."""
    scenario = (
        Scenario()
        .player("alice", hand=["Sami's Curiosity"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life = scenario.player("alice").life

    scenario.cast_and_resolve("Sami's Curiosity", scenario.untapped_sources("Forest")[0])

    lander = scenario.find("Lander Token", Zone.BATTLEFIELD, "alice")
    assert lander.card.subtypes == ["Lander"]
    assert scenario.player("alice").life == life + 2


# -- Cryogen Relic -----------------------------------------------------------


def _relic_board(**alice):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=alice.get("hand", [RELIC]),
            battlefield=alice.get("battlefield", ["Island", "Island", "Island", "Island"]),
            library=["Forest", "Mountain", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_relic_draws_when_it_enters():
    scenario = _relic_board()
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(RELIC, *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before - 1 + 1
    assert scenario.find("Forest", Zone.HAND).zone is Zone.HAND


def test_relic_draws_again_when_it_leaves():
    relic_scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Abrade"],
            battlefield=[RELIC, "Mountain", "Mountain"],
            library=["Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    relic_scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = relic_scenario.find(RELIC, Zone.BATTLEFIELD, "alice")

    casting = relic_scenario.cast("Abrade")
    casting.choose_modes([2])  # "Destroy target artifact."
    casting.choose_targets([relic])
    payment = casting.begin_paying()
    relic_scenario.pay_with(payment, *relic_scenario.untapped_sources("Mountain", "Mountain"))
    relic_scenario.put_on_stack(casting)
    relic_scenario.resolve_top()
    relic_scenario.pass_until_resolved()

    assert relic.zone is Zone.GRAVEYARD
    assert relic_scenario.find("Forest", Zone.HAND).zone is Zone.HAND, "CR 603.10a: the leave drew"


def test_relic_sacrifice_stuns_a_tapped_creature_and_draws():
    scenario = _relic_board(battlefield=[RELIC, "Island", "Island"], hand=[])
    relic = scenario.find(RELIC, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(relic, *scenario.untapped_sources("Island", "Island"), targets=[bears])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert relic.zone is Zone.GRAVEYARD
    assert bears.counter_count(Counter.STUN) == 1
    assert len(scenario.player("alice").hand) == hand_before + 1, "it left, so it drew"

    bears.untap()
    assert bears.tapped, "CR 122.1d: the next untap is replaced"
    assert bears.counter_count(Counter.STUN) == 0
    bears.untap()
    assert not bears.tapped


def test_relic_cannot_target_an_untapped_creature():
    scenario = _relic_board(battlefield=[RELIC, "Island", "Island"], hand=[])
    relic = scenario.find(RELIC, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="(?i)tapped"):
        scenario.activate(relic, *scenario.untapped_sources("Island", "Island"), targets=[bears])

    assert relic.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.STUN) == 0


def test_relic_sacrifice_with_no_target_still_draws():
    """'Up to one target': zero targets is legal, the sacrifice cost is paid
    and the leave trigger draws."""
    scenario = _relic_board(battlefield=[RELIC, "Island", "Island"], hand=[])
    relic = scenario.find(RELIC, Zone.BATTLEFIELD, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(relic, *scenario.untapped_sources("Island", "Island"), targets=[])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert relic.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 1


# -- Iron-Shield Elf ---------------------------------------------------------


def _elf_board(hand=("Forest",), bob_hand=("Lightning Bolt",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=[ELF])
        .player("bob", hand=list(bob_hand), battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_elf_discards_a_card_to_become_indestructible_and_tapped():
    scenario = _elf_board()
    elf = scenario.creature(ELF, "alice")
    forest = scenario.find("Forest", Zone.HAND)

    scenario.activate(elf, discarding=[forest])
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD
    assert is_indestructible(elf, scenario.game)
    assert elf.tapped, "the 'Tap it.' sentence"


def test_elf_survives_lethal_damage_while_indestructible():
    scenario = _elf_board()
    elf = scenario.creature(ELF, "alice")
    scenario.activate(elf, discarding=[scenario.find("Forest", Zone.HAND)])
    scenario.pass_until_resolved()

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob")[:1],
        username="bob",
        targets=[elf],
    )
    scenario.state_based_actions()

    assert elf.zone is Zone.BATTLEFIELD, "CR 702.12b: lethal damage does not destroy it"
    assert elf.damage == 3


def test_elf_without_the_activation_dies_to_the_same_bolt():
    scenario = _elf_board()
    elf = scenario.creature(ELF, "alice")

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob")[:1],
        username="bob",
        targets=[elf],
    )
    scenario.state_based_actions()

    assert elf.zone is Zone.GRAVEYARD


def test_elf_indestructible_does_not_stop_exile():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=[ELF])
        .player("bob", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elf = scenario.creature(ELF, "alice")
    scenario.activate(elf, discarding=[scenario.find("Forest", Zone.HAND)])
    scenario.pass_until_resolved()

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Swords to Plowshares",
        *scenario.untapped_sources("Plains", username="bob"),
        username="bob",
        targets=[elf],
    )

    assert elf.zone is Zone.EXILE


def test_elf_cannot_activate_with_an_empty_hand():
    scenario = _elf_board(hand=())
    elf = scenario.creature(ELF, "alice")

    with pytest.raises(ValueError, match="(?i)discard"):
        scenario.activate(elf, discarding=[])

    assert not elf.tapped
    assert not is_indestructible(elf, scenario.game)


def test_elf_indestructible_ends_with_the_turn():
    scenario = _elf_board()
    elf = scenario.creature(ELF, "alice")
    scenario.activate(elf, discarding=[scenario.find("Forest", Zone.HAND)])
    scenario.pass_until_resolved()
    assert is_indestructible(elf, scenario.game)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()

    assert not is_indestructible(elf, scenario.game)


# -- Monument to Endurance ---------------------------------------------------

DRAW = "Draw a card."
TREASURE = "Create a Treasure token."
DRAIN = "Each opponent loses 3 life."


def _monument_board(hand_size=5):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"] * hand_size,
            battlefield=[MONUMENT, ELF, "Grizzly Bears"],
            library=["Mountain"] * 6,
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _discard_with_elf(scenario, mode):
    elf = scenario.creature(ELF, "alice")
    elf.tapped = False
    forest = scenario.find("Forest", Zone.HAND, "alice")
    if mode is not None:
        scenario.will_choose_mode(mode, username="alice", source=MONUMENT)
    scenario.activate(elf, discarding=[forest])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()


def test_monument_draw_mode():
    scenario = _monument_board()
    hand_before = len(scenario.player("alice").hand)

    _discard_with_elf(scenario, DRAW)

    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


def test_monument_treasure_mode():
    scenario = _monument_board()

    _discard_with_elf(scenario, TREASURE)

    assert scenario.find("Treasure Token", Zone.BATTLEFIELD, "alice")


def test_monument_drain_mode():
    scenario = _monument_board()

    _discard_with_elf(scenario, DRAIN)

    assert _bob_life(scenario) == 17


def test_monument_each_discard_in_a_turn_uses_a_different_mode():
    scenario = _monument_board()
    hand_before = len(scenario.player("alice").hand)

    _discard_with_elf(scenario, DRAW)
    _discard_with_elf(scenario, TREASURE)
    _discard_with_elf(scenario, DRAIN)

    assert len(scenario.player("alice").hand) == hand_before - 3 + 1
    assert scenario.find("Treasure Token", Zone.BATTLEFIELD, "alice")
    assert _bob_life(scenario) == 17


def test_monument_refuses_a_mode_already_chosen_this_turn():
    """CR 700.2d: a repeat of the draw mode is not offered, so the engine
    must not accept it."""
    scenario = _monument_board()
    _discard_with_elf(scenario, DRAW)
    scenario.will_choose_mode(DRAW, username="alice", source=MONUMENT)

    with pytest.raises(ValueError, match="(?i)mode|chosen"):
        elf = scenario.creature(ELF, "alice")
        elf.tapped = False
        scenario.activate(elf, discarding=[scenario.find("Forest", Zone.HAND, "alice")])
        scenario.pass_until_resolved()
        scenario.pass_until_resolved()


def test_monument_fourth_discard_in_a_turn_has_no_mode_left():
    scenario = _monument_board()
    _discard_with_elf(scenario, DRAW)
    _discard_with_elf(scenario, TREASURE)
    _discard_with_elf(scenario, DRAIN)
    hand_before = len(scenario.player("alice").hand)
    life_before = _bob_life(scenario)
    treasures_before = [c for c in scenario.game.battlefield if c.name == "Treasure Token"]

    _discard_with_elf(scenario, None)

    assert len(scenario.player("alice").hand) == hand_before - 1, "no draw"
    assert _bob_life(scenario) == life_before
    assert [c for c in scenario.game.battlefield if c.name == "Treasure Token"] == treasures_before


def test_monument_modes_reset_on_the_next_turn():
    scenario = _monument_board()
    _discard_with_elf(scenario, DRAW)
    for _ in range(2):  # alice's turn, then bob's, then alice's again
        scenario.start_at(Step.CLEANUP)
        scenario.turn_based_actions()
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.active_player.username == "alice"
    hand_before = len(scenario.player("alice").hand)

    _discard_with_elf(scenario, DRAW)

    assert len(scenario.player("alice").hand) == hand_before, "the draw mode is available again"
