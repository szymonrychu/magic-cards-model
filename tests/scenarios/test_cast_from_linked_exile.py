"""Scenario: "you may cast `<spell>` from among cards [you own] exiled with
this `<object>`" - a resolution-time cast out of a permanent's own linked
pile (CR 607.2a, CR 608.2g).

Boiling Rock Rioter: "Tap an untapped Ally you control: Exile target card
from a graveyard.\nWhenever this creature attacks, you may cast an Ally spell
from among cards you own exiled with this creature." The trigger grants only
the timing - the Ally's mana cost is paid as for any cast (CR 601.2f-h).

Kaho, Minamo Historian (the second printing, Modern-legal and outside the
deck pool): "When Kaho enters, search your library for up to three instant
cards, exile them, then shuffle.\n{X}, {T}: You may cast a spell with mana
value X from among cards exiled with Kaho without paying its mana cost." -
the same reader with a mana-value bound instead of a subtype, and the free
branch instead of the paid one; the name is read as "this permanent".

- CR 607.2a: only cards the object's own exile ability exiled - a second
  Rioter's pile is its own.
- CR 108.3: "you own" - an Ally from the opponent's graveyard is in the pile
  but is not castable by this trigger.
- CR 608.2d: the "may" is offered only when a legal choice exists.
- CR 118.3 / CR 601.2h: an unpayable cost makes the cast illegal; the card
  stays in exile.
- CR 107.3a: Kaho's X is the value announced as the ability was activated.

CR numbers verified with `mise run rules:find` this session: 607.2a, 608.2g,
601.2f, 601.2h, 108.3, 608.2d, 118.3, 107.3a, 701.23b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState

from .harness import PlayedScenario, Scenario


def _rioters(*, graveyard: list[str], bob_graveyard: list[str] | None = None, swamps: int = 3):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Boiling Rock Rioter", "Boiling Rock Rioter", *["Swamp"] * swamps],
            graveyard=graveyard,
            library=["Swamp"] * 5,
        )
        .player("bob", graveyard=bob_graveyard or [], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.permanents_controlled_by("alice"):
        permanent.summoning_sick = False
    return scenario


def _exile_with(
    scenario: PlayedScenario, rioter: CardState, tapping: CardState, card: CardState
) -> None:
    """Rioter's own "Tap an untapped Ally you control: Exile target card from
    a graveyard." - the tapped Ally pays the cost, `rioter` is the object the
    card is exiled with (CR 607.2a)."""
    scenario.activate(rioter, index=0, tapping_for_cost=[tapping], targets=[card])
    scenario.pass_until_resolved()
    assert card.zone is Zone.EXILE


def _attack_with(scenario: PlayedScenario, rioter: CardState) -> None:
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    assert scenario.step is Step.DECLARE_ATTACKERS
    scenario.attack_with(rioter)
    scenario.game.put_triggers_on_stack()


def _resolve_stack(scenario: PlayedScenario) -> None:
    for _ in range(10):
        if not scenario.game.stack:
            return
        scenario.pass_until_resolved()


def test_the_attack_trigger_casts_the_linked_ally_paying_its_cost():
    scenario = _rioters(graveyard=["Boiling Rock Rioter"])
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    exiled = scenario.find("Boiling Rock Rioter", Zone.GRAVEYARD, "alice")
    _exile_with(scenario, attacker, helper, exiled)

    scenario.will_take_the_may(True, source="Boiling Rock Rioter")
    scenario.will_choose_cards(exiled, username="alice", source="Boiling Rock Rioter")
    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    assert exiled.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(exiled).username == "alice"
    swamps = [s for s in scenario.game.permanents_controlled_by("alice") if s.name == "Swamp"]
    assert sum(1 for swamp in swamps if swamp.tapped) >= 2, "CR 601.2h: {2}{B} was paid"


def test_a_non_ally_card_in_the_pile_is_not_offered():
    scenario = _rioters(graveyard=["Grizzly Bears"])
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    _exile_with(scenario, attacker, helper, bears)

    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    offered = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Boiling Rock Rioter"
    ]
    assert offered and not offered[-1].affirmative_is_legal, "CR 608.2d"
    assert bears.zone is Zone.EXILE


def test_an_ally_owned_by_the_opponent_is_not_offered():
    """ "Cards **you own**" (CR 108.3): bob's Rioter is in the pile, exiled
    from bob's graveyard, but alice may not cast it this way."""
    scenario = _rioters(graveyard=[], bob_graveyard=["Boiling Rock Rioter"])
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    theirs = scenario.find("Boiling Rock Rioter", Zone.GRAVEYARD, "bob")
    _exile_with(scenario, attacker, helper, theirs)

    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    offered = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Boiling Rock Rioter"
    ]
    assert offered and not offered[-1].affirmative_is_legal
    assert theirs.zone is Zone.EXILE


