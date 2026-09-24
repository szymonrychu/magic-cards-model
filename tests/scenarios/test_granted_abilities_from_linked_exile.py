"""Activated abilities granted from a linked exile pile, and mana spent as
though it were any color to activate them.

Agatha's Soul Cauldron (oracle text in `data/printings`):

    You may spend mana as though it were mana of any color to activate
    abilities of creatures you control.
    Creatures you control with +1/+1 counters on them have all activated
    abilities of all creature cards exiled with Agatha's Soul Cauldron.
    {T}: Exile target card from a graveyard. When a creature card is exiled
    this way, put a +1/+1 counter on target creature you control.

Proof printings (not listed cards, not in any deck):

- Patchwork Crawler - "{2}{U}: Exile target creature card from your graveyard
  and put a +1/+1 counter on this creature. / This creature has all activated
  abilities of all creature cards exiled with it." - the same grant, subject
  "this creature", pile "exiled with it".
- Drana and Linvala - "Activated abilities of creatures your opponents control
  can't be activated. / Drana and Linvala has all activated abilities of all
  creatures your opponents control. You may spend mana as though it were mana
  of any color to activate those abilities." - the grant read off the
  battlefield rather than an exile pile, and the any-color permission scoped
  to "those abilities".

Rules, looked up with `mise run rules:find`:

- **CR 607.2a** - an ability that exiles cards and one that refers to cards
  "exiled with [this object]" are linked; the second sees only the first's
  pile.
- **CR 613.1f** - layer 6: ability-adding effects.
- **CR 400.7** - an object that changes zones is a new object; a Cauldron that
  leaves and returns has no pile.
- **CR 609.4b** - spending mana "as though it were mana of any [type or
  color]" "affects only how the player may pay a cost. It doesn't change that
  cost, and it doesn't change what mana was actually spent".
- **CR 602.5a** - a granted `{T}` ability still waits out summoning sickness.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

CAULDRON = "Agatha's Soul Cauldron"
CRAWLER = "Patchwork Crawler"
DRANA = "Drana and Linvala"
DRUID = "Devoted Druid"
ROOTWALLA = "Basking Rootwalla"
DRUID_TAP = "{T}: Add {G}."


def board(
    alice: list[str],
    *,
    alice_graveyard: list[str] | None = None,
    bob: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, graveyard=alice_graveyard or [], library=["Plains"] * 8)
        .player("bob", battlefield=bob or [], graveyard=bob_graveyard or [], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def cauldron_exiles(scenario: PlayedScenario, name: str, owner: str, counter_on=None) -> None:
    """Tap the Cauldron to exile `name` from `owner`'s graveyard; the reflexive
    trigger (if a creature card went) puts its counter on `counter_on`."""
    cauldron = scenario.find(CAULDRON, Zone.BATTLEFIELD, "alice")
    target = scenario.find(name, Zone.GRAVEYARD, owner)
    if counter_on is not None:
        scenario.will_choose_targets(counter_on, source=CAULDRON)
    scenario.activate(cauldron, targets=[target])
    while scenario.stack_names():
        scenario.pass_until_resolved()
    assert target.zone is Zone.EXILE


def ability_texts(scenario: PlayedScenario, permanent) -> list[str]:
    return [ability.raw for ability in scenario.game.activated_abilities(permanent)]


# -- the grant (CR 607.2a, CR 613.1f) ---------------------------------------


def test_a_creature_with_a_counter_gains_the_exiled_creatures_abilities():
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert DRUID_TAP in ability_texts(scenario, bears)

    index = ability_texts(scenario, bears).index(DRUID_TAP)
    scenario.activate(bears, index=index)
    assert bears.tapped
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 1


def test_the_granted_non_mana_ability_resolves_on_its_new_host():
    """Devoted Druid's "Put a -1/-1 counter on this creature: Untap this
    creature." - "this creature" is the Bears now."""
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)
    texts = ability_texts(scenario, bears)
    scenario.activate(bears, index=texts.index(DRUID_TAP))

    scenario.activate(
        bears, index=texts.index("Put a -1/-1 counter on this creature: Untap this creature.")
    )
    scenario.pass_until_resolved()

    assert not bears.tapped
    # CR 704.5q: the -1/-1 counter and the +1/+1 counter annihilate, and with
    # no +1/+1 counter left the Bears is outside the Cauldron's subject again.
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert DRUID_TAP not in ability_texts(scenario, bears)


def test_legal_actions_offer_the_granted_ability():
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)

    kinds = {
        action.kind
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == bears.id
    }
    assert ActionKind.ACTIVATE_MANA in kinds


