"""Turn-history conditions about what a player did this turn (EC4 cluster
H5): spells cast (by quality, mana value, ordinal and origin), lands played,
cards discarded and drawn, permanents sacrificed, counters put, loyalty
abilities activated, cards played from exile, and crimes committed - read by
an intervening "if" (CR 603.4, rechecked on resolution by CR 608.2a) and by an
"Activate only if" restriction (CR 602.5b).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 700.13** - "A player commits a crime as that player casts a spell,
  activates an ability, or puts a triggered ability on the stack and that
  spell or ability targets at least one opponent; at least one permanent,
  spell, or ability an opponent controls; and/or at least one card in an
  opponent's graveyard."
- **CR 601.2i** - a spell becomes cast once it is on the stack with its costs
  paid; **CR 202.3** - mana value.
- **CR 701.21a** - sacrifice; **CR 701.9a** - discard; **CR 121.2** - each
  card drawn is its own draw.
- **CR 122.6** / **CR 122.6a** - counters put on a permanent, and who puts
  them.
- **CR 606.3** - loyalty abilities.
- **CR 603.4**, **CR 608.2a**, **CR 602.5b** as in the other history files.

Every clause here failed closed before `machines/conditions/history.py` read
it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import (
    ExtraTriggerEvent,
    GameEvent,
    intervening_if_answer,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_end_step(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    if scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
        scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    scenario.game.put_triggers_on_stack()


def _triggered(scenario, name: str) -> bool:
    return f"{name}'s triggered ability" in scenario.stack_names()


def _printed_triggers(printing):
    """Every triggered ability the printing's text parses to."""
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
    from magic_cards_model.machines.triggers import triggered_abilities_of

    found = [each for each in parse_abilities(printing) if isinstance(each, TriggeredAbility)]
    return found + [each for each in triggered_abilities_of(printing) if each not in found]


