"""Number sweep G0b: the "that many" count channel.

One mechanism carries a count from where it happened to the words that point
back at it:

- **a clause's count** - an earlier instruction of the same resolving spell
  or ability records how many objects it actually moved (discarded,
  sacrificed, exiled), and a later "that many" reads it (CR 608.2c: the
  instructions are followed in the order written, and later text may refer
  back to earlier text);
- **a trigger event's count** - a trigger's own "that many"/"that much" reads
  the amount its trigger event carried (CR 603.2c: one event, however many
  occurrences it contains);
- **a cost's count** - an activated ability's "`<verb>` this way" reads how
  many objects its cost moved (CR 602.2b: the cost is paid as it is
  activated, before the ability exists).

A reflexive ability (CR 603.12) reads the count its creating ability moved,
fixed when it is created, so its own target announcement (CR 603.3d) knows
how many "up to that many" allows.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file:

- **CR 107.3f** - an X that appears only in an ability's text is chosen by
  its controller as it resolves.
- **CR 107.1c** - "any number" is any positive number or zero.
- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]."
- **CR 121.2** - "If a player is instructed to draw multiple cards, that
  player performs that many individual card draws."
- **CR 601.2c / 603.3d** - targets are announced as the ability goes on the
  stack.
- **CR 602.2b** - activating an ability follows the casting process,
  costs included.
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs."
- **CR 603.12** - reflexive triggered abilities.
- **CR 608.2c** - instructions in the order written.
- **CR 701.9a** - discard; **CR 701.21a** - sacrifice; **CR 701.23d** -
  searching for a quantity.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.effects import activated_effect_for
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from tests.cards import card
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# -- a clause's count: discard, then draw that many ---------------------------


def _jaya_board(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Jaya Ballard"],
            library=["Forest", "Island", "Swamp", "Plains", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_jaya_ballard_draws_as_many_as_she_actually_discarded():
    """Jaya Ballard's +1: "Discard up to three cards, then draw that many
    cards." Two discarded is two drawn - not three, the printed ceiling."""
    scenario = _jaya_board(["Grizzly Bears", "Lightning Bolt", "Craw Wurm"])
    alice = scenario.player("alice")
    jaya = scenario.find("Jaya Ballard", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.will_choose_cards(bears, bolt, username="alice")
    scenario.activate(jaya, index=1)
    _resolve_stack(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 3, "Craw Wurm kept, two drawn"
    assert len(alice.library) == 3
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_jaya_ballard_discarding_nothing_draws_nothing():
    """CR 107.1c: "up to three" includes zero, and zero discarded is zero
    drawn."""
    scenario = _jaya_board(["Grizzly Bears"])
    alice = scenario.player("alice")
    jaya = scenario.find("Jaya Ballard", Zone.BATTLEFIELD, "alice")

    scenario.will_choose_cards(username="alice")
    scenario.activate(jaya, index=1)
    _resolve_stack(scenario)

    assert [c.name for c in alice.hand] == ["Grizzly Bears"]
    assert len(alice.library) == 5


def test_cavalier_of_flame_discards_any_number_then_draws_that_many():
    """Cavalier of Flame's enters trigger: "discard any number of cards, then
    draw that many cards." A different quantity word ("any number of") and a
    triggered rather than a loyalty ability, through the same channel."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cavalier of Flame", "Grizzly Bears", "Lightning Bolt", "Craw Wurm"],
            library=["Forest", "Island", "Swamp", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    discarded = [
        scenario.find(name, Zone.HAND, "alice")
        for name in ("Grizzly Bears", "Lightning Bolt", "Craw Wurm")
    ]

    scenario.put_onto_battlefield("Cavalier of Flame", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(*discarded, username="alice")
    _resolve_stack(scenario)

    assert all(state.zone is Zone.GRAVEYARD for state in discarded)
    assert len(alice.hand) == 3
    assert len(alice.library) == 1


def test_a_short_library_draws_as_many_as_it_can():
    """CR 121.2: "that many individual card draws" - with one card left, the
    first draw succeeds and the second is a draw from an empty library, which
    is the state-based loss's business, not a smaller count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt"],
            battlefield=["Jaya Ballard"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    jaya = scenario.find("Jaya Ballard", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(*alice.hand, username="alice")
    scenario.activate(jaya, index=1)
    _resolve_stack(scenario)

    assert [c.name for c in alice.hand] == ["Forest"]
    assert alice.library == []


# -- "you may ... If you do, draw that many" ---------------------------------


def _fable_at_chapter_two(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Fable of the Mirror-Breaker"],
            library=["Forest", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)  # chapter I's Goblin Shaman token
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    return scenario


def test_fable_ii_draws_as_many_as_were_discarded():
    """Fable of the Mirror-Breaker II: "You may discard up to two cards. If
    you do, draw that many cards." One discarded is one drawn."""
    scenario = _fable_at_chapter_two(["Grizzly Bears", "Lightning Bolt"])
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.will_take_the_may(True, source="Fable of the Mirror-Breaker")
    scenario.will_choose_cards(bears, username="alice")
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert sorted(c.name for c in alice.hand) == ["Forest", "Lightning Bolt"]
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_sephiroth_one_winged_angel_draws_one_card_per_creature_sacrificed():
    """Sephiroth, One-Winged Angel's attack trigger: "you may sacrifice any
    number of other creatures. If you do, draw that many cards." The count is
    the sacrifice's, read by the same "draw that many" the discard shapes
    use."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sephiroth, Fabled SOLDIER"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Memnite"],
            library=["Forest", "Island", "Swamp", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sephiroth = scenario.put_onto_battlefield("Sephiroth, Fabled SOLDIER", "alice")
    scenario.will_take_the_may(False, source="Sephiroth, Fabled SOLDIER")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    sephiroth.transform()
    sephiroth.summoning_sick = False
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sephiroth)
    scenario.will_take_the_may(True, source="Sephiroth, One-Winged Angel")
    scenario.will_choose_cards(*bears, username="alice")
    attack_trigger = next(
        item for item in scenario.game.stack if "sacrifice any number" in item.ability.text
    )
    scenario.game.stack.remove(attack_trigger)
    scenario.game.stack.append(attack_trigger)
    scenario.resolve_top()

    assert all(bear.zone is Zone.GRAVEYARD for bear in bears)
    assert scenario.creature("Memnite", "alice").zone is Zone.BATTLEFIELD
    assert len(alice.hand) == 2


# -- a clause's count carried to another player: Settle the Wreckage ----------


def test_settle_the_wreckage_gives_one_basic_per_exiled_attacker():
    """Settle the Wreckage: "Exile all attacking creatures target player
    controls. That player may search their library for that many basic land
    cards, put those cards onto the battlefield tapped, then shuffle." Two
    attackers exiled is two basics, for the attacking player."""
    scenario = (
        Scenario()
        .player("alice", hand=["Settle the Wreckage"], battlefield=["Plains"] * 4)
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Grizzly Bears", "Memnite"],
            library=["Forest", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()
    while scenario.game.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bob = scenario.player("bob")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    memnite = scenario.creature("Memnite", "bob")
    for bear in bears:
        bear.summoning_sick = False
    scenario.attack_with(*bears)

    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("bob")
    scenario.will_take_the_may(True, username="bob")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Settle the Wreckage", *plains, username="alice", targets=["bob"])

    assert all(bear.zone is Zone.EXILE for bear in bears)
    assert memnite.zone is Zone.BATTLEFIELD, "not attacking"
    lands = [p for p in scenario.game.permanents_controlled_by("bob") if p.card.is_land]
    assert len(lands) == 2
    assert all(land.tapped for land in lands)
    assert len(bob.library) == 1


# -- a trigger event's count ---------------------------------------------------


def _earth_king_board(attackers: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Earth King", *attackers],
            library=["Forest", "Mountain", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_the_earth_king_searches_for_one_land_per_qualifying_attacker():
    """The Earth King: "Whenever one or more creatures you control with power
    4 or greater attack, search your library for up to that many basic land
    cards, put them onto the battlefield tapped, then shuffle." Two Craw
    Wurms and a Grizzly Bears attacking is one trigger (CR 603.2c) counting
    two."""
    scenario = _earth_king_board(["Craw Wurm", "Craw Wurm", "Grizzly Bears"])
    wurms = scenario.creatures("Craw Wurm", "Craw Wurm", username="alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(*wurms, bears)
    assert len(scenario.game.stack) == 1, "one trigger for the whole attack"
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    lands = [p for p in scenario.game.permanents_controlled_by("alice") if p.card.is_land]
    assert len(lands) == 2
    assert all(land.tapped for land in lands)
    assert len(alice.library) == 2
    assert scenario.game.search_description_notices == []


def test_the_earth_king_does_not_trigger_without_a_qualifying_attacker():
    scenario = _earth_king_board(["Grizzly Bears"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert scenario.game.stack == []


def test_marauding_makos_that_many_reads_the_shared_trigger_event_reader():
    """Marauding Mako: "Whenever you discard one or more cards, put that many
    +1/+1 counters on this creature." Discarding through Jaya's +1 (three
    cards, one event) is three counters - the trigger's own count, not the
    clause count of the ability that caused it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt", "Craw Wurm"],
            battlefield=["Jaya Ballard", "Marauding Mako"],
            library=["Forest", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    jaya = scenario.find("Jaya Ballard", Zone.BATTLEFIELD, "alice")
    mako = scenario.creature("Marauding Mako", "alice")
    scenario.will_choose_cards(*alice.hand, username="alice")
    scenario.activate(jaya, index=1)
    _resolve_stack(scenario)

    assert mako.counters["+1/+1"] == 3
    assert len(alice.hand) == 3


def test_photon_adds_as_much_mana_as_the_combat_damage_it_dealt():
    """Photon, Mighty Marvel: "Whenever Photon deals combat damage to a
    player, add that much mana of any one color." Two damage is two mana of
    the one colour chosen."""
    scenario = (
        Scenario().player("alice", battlefield=["Photon, Mighty Marvel"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    photon = scenario.creature("Photon, Mighty Marvel", "alice")
    scenario.attack_with(photon)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.will_choose(Color.RED.value, source="Photon, Mighty Marvel")
    scenario.game.put_triggers_on_stack()
    assert scenario.player("bob").life == 18
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 2
    assert pool.total == 2


# -- a reflexive ability's count (CR 603.12) ------------------------------------


def test_swashbuckler_grants_double_strike_to_up_to_that_many_targets():
    """Swashbuckler Extraordinaire: "Whenever you attack, you may sacrifice
    one or more Treasures. When you do, up to that many target creatures gain
    double strike until end of turn." Two Treasures sacrificed, two targets
    allowed; a third is refused at announcement."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swashbuckler Extraordinaire", "Swashbuckler Extraordinaire"],
            battlefield=["Grizzly Bears", "Memnite"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Swashbuckler Extraordinaire", "alice")
    scenario.put_onto_battlefield("Swashbuckler Extraordinaire", "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    treasures = [p for p in scenario.game.battlefield if p.name == "Treasure Token"]
    assert len(treasures) == 2
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    assert len(scenario.game.stack) == 2
    scenario.will_take_the_may(True, source="Swashbuckler Extraordinaire")
    scenario.will_choose_cards(*treasures, username="alice")
    scenario.will_choose_targets(bears, memnite, source="Swashbuckler Extraordinaire")
    scenario.resolve_top()
    assert all(treasure.zone is not Zone.BATTLEFIELD for treasure in treasures)
    scenario.game.put_triggers_on_stack()
    reflexive = scenario.game.stack[-1]
    assert {target.card_id for target in reflexive.targets} == {bears.id, memnite.id}
    scenario.resolve_top()

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert has_keyword(memnite, Keyword.DOUBLE_STRIKE, scenario.game)
    assert scenario.game.reflexive_clause_notices == []


def test_campsite_cuisine_x_is_the_number_of_foods_sacrificed():
    """Campsite Cuisine: "Whenever you attack, you may sacrifice X Foods.
    When you do, up to X target attacking creatures each get +3/+3 and gain
    trample and indestructible until end of turn." CR 107.3f: X is chosen as
    the ability resolves - it is how many Foods were sacrificed - and the
    reflexive ability's X is that same number."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Campsite Cuisine", "Campsite Cuisine"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Memnite"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Campsite Cuisine", "alice")
    scenario.put_onto_battlefield("Campsite Cuisine", "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    foods = [p for p in scenario.game.battlefield if p.name == "Food Token"]
    assert len(foods) == 2
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    memnite = scenario.creature("Memnite", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*bears, memnite)
    assert len(scenario.game.stack) == 2, "one attack trigger per Campsite Cuisine"
    scenario.will_take_the_may(True, source="Campsite Cuisine")
    scenario.will_choose_cards(*foods, username="alice")
    scenario.will_choose_targets(*bears, source="Campsite Cuisine")
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    for bear in bears:
        assert scenario.game.power_of(bear) == 5
        assert has_keyword(bear, Keyword.TRAMPLE, scenario.game)
        assert is_indestructible(bear, scenario.game)
    assert scenario.game.power_of(memnite) == 1


# -- a cost's count: "this way" -------------------------------------------------


def test_corpseweft_token_is_twice_the_cards_exiled_to_pay_for_it():
    """Corpseweft: "{1}{B}, Exile one or more creature cards from your
    graveyard: Create a tapped X/X black Zombie Horror creature token, where
    X is twice the number of cards exiled this way." Two exiled is a 4/4."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=["Corpseweft", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears", "Grizzly Bears", "Craw Wurm"],
        )
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    corpseweft = scenario.find("Corpseweft", Zone.BATTLEFIELD, "alice")
    chosen = [card for card in alice.graveyard if card.name == "Grizzly Bears"]
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.activate(corpseweft, *swamps, exiling=chosen)
    _resolve_stack(scenario)

    (token,) = [p for p in scenario.game.battlefield if p.name == "Zombie Horror Token"]
    assert scenario.game.power_of(token) == 4
    assert scenario.game.toughness_of(token) == 4
    assert token.tapped


def test_radiant_lotus_adds_three_mana_per_artifact_sacrificed():
    """Radiant Lotus: "{T}, Sacrifice one or more artifacts: Choose a color.
    Target player adds three mana of the chosen color for each artifact
    sacrificed this way." Two Memnites is six."""
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"], battlefield=["Radiant Lotus", "Memnite", "Memnite"])
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lotus = scenario.find("Radiant Lotus", Zone.BATTLEFIELD, "alice")
    victims = scenario.creatures("Memnite", "Memnite", username="alice")
    scenario.will_choose(Color.GREEN.value, source="Radiant Lotus")
    scenario.activate(lotus, sacrificing=list(victims), targets=[scenario.player("alice")])
    _resolve_stack(scenario)

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.GREEN) == 6


def test_this_way_counts_read_off_the_ability_not_the_caller():
    """Both "this way" abilities parse off their own printed text - no
    registry row, no card name."""
    for name in ("Corpseweft", "Radiant Lotus"):
        printing = card(name)
        (ability,) = [a for a in parse_abilities(printing) if hasattr(a, "cost")]
        assert activated_effect_for(name, 0, ability.effect) is not None, name


# -- nothing to point back at: fail closed ------------------------------------


def test_that_many_with_nothing_counted_draws_nothing_and_says_so():
    """Cavalier of Flame's own "draw that many cards", run where nothing has
    been counted and no trigger event carries a number: no guessed draw, and
    an `UnmodeledTriggerEffectNotice` naming the clause."""
    from magic_cards_model.machines.effects import parse_clause_effect

    scenario = (
        Scenario()
        .player("alice", battlefield=["Cavalier of Flame"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (enters,) = [
        a for a in parse_abilities(card("Cavalier of Flame")) if "that many" in (a.effect or "")
    ]
    draw_clause = enters.effect.split(", then ")[1]
    draw = parse_clause_effect(draw_clause)
    assert draw is not None

    draw(scenario.game, alice, "Cavalier of Flame", None)

    assert alice.hand == []
    assert len(alice.library) == 2
    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert "that many" in notice.text