def test_a_creature_without_a_counter_does_not_gain_them():
    scenario = board([CAULDRON, "Grizzly Bears", "Ornithopter"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)

    thopter = scenario.creature("Ornithopter")
    assert DRUID_TAP not in ability_texts(scenario, thopter)


def test_an_opponents_creature_with_a_counter_does_not_gain_them():
    """ "Creatures **you** control" - the Cauldron's controller's."""
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID], bob=["Grizzly Bears"])
    cauldron_exiles(
        scenario, DRUID, "alice", counter_on=scenario.creature("Grizzly Bears", "alice")
    )
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters(Counter.PLUS_ONE, 1)

    assert DRUID_TAP not in ability_texts(scenario, theirs)


def test_a_noncreature_card_in_the_pile_grants_nothing():
    """ "all creature cards exiled with" - a Mind Stone exiled with the
    Cauldron is in the pile and is not a creature card."""
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=["Mind Stone"])
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 1)
    cauldron_exiles(scenario, "Mind Stone", "alice")

    assert "{1}, {T}, Sacrifice this artifact: Draw a card." not in ability_texts(scenario, bears)
    assert len(ability_texts(scenario, bears)) == 0


def test_a_card_exiled_some_other_way_is_not_in_the_pile():
    """CR 607.2a: only the Cauldron's own exile ability fills its pile."""
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 1)
    druid = scenario.find(DRUID, Zone.GRAVEYARD, "alice")
    scenario.game.exile_cards([druid])

    assert DRUID_TAP not in ability_texts(scenario, bears)


def test_the_grant_ends_when_the_cauldron_leaves_and_a_new_cauldron_has_no_pile():
    """CR 604.2 and CR 400.7."""
    scenario = board([CAULDRON, "Grizzly Bears"], alice_graveyard=[DRUID])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)
    cauldron = scenario.find(CAULDRON, Zone.BATTLEFIELD, "alice")

    scenario.game.return_to_hand(cauldron)
    assert DRUID_TAP not in ability_texts(scenario, bears)

    scenario.put_onto_battlefield(CAULDRON, "alice")
    assert DRUID_TAP not in ability_texts(scenario, bears)


def test_a_granted_tap_ability_on_a_fresh_creature_waits_out_summoning_sickness():
    """CR 602.5a: the Bears arrived this turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[CAULDRON, "Forest", "Forest"],
            hand=["Grizzly Bears"],
            graveyard=[DRUID],
            library=["Plains"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    cauldron_exiles(scenario, DRUID, "alice", counter_on=bears)

    index = ability_texts(scenario, bears).index(DRUID_TAP)
    refusal = scenario.why_cannot_activate(bears, index)
    assert refusal is not None and "most recent turn began" in refusal


# -- spending mana as though any color (CR 609.4b) --------------------------


def test_a_creatures_green_cost_is_paid_with_white_mana():
    scenario = board([CAULDRON, ROOTWALLA, "Plains", "Plains"])
    rootwalla = scenario.creature(ROOTWALLA)
    plains = scenario.untapped_sources("Plains", "Plains")

    scenario.activate(rootwalla, *plains)
    scenario.pass_until_resolved()

    assert scenario.game.power_of(rootwalla) == 3


def test_legal_actions_report_the_white_paid_activation_affordable():
    scenario = board([CAULDRON, ROOTWALLA, "Plains", "Plains"])
    rootwalla = scenario.creature(ROOTWALLA)

    (action,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == rootwalla.id and action.kind is ActionKind.ACTIVATE
    ]
    assert action.affordable is Affordability.YES


def test_colorless_mana_pays_a_colored_cost_too():
    """Sol Ring's `{C}{C}` pays `{1}{G}`: colorless mana is mana, and it is spent
    as though it were green."""
    scenario = board([CAULDRON, ROOTWALLA, "Sol Ring"])
    rootwalla = scenario.creature(ROOTWALLA)

    scenario.activate(rootwalla, scenario.creature("Sol Ring"))
    scenario.pass_until_resolved()

    assert scenario.game.power_of(rootwalla) == 3


def test_without_the_cauldron_white_mana_does_not_pay_green():
    scenario = board([ROOTWALLA, "Plains", "Plains"])
    rootwalla = scenario.creature(ROOTWALLA)

    with pytest.raises(ValueError):
        scenario.activate(rootwalla, *scenario.untapped_sources("Plains", "Plains"))


def test_an_opponents_cauldron_does_not_help():
    scenario = board([ROOTWALLA, "Plains", "Plains"], bob=[CAULDRON])
    rootwalla = scenario.creature(ROOTWALLA)

    with pytest.raises(ValueError):
        scenario.activate(rootwalla, *scenario.untapped_sources("Plains", "Plains"))


def test_a_noncreature_ability_is_not_covered():
    """ "abilities of creatures you control": an artifact's colored activation
    cost still wants its color - Aether Spellbomb's `{U}, Sacrifice`."""
    scenario = board([CAULDRON, "Aether Spellbomb", "Plains"], bob=["Grizzly Bears"])
    spellbomb = scenario.creature("Aether Spellbomb")
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.activate(spellbomb, *scenario.untapped_sources("Plains"), targets=[bears])