def _board(alice: list[str], bob: list[str] | None = None, library=None, **kwargs):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, library=library or ["Plains"] * 6, **kwargs)
        .player("bob", battlefield=bob or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _not_met(refusal: str | None) -> bool:
    return refusal is not None and "not met" in refusal


# -- "you've sacrificed an <quality> this turn" / "N or more <quality>" ---------


def test_detectives_satchel_needs_an_artifact_sacrificed():
    """Detective's Satchel: "{T}: Create a 1/1 colorless Thopter artifact
    creature token with flying. Activate only if you've sacrificed an artifact
    this turn." """
    scenario = _board(["Detective's Satchel", "Ornithopter", "Grizzly Bears"])
    satchel = scenario.find("Detective's Satchel", Zone.BATTLEFIELD, "alice")
    assert (
        scenario.why_cannot_activate(satchel, 0, "alice")
        == "Detective's Satchel's activation restriction is not met (CR 602.5b)"
    )
    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "alice"))
    assert _not_met(scenario.why_cannot_activate(satchel, 0, "alice"))

    scenario.game.sacrifice(scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice"))
    assert scenario.why_cannot_activate(satchel, 0, "alice") is None
    scenario.activate(satchel, username="alice")
    scenario.pass_until_resolved()
    assert any(state.token and "Thopter" in state.subtypes for state in scenario.game.battlefield)


def test_the_sacrifice_restriction_follows_a_control_change():
    """CR 602.5b: bob's Satchel taken by alice (Hijack) is judged by what alice
    sacrificed, not bob."""
    scenario = (
        Scenario()
        .player("alice", hand=["Hijack"], battlefield=["Mountain"] * 3 + ["Memnite"])
        .player("bob", battlefield=["Detective's Satchel", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    satchel = scenario.find("Detective's Satchel", Zone.BATTLEFIELD, "bob")
    scenario.game.sacrifice(scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob"))
    scenario.cast_and_resolve(
        "Hijack", *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=[satchel]
    )
    assert scenario.game.controller_of(satchel).username == "alice"
    assert _not_met(scenario.why_cannot_activate(satchel, 0, "alice"))

    scenario.game.sacrifice(scenario.creature("Memnite", "alice"))
    assert scenario.why_cannot_activate(satchel, 0, "alice") is None


def _with_food(*, sacrifice: bool):
    scenario = _board(["Elanor Gardner"], hand=["Gilded Goose"], library=["Forest"] * 3)
    scenario.put_onto_battlefield("Gilded Goose", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    if sacrifice:
        (food,) = [s for s in scenario.game.battlefield if "Food" in s.subtypes]
        scenario.game.sacrifice(food)
    _to_end_step(scenario)
    return scenario


def test_elanor_searches_after_you_sacrificed_a_food():
    """Elanor Gardner: "At the beginning of your end step, if you sacrificed a
    Food this turn, you may search your library for a basic land card, ..." """
    assert _triggered(_with_food(sacrifice=True), "Elanor Gardner")
    scenario = _with_food(sacrifice=False)
    assert not _triggered(scenario, "Elanor Gardner")
    assert scenario.game.intervening_if_notices == []


def _clues_sacrificed(count: int):
    scenario = _board(["Briarbridge Patrol"], hand=["Detective's Satchel", "Detective's Satchel"])
    for _ in range(2):
        scenario.put_onto_battlefield("Detective's Satchel", "alice")
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.pass_until_resolved()
    clues = [s for s in scenario.game.battlefield if "Clue" in s.subtypes]
    assert len(clues) == 4
    for clue in clues[:count]:
        scenario.game.sacrifice(clue)
    _to_end_step(scenario)
    return scenario


def test_three_or_more_clues_sacrificed():
    """Briarbridge Patrol: "At the beginning of each end step, if you
    sacrificed three or more Clues this turn, you may put a creature card from
    your hand onto the battlefield." """
    assert _triggered(_clues_sacrificed(3), "Briarbridge Patrol")
    scenario = _clues_sacrificed(2)
    assert not _triggered(scenario, "Briarbridge Patrol")
    assert scenario.game.intervening_if_notices == []


# -- discarded / drew -----------------------------------------------------------


def test_gilt_blade_prowler_needs_a_discard():
    """Gilt-Blade Prowler: "{1}, {T}, Pay 1 life: Draw a card. Activate only if
    you've discarded a card this turn." """
    scenario = _board(["Gilt-Blade Prowler", "Plains"], hand=["Island"])
    prowler = scenario.creature("Gilt-Blade Prowler", "alice")
    assert _not_met(scenario.why_cannot_activate(prowler, 0, "alice"))
    scenario.game.discard_cards("alice", [scenario.find("Island", Zone.HAND, "alice")])
    assert scenario.why_cannot_activate(prowler, 0, "alice") is None


def test_you_discarded_and_a_player_discarded():
    """Ragged Recluse: "if you discarded a card this turn"; The Raven Man: "if
    a player discarded a card this turn"."""
    scenario = _board(["Ragged Recluse // Odious Witch", "The Raven Man"], hand=["Island"])
    scenario.game.discard_cards("alice", [scenario.find("Island", Zone.HAND, "alice")])
    _to_end_step(scenario)
    assert _triggered(scenario, "Ragged Recluse")
    assert _triggered(scenario, "The Raven Man")

    scenario = (
        Scenario()
        .player("alice", battlefield=["Ragged Recluse // Odious Witch", "The Raven Man"])
        .player("bob", hand=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.discard_cards("bob", [scenario.find("Island", Zone.HAND, "bob")])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Ragged Recluse")
    assert _triggered(scenario, "The Raven Man")
    assert scenario.game.intervening_if_notices == []


def test_you_drew_two_or_more_cards():
    """Archmage Ascension: "At the beginning of each end step, if you drew two
    or more cards this turn, you may put a quest counter on this
    enchantment." """
    scenario = _board(["Archmage Ascension"])
    scenario.game.draw_cards("alice", 2)
    _to_end_step(scenario)
    assert _triggered(scenario, "Archmage Ascension")

    scenario = _board(["Archmage Ascension"])
    scenario.game.draw_cards("alice", 1)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Archmage Ascension")
    assert scenario.game.intervening_if_notices == []


# -- spells cast ----------------------------------------------------------------


def test_potioners_trove_needs_an_instant_or_sorcery_cast():
    """Potioner's Trove: "{T}: You gain 2 life. Activate only if you've cast an
    instant or sorcery spell this turn." """
    scenario = _board(["Potioner's Trove", "Mountain"], hand=["Lightning Bolt"])
    trove = scenario.find("Potioner's Trove", Zone.BATTLEFIELD, "alice")
    assert _not_met(scenario.why_cannot_activate(trove, 1, "alice"))
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.why_cannot_activate(trove, 1, "alice") is None


def test_a_creature_spell_is_not_an_instant_or_sorcery():
    """Sanar, Unfinished Genius (a second printing): "{T}: Create a Treasure
    token. Activate only if you've cast an instant or sorcery spell this
    turn." """
    scenario = _board(
        ["Sanar, Unfinished Genius // Wild Idea", "Forest", "Forest"], hand=["Grizzly Bears"]
    )
    sanar = scenario.creature("Sanar, Unfinished Genius", "alice")
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    assert _not_met(scenario.why_cannot_activate(sanar, 0, "alice"))


def test_the_second_spell_you_cast_this_turn():
    """Codespell Cleric: "When this creature enters, if it was the second spell
    you cast this turn, put a +1/+1 counter on target creature." """
    scenario = _board(["Island", "Plains", "Grizzly Bears"], hand=["Opt", "Codespell Cleric"])
    scenario.choose_trigger_targets(
        "Codespell Cleric", [scenario.creature("Grizzly Bears", "alice")]
    )
    scenario.cast_and_resolve("Opt", *scenario.untapped_sources("Island"))
    scenario.cast_and_resolve("Codespell Cleric", *scenario.untapped_sources("Plains"))
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario, "Codespell Cleric")
    scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "alice").counter_count("+1/+1") == 1


def test_the_first_spell_is_not_the_second():
    scenario = _board(["Plains", "Grizzly Bears"], hand=["Codespell Cleric"])
    scenario.cast_and_resolve("Codespell Cleric", *scenario.untapped_sources("Plains"))
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Codespell Cleric")
    assert scenario.game.intervening_if_notices == []


def test_a_spell_with_mana_value_four_or_greater():
    """Rhino, Barreling Brute: "Whenever Rhino attacks, if you've cast a spell
    with mana value 4 or greater this turn, draw a card." """
    scenario = _board(["Rhino, Barreling Brute"] + ["Plains"] * 5, hand=["Serra Angel"])
    scenario.cast_and_resolve("Serra Angel", *scenario.untapped_sources(*["Plains"] * 5))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Rhino, Barreling Brute", "alice"))
    assert _triggered(scenario, "Rhino, Barreling Brute")

    scenario = _board(["Rhino, Barreling Brute", "Island", "Island", "Island"], hand=["Divination"])
    scenario.cast_and_resolve(
        "Divination", *scenario.untapped_sources("Island", "Island", "Island")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Rhino, Barreling Brute", "alice"))
    assert not _triggered(scenario, "Rhino, Barreling Brute")
    assert scenario.game.intervening_if_notices == []


def _predatory_advantage(*, bob_casts: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Forest", "Forest"], hand=["Grizzly Bears"])
        .player("alice", battlefield=["Predatory Advantage"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if bob_casts:
        scenario.cast_and_resolve(
            "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest", username="bob")
        )
    _to_end_step(scenario)
    return scenario


def test_that_player_did_not_cast_a_creature_spell():
    """Predatory Advantage: "At the beginning of each opponent's end step, if
    that player didn't cast a creature spell this turn, create a 2/2 green
    Lizard creature token." """
    scenario = _predatory_advantage(bob_casts=False)
    assert _triggered(scenario, "Predatory Advantage")
    scenario.pass_until_resolved()  # true at both: it resolves
    assert [p for p in scenario.game.permanents_controlled_by("alice") if "Lizard" in p.subtypes]
    scenario = _predatory_advantage(bob_casts=True)
    assert not _triggered(scenario, "Predatory Advantage")
    assert scenario.game.intervening_if_notices == []


def test_predatory_advantage_does_nothing_after_a_creature_is_flashed_in_response():
    """True as it triggers, false by resolution: the opponent casts a creature
    spell with flash (CR 702.8a) in response during their own end step, so CR
    608.2a removes the trigger and no Lizard is made."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Forest", "Forest"], hand=["Ambush Viper"])
        .player("alice", battlefield=["Predatory Advantage"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert _triggered(scenario, "Predatory Advantage")
    scenario.cast_and_resolve(
        "Ambush Viper",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_until_resolved()
    assert not scenario.game.stack
    assert not [
        p for p in scenario.game.permanents_controlled_by("alice") if "Lizard" in p.subtypes
    ]


def test_a_spell_cast_from_anywhere_other_than_your_hand():
    """Spider-Man 2099: "At the beginning of your end step, if you've played a
    land or cast a spell this turn from anywhere other than your hand, ..." -
    flashback casts from the graveyard (CR 702.34a)."""
    scenario = _board(
        ["Spider-Man 2099"] + ["Mountain"] * 3,
        graveyard=["Faithless Looting"],
        hand=["Island", "Island"],
    )
    scenario.choose_trigger_targets("Spider-Man 2099", ["bob"])
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    _to_end_step(scenario)
    assert _triggered(scenario, "Spider-Man 2099")


def test_a_spell_cast_from_your_hand_does_not_count():
    scenario = _board(["Spider-Man 2099", "Mountain"], hand=["Lightning Bolt"])
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _to_end_step(scenario)
    assert not _triggered(scenario, "Spider-Man 2099")
    assert scenario.game.intervening_if_notices == []


# -- counters put ----------------------------------------------------------------


def _counters_put(scenario, permanent, kind: str, amount: int = 1) -> GameEvent:
    """Put counters through the engine and hand back the event it raised for
    them (CR 122.6) - what a "whenever counters are put" trigger is asked
    about."""
    scenario.game.add_counters(permanent, kind, amount)
    return GameEvent(
        event=ExtraTriggerEvent.COUNTERS_PUT,
        subject_id=permanent.id,
        subject_name=permanent.name,
        subject_controller=permanent.controller,
        subject_card=permanent.card,
        counter_kind=kind,
        amount=amount,
        player=permanent.controller,
    )


def _first_time_holds(scenario, card: str, event: GameEvent) -> bool | None:
    """The printing's own intervening "if", read against the real board and
    event (`machines/triggers.intervening_if_answer`) - the "one or more
    counters are put on another permanent you control" event itself is not
    matched by `machines/triggers.py` yet, so the reader is proven directly."""
    source = scenario.creature(card, "alice")
    (ability,) = [each for each in _printed_triggers(source.card) if each.intervening_if][:1]
    return intervening_if_answer(scenario.game, ability, source, event, source.zone_change_stamp)


def test_the_first_time_plus_one_counters_went_on_that_permanent():
    """Botanical Brawler: "Whenever one or more +1/+1 counters are put on
    another permanent you control, if it's the first time +1/+1 counters have
    been put on that permanent this turn, put a +1/+1 counter on this
    creature." """
    scenario = _board(["Botanical Brawler", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    first = _counters_put(scenario, bears, "+1/+1")
    assert _first_time_holds(scenario, "Botanical Brawler", first) is True

    second = _counters_put(scenario, bears, "+1/+1", 2)
    assert _first_time_holds(scenario, "Botanical Brawler", second) is False


def test_the_first_time_still_holds_as_it_resolves():
    """CR 608.2a rechecks the clause on resolution - about the counters that
    triggered it, which were still the first ones even when more have been put
    since."""
    scenario = _board(["Botanical Brawler", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    first = _counters_put(scenario, bears, "+1/+1")
    _counters_put(scenario, bears, "+1/+1", 2)
    assert _first_time_holds(scenario, "Botanical Brawler", first) is True


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def test_botanical_brawler_triggers_on_another_permanents_first_counters():
    """The trigger itself (CR 122.6's counters put on an object, CR 603.2):
    the first +1/+1 counters on another permanent you control trigger it and
    it resolves, a second batch on that permanent the same turn never
    triggers (CR 603.4)."""
    scenario = _board(["Botanical Brawler", "Grizzly Bears"])
    brawler = scenario.creature("Botanical Brawler", "alice")
    # The staged 0/0 gets the two counters it enters with; counters on the
    # Brawler itself are not "another permanent".
    scenario.game.add_counters(brawler, "+1/+1", 2, putter="alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    before = brawler.counter_count("+1/+1")

    scenario.game.add_counters(bears, "+1/+1", 1, putter="alice")
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario, "Botanical Brawler")
    _resolve_all(scenario)
    brawler = scenario.creature("Botanical Brawler", "alice")
    assert brawler.counter_count("+1/+1") == before + 1

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "+1/+1", 1, putter="alice")
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Botanical Brawler")
    assert scenario.game.intervening_if_notices == []


def test_botanical_brawler_ignores_itself_and_an_opponents_permanent():
    """ "another permanent you control": not the Brawler itself, not a
    permanent an opponent controls, and not a counter of another kind."""
    scenario = _board(["Botanical Brawler", "Grizzly Bears"], ["Grizzly Bears"])
    brawler = scenario.creature("Botanical Brawler", "alice")
    scenario.game.add_counters(brawler, "+1/+1", 1, putter="alice")
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "bob"), "+1/+1", 1)
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "alice"), "shield", 1)
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Botanical Brawler")


def test_stalwart_successor_puts_a_counter_on_that_creature():
    """Stalwart Successor: "Whenever one or more counters are put on a
    creature you control, if it's the first time counters have been put on
    that creature this turn, put a +1/+1 counter on that creature." - any
    kind of counter, and its own +1/+1 counter is not a first time, so it
    does not trigger again."""
    scenario = _board(["Stalwart Successor", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "shield", 1, putter="alice")
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario, "Stalwart Successor")
    _resolve_all(scenario)
    assert scenario.creature("Grizzly Bears", "alice").counter_count("+1/+1") == 1
    assert scenario.game.intervening_if_notices == []


def test_a_counter_of_another_kind_first_does_not_make_plus_one_counters_second():
    """ "first time +1/+1 counters" counts +1/+1 placements only; Stalwart
    Successor's "first time counters" (a second printing) counts every kind."""
    scenario = _board(["Botanical Brawler", "Stalwart Successor", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _counters_put(scenario, bears, "shield")
    plus_one = _counters_put(scenario, bears, "+1/+1")
    assert _first_time_holds(scenario, "Botanical Brawler", plus_one) is True
    assert _first_time_holds(scenario, "Stalwart Successor", plus_one) is False


def test_a_counter_put_on_a_permanent_under_your_control():
    """Fairgrounds Trumpeter: "At the beginning of each end step, if a +1/+1
    counter was put on a permanent under your control this turn, put a +1/+1
    counter on this creature." """
    scenario = _board(["Fairgrounds Trumpeter", "Grizzly Bears"], ["Grizzly Bears"])
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "alice"), "+1/+1", 1)
    _to_end_step(scenario)
    assert _triggered(scenario, "Fairgrounds Trumpeter")

    scenario = _board(["Fairgrounds Trumpeter", "Grizzly Bears"], ["Grizzly Bears"])
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "bob"), "+1/+1", 1)
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "alice"), "-1/-1", 1)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Fairgrounds Trumpeter")
    assert scenario.game.intervening_if_notices == []


def test_you_put_a_counter_on_this_creature():
    """Fractal Tender: "At the beginning of each end step, if you put a counter
    on this creature this turn, create a 0/0 ... Fractal creature token and put
    three +1/+1 counters on it." """
    scenario = _board(["Fractal Tender", "Grizzly Bears"])
    scenario.game.add_counters(scenario.creature("Fractal Tender", "alice"), "+1/+1", 1)
    _to_end_step(scenario)
    assert _triggered(scenario, "Fractal Tender")

    scenario = _board(["Fractal Tender", "Grizzly Bears"])
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "alice"), "+1/+1", 1)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Fractal Tender")
    assert scenario.game.intervening_if_notices == []


def test_you_put_a_counter_on_a_creature():
    """Lasting Tarfire (a second printing): "if you put a counter on a creature
    this turn" - any creature, counted by who put the counter (CR 122.6a)."""
    scenario = _board(["Lasting Tarfire"], ["Grizzly Bears"])
    scenario.game.add_counters(
        scenario.creature("Grizzly Bears", "bob"), "+1/+1", 1, putter="alice"
    )
    _to_end_step(scenario)
    assert _triggered(scenario, "Lasting Tarfire")

    scenario = _board(["Lasting Tarfire"], ["Grizzly Bears"])
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "bob"), "+1/+1", 1, putter="bob")
    _to_end_step(scenario)
    assert not _triggered(scenario, "Lasting Tarfire")


