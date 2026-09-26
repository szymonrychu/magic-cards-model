"""Scenario: hand discard/draw spells (Secrets of Strixhaven, T8).

Four shapes:

- Mind Roots: "Target player discards two cards. Put up to one land card
  discarded this way onto the battlefield tapped under your control." CR
  607.1 anaphora over the exact cards that discard moved, landing under the
  *caster's* control (CR 110.2a), never the discarding player's.
- Borrowed Knowledge: "Choose one - Discard your hand, then draw cards equal
  to the number of cards in target opponent's hand. / Discard your hand,
  then draw cards equal to the number of cards discarded this way." One new
  reader (a target's hand size) and one pre-existing one (`counted_this_
  way`), proved independently.
- Steal the Show: "Choose one or both - Target player discards any number of
  cards, then draws that many cards. / Steal the Show deals damage equal to
  the number of instant and sorcery cards in your graveyard to target
  creature or planeswalker." The second mode needs `count_expression`'s
  widened "`<A>` and `<B>` cards in your graveyard" reader, proved again
  independently on Cosmic Epiphany - a different, non-modal card whose
  whole text is that exact count applied to a plain draw instead of a
  targeted damage effect.
- Recurring Insight: "Draw cards equal to the number of cards in target
  opponent's hand." (plus Rebound) - the second proof of the target's-hand
  count reader Borrowed Knowledge's own first mode also needs, standing on
  its own rather than tucked inside a mode.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 701.9a/701.9b** - discarding moves a card to the graveyard, and by
  default the discarding player chooses which.
- **CR 608.2b** - a target gone by resolution is skipped, not substituted.
- **CR 110.2a** - a permanent an effect puts onto the battlefield with
  nobody else named enters under that effect's own controller's control.
- **CR 607.1** - two abilities where one refers to what the other did are
  linked, and the second reads only what the first actually produced.
- **CR 700.2/700.2a** - a modal spell's modes are chosen as it is put on the
  stack, in the printed order, each run independently on resolution.
- **CR 121.1/121.2** - drawing a card, one at a time.
- **CR 402.1** - the hand is where a player holds drawn cards.
- **CR 120.3e/704.5g** - lethal damage on a creature is a state-based action.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- Mind Roots -----------------------------------------------------------


def test_mind_roots_puts_a_discarded_land_onto_the_battlefield_under_casters_control():
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Roots"], battlefield=["Swamp", "Forest", "Swamp"])
        .player("bob", hand=["Island", "Mountain", "Plains"])
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    island, mountain, _plains = bob.hand
    sources = scenario.untapped_sources("Swamp", "Forest", "Swamp")
    scenario.will_discard(island, mountain, username="bob")
    scenario.will_choose_cards(island, username="alice")
    scenario.cast_and_resolve("Mind Roots", *sources, targets=["bob"])
    assert [card.name for card in bob.hand] == ["Plains"]
    assert [card.name for card in bob.graveyard] == ["Mountain"]
    island_permanent = next(state for state in scenario.game.battlefield if state.id == island.id)
    assert island_permanent.controller == "alice"
    assert island_permanent.tapped


def test_mind_roots_declining_the_land_leaves_it_in_the_graveyard():
    """ "Up to one" - zero is a legal choice (CR 608.2d)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Roots"], battlefield=["Swamp", "Forest", "Swamp"])
        .player("bob", hand=["Island", "Mountain", "Plains"])
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    island, mountain, _plains = bob.hand
    sources = scenario.untapped_sources("Swamp", "Forest", "Swamp")
    scenario.will_discard(island, mountain, username="bob")
    scenario.will_choose_cards(username="alice")  # decline: put none onto the battlefield
    scenario.cast_and_resolve("Mind Roots", *sources, targets=["bob"])
    assert sorted(card.name for card in bob.graveyard) == ["Island", "Mountain"]
    assert not any(state.id == island.id for state in scenario.game.battlefield)


def test_mind_roots_with_no_land_discarded_has_nothing_to_put_onto_the_battlefield():
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Roots"], battlefield=["Swamp", "Forest", "Swamp"])
        .player("bob", hand=["Lightning Bolt", "Opt", "Shock"])
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    bolt, opt, _shock = bob.hand
    sources = scenario.untapped_sources("Swamp", "Forest", "Swamp")
    before = len(scenario.game.battlefield)
    scenario.will_discard(bolt, opt, username="bob")
    scenario.cast_and_resolve("Mind Roots", *sources, targets=["bob"])
    assert sorted(card.name for card in bob.graveyard) == ["Lightning Bolt", "Opt"]
    # Nothing discarded is a land, so nothing new reaches the battlefield -
    # the count is unchanged from before the cast.
    assert len(scenario.game.battlefield) == before


# -- Borrowed Knowledge -----------------------------------------------------


