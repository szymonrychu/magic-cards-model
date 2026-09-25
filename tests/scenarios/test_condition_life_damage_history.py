"""Turn-history conditions about life and damage (EC4 cluster H4): how much
life a player gained or lost this turn or last turn, how much damage a player
or a permanent was dealt and by what, excess damage, and energy paid - read
by an intervening "if" (CR 603.4, rechecked on resolution by CR 608.2a) and by
an "Activate only if" restriction (CR 602.5b).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 119.3** - an effect that makes a player lose life; **CR 120.3a** -
  damage dealt to a player causes that player to lose that much life, so
  damage is life loss too.
- **CR 120.1** - "An object that deals damage is the source of that damage."
- **CR 120.2a** / **CR 120.2b** - combat damage and noncombat damage.
- **CR 120.10** - excess damage: damage to a creature greater than lethal
  damage, or to a planeswalker greater than its loyalty before the damage.
- **CR 107.14** - "To pay {E}, a player removes one energy counter from
  themselves."
- **CR 603.4**, **CR 608.2a**, **CR 602.5b** as in the other history files.

Every clause here failed closed before `machines/conditions/history.py` read
it.
"""

from magic_cards_model.machines import Step
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


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep
    scenario.game.put_triggers_on_stack()


def _triggered(scenario, name: str) -> bool:
    return f"{name}'s triggered ability" in scenario.stack_names()


def _printed_triggers(printing):
    """Every triggered ability the printing's text parses to."""
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
    from magic_cards_model.machines.triggers import triggered_abilities_of

    found = [each for each in parse_abilities(printing) if isinstance(each, TriggeredAbility)]
    return found + [each for each in triggered_abilities_of(printing) if each not in found]


def _clause_holds(scenario, source, event=None) -> bool | None:
    """The source's own intervening "if", read now against the real board
    (`machines/triggers.intervening_if_answer`) - for a trigger whose event
    `machines/triggers.py` does not raise yet, so the reader is proven on the
    printing's own parsed ability rather than through the trigger."""
    from magic_cards_model.machines.triggers import intervening_if_answer

    (ability,) = [each for each in _printed_triggers(source.card) if each.intervening_if][:1]
    return intervening_if_answer(scenario.game, ability, source, event, source.zone_change_stamp)


