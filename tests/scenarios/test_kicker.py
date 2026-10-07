"""Kicker: an optional additional cost announced while casting (CR 702.33).

CR 702.33a: "Kicker is a static ability that functions while the spell with
kicker is on the stack. 'Kicker [cost]' means "You may pay an additional [cost]
as you cast this spell.""

CR 118.8a makes it an *additional* cost, which is the difference from evoke: the
printed mana cost is still paid on top of it, not replaced by it.

CR 702.33d: "If a spell's controller declares the intention to pay any of that
spell's kicker costs, that spell has been 'kicked.'" That flag is the whole
reason kicker needs recording at all - CR 702.33e and CR 607.2i link it to the
card's other ability, "If this spell was kicked, it deals 4 damage instead."

CR 702.33c's multikicker may be paid any number of times; plain kicker may not,
and refusing a second payment is the corner case here.

What a kicked spell *does* differently is read at resolution off
`Game.cast_record(spell).kicked` (`_parse_damage_target_kicked_instead_clause`
in `machines/effects.py`), covered below by
`test_an_unkicked_burst_lightning_deals_its_base_damage` and
`test_a_kicked_burst_lightning_deals_the_kicked_amount_instead` - Burst
Lightning used to have no `EFFECTS` row at all and resolved doing nothing,
kicked or not, until its own two-sentence shape ("<Name> deals 2 damage to any
target. If this spell was kicked, it deals 4 damage instead.") got a reader.
Burst Lightning's own printed "Kicker {4} (...)" *line* used to poison the
clause split of the sentence after it too (the same bug flashback's own line
caused; `_strip_keyword_ability_lines` fixes both) - both are exercised end to end here.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import optional_additional_costs
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.cards import pool
from tests.scenarios.harness import Scenario, mana_from


def board(lands: int = 5) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Burst Lightning"], battlefield=["Mountain"] * lands)
        .player("bob")
    )


def cast_it(scenario, *, kicked: bool):
    casting = scenario.cast("Burst Lightning")
    if kicked:
        casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    needed = 5 if kicked else 1
    for source in scenario.untapped_sources(*["Mountain"] * needed):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return casting


def test_an_unkicked_spell_costs_only_its_mana_cost():
    """The cost is optional: not paying it is the default."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    assert str(casting.total_cost.mana) == "{R}"
    assert casting.kicked == 0


def test_paying_the_kicker_adds_it_to_the_total_cost():
    """CR 118.8a: additional, so {R} becomes {4}{R} rather than {4}."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    assert str(casting.total_cost.mana) == "{4}{R}"


def test_a_kicked_spell_records_that_it_was_kicked():
    """CR 702.33d: the flag CR 702.33e's linked ability reads."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = cast_it(scenario, kicked=True)
    spell = scenario.put_on_stack(casting)

    assert casting.kicked == 1
    assert spell.zone is Zone.STACK
    assert all(source.tapped for source in scenario.game.battlefield)


def test_an_unkicked_spell_leaves_the_extra_lands_untapped():
    """The other side of the same board: one Mountain pays for it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_it(scenario, kicked=False)
    tapped = [source for source in scenario.game.battlefield if source.tapped]
    assert len(tapped) == 1


def test_the_kicker_cannot_be_paid_without_the_mana():
    """CR 118.3: the total cost is one cost, and it is paid in full or not at all."""
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))

    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_plain_kicker_cannot_be_paid_twice():
    """CR 702.33c: paying more than once is multikicker's rule, not kicker's."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    with pytest.raises(ValueError, match="plain kicker"):
        casting.pay_kicker()


def test_a_card_without_kicker_refuses_the_announcement():
    """Kicker is printed or it is not: there is no default kicker cost."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="no kicker ability"):
        casting.pay_kicker()


def test_rewinding_a_kicked_casting_returns_the_mana_sources():
    """CR 733.1: the whole announcement is reversed, kicker included."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = cast_it(scenario, kicked=True)
    casting.cancel()

    assert all(source.untapped for source in scenario.game.battlefield)
    assert scenario.find("Burst Lightning", Zone.HAND, "alice").zone is Zone.HAND


def test_an_unkicked_burst_lightning_deals_its_base_damage():
    """ "Burst Lightning deals 2 damage to any target." (CR 119.3), unkicked."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    casting = cast_it(scenario, kicked=False)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob.life == 18


def test_a_kicked_burst_lightning_deals_the_kicked_amount_instead():
    """ "If this spell was kicked, it deals 4 damage instead." - not 2 plus 4."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    casting = cast_it(scenario, kicked=True)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob.life == 16


