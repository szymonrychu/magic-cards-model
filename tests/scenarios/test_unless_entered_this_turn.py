"""A discard waived by a condition: "discard a card unless `<condition>`" - and
the conditions the pool prints with it, "this creature entered this turn" and
"you attacked this turn".

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]." Moon-Circuit Hacker's discard happens only once the draw was
  chosen.
- **CR 118.12a** - "[Do something] unless [a player does something else]"
  means the same as the player may do the something else and, if they
  don't, the first thing happens; here the "something else" is a fact about
  the game, read as the ability resolves.
- **CR 702.49a** - ninjutsu puts the card onto the battlefield, so it entered
  this turn.
- **CR 608.2h** - information about the ability's own source is read from the
  object as it last existed if it has left the battlefield.
- **CR 508.1** - declaring attackers is how a player attacks.

Moon-Circuit Hacker is the reported card. The proof printings are Kaito
Shizuki's `+1` ("Draw a card. Then discard a card unless you attacked this
turn.") - the same "discard ... unless" reader over a different condition -
and Gathering Place's "{T}: Add {G} or {W}. Activate only if this land
entered this turn or if you control a basic land." - the same "this
`<permanent>` entered this turn" condition gating an activation instead, one
half of an "or if" pair. Kaito is Pioneer and Modern legal, Gathering Place
Standard legal; neither is in an api deck.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import ninjutsu_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def hacker_board(*, hacker_on_battlefield: bool):
    battlefield = ["Grizzly Bears", "Island"]
    hand = ["Lightning Bolt"]
    if hacker_on_battlefield:
        battlefield.append("Moon-Circuit Hacker")
    else:
        hand.append("Moon-Circuit Hacker")
    return (
        Scenario()
        .player("alice", hand=hand, battlefield=battlefield, library=["Plains", "Swamp"])
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def ninjutsu_in(scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    hacker = scenario.find("Moon-Circuit Hacker", Zone.HAND, "alice")
    activation = ninjutsu_activation(scenario.game, hacker, bears, "alice")
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return hacker


def hit_with_staged_hacker(scenario):
    hacker = scenario.creature("Moon-Circuit Hacker", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(hacker, defending="bob")
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    return hacker


def test_a_ninjutsud_hacker_draws_and_does_not_discard():
    scenario = hacker_board(hacker_on_battlefield=False)
    ninjutsu_in(scenario)
    scenario.will_take_the_may(True, source="Moon-Circuit Hacker")

    scenario.combat_damage()
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert sorted(s.name for s in alice.hand) == ["Grizzly Bears", "Lightning Bolt", "Plains"]
    assert alice.graveyard == []


def test_a_hacker_that_entered_on_an_earlier_turn_draws_then_discards():
    scenario = hacker_board(hacker_on_battlefield=True)
    hit_with_staged_hacker(scenario)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Moon-Circuit Hacker")
    scenario.will_discard(bolt)

    scenario.combat_damage()
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert [s.name for s in alice.hand] == ["Plains"]


def test_declining_the_draw_skips_the_discard_too():
    scenario = hacker_board(hacker_on_battlefield=True)
    hit_with_staged_hacker(scenario)
    scenario.will_take_the_may(False, source="Moon-Circuit Hacker")

    scenario.combat_damage()
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert [s.name for s in alice.hand] == ["Lightning Bolt"]
    assert alice.graveyard == []


def test_the_discard_may_be_the_card_just_drawn():
    scenario = hacker_board(hacker_on_battlefield=True)
    hit_with_staged_hacker(scenario)
    scenario.will_take_the_may(True, source="Moon-Circuit Hacker")
    plains = scenario.player("alice").library[0]
    scenario.will_discard(plains)

    scenario.combat_damage()
    resolve_all(scenario)

    alice = scenario.player("alice")
    assert plains.zone is Zone.GRAVEYARD
    assert [s.name for s in alice.hand] == ["Lightning Bolt"]


def test_a_ninjutsud_hacker_bounced_before_its_trigger_resolves_still_skips_the_discard():
    """CR 608.2h: the source's last known information still says it entered
    this turn."""
    scenario = hacker_board(hacker_on_battlefield=False)
    hacker = ninjutsu_in(scenario)
    scenario.will_take_the_may(True, source="Moon-Circuit Hacker")
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(hacker)

    while scenario.game.stack:
        scenario.resolve_top()

    alice = scenario.player("alice")
    assert alice.graveyard == []
    assert "Plains" in [s.name for s in alice.hand]


# -- proof printing: Kaito Shizuki's +1 ---------------------------------------


def kaito_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Kaito Shizuki", "Grizzly Bears"],
            library=["Plains", "Swamp"],
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    return scenario


def kaito_plus_one(scenario) -> None:
    kaito = scenario.find("Kaito Shizuki", Zone.BATTLEFIELD, "alice")
    scenario.activate(kaito, index=0)
    scenario.resolve_top()


def test_kaito_discards_when_you_have_not_attacked():
    scenario = kaito_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_discard(bolt)

    kaito_plus_one(scenario)

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert [s.name for s in alice.hand] == ["Plains"]


def test_kaito_keeps_the_card_after_you_attacked():
    scenario = kaito_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.start_at(Step.POSTCOMBAT_MAIN)

    kaito_plus_one(scenario)

    alice = scenario.player("alice")
    assert sorted(s.name for s in alice.hand) == ["Lightning Bolt", "Plains"]
    assert alice.graveyard == []


def test_an_opponents_attack_is_not_your_attack():
    """ "You attacked" is the controller's own declaration (CR 508.1): bob's
    attack on his turn does not waive alice's discard on hers."""
    scenario = kaito_board()
    scenario.game.record_turn_fact("attacked", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_discard(bolt)

    kaito_plus_one(scenario)

    assert bolt.zone is Zone.GRAVEYARD


# -- proof printing: Gathering Place ------------------------------------------


def gathering_place_board(*, in_hand: bool, basics: list[str] | None = None):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Gathering Place"] if in_hand else [],
            battlefield=([] if in_hand else ["Gathering Place"]) + (basics or []),
        )
        .player("bob")
        .build()
    )


def test_gathering_place_taps_for_color_the_turn_it_entered():
    scenario = gathering_place_board(in_hand=True)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Gathering Place")
    place = scenario.find("Gathering Place", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(place, index=1) is None


def test_gathering_place_on_a_later_turn_needs_a_basic_land():
    scenario = gathering_place_board(in_hand=False)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    place = scenario.find("Gathering Place", Zone.BATTLEFIELD, "alice")

    reason = scenario.why_cannot_activate(place, index=1)

    assert reason is not None
    assert "not met" in reason


def test_gathering_place_on_a_later_turn_with_a_basic_land_taps_for_color():
    """ "... or if you control a basic land": either half is enough."""
    scenario = gathering_place_board(in_hand=False, basics=["Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    place = scenario.find("Gathering Place", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(place, index=1) is None


def test_gathering_place_colorless_ability_is_never_restricted():
    scenario = gathering_place_board(in_hand=False)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    place = scenario.find("Gathering Place", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(place, index=0) is None
