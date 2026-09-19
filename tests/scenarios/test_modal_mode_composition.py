"""Scenario: a mode of a modal spell or triggered ability whose own text is a
shape `_parse_mixed_clause`/`parse_mixed_effect(_for_spell)` already reads for
an ordinary card, but that a mode never reached before this file - each gap
below is a real one-mode failure `_modal_category`'s new worst-mode rule
(`tests/test_sweep_pool.py::test_modal_category_is_worst_mode_not_best_mode`)
surfaced once it stopped hiding behind a sibling mode that did work.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` (and cross-checked with `mise run rules:find`, on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 700.2a** - "the spell's controller chooses which mode... the effect
  of only the chosen mode is applied" - why a legal mode that does nothing
  is a real defect, not a partial one.
- **CR 608.2c** - clause order within one instruction.
- **CR 118.12a** - counter-unless-pay.
- **CR 111.2/701.7a** - token creation and its controller.
- **CR 613.1f** - a keyword grant, layer 6.
- **CR 107.3f** - a card's own "where X is ..." definition, fixed once at
  resolution (CR 608.2h/611.2c).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_surgical_precision_mode_two_draws_and_gains_life():
    """ "You draw a card and gain 2 life." - `split_effect_clauses`'s bare
    "and" leaves the second clause's subject implicit ("gain 2 life"), which
    `_parse_optional_player_clause` now retries with "you " restored.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Surgical Precision"],
            battlefield=["Plains", "Plains"],
            library=["Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.game.player("alice")
    hand_before = len(alice.hand)
    life_before = alice.life

    casting = scenario.cast("Surgical Precision")
    casting.choose_modes([2])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # The card itself left the hand to be cast; the draw puts one back.
    assert len(alice.hand) == hand_before - 1 + 1
    assert alice.life == life_before + 2


def test_icy_reception_mode_one_counters_a_creature_spell_unless_paid():
    """ "Counter target creature or legendary spell unless its controller
    pays {3}." - `machines/targeting.py` already reads this compound target;
    only the counter-unless-pay clause parser needed to accept a target
    phrase other than the literal word "spell".
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Icy Reception"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_casting = scenario.cast("Grizzly Bears", username="bob")
    bob_payment = bob_casting.begin_paying()
    scenario.pay_with(bob_payment, *scenario.untapped_sources("Forest", "Forest", username="bob"))
    bears_on_stack = scenario.put_on_stack(bob_casting)
    scenario.pass_priority()

    alice_casting = scenario.cast("Icy Reception", username="alice")
    alice_casting.choose_modes([1])
    alice_casting.choose_targets([bears_on_stack])
    payment = alice_casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", username="alice"))
    scenario.put_on_stack(alice_casting)
    scenario.resolve_top()

    assert bears_on_stack.zone is Zone.GRAVEYARD


def test_fulminous_forte_mode_one_hits_only_opponents_creatures_and_planeswalkers():
    """ "Fulminous Forte deals 1 damage to each creature and planeswalker
    your opponents control." - a compound type list with a controller
    restriction, read as one whole-clause shape rather than absorbed
    unfinished into the unfiltered "each creature" reading of the fragment
    the bare-"and" split leaves behind.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fulminous Forte"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bobs_bear = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Fulminous Forte", username="alice")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert alice_bears.damage == 0
    assert bobs_bear.damage == 1


def test_stingerquill_charm_mode_three_creates_a_hasty_cadet():
    """ "Create a 2/2 colorless Wizard Soldier creature token named Cadet. It
    gains haste until end of turn." - a token-creation antecedent, whose
    referent (the token itself) does not exist until the antecedent runs,
    unlike every other object-anaphor pair's antecedent.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Stingerquill Charm"], battlefield=["Swamp", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Stingerquill Charm", username="alice")
    casting.choose_modes([3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    (cadet,) = [
        state
        for state in scenario.game.battlefield
        if state.token and state.name == "Cadet" and state.controller == "alice"
    ]
    assert (cadet.power, cadet.toughness) == (2, 2)
    assert has_keyword(cadet, Keyword.HASTE, scenario.game)


def test_fateshaper_aspirant_mode_two_counters_and_grants_two_keywords():
    """ "Put a +1/+1 counter on target creature. It gains vigilance and
    indestructible until end of turn." - a rider granting *more than one*
    keyword, which `_KEYWORD_GRANT_RE` used to read as a single (unknown,
    hyphenated) keyword name and refuse.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Fateshaper Aspirant"], battlefield=["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode(
        "Put a +1/+1 counter on target creature. It gains vigilance and indestructible "
        "until end of turn.",
        username="alice",
    )
    casting = scenario.cast("Fateshaper Aspirant", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 5))
    aspirant = scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.will_choose_targets(aspirant, username="alice")
    scenario.resolve_top()

    assert aspirant.counters[Counter.PLUS_ONE] == 1
    assert has_keyword(aspirant, Keyword.VIGILANCE, scenario.game)
    assert is_indestructible(aspirant, scenario.game)


def test_yuriko_mode_one_shrinks_by_the_graveyard_count():
    """ "Target creature gets -X/-0 until end of turn, where X is the number
    of cards in your graveyard." - an *asymmetric* X pump
    (`_parse_where_x_is_continuous_effect` used to read only a symmetric
    "X/X" template) over an unfiltered graveyard count (`count_expression`
    only read a graveyard count with a card-type qualifier in front of it).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Yuriko, Hope from the Shadows"],
            battlefield=["Island"],
            graveyard=["Lightning Bolt", "Mountain", "Opt"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_mode(
        "Target creature gets -X/-0 until end of turn, where X is the number of cards "
        "in your graveyard.",
        username="alice",
    )
    casting = scenario.cast("Yuriko, Hope from the Shadows", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.will_choose_targets(bears, username="alice")
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).power_toughness == (2 - 3, 2)