def test_borrowed_knowledge_mode_one_draws_equal_to_target_opponents_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Borrowed Knowledge", "Lightning Bolt", "Opt"],
            battlefield=["Mountain", "Plains", "Swamp", "Island"],
            library=["Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", hand=["Island", "Mountain"])
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Swamp", "Island")
    casting = scenario.cast("Borrowed Knowledge", username="alice")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert [card.name for card in alice.hand] == ["Forest", "Forest"]
    assert sorted(card.name for card in alice.graveyard) == [
        "Borrowed Knowledge",
        "Lightning Bolt",
        "Opt",
    ]


def test_borrowed_knowledge_mode_two_draws_equal_to_cards_discarded_this_way():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Borrowed Knowledge", "Lightning Bolt", "Opt"],
            battlefield=["Mountain", "Plains", "Swamp", "Island"],
            library=["Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Swamp", "Island")
    casting = scenario.cast("Borrowed Knowledge", username="alice")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert [card.name for card in alice.hand] == ["Forest", "Forest"]


def test_borrowed_knowledge_mode_two_with_an_empty_hand_draws_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Borrowed Knowledge"],
            battlefield=["Mountain", "Plains", "Swamp", "Island"],
            library=["Forest", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Swamp", "Island")
    casting = scenario.cast("Borrowed Knowledge", username="alice")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert alice.hand == []
    assert len(alice.library) == 2


# -- Recurring Insight (proof: a second printing of "the number of cards in
# target opponent's hand", standing alone rather than inside a mode) --------


def test_recurring_insight_proves_the_target_hand_count_reader_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Recurring Insight"],
            battlefield=["Island"] * 4 + ["Swamp"] * 3,
            library=["Forest"] * 4,
        )
        .player("bob", hand=["Mountain", "Plains", "Forest"])
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Swamp"] * 3))
    scenario.cast_and_resolve("Recurring Insight", *sources, targets=["bob"])
    assert [card.name for card in alice.hand] == ["Forest", "Forest", "Forest"]


# -- Steal the Show ---------------------------------------------------------


def test_steal_the_show_mode_one_discards_and_draws_that_many():
    scenario = (
        Scenario()
        .player("alice", hand=["Steal the Show"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", hand=["Island", "Mountain", "Plains"], library=["Forest"] * 3)
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Steal the Show", username="alice")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_discard(*bob.hand, username="bob")
    scenario.resolve_top()
    assert sorted(card.name for card in bob.hand) == ["Forest", "Forest", "Forest"]
    assert sorted(card.name for card in bob.graveyard) == ["Island", "Mountain", "Plains"]


def test_steal_the_show_mode_one_may_discard_zero():
    """ "Any number of cards" - CR 107.1c includes zero, a real answer."""
    scenario = (
        Scenario()
        .player("alice", hand=["Steal the Show"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", hand=["Island", "Mountain", "Plains"], library=["Forest"] * 3)
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Steal the Show", username="alice")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(username="bob")  # decline: discard none
    scenario.resolve_top()
    assert sorted(card.name for card in bob.hand) == ["Island", "Mountain", "Plains"]
    assert bob.graveyard == []


def test_steal_the_show_mode_two_damage_equals_instant_and_sorcery_in_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Steal the Show"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            graveyard=["Lightning Bolt", "Opt"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Steal the Show", username="alice")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD, "2 instant/sorcery cards is 2 damage, lethal to a 2/2"


def test_steal_the_show_choosing_both_modes_runs_each_in_printed_order():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Steal the Show"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            graveyard=["Lightning Bolt", "Opt"],
        )
        .player(
            "bob",
            hand=["Island", "Mountain"],
            battlefield=["Grizzly Bears"],
            library=["Forest"] * 2,
        )
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Steal the Show", username="alice")
    casting.choose_modes([1, 2])
    casting.choose_targets(["bob", bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_discard(*bob.hand, username="bob")
    scenario.resolve_top()
    scenario.state_based_actions()
    assert sorted(card.name for card in bob.hand) == ["Forest", "Forest"]
    assert bears.zone is Zone.GRAVEYARD


# -- Cosmic Epiphany (proof: a second, non-modal printing of
# `count_expression`'s widened "instant and sorcery cards in your graveyard") -


def test_cosmic_epiphany_proves_the_type_list_count_reader():
    """Cosmic Epiphany: "Draw cards equal to the number of instant and
    sorcery cards in your graveyard." - a different, non-modal card sharing
    only the widened `count_expression` reader (`_COUNT_CARDS_IN_YOUR_
    GRAVEYARD_RE`'s "`<A>` and `<B>` cards" branch), through the plain
    "draw cards equal to `<expr>`" path rather than Steal the Show's own
    damage-to-a-target one - proving the reader itself, not one card's
    printed sentence around it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cosmic Epiphany"],
            battlefield=["Island"] * 4 + ["Mountain"] * 2,
            graveyard=["Lightning Bolt", "Opt", "Divination"],
            library=["Forest"] * 3,
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Mountain"] * 2))
    scenario.cast_and_resolve("Cosmic Epiphany", *sources)
    assert sorted(card.name for card in alice.hand) == ["Forest", "Forest", "Forest"]
