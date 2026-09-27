"""Scenario: exiling a spell as it resolves (with a counter), and casting
free from among cards in exile with that counter (ECL).

Goliath Daydreamer:
- "Whenever you cast an instant or sorcery spell from your hand, exile that
  card with a dream counter on it instead of putting it into your graveyard
  as it resolves." CR 614.1a: a replacement effect ("instead"); the trigger
  (CR 603.2) sets it up for that one spell, and it applies only "as it
  resolves" (CR 608.2n), so a countered spell still goes to the graveyard
  (CR 701.6a).
- "Whenever this creature attacks, you may cast a spell from among cards you
  own in exile with dream counters on them without paying its mana cost."
  CR 608.2g: cast during the trigger's resolution; CR 118.9: without paying
  its mana cost.

Proof printings: Feather, the Redeemed ("exile that card instead of putting
it into your graveyard as it resolves. If you do, return it to your hand at
the beginning of the next end step."), Lilah, Undefeated Slickshot ("... If
you do, it becomes plotted.", CR 702.170c) and Dragon-Kami's Egg ("you may
cast a creature spell from among cards you own in exile with hatching
counters on them without paying its mana cost").

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 614.1a, CR 603.2, CR 608.2n, CR 701.6a, CR 608.2g,
CR 118.9, CR 702.170c, CR 122.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _dream(card) -> int:
    return card.counters["dream"]


def _goliath_board(*, hand=("Lightning Bolt",), exile=(), battlefield_extra=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Goliath Daydreamer", "Mountain", "Mountain", *battlefield_extra],
            exile=list(exile),
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Island", "Island"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_instant_cast_from_hand_is_exiled_with_a_dream_counter_as_it_resolves():
    scenario = _goliath_board()
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    assert scenario.stack_names() == ["Lightning Bolt", "Goliath Daydreamer's triggered ability"]
    scenario.resolve_top()  # the trigger
    scenario.resolve_top()  # the Bolt

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE
    assert _dream(bolt) == 1
    assert scenario.player("alice").graveyard == []


def test_a_countered_spell_still_goes_to_the_graveyard():
    """ "As it resolves" - CR 701.6a: a countered spell doesn't resolve."""
    scenario = _goliath_board(bob_hand=("Counterspell",))
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.resolve_top()  # the trigger
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Counterspell", auto=True, username="bob", targets=[bolt])
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert _dream(bolt) == 0


def test_a_creature_spell_does_not_trigger():
    scenario = _goliath_board(hand=("Raging Goblin",))
    scenario.cast_onto_stack("Raging Goblin", auto=True, username="alice")
    assert scenario.stack_names() == ["Raging Goblin"]


def test_a_spell_cast_from_the_graveyard_does_not_trigger():
    """ "From your hand" - Faithless Looting's flashback is cast from the
    graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Faithless Looting"],
            battlefield=["Goliath Daydreamer", "Mountain", "Mountain", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    assert scenario.stack_names() == ["Faithless Looting"]


def test_attacking_casts_a_dream_card_free_and_it_goes_to_the_graveyard_after():
    """The free cast is from exile, not from hand, so the first ability does
    not exile it a second time."""
    scenario = _goliath_board()
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.resolve_top()
    scenario.resolve_top()
    assert _dream(bolt) == 1

    goliath = scenario.creature("Goliath Daydreamer", "alice")
    goliath.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    scenario.attack_with(goliath)
    scenario.resolve_top()  # the attack trigger casts the Bolt
    assert scenario.stack_names() == ["Lightning Bolt"]
    assert scenario.game.cast_record_of(bolt) is not None
    scenario.resolve_top()

    assert scenario.player("bob").life == 14
    assert bolt.zone is Zone.GRAVEYARD


def test_a_card_in_exile_without_a_dream_counter_is_not_offered():
    scenario = _goliath_board(hand=(), exile=("Lightning Bolt",))
    goliath = scenario.creature("Goliath Daydreamer", "alice")
    goliath.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(goliath)
    scenario.resolve_top()
    assert scenario.stack_names() == []
    (bolt,) = [c for c in scenario.game.exile if c.name == "Lightning Bolt"]
    assert bolt.zone is Zone.EXILE


def test_declining_leaves_the_dream_card_in_exile():
    scenario = _goliath_board()
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.resolve_top()
    scenario.resolve_top()
    goliath = scenario.creature("Goliath Daydreamer", "alice")
    goliath.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(False, username="alice")
    scenario.attack_with(goliath)
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert _dream(bolt) == 1


def test_a_dream_card_someone_else_owns_is_not_offered():
    """ "Cards you own" - a dream counter on Bob's exiled card is Bob's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goliath Daydreamer"], library=["Island"] * 5)
        .player("bob", exile=["Lightning Bolt"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bobs,) = [c for c in scenario.game.exile if c.name == "Lightning Bolt"]
    bobs.add_counters("dream", 1)
    goliath = scenario.creature("Goliath Daydreamer", "alice")
    goliath.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(goliath)
    scenario.resolve_top()
    assert scenario.stack_names() == []
    assert bobs.zone is Zone.EXILE


def test_feather_returns_the_exiled_spell_to_hand_at_the_next_end_step():
    """The proof printing: the same replacement without a counter, with an
    "If you do, return it to your hand at the beginning of the next end
    step." rider."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Feather, the Redeemed", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    feather = scenario.creature("Feather, the Redeemed", "alice")
    growth = scenario.cast_onto_stack("Giant Growth", auto=True, targets=[feather])
    scenario.resolve_top()  # Feather's trigger
    scenario.resolve_top()  # Giant Growth
    assert growth.zone is Zone.EXILE

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()

    assert growth.zone is Zone.HAND


def test_lilah_plots_the_multicolored_spell_it_exiles():
    """The proof printing: "If you do, it becomes plotted." (CR 702.170c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Helix"],
            battlefield=["Lilah, Undefeated Slickshot", "Mountain", "Plains"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    helix = scenario.cast_onto_stack("Lightning Helix", auto=True, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert helix.zone is Zone.EXILE
    assert helix.exile_annotation is not None
    assert helix.exile_annotation.marker.value == "plotted"


def test_dragon_kami_egg_casts_a_hatching_creature_free_when_a_dragon_dies():
    """The proof printing for the cast-from-among-counters reader: a creature
    spell, hatching counters, a dies trigger ("or a Dragon you control")."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Dragon-Kami Reborn"],
            battlefield=["Spinerock Tyrant"],
            exile=["Craw Wurm", "Lightning Bolt"],
            library=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm, bolt = sorted(
        (c for c in scenario.game.exile if c.name in ("Craw Wurm", "Lightning Bolt")),
        key=lambda c: c.name,
    )
    wurm.add_counters("hatching", 1)
    bolt.add_counters("hatching", 1)
    saga = scenario.find("The Dragon-Kami Reborn", Zone.HAND, "alice")
    egg = scenario.game.put_onto_battlefield(saga, "alice", transformed=True)
    assert egg.name == "Dragon-Kami's Egg"
    scenario.game.destroy(scenario.creature("Spinerock Tyrant", "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert wurm.zone is Zone.BATTLEFIELD
    assert bolt.zone is Zone.EXILE, "only a creature spell may be cast this way"