# -- the option has to reach a seat, not only a caller driving `Casting` ------
#
# CR 601.2b: "If the spell has alternative or additional costs that will be
# paid as it's being cast such as buyback or kicker costs (see rules 118.8 and
# 118.9), the player announces their intentions to pay any or all of those
# costs". CR 118.8b: "Some additional costs are optional." An announcement a
# seat is never told about cannot be made, so the two surfaces this library
# owes its consumers - `legal_actions` (what may I do) and `Game.cast` (do it,
# atomically) - are where kicker was actually missing: every test above drives
# `Casting` by hand, which no seat does.


def _lands(scenario, username: str = "alice"):
    return scenario.game.permanents_controlled_by(username)


def _tapped(scenario, username: str = "alice") -> int:
    return len([source for source in _lands(scenario, username) if source.tapped])


def _cast_action(scenario, name: str, username: str = "alice"):
    actions = [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST
        and action.card_id == scenario.find(name, Zone.HAND, username).id
    ]
    assert len(actions) == 1, actions
    return actions[0]


def test_a_kickers_cost_is_offered_on_the_cast_action():
    """The reported bug: Sowing Mycospawn cast with kicker, and the seat was
    never presented with the option to pay it (CR 601.2b, CR 702.33a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sowing Mycospawn"], battlefield=["Wastes"] * 8)
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Sowing Mycospawn")

    assert [(option.keyword, option.cost) for option in action.additional_cost_options] == [
        ("kicker", "{1}{C}")
    ]
    assert action.additional_cost_options[0].rule == "CR 702.33a"
    assert action.additional_cost_options[0].repeatable is False


def test_the_atomic_cast_can_pay_the_kicker():
    """CR 702.33d: `Game.cast` is the whole CR 601.2 sequence as one action,
    so the kicker announcement has to be sayable there or a seat can want it
    and still not get it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sowing Mycospawn"], battlefield=["Forest"] + ["Wastes"] * 5)
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spawn = scenario.find("Sowing Mycospawn", Zone.HAND, "alice")

    spell = scenario.game.cast(spawn, "alice", kicker=1, mana_sources=_lands(scenario))

    assert spell.zone is Zone.STACK
    assert scenario.game.cast_record(spell).kicked == 1
    # CR 118.8a: additional, so the kicker's {1}{C} is charged on top of the
    # printed {3}{G} - six sources, not four.
    assert _tapped(scenario) == 6


def test_an_unkicked_atomic_cast_is_still_the_default():
    """CR 118.8b: optional. Saying nothing pays nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sowing Mycospawn"], battlefield=["Forest"] + ["Wastes"] * 5)
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spawn = scenario.find("Sowing Mycospawn", Zone.HAND, "alice")

    spell = scenario.game.cast(spawn, "alice", mana_sources=_lands(scenario))

    assert scenario.game.cast_record(spell).kicked == 0
    assert _tapped(scenario) == 4


# -- generality: the fix is CR 601.2b's mechanic, not the word "Kicker" -------


def test_multikicker_is_offered_as_a_repeatable_option():
    """Everflowing Chalice, neither the reported card nor in its deck:
    CR 702.33c's multikicker is a different keyword, a different cost shape
    ({2} generic against Sowing Mycospawn's {1}{C}), on an artifact with no
    targets and a printed mana cost of {0} - and it may be paid any number of
    times."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Everflowing Chalice"], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Everflowing Chalice")

    assert [(option.keyword, option.cost) for option in action.additional_cost_options] == [
        ("multikicker", "{2}")
    ]
    assert action.additional_cost_options[0].repeatable is True
    assert action.additional_cost_options[0].rule == "CR 702.33c"


def test_multikicker_can_be_paid_more_than_once_through_the_atomic_cast():
    """CR 702.33c/702.33d: "it may be kicked multiple times"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Everflowing Chalice"], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.HAND, "alice")

    spell = scenario.game.cast(chalice, "alice", kicker=2, mana_sources=_lands(scenario))

    assert scenario.game.cast_record(spell).kicked == 2
    assert _tapped(scenario) == 4


def test_a_second_kicker_payment_is_refused_for_plain_kicker_through_the_atomic_cast():
    """CR 702.33a against CR 702.33c: plain kicker is paid once or not at all,
    and the atomic cast refuses rather than charging twice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sowing Mycospawn"], battlefield=["Forest"] + ["Wastes"] * 8)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spawn = scenario.find("Sowing Mycospawn", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="plain kicker"):
        scenario.game.cast(spawn, "alice", kicker=2, mana_sources=_lands(scenario))

    assert spawn.zone is Zone.HAND
    assert all(source.untapped for source in _lands(scenario))


