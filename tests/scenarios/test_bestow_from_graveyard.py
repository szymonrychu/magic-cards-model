"""Bestow's own CR 604.6 permission: "You may cast this card from your
graveyard using its bestow ability." (Detective's Phoenix).

Read whole in this session with `mise run rules:find`:

- **CR 604.6** - "Some static abilities apply while a card is in any zone
  that you could cast or play it from (usually your hand). These are limited
  to those that read, 'You may [cast/play] [this card] . . . ,' ..." -
  Detective's Phoenix's own sentence, opening the graveyard the same way for
  its own bestow ability that CR 604.6 describes.
- **CR 702.103a** - "Bestow represents a static ability that functions in
  any zone from which you could play the card it's on." Once CR 604.6 opens
  the graveyard, CR 702.103a's own "any zone" already reaches it - the
  permission and the ability are two separate sentences on the card, and
  `machines/casting._printed_zone_permissions` is what joins them generically
  (copying bestow's own hand-cast option onto the graveyard with the same
  cost and rule), not a case built for this card by name.
- **CR 702.103b** - "As a spell cast bestowed is put onto the stack, it
  becomes an Aura enchantment and gains enchant creature."
- **CR 702.103f** - "If a bestowed Aura becomes unattached, it ceases to be
  bestowed. If a bestowed Aura is attached to an illegal object or player,
  it becomes unattached and ceases to be bestowed. This is an exception to
  rule 704.5m."

This is distinct from S26's "cast from graveyard, with exile" template
(escape, jump-start and the like moving the card to exile as part of the
cast) - bestow's own graveyard permission never touches exile at all; the
Phoenix, once resolved, is either an Aura attached to a creature on the
battlefield or, per CR 702.103f, a creature there in its own right.

Two real engine gaps surfaced while proving this and are fixed alongside it,
both in the resolution path every bestow spell shares, not anything specific
to the graveyard permission:

- `Game._put_on_stack` re-states the zone of a spell already on the stack
  (CR 601.2a already put it there at announcement) - `CardState.move_to`
  read that re-statement as an ordinary zone change and cleared `bestowed`
  before CR 601.2f's cost was even paid, so no bestowed spell could ever
  resolve as the Aura CR 702.103b promises, hardcast or from the graveyard
  alike. Fixed in `move_to` by excluding a move to the zone a card is
  already in.
- `machines/keywords.why_cannot_enchant` only ever read a card's own printed
  "Enchant [x]" line, never CR 702.103b's own dynamic grant - so CR 704.5m's
  state-based sweep read a freshly bestowed, legally attached Aura as having
  "no enchant ability" and put it in the graveyard the instant it entered.
  `aura_state_based_actions` had the same gap for CR 702.103f's own
  exception, sending a bestowed Aura whose host died to the graveyard by the
  ordinary CR 704.5m route instead of leaving it on the battlefield as the
  creature it reverts to.

Hopeful Eidolon (Theros, Modern and Pioneer legal, off pool, not one of this
task's required cards) is the second printing that proves both fixes
generalise: a hardcast bestow (no graveyard permission of its own) with a
plainer cost ({3}{W}, no `Collect evidence`) and a different pump.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario

PHOENIX = "Detective's Phoenix"
EIDOLON = "Hopeful Eidolon"


# -- the permission itself (CR 604.6) ----------------------------------------


def test_bestow_hands_out_a_hand_option_and_a_graveyard_option():
    options = [o for o in keyword_cast_options(card(PHOENIX)) if o.keyword == "Bestow"]
    zones = {o.zone for o in options}
    assert zones == {Zone.HAND, Zone.GRAVEYARD}
    for option in options:
        assert option.cost is not None
        assert option.cost.mana == ManaCost.parse("{R}")


def test_a_card_with_no_such_sentence_gets_no_graveyard_option():
    """Hopeful Eidolon prints bestow but never "you may cast this card from
    your graveyard" - CR 604.6 opens no extra zone without its own sentence,
    so only the ordinary hand option exists."""
    options = [o for o in keyword_cast_options(card(EIDOLON)) if o.keyword == "Bestow"]
    assert [o.zone for o in options] == [Zone.HAND]


def test_detectives_phoenix_from_the_graveyard_always_goes_through_the_bestow_option():
    """CR 601.3's permission question ("is there any rule or effect that
    lets this be cast from here") is per-zone, not per-announcement: the one
    option `_printed_zone_permissions` hands out for the graveyard is
    bestow's own, so it is the only thing `why_cannot_cast_from` can ever be
    answering yes about for this card in this zone - proven by reading the
    option back rather than by a hardcast this permission was never written
    to offer (`test_a_card_with_no_such_sentence_gets_no_graveyard_option`
    above is the negative half: a card with no such sentence gets no
    graveyard option at all)."""
    from magic_cards_model.machines.casting import why_cannot_cast_from

    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=[PHOENIX, "Elder Gargaroth", "Sol Ring"],
            battlefield=["Mountain"] * 3,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phoenix = scenario.find(PHOENIX, Zone.GRAVEYARD, "alice")

    assert why_cannot_cast_from(phoenix, "alice", Zone.GRAVEYARD, scenario.game) is None
    (option,) = [
        o
        for o in keyword_cast_options(phoenix.card)
        if o.keyword == "Bestow" and o.zone is Zone.GRAVEYARD
    ]
    assert not option.pays_mana_cost


# -- casting Detective's Phoenix bestowed, from the graveyard ----------------


def test_cast_bestowed_from_the_graveyard_attaches_and_pumps_the_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=[PHOENIX, "Elder Gargaroth", "Sol Ring"],
            battlefield=["Mountain"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    alice = scenario.player("alice")

    casting = scenario.cast(PHOENIX, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Bestow")
    casting.choose_targets([bears])
    assert casting.total_cost.mana == ManaCost.parse("{R}")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    phoenix = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert phoenix.zone is Zone.BATTLEFIELD
    assert phoenix.bestowed is True
    assert phoenix.attached_to == bears.id
    assert alice.graveyard == []
    exiled_mvs = sorted(state.mana_value for state in scenario.game.exile)
    assert sum(exiled_mvs) >= 6
    assert scenario.game.characteristics_of(bears).power == 4
    assert scenario.game.characteristics_of(bears).toughness == 4
    assert has_keyword(bears, Keyword.FLYING, scenario.game)
    assert has_keyword(bears, Keyword.HASTE, scenario.game)


def test_the_graveyard_bestow_cost_is_refused_without_enough_mana_value():
    """CR 701.59b: a graveyard that cannot reach the Collect evidence 6
    threshold cannot pay it, so the cast (and with it, the permission this
    file is about) never gets off the ground."""
    scenario = (
        Scenario()
        .player("alice", graveyard=[PHOENIX, "Sol Ring"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast(PHOENIX, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Bestow")
    casting.choose_targets([bears])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))


# -- hardcast bestow, and CR 702.103f's own exception to CR 704.5m ----------


def test_hopeful_eidolon_hardcast_bestowed_attaches_and_pumps():
    """The plainer of the two proofs: a hand-cast, non-X, non-graveyard
    bestow, showing the same resolution path Detective's Phoenix's own
    graveyard cast goes through works independent of the zone it was cast
    from."""
    scenario = (
        Scenario()
        .player("alice", hand=[EIDOLON], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast(EIDOLON)
    casting.use_keyword("Bestow")
    casting.choose_targets([bears])
    assert casting.total_cost.mana == ManaCost.parse("{3}{W}")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    eidolon = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert eidolon.zone is Zone.BATTLEFIELD
    assert eidolon.bestowed is True
    assert eidolon.attached_to == bears.id
    assert scenario.game.characteristics_of(bears).power == 3
    assert scenario.game.characteristics_of(bears).toughness == 3
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game)


def test_hopeful_eidolon_hardcast_for_its_mana_cost_stays_a_creature():
    scenario = Scenario().player("alice", hand=[EIDOLON], battlefield=["Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(EIDOLON)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    eidolon = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert eidolon.zone is Zone.BATTLEFIELD
    assert eidolon.bestowed is False
    assert scenario.game.characteristics_of(eidolon).is_creature


def test_the_enchanted_creature_dying_reverts_the_bestowed_aura_to_a_creature():
    """CR 702.103f, both sentences: the Phoenix does not go to the graveyard
    for its Aura being illegally attached (CR 704.5m's own ordinary rule) -
    it becomes unattached, ceases to be bestowed, and stays on the
    battlefield as the 2/2 flying, haste creature it prints."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=[PHOENIX, "Elder Gargaroth", "Sol Ring"],
            battlefield=["Mountain"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast(PHOENIX, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Bestow")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    phoenix = scenario.put_on_stack(casting)
    scenario.resolve_top()

    scenario.game.destroy(bears)
    scenario.game.check_state_based_actions()

    assert phoenix.zone is Zone.BATTLEFIELD
    assert phoenix.bestowed is False
    assert phoenix.attached_to is None
    phoenix_chars = scenario.game.characteristics_of(phoenix)
    assert phoenix_chars.is_creature
    assert (phoenix_chars.power, phoenix_chars.toughness) == (2, 2)
    assert has_keyword(phoenix, Keyword.FLYING, scenario.game)
    assert has_keyword(phoenix, Keyword.HASTE, scenario.game)