def test_the_cost_itself_is_unchanged():
    """CR 609.4b: the white mana is what was spent - no green left the pool
    because none was there, and the cost still reads `{1}{G}`."""
    scenario = board([CAULDRON, ROOTWALLA, "Plains", "Plains"])
    rootwalla = scenario.creature(ROOTWALLA)
    total = scenario.game.activation_cost(rootwalla, 0, "alice")

    assert str(total.mana) == "{1}{G}"


def test_a_granted_ability_is_paid_with_any_color():
    """The two halves together: Rootwalla exiled with the Cauldron, its
    `{1}{G}` pump granted to the Bears, paid with two Plains."""
    scenario = board([CAULDRON, "Grizzly Bears", "Plains", "Plains"], alice_graveyard=[ROOTWALLA])
    bears = scenario.creature("Grizzly Bears")
    cauldron_exiles(scenario, ROOTWALLA, "alice", counter_on=bears)
    texts = ability_texts(scenario, bears)
    pump = next(i for i, text in enumerate(texts) if text.startswith("{1}{G}:"))

    scenario.activate(bears, *scenario.untapped_sources("Plains", "Plains"), index=pump)
    scenario.pass_until_resolved()

    assert scenario.game.power_of(bears) == 2 + 1 + 2


# -- proof: Patchwork Crawler ("this creature ... exiled with it") ----------


def test_patchwork_crawler_gains_the_abilities_of_what_it_exiled():
    scenario = board([CRAWLER, "Island", "Island", "Island"], alice_graveyard=[DRUID])
    crawler = scenario.creature(CRAWLER)
    druid = scenario.find(DRUID, Zone.GRAVEYARD, "alice")
    assert DRUID_TAP not in ability_texts(scenario, crawler)

    scenario.activate(
        crawler, *scenario.untapped_sources("Island", "Island", "Island"), targets=[druid]
    )
    scenario.pass_until_resolved()

    assert druid.zone is Zone.EXILE
    assert DRUID_TAP in ability_texts(scenario, crawler)
    scenario.activate(crawler, index=ability_texts(scenario, crawler).index(DRUID_TAP))
    assert crawler.tapped


# -- proof: Drana and Linvala (battlefield grant, "those abilities") --------


def test_drana_and_linvala_has_opponents_creatures_abilities_and_they_do_not():
    scenario = board([DRANA], bob=["Llanowar Elves"])
    drana = scenario.creature(DRANA)
    elves = scenario.creature("Llanowar Elves", "bob")

    assert scenario.why_cannot_activate(elves, username="bob") is not None
    assert DRUID_TAP in ability_texts(scenario, drana)
    scenario.activate(drana, index=ability_texts(scenario, drana).index(DRUID_TAP))
    assert drana.tapped


def test_drana_pays_a_granted_green_cost_with_white_mana():
    scenario = board([DRANA, "Plains", "Plains"], bob=[ROOTWALLA])
    drana = scenario.creature(DRANA)
    texts = ability_texts(scenario, drana)
    pump = next(i for i, text in enumerate(texts) if text.startswith("{1}{G}:"))

    scenario.activate(drana, *scenario.untapped_sources("Plains", "Plains"), index=pump)
    scenario.pass_until_resolved()

    assert scenario.game.power_of(drana) == 3 + 2


def test_drana_the_permission_is_only_for_those_abilities():
    """alice's own Rootwalla's `{1}{G}` is not one of "those abilities"."""
    scenario = board([DRANA, ROOTWALLA, "Plains", "Plains"])
    rootwalla = scenario.creature(ROOTWALLA)

    with pytest.raises(ValueError):
        scenario.activate(rootwalla, *scenario.untapped_sources("Plains", "Plains"))


def test_every_clause_is_handled():
    for name in (CAULDRON, CRAWLER, DRANA):
        for clause in card_support(card(name)).clauses:
            assert clause.outcome == "handled", (name, clause.text, clause.outcome)