def test_a_replicate_cost_is_offered_the_same_way():
    """CR 702.56a is CR 601.2b's same optional additional cost with another
    keyword on it, so it rides the same enumeration rather than a second
    one - Gigadrowse, a third card and a third cost shape ({U})."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Gigadrowse"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Gigadrowse")

    assert [(option.keyword, option.cost) for option in action.additional_cost_options] == [
        ("replicate", "{U}")
    ]
    assert action.additional_cost_options[0].repeatable is True


def test_a_card_with_no_optional_additional_cost_offers_none():
    """The other side of it: nothing invented where nothing is printed."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cast_action(scenario, "Lightning Bolt").additional_cost_options == ()


def test_an_optional_exile_from_hand_cost_is_enumerated_as_understood():
    """CR 118.8b's optional additional cost is not always a keyword: March of
    Otherworldly Light prints "As an additional cost to cast this spell, you
    may exile any number of white cards from your hand". `Casting.
    exile_for_cost_reduction` charges it (and applies the linked "{2} less for
    each card exiled this way"), so the row is enumerated under its own
    announcement name, understood (R0b-T4; before that it was the loud
    `understood=False` fail-closed row)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["March of Otherworldly Light"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (option,) = _cast_action(scenario, "March of Otherworldly Light").additional_cost_options

    assert option.keyword == "exile any number"
    assert option.cost == "you may exile any number of white cards from your hand"
    assert option.understood is True


#: Every optional additional cost the pool prints that `Casting` has no way to
#: charge, by card name. A printing added later that opens a new unreadable
#: shape fails the sweep below rather than quietly failing closed in a game,
#: and one the enumerator has since learned to charge fails it too rather than
#: outliving its reason.
KNOWN_UNCHARGEABLE_OPTIONAL_COSTS: set[str] = set()


def test_every_optional_additional_cost_in_the_pool_is_enumerated():
    """The mechanic, swept rather than named: every printing in the pool
    carrying one of CR 601.2b's optional additional costs is enumerated by
    `optional_additional_costs`, with the keyword's own CR rule and CR
    702.33c/702.56a's "any number of times" read off the keyword rather than
    guessed - and the set nothing can charge is exactly the known one, in
    both directions."""
    enumerated: dict[str, list] = {}
    for name, card in pool().items():
        options = optional_additional_costs(card)
        if options:
            enumerated[name] = options

    # Every printing whose Scryfall keywords name one of the family is read.
    by_keyword = {
        name: {keyword.lower() for keyword in card.keywords}
        & {
            "kicker",
            "multikicker",
            "replicate",
            "offspring",
            "gift",
            "bargain",
            "casualty",
            "conspire",
        }
        for name, card in pool().items()
    }
    for name, keywords in by_keyword.items():
        if not keywords:
            continue
        assert name in enumerated, f"{name} prints {keywords} and was not enumerated"
        assert {option.keyword for option in enumerated[name]} >= keywords

    assert {
        name
        for name, options in enumerated.items()
        if any(not option.understood for option in options)
    } == KNOWN_UNCHARGEABLE_OPTIONAL_COSTS

    rules = {
        (option.keyword, option.rule, option.repeatable)
        for options in enumerated.values()
        for option in options
    }
    assert rules == {
        ("kicker", "CR 702.33a", False),
        ("multikicker", "CR 702.33c", True),
        ("replicate", "CR 702.56a", True),
        ("offspring", "CR 702.175a", False),
        ("gift", "CR 702.174a", False),
        ("blight", "CR 701.68a", False),
        # CR 702.166a's bargain, and the two "you may ..." sentences Casting
        # charges: CR 701.59a's collect evidence and a reveal (CR 701.20a).
        ("bargain", "CR 702.166a", False),
        # CR 702.153a's casualty (Join the Maestros).
        ("casualty", "CR 702.153a", False),
        # CR 702.78a's conspire (Burn Trail).
        ("conspire", "CR 702.78a", False),
        ("collect evidence", "CR 701.59a", False),
        ("reveal", "CR 701.20a", False),
        # Celestial Reunion's "you may choose a creature type and behold two
        # creatures of that type" (CR 701.4a, `behold_chosen_type_for_cost`).
        ("behold", "CR 701.4a", False),
        # March of Wretched Sorrow's "you may exile any number of black cards from
        # your hand" (`Casting.exile_for_cost_reduction`, R0b-T4).
        ("exile any number", "CR 118.8b", False),
        # Rottenmouth Viper's "you may sacrifice any number of nonland
        # permanents" (CR 118.8b's optional additional cost, R0a-T4).
        ("sacrifice any number", "CR 118.8b", False),
        # Redirect Lightning's "pay 5 life or pay {2}": which half is paid is
        # CR 601.2b's announcement (`life_or_mana_additional_costs`).
        ("pay life", "CR 601.2b", False),
        # Ruinous Waterbending's and Spirit Water Revival's "you may waterbend
        # {N}" (CR 701.67a, `Casting.pay_waterbend`).
        ("waterbend", "CR 701.67a", False),
    }