def test_an_ally_exiled_with_the_other_rioter_is_not_offered():
    """CR 607.2a: the helper Rioter's pile is not the attacker's."""
    scenario = _rioters(graveyard=["Boiling Rock Rioter"])
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    exiled = scenario.find("Boiling Rock Rioter", Zone.GRAVEYARD, "alice")
    # The helper's own ability, paid by tapping the helper itself, so the
    # attacker stays untapped to attack.
    _exile_with(scenario, helper, helper, exiled)

    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    offered = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Boiling Rock Rioter"
    ]
    assert offered and not offered[-1].affirmative_is_legal
    assert exiled.zone is Zone.EXILE


def test_an_unpayable_cast_leaves_the_card_in_exile():
    """CR 118.3, CR 601.2h: with no mana to pay {2}{B} the cast is illegal
    and the game returns to before it was proposed - the Ally stays in
    exile (firebending's {R} alone cannot pay it)."""
    scenario = _rioters(graveyard=["Boiling Rock Rioter"], swamps=0)
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    exiled = scenario.find("Boiling Rock Rioter", Zone.GRAVEYARD, "alice")
    _exile_with(scenario, attacker, helper, exiled)

    scenario.will_take_the_may(True, source="Boiling Rock Rioter")
    scenario.will_choose_cards(exiled, username="alice", source="Boiling Rock Rioter")
    scenario.will_pay_the_mana_cost(False, username="alice")
    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    assert exiled.zone is Zone.EXILE
    assert exiled.face_up


def test_declining_leaves_the_card_in_exile():
    scenario = _rioters(graveyard=["Boiling Rock Rioter"])
    attacker, helper = scenario.creatures(
        "Boiling Rock Rioter", "Boiling Rock Rioter", username="alice"
    )
    exiled = scenario.find("Boiling Rock Rioter", Zone.GRAVEYARD, "alice")
    _exile_with(scenario, attacker, helper, exiled)

    scenario.will_take_the_may(False, source="Boiling Rock Rioter", times=None)
    _attack_with(scenario, attacker)
    _resolve_stack(scenario)

    assert exiled.zone is Zone.EXILE


# -- the second printing: Kaho, Minamo Historian ------------------------------


def _kaho(instants: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kaho, Minamo Historian"],
            battlefield=["Island"] * 4,
            library=[*instants, *["Island"] * 5],
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_and_exile(scenario: PlayedScenario, *chosen: str) -> tuple[CardState, list[CardState]]:
    cards = [scenario.find(name, Zone.LIBRARY, "alice") for name in chosen]
    scenario.will_choose_cards(*cards, username="alice")
    kaho = scenario.put_onto_battlefield("Kaho, Minamo Historian", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    kaho.summoning_sick = False
    return kaho, cards


def test_kaho_exiles_up_to_three_instants_with_itself():
    scenario = _kaho(["Mana Leak", "Counterspell", "Lightning Bolt"])
    kaho, cards = _enter_and_exile(scenario, "Mana Leak", "Lightning Bolt")

    for card in cards:
        assert card.zone is Zone.EXILE
        assert card.exile_annotation is not None
        assert card.exile_annotation.linked_permanent_id == kaho.id
    assert scenario.find("Counterspell", Zone.LIBRARY, "alice").zone is Zone.LIBRARY


def test_kaho_casts_the_instant_with_mana_value_x_for_free():
    scenario = _kaho(["Mana Leak", "Lightning Bolt"])
    kaho, (leak, bolt) = _enter_and_exile(scenario, "Mana Leak", "Lightning Bolt")

    scenario.will_take_the_may(True, source="Kaho, Minamo Historian")
    scenario.will_choose_cards(bolt, username="alice", source="Kaho, Minamo Historian")
    scenario.will_choose_targets("bob", username="alice")
    islands = scenario.untapped_sources("Island", username="alice")
    scenario.activate(kaho, *islands, index=0, x_value=1)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.STACK
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 17
    assert leak.zone is Zone.EXILE, "mana value 2 was never offered for X=1"


def test_kaho_offers_nothing_when_no_exiled_card_has_mana_value_x():
    scenario = _kaho(["Mana Leak", "Lightning Bolt"])
    kaho, (leak, bolt) = _enter_and_exile(scenario, "Mana Leak", "Lightning Bolt")

    islands = scenario.untapped_sources(*["Island"] * 3, username="alice")
    scenario.activate(kaho, *islands, index=0, x_value=3)
    scenario.pass_until_resolved()

    offered = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Kaho, Minamo Historian"
    ]
    assert offered and not offered[-1].affirmative_is_legal
    assert leak.zone is Zone.EXILE and bolt.zone is Zone.EXILE