def _board(alice: list[str], bob: list[str] | None = None, **kwargs):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, library=["Plains"] * 6, **kwargs)
        .player("bob", battlefield=bob or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- "you gained N or more life this turn" --------------------------------------


def test_griffin_aerie_makes_a_griffin_after_three_life_gained():
    """Griffin Aerie: "At the beginning of your end step, if you gained 3 or
    more life this turn, create a 2/2 white Griffin creature token with
    flying." - counted across separate gains."""
    scenario = _board(["Griffin Aerie"])
    scenario.game.gain_life("alice", 1)
    scenario.game.gain_life("alice", 2)
    _to_end_step(scenario)
    assert _triggered(scenario, "Griffin Aerie")
    scenario.pass_until_resolved()
    assert any(state.token and "Griffin" in state.subtypes for state in scenario.game.battlefield)


def test_griffin_aerie_does_nothing_after_two_life_gained():
    scenario = _board(["Griffin Aerie"])
    scenario.game.gain_life("alice", 2)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Griffin Aerie")
    assert scenario.game.intervening_if_notices == []


def test_angelic_accord_reads_a_different_threshold():
    """A second printing: Angelic Accord's "4 or more", at each end step."""
    scenario = _board(["Angelic Accord"])
    scenario.game.gain_life("alice", 4)
    _to_end_step(scenario)
    assert _triggered(scenario, "Angelic Accord")

    scenario = _board(["Angelic Accord"])
    scenario.game.gain_life("alice", 3)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Angelic Accord")


def test_brackish_trudge_returns_only_after_life_was_gained():
    """Brackish Trudge: "{1}{B}: Return this card from your graveyard to your
    hand. Activate only if you gained life this turn." """
    scenario = _board(["Swamp", "Swamp"], graveyard=["Brackish Trudge"])
    trudge = scenario.find("Brackish Trudge", Zone.GRAVEYARD, "alice")
    assert (
        scenario.why_cannot_activate(trudge, 0, "alice")
        == "Brackish Trudge's activation restriction is not met (CR 602.5b)"
    )
    scenario.game.gain_life("alice", 1)
    assert scenario.why_cannot_activate(trudge, 0, "alice") is None
    scenario.activate(trudge, *scenario.untapped_sources("Swamp", "Swamp"), username="alice")
    scenario.pass_until_resolved()
    assert scenario.find("Brackish Trudge", Zone.HAND, "alice") is not None


# -- "<who> lost [N or more] life this turn / last turn" -------------------------


def test_an_opponent_lost_two_or_more_life():
    """Bloodchief Ascension: "At the beginning of each end step, if an opponent
    lost 2 or more life this turn, you may put a quest counter on this
    enchantment." - damage is life loss too (CR 120.3a)."""
    scenario = _board(["Bloodchief Ascension"])
    scenario.game.deal_damage(scenario.player("bob"), 2)
    _to_end_step(scenario)
    assert _triggered(scenario, "Bloodchief Ascension")

    scenario = _board(["Bloodchief Ascension"])
    scenario.game.lose_life("bob", 1)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Bloodchief Ascension")
    assert scenario.game.intervening_if_notices == []


def test_sygg_reads_three_or_more():
    """A second printing: Sygg, River Cutthroat's "3 or more"."""
    scenario = _board(["Sygg, River Cutthroat"])
    scenario.game.lose_life("bob", 3)
    _to_end_step(scenario)
    assert _triggered(scenario, "Sygg, River Cutthroat")

    scenario = _board(["Sygg, River Cutthroat"])
    scenario.game.lose_life("alice", 3)  # not an opponent
    _to_end_step(scenario)
    assert not _triggered(scenario, "Sygg, River Cutthroat")


def test_a_player_includes_you():
    """Knight of the Ebon Legion: "if a player lost 4 or more life this turn"."""
    scenario = _board(["Knight of the Ebon Legion"])
    scenario.game.lose_life("alice", 4)
    _to_end_step(scenario)
    assert _triggered(scenario, "Knight of the Ebon Legion")

    scenario = _board(["Knight of the Ebon Legion"])
    scenario.game.lose_life("bob", 3)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Knight of the Ebon Legion")


def test_you_lost_two_or_more_life():
    """The Book of Vile Darkness: "if you lost 2 or more life this turn"."""
    scenario = _board(["The Book of Vile Darkness"])
    scenario.game.lose_life("alice", 1)
    scenario.game.lose_life("alice", 1)
    _to_end_step(scenario)
    assert _triggered(scenario, "The Book of Vile Darkness")

    scenario = _board(["The Book of Vile Darkness"])
    scenario.game.lose_life("bob", 5)
    _to_end_step(scenario)
    assert not _triggered(scenario, "The Book of Vile Darkness")


def test_you_lost_life_last_turn():
    """First Response: "At the beginning of each upkeep, if you lost life last
    turn, create a 1/1 white Soldier creature token." """
    scenario = _board(["First Response"])
    scenario.game.lose_life("alice", 1)
    _next_turn(scenario)  # bob's upkeep
    assert _triggered(scenario, "First Response")
    assert scenario.game.intervening_if_notices == []


def test_no_life_lost_last_turn_does_nothing():
    scenario = _board(["First Response"])
    _next_turn(scenario)
    assert not _triggered(scenario, "First Response")
    assert scenario.game.intervening_if_notices == []


def test_life_lost_two_turns_ago_is_not_last_turn():
    scenario = _board(["Paladin of Atonement"])
    scenario.game.lose_life("alice", 1)
    _next_turn(scenario)  # bob's upkeep: last turn was alice's
    assert _triggered(scenario, "Paladin of Atonement")
    scenario.pass_until_resolved()
    _next_turn(scenario)  # alice's upkeep: last turn was bob's, and nothing was lost
    assert not _triggered(scenario, "Paladin of Atonement")


def test_an_opponent_lost_life_last_turn():
    """Feast on the Fallen: "At the beginning of each upkeep, if an opponent
    lost life last turn, put a +1/+1 counter on target creature you control." """
    scenario = _board(["Feast on the Fallen", "Grizzly Bears"])
    scenario.choose_trigger_targets(
        "Feast on the Fallen", [scenario.creature("Grizzly Bears", "alice")]
    )
    scenario.game.lose_life("bob", 1)
    _next_turn(scenario)
    assert _triggered(scenario, "Feast on the Fallen")

    scenario = _board(["Feast on the Fallen", "Grizzly Bears"])
    scenario.game.lose_life("alice", 1)
    _next_turn(scenario)
    assert not _triggered(scenario, "Feast on the Fallen")


# -- "you didn't lose life this turn" (a negation, rechecked on resolution) ----


def _luminarch_at_bobs_end_step(alice_loses: int):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", library=["Plains"] * 4)
        .player("alice", battlefield=["Luminarch Ascension"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if alice_loses:
        scenario.game.lose_life("alice", alice_loses)
    _to_end_step(scenario)
    return scenario


def _quest_counters(scenario) -> int:
    ascension = scenario.find("Luminarch Ascension", Zone.BATTLEFIELD, "alice")
    return ascension.counter_count("quest")


def test_luminarch_ascension_counts_a_turn_without_life_loss():
    """Luminarch Ascension: "At the beginning of each opponent's end step, if
    you didn't lose life this turn, you may put a quest counter on this
    enchantment." - true at both checks: it resolves."""
    scenario = _luminarch_at_bobs_end_step(0)
    assert _triggered(scenario, "Luminarch Ascension")
    scenario.pass_until_resolved()
    assert _quest_counters(scenario) == 1


def test_luminarch_ascension_never_triggers_after_life_loss():
    """False when the step begins: CR 603.4 - it never triggers."""
    scenario = _luminarch_at_bobs_end_step(1)
    assert not _triggered(scenario, "Luminarch Ascension")
    assert scenario.game.intervening_if_notices == []


def test_luminarch_ascension_does_nothing_if_life_is_lost_before_it_resolves():
    """True as it triggers, false by resolution: CR 608.2a removes it and it
    does nothing."""
    scenario = _luminarch_at_bobs_end_step(0)
    assert _triggered(scenario, "Luminarch Ascension")
    scenario.game.lose_life("alice", 1)
    scenario.pass_until_resolved()
    assert _quest_counters(scenario) == 0


# -- "you gained and lost life" / "you gained or lost life" ---------------------


def test_gained_and_lost_needs_both():
    """Lunar Convocation: "At the beginning of your end step, if you gained and
    lost life this turn, create a 1/1 black Bat creature token with flying." -
    its first ability, "if you gained life this turn", triggers alongside."""
    scenario = _board(["Lunar Convocation"])
    scenario.game.gain_life("alice", 1)
    scenario.game.lose_life("alice", 1)
    _to_end_step(scenario)
    assert scenario.stack_names().count("Lunar Convocation's triggered ability") == 2

    scenario = _board(["Lunar Convocation"])
    scenario.game.gain_life("alice", 1)
    _to_end_step(scenario)
    assert scenario.stack_names().count("Lunar Convocation's triggered ability") == 1
    assert scenario.game.intervening_if_notices == []


def test_gained_or_lost_needs_either():
    """Starlit Soothsayer and Star Charter: "if you gained or lost life this
    turn"."""
    for card in ("Starlit Soothsayer", "Star Charter"):
        scenario = _board([card])
        scenario.game.lose_life("alice", 1)
        _to_end_step(scenario)
        assert _triggered(scenario, card)

        scenario = _board([card])
        _to_end_step(scenario)
        assert not _triggered(scenario, card)
        assert scenario.game.intervening_if_notices == []


# -- damage dealt to players -----------------------------------------------------


def test_skarrgan_firebird_needs_damage_not_just_life_loss():
    """Skarrgan Firebird: "{R}{R}{R}: Return this card from your graveyard to
    your hand. Activate only if an opponent was dealt damage this turn." """
    scenario = _board(["Mountain"] * 3, graveyard=["Skarrgan Firebird"])
    firebird = scenario.find("Skarrgan Firebird", Zone.GRAVEYARD, "alice")
    scenario.game.lose_life("bob", 2)
    refusal = scenario.why_cannot_activate(firebird, 0, "alice")
    assert refusal is not None and "not met" in refusal

    scenario.game.deal_damage(scenario.player("bob"), 1)
    assert scenario.why_cannot_activate(firebird, 0, "alice") is None


def _blitzball_after_attack(attacker: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Blitzball", attacker], library=["Plains"] * 6)
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature(attacker, "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    return scenario, scenario.find("Blitzball", Zone.BATTLEFIELD, "alice")


def test_blitzball_needs_combat_damage_from_a_legendary_creature():
    """Blitzball: "{T}, Sacrifice this artifact: Draw two cards. Activate only
    if an opponent was dealt combat damage by a legendary creature this
    turn." """
    scenario, blitzball = _blitzball_after_attack("Tolsimir, Midnight's Light")
    assert scenario.why_cannot_activate(blitzball, 1, "alice") is None

    scenario, blitzball = _blitzball_after_attack("Grizzly Bears")
    refusal = scenario.why_cannot_activate(blitzball, 1, "alice")
    assert refusal is not None and "not met" in refusal


def test_you_were_dealt_four_or_more_damage():
    """Boarded Window: "At the beginning of each end step, if you were dealt 4
    or more damage this turn, exile this artifact." - damage, not life loss."""
    scenario = _board(["Boarded Window"])
    scenario.game.deal_damage(scenario.player("alice"), 2)
    scenario.game.deal_damage(scenario.player("alice"), 2)
    _to_end_step(scenario)
    assert _triggered(scenario, "Boarded Window")

    scenario = _board(["Boarded Window"])
    scenario.game.lose_life("alice", 4)
    scenario.game.deal_damage(scenario.player("alice"), 3)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Boarded Window")
    assert scenario.game.intervening_if_notices == []


def _blitzball_sidequest(bears: int):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sidequest: Play Blitzball // World Champion, Celestial Weapon"]
            + ["Grizzly Bears"] * bears,
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*[s for s in scenario.game.battlefield if s.name == "Grizzly Bears"])
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.turn.advance_to(Step.COMBAT_DAMAGE)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end of combat step begins (CR 511.1)
    scenario.game.put_triggers_on_stack()
    return scenario


def test_a_player_dealt_six_or_more_combat_damage():
    """Sidequest: Play Blitzball: "At the end of combat on your turn, if a
    player was dealt 6 or more combat damage this turn, transform this
    enchantment, then attach it to a creature you control." - CR 511.2: it
    triggers as the end of combat step begins."""

    def holds(bears: int) -> bool | None:
        scenario = _blitzball_sidequest(bears)
        sidequest = scenario.find("Sidequest: Play Blitzball", Zone.BATTLEFIELD, "alice")
        return _clause_holds(scenario, sidequest)

    assert holds(3) is True
    assert holds(2) is False

    scenario = _blitzball_sidequest(3)
    assert _triggered(scenario, "Sidequest: Play Blitzball")
    scenario.pass_until_resolved()
    champion = scenario.find("World Champion, Celestial Weapon", Zone.BATTLEFIELD, "alice")
    assert champion.transformed
    bears = {state.id for state in scenario.game.battlefield if state.name == "Grizzly Bears"}
    assert champion.attached_to in bears

    scenario = _blitzball_sidequest(2)
    assert not _triggered(scenario, "Sidequest: Play Blitzball")
    assert scenario.game.intervening_if_notices == []


def test_the_end_of_combat_on_your_turn_is_not_an_opponents():
    """ "on your turn": the opponent's end of combat step does not trigger it,
    however much combat damage was dealt."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"] * 3, library=["Plains"] * 4)
        .player(
            "bob",
            battlefield=["Sidequest: Play Blitzball // World Champion, Celestial Weapon"],
            library=["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*[s for s in scenario.game.battlefield if s.name == "Grizzly Bears"])
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.turn.advance_to(Step.COMBAT_DAMAGE)
    scenario.game.sync_priority_with_step()
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Sidequest: Play Blitzball")


def _dealt_damage_to_an_opponent(card: str, *, attack: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[card], library=["Plains"] * 4)
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    if attack:
        scenario.attack_with(scenario.creature(card, "alice"))
        scenario.no_blocks()
        scenario.combat_damage()
    _to_end_step(scenario)
    return scenario


def test_this_creature_dealt_damage_to_an_opponent():
    """Dunerider Outlaw and Whirling Dervish: "At the beginning of each end
    step, if this creature dealt damage to an opponent this turn, put a +1/+1
    counter on it." """
    for card in ("Dunerider Outlaw", "Whirling Dervish"):
        assert _triggered(_dealt_damage_to_an_opponent(card, attack=True), card)
        scenario = _dealt_damage_to_an_opponent(card, attack=False)
        assert not _triggered(scenario, card)
        assert scenario.game.intervening_if_notices == []


def test_it_has_dealt_ten_or_more_damage_to_that_player():
    """Vessel of the All-Consuming: "Whenever this creature deals damage to a
    player, if it has dealt 10 or more damage to that player this turn, they
    lose the game." - summed over this turn, per player."""
    scenario = _board(["Hidetsugu Consumes All // Vessel of the All-Consuming"])
    vessel = scenario.find("Hidetsugu Consumes All", Zone.BATTLEFIELD, "alice")
    vessel.transformed = True
    bob = scenario.player("bob")

    scenario.game.deal_damage(bob, 6, source=vessel)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names().count("Vessel of the All-Consuming's triggered ability") == 1
    while scenario.game.stack:
        scenario.pass_until_resolved()

    scenario.game.deal_damage(bob, 4, source=vessel)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names().count("Vessel of the All-Consuming's triggered ability") == 2
    assert scenario.game.intervening_if_notices == []


# -- damage dealt to permanents ----------------------------------------------------


def _zubera(card: str, damage: int):
    scenario = _board([card])
    zubera = scenario.creature(card, "alice")
    scenario.game.deal_damage(zubera, damage)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    return scenario


def test_four_damage_dealt_to_it_before_it_died():
    """Burning-Eye Zubera and Rushing-Tide Zubera: "When this creature dies, if
    4 or more damage was dealt to it this turn, ..." """
    for card in ("Burning-Eye Zubera", "Rushing-Tide Zubera"):
        scenario = _zubera(card, 4)
        assert scenario.find(card, Zone.GRAVEYARD, "alice") is not None
        assert _triggered(scenario, card) or any(
            item.source_name == card for item in scenario.pending_triggers
        )

        scenario = _zubera(card, 3)
        assert scenario.find(card, Zone.GRAVEYARD, "alice") is not None
        assert not _triggered(scenario, card)
        assert scenario.game.intervening_if_notices == []


def test_excess_damage_to_an_opponents_creature():
    """Rith, Liberated Primeval: "At the beginning of your end step, if a
    creature or planeswalker an opponent controlled was dealt excess damage
    this turn, create a 4/4 red Dragon creature token with flying." - CR
    120.10: more than lethal damage."""
    scenario = _board(["Rith, Liberated Primeval"], ["Grizzly Bears"])
    scenario.game.deal_damage(scenario.creature("Grizzly Bears", "bob"), 3)
    _to_end_step(scenario)
    assert _triggered(scenario, "Rith, Liberated Primeval")

    scenario = _board(["Rith, Liberated Primeval"], ["Grizzly Bears"])
    scenario.game.deal_damage(scenario.creature("Grizzly Bears", "bob"), 2)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Rith, Liberated Primeval")
    assert scenario.game.intervening_if_notices == []


def test_excess_damage_to_your_own_creature_does_not_count():
    scenario = _board(["Rith, Liberated Primeval", "Grizzly Bears"])
    scenario.game.deal_damage(scenario.creature("Grizzly Bears", "alice"), 5)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Rith, Liberated Primeval")


def test_excess_counts_damage_already_marked():
    """Lethal damage takes damage already marked into account (CR 120.6): a
    second 2 on a 2/2 already holding 1 is 1 excess."""
    scenario = _board(["Rith, Liberated Primeval"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.deal_damage(bears, 1)
    scenario.game.deal_damage(bears, 2)
    _to_end_step(scenario)
    assert _triggered(scenario, "Rith, Liberated Primeval")


def _axe_board(*, blocked: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Thirsting Axe", "Grizzly Bears"], library=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 4)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Thirsting Axe", Zone.BATTLEFIELD, "alice").attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    if blocked:
        scenario.attack_with(bears)
        scenario.block(bears, scenario.creature("Grizzly Bears", "bob"))
        scenario.combat_damage()
    _to_end_step(scenario)
    return scenario


def test_thirsting_axe_sacrifices_a_creature_that_dealt_no_combat_damage_to_a_creature():
    """Thirsting Axe: "At the beginning of your end step, if equipped creature
    didn't deal combat damage to a creature this turn, sacrifice it." """
    scenario = _axe_board(blocked=False)
    assert _triggered(scenario, "Thirsting Axe")
    assert scenario.game.intervening_if_notices == []


def test_thirsting_axe_spares_a_creature_that_dealt_combat_damage_to_a_creature():
    scenario = _axe_board(blocked=True)
    assert not _triggered(scenario, "Thirsting Axe")
    assert scenario.game.intervening_if_notices == []


def _temple_after(bolts: int, lands: int = 2):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ojer Axonil, Deepest Might // Temple of Power"] + ["Mountain"] * lands,
            hand=["Lightning Bolt"] * bolts,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    temple = scenario.find("Ojer Axonil, Deepest Might", Zone.BATTLEFIELD, "alice")
    temple.transformed = True
    mountains = scenario.untapped_sources(*["Mountain"] * lands)
    for index in range(bolts):
        scenario.cast_and_resolve("Lightning Bolt", mountains[index], targets=["bob"])
    return scenario, temple


def test_red_sources_you_controlled_dealt_four_or_more_noncombat_damage():
    """Temple of Power: "{2}{R}, {T}: Transform this land. Activate only if red
    sources you controlled dealt 4 or more noncombat damage this turn and only
    as a sorcery." - two Lightning Bolts are 6."""
    scenario, temple = _temple_after(2)
    assert scenario.why_cannot_activate(temple, 1, "alice") is None

    scenario, temple = _temple_after(1)
    refusal = scenario.why_cannot_activate(temple, 1, "alice")
    assert refusal is not None and "not met" in refusal


# -- energy ---------------------------------------------------------------------


def test_izzet_generatorium_counts_energy_paid():
    """Izzet Generatorium: "{T}: Draw a card. Activate only if you've paid or
    lost four or more {E} this turn." (CR 107.14)"""
    scenario = _board(["Izzet Generatorium"])
    generatorium = scenario.find("Izzet Generatorium", Zone.BATTLEFIELD, "alice")
    scenario.game.add_player_counters("alice", "energy", 6)
    assert scenario.game.may_pay_energy("alice", 3)
    refusal = scenario.why_cannot_activate(generatorium, 0, "alice")
    assert refusal is not None and "not met" in refusal

    assert scenario.game.may_pay_energy("alice", 1)
    assert scenario.why_cannot_activate(generatorium, 0, "alice") is None


# -- "you haven't been dealt combat damage since your last turn" -----------------


def _marchesa(*, bob_attacks: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Invasion of Fiora // Marchesa, Resolute Monarch"],
            library=["Plains"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 6)
        .build()
    )
    marchesa = scenario.find("Invasion of Fiora", Zone.BATTLEFIELD, "alice")
    marchesa.transformed = True
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)  # bob's turn
    if bob_attacks:
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
        scenario.no_blocks()
        scenario.combat_damage()
    _next_turn(scenario)  # alice's upkeep
    return scenario


def test_marchesa_draws_when_you_took_no_combat_damage_since_your_last_turn():
    """Marchesa, Resolute Monarch: "At the beginning of your upkeep, if you
    haven't been dealt combat damage since your last turn, you draw a card and
    you lose 1 life." """
    scenario = _marchesa(bob_attacks=False)
    assert _triggered(scenario, "Marchesa, Resolute Monarch")
    assert scenario.game.intervening_if_notices == []


def test_marchesa_does_not_draw_after_combat_damage_on_the_opponents_turn():
    scenario = _marchesa(bob_attacks=True)
    assert not _triggered(scenario, "Marchesa, Resolute Monarch")
    assert scenario.game.intervening_if_notices == []