# -- loyalty abilities, playing from exile ----------------------------------------


def test_the_chain_veil_punishes_a_turn_without_a_loyalty_ability():
    """The Chain Veil: "At the beginning of your end step, if you didn't
    activate a loyalty ability of a planeswalker this turn, you lose 2 life." """
    scenario = _board(["The Chain Veil"])
    _to_end_step(scenario)
    assert _triggered(scenario, "The Chain Veil")

    scenario = _board(["The Chain Veil", "Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    scenario.activate(liliana, index=0, username="alice")
    scenario.pass_until_resolved()
    _to_end_step(scenario)
    assert not _triggered(scenario, "The Chain Veil")
    assert scenario.game.intervening_if_notices == []


def _visions(*, play_it: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Visions of Phyrexia"], library=["Forest"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.game.untap_step()
    scenario.advance()  # upkeep: Visions exiles the top card, playable this turn
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if play_it:
        scenario.play_land("Forest", from_zone=Zone.EXILE)
    _to_end_step(scenario)
    return scenario


def test_visions_of_phyrexia_makes_a_powerstone_when_nothing_was_played_from_exile():
    """Visions of Phyrexia: "At the beginning of your end step, if you didn't
    play a card from exile this turn, create a tapped Powerstone token." """
    scenario = _visions(play_it=False)
    assert _triggered(scenario, "Visions of Phyrexia")
    scenario.pass_until_resolved()  # true at both: it resolves
    assert [
        p for p in scenario.game.permanents_controlled_by("alice") if "Powerstone" in p.subtypes
    ]


def test_visions_of_phyrexia_does_nothing_after_playing_the_exiled_land():
    scenario = _visions(play_it=True)
    assert not _triggered(scenario, "Visions of Phyrexia")
    assert scenario.game.intervening_if_notices == []


# -- "you've committed a crime this turn" (CR 700.13) ----------------------------


def _servant_after(targets):
    scenario = _board(
        ["Servant of the Stinger", "Mountain", "Grizzly Bears"],
        ["Grizzly Bears"],
        hand=["Lightning Bolt"],
    )
    if targets is not None:
        target = targets(scenario)
        scenario.cast_and_resolve(
            "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[target]
        )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Servant of the Stinger", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    return scenario


def test_targeting_an_opponent_is_a_crime():
    """Servant of the Stinger: "Whenever this creature deals combat damage to a
    player, if you've committed a crime this turn, you may sacrifice this
    creature. ..." """
    assert _triggered(_servant_after(lambda s: "bob"), "Servant of the Stinger")


def test_targeting_an_opponents_permanent_is_a_crime():
    scenario = _servant_after(lambda s: s.creature("Grizzly Bears", "bob"))
    assert _triggered(scenario, "Servant of the Stinger")


def test_targeting_your_own_permanent_is_not_a_crime():
    scenario = _servant_after(lambda s: s.creature("Grizzly Bears", "alice"))
    assert not _triggered(scenario, "Servant of the Stinger")
    assert scenario.game.intervening_if_notices == []


def test_no_crime_at_all():
    scenario = _servant_after(None)
    assert not _triggered(scenario, "Servant of the Stinger")
    assert scenario.game.intervening_if_notices == []


def test_an_activated_ability_targeting_an_opponent_is_a_crime():
    """CR 700.13's "activates an ability" half: Walking Ballista's "Remove a
    +1/+1 counter from this creature: It deals 1 damage to any target." aimed
    at bob."""
    scenario = _board(["Servant of the Stinger", "Walking Ballista"])
    ballista = scenario.creature("Walking Ballista", "alice")
    scenario.game.add_counters(ballista, "+1/+1", 1)
    scenario.activate(ballista, index=1, username="alice", targets=["bob"])
    scenario.pass_until_resolved()
    assert (
        scenario.game.condition_holds("alice", "you've committed a crime this turn", ballista)
        is True
    )
    assert scenario.game.condition_holds("bob", "you've committed a crime this turn", ballista) is (
        False
    )


def test_visions_of_phyrexia_does_nothing_after_the_exiled_card_is_cast_in_response():
    """True as it triggers, false by resolution: the exiled instant is cast
    from exile with the end-step trigger on the stack, so CR 608.2a removes
    the trigger and no Powerstone is made."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Visions of Phyrexia", "Mountain"],
            library=["Lightning Bolt"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.game.untap_step()
    scenario.advance()  # upkeep: Visions exiles the top card, playable this turn
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert _triggered(scenario, "Visions of Phyrexia")
    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE, targets=["bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()  # the Bolt
    scenario.pass_until_resolved()  # the trigger
    assert not scenario.game.stack
    assert not [
        p for p in scenario.game.permanents_controlled_by("alice") if "Powerstone" in p.subtypes
    ]
