""" "Reveal the top card of your library and put that card into your hand.
You lose life equal to its mana value." (`_merge_reveal_top_hand_lose_life_
equal_to_mana_value_clauses` in `machines/effects.py`).

The reader already knew the older printed wording, "... equal to that card's
mana value" (Pain Seer). Current Oracle text prints the pronoun instead -
Darkstar Augur's upkeep trigger, and Dark Confidant's own, whose Oracle text
now reads "its mana value" too - so both spellings are one instruction:

- **Darkstar Augur** (the listed card): upkeep trigger, plus Offspring {B}
  whose 1/1 token copy (CR 702.175a) carries the same triggered ability and
  so triggers on its own at the same upkeep.
- **Dark Confidant** (the second printing, not a listed card and not in any
  api deck): the same upkeep trigger on a different body.

Corner cases:

- CR 202.3e: an {X} in the mana cost of a card in the library counts as 0,
  so an X spell costs only its non-X symbols.
- CR 202.3a: a card with no mana cost (a land) has mana value 0 - revealing
  one loses no life.
- An empty library: no card to reveal, move or measure (CR 609.3), nothing
  happens and no life is lost.
- CR 701.20a: a reveal is shown to every player.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 202.3a, 202.3e, 609.3, 701.20a, 702.175a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AUGUR = "Darkstar Augur"
CONFIDANT = "Dark Confidant"


def _resolve_all(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _into_alices_upkeep(creature: str, library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[creature], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    return scenario


def test_darkstar_augur_reveals_the_top_card_puts_it_in_hand_and_loses_its_mana_value():
    scenario = _into_alices_upkeep(AUGUR, ["Tarmogoyf", "Forest"])
    alice = scenario.player("alice")

    assert [item.source_name for item in scenario.game.stack] == [AUGUR]
    _resolve_all(scenario)

    assert [card.name for card in alice.hand] == ["Tarmogoyf"]
    assert [card.name for card in alice.library] == ["Forest"]
    assert alice.life == 20 - 2  # Tarmogoyf is {1}{G}
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_dark_confidant_reads_the_same_instruction():
    scenario = _into_alices_upkeep(CONFIDANT, ["Lightning Bolt", "Forest"])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert [card.name for card in alice.hand] == ["Lightning Bolt"]
    assert alice.life == 20 - 1


def test_the_reveal_is_shown_to_every_player():
    scenario = _into_alices_upkeep(AUGUR, ["Lightning Bolt"])

    _resolve_all(scenario)

    reveals = [r for r in scenario.game.reveals if r.source == AUGUR]
    assert [(r.card_name, r.viewers) for r in reveals] == [("Lightning Bolt", None)]


def test_an_x_spell_counts_x_as_zero():
    """CR 202.3e: Fireball ({X}{R}) in the library has mana value 1."""
    scenario = _into_alices_upkeep(AUGUR, ["Fireball"])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert [card.name for card in alice.hand] == ["Fireball"]
    assert alice.life == 19


def test_an_all_x_cost_is_mana_value_zero():
    """CR 202.3e: Walking Ballista ({X}{X}) costs nothing to reveal."""
    scenario = _into_alices_upkeep(CONFIDANT, ["Walking Ballista"])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert [card.name for card in alice.hand] == ["Walking Ballista"]
    assert alice.life == 20


def test_a_land_loses_no_life():
    scenario = _into_alices_upkeep(AUGUR, ["Forest"])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert [card.name for card in alice.hand] == ["Forest"]
    assert alice.life == 20


def test_an_empty_library_does_nothing():
    scenario = _into_alices_upkeep(AUGUR, [])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert alice.hand == []
    assert alice.life == 20
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_six_drop_hurts():
    scenario = _into_alices_upkeep(CONFIDANT, ["Doomsday Excruciator"])
    alice = scenario.player("alice")

    _resolve_all(scenario)

    assert alice.life == 14


def test_the_offspring_token_copy_triggers_too():
    """CR 702.175a: the offspring token is a copy of Darkstar Augur, so it has
    the upkeep trigger as well - two triggers, two cards, two life losses."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[AUGUR],
            battlefield=["Swamp"] * 4,
            library=["Tarmogoyf", "Lightning Bolt", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    casting = scenario.cast(AUGUR, username="alice")
    casting.pay_offspring()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    augurs = [s for s in scenario.game.battlefield if s.name == AUGUR]
    assert sorted(s.token for s in augurs) == [False, True]

    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        scenario.advance()
        if not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
            _resolve_all(scenario)
    alice = scenario.player("alice")
    stacked = [item.source_name for item in scenario.game.stack] + [
        item.source_name for item in scenario.pending_triggers
    ]
    assert stacked.count(AUGUR) == 2
    _resolve_all(scenario)

    in_hand = sorted(card.name for card in alice.hand)
    assert in_hand == ["Lightning Bolt", "Tarmogoyf"]
    assert alice.life == 20 - 2 - 1
    assert all(card.zone is Zone.HAND for card in alice.hand)
