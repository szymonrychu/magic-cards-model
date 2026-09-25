"""Paid-cost conditions: which optional and alternative costs a spell was cast
for - kicked (twice, with a named kicker, or not at all), bargained, surge,
prowl, spectacle, madness, sneak, web-slinging, evidence collected, a Dragon
revealed or controlled, and tribute (paid as the creature enters).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 702.33a** - kicker is an optional additional cost; **CR 702.33b** -
  "Kicker [cost 1] and/or [cost 2]" means the same as two kicker abilities;
  **CR 702.33d** - declaring any kicker cost makes the spell "kicked", and a
  spell with two kicker costs may be kicked twice; **CR 702.33f** - "if it
  was kicked with its [A] kicker" is linked to that one cost.
- **CR 702.166a** - bargain: "you may sacrifice an artifact, enchantment, or
  token"; **CR 702.166b** - paying it makes the spell "bargained".
- **CR 702.117a** - surge: an alternative cost usable "if you or one of your
  teammates has cast another spell this turn".
- **CR 702.188a** - web-slinging: pay [cost] and return a tapped creature you
  control to its owner's hand rather than the mana cost.
- **CR 701.59a** - collect evidence N: exile cards from your graveyard with
  total mana value N or greater; **CR 701.59c** - "if evidence was
  collected" is linked to it.
- **CR 702.104a** - tribute N: an opponent of your choice may put N +1/+1
  counters on it as it enters; **CR 702.104b** - "tribute wasn't paid" is
  true if that opponent didn't.
- **CR 702.76a** (prowl), **CR 702.137a** (spectacle), **CR 702.35a**
  (madness), **CR 702.190a** (sneak) - alternative costs.
- **CR 603.4** - an intervening "if" false as the event occurs never
  triggers.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice, bob=None, *, hand=None, graveyard=None, library=None, bob_hand=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=alice,
            hand=hand or [],
            graveyard=graveyard or [],
            library=library or ["Plains"] * 8,
        )
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _triggers(scenario) -> list[str]:
    scenario.game.put_triggers_on_stack()
    return [name for name in scenario.stack_names() if name.endswith("triggered ability")]


def _no_trigger(scenario) -> None:
    assert _triggers(scenario) == []
    assert scenario.game.intervening_if_notices == []


def _cast(scenario, name, *sources, announce=None, username="alice", zone=Zone.HAND):
    casting = scenario.cast(name, username, from_zone=zone)
    if announce is not None:
        announce(casting)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    return scenario.put_on_stack(casting)


# -- kicked / not kicked ----------------------------------------------------------


def test_he_was_kicked():
    """Josu Vess, Lich Knight: "When Josu Vess enters, if he was kicked,
    create eight 2/2 black Zombie Knight creature tokens with menace." """
    scenario = _board(["Swamp"] * 10, hand=["Josu Vess, Lich Knight"])
    _cast(
        scenario,
        "Josu Vess, Lich Knight",
        *scenario.untapped_sources(*["Swamp"] * 10),
        announce=lambda casting: casting.pay_kicker(1),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Josu Vess, Lich Knight's triggered ability"]
    scenario.pass_until_resolved()
    zombies = [s for s in scenario.game.permanents_controlled_by("alice") if s.token]
    assert len(zombies) == 8


def test_he_was_not_kicked_never_triggers():
    scenario = _board(["Swamp"] * 4, hand=["Josu Vess, Lich Knight"])
    _cast(scenario, "Josu Vess, Lich Knight", *scenario.untapped_sources(*["Swamp"] * 4))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_a_legend_named_by_its_own_name():
    """Jace, Mirror Mage: "When Jace enters, if Jace was kicked" - the name
    is the source (CR 201.5)."""
    scenario = _board(["Island"] * 5, hand=["Jace, Mirror Mage"])
    _cast(
        scenario,
        "Jace, Mirror Mage",
        *scenario.untapped_sources(*["Island"] * 5),
        announce=lambda casting: casting.pay_kicker(1),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Jace, Mirror Mage's triggered ability"]


def test_wasnt_kicked_sacrifices_at_the_end_step():
    """Skizzik: "At the beginning of the end step, if this creature wasn't
    kicked, sacrifice it." - kicked, it stays."""
    from magic_cards_model.machines.triggers import GameEvent, TriggerEvent

    for kicked in (False, True):
        scenario = _board(["Mountain"] * 5, hand=["Skizzik"])
        _cast(
            scenario,
            "Skizzik",
            *scenario.untapped_sources(*["Mountain"] * (5 if kicked else 4)),
            announce=(lambda casting: casting.pay_kicker(1)) if kicked else None,
        )
        scenario.resolve_top()
        scenario.start_at(Step.END_STEP)
        scenario.game.emit(
            GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
        )
        if kicked:
            _no_trigger(scenario)
        else:
            assert _triggers(scenario) == ["Skizzik's triggered ability"]
            scenario.pass_until_resolved()
            assert scenario.find("Skizzik", Zone.GRAVEYARD, "alice") is not None


def test_that_spell_was_kicked_reads_the_cast_spell():
    """Bloodstone Goblin: "Whenever you cast a spell, if that spell was
    kicked, this creature gets +1/+1 and gains menace until end of turn." """
    scenario = _board(["Bloodstone Goblin", *["Mountain"] * 5], hand=["Skizzik"])
    _cast(
        scenario,
        "Skizzik",
        *scenario.untapped_sources(*["Mountain"] * 5),
        announce=lambda casting: casting.pay_kicker(1),
    )
    assert _triggers(scenario) == ["Bloodstone Goblin's triggered ability"]
    scenario = _board(["Hallar, the Firefletcher", *["Mountain"] * 4], hand=["Skizzik"])
    _cast(scenario, "Skizzik", *scenario.untapped_sources(*["Mountain"] * 4))
    _no_trigger(scenario)


# -- two kicker costs: "and/or", "kicked twice", "with its [A] kicker" -------------


def test_kicked_twice_pays_both_kicker_costs():
    """Archangel of Wrath: "Kicker {B} and/or {R}" (CR 702.33b) - paying
    both kicks it twice: both enters triggers."""
    scenario = _board(
        ["Plains", "Plains", "Plains", "Plains", "Swamp", "Mountain"], hand=["Archangel of Wrath"]
    )

    def both(casting):
        casting.pay_kicker(1, which="{B}")
        casting.pay_kicker(1, which="{R}")

    spell = _cast(
        scenario,
        "Archangel of Wrath",
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Swamp", "Mountain"),
        announce=both,
    )
    assert scenario.game.cast_record(spell).kicked == 2
    scenario.resolve_top()
    assert _triggers(scenario) == ["Archangel of Wrath's triggered ability"] * 2


def test_kicked_once_is_not_kicked_twice():
    scenario = _board(["Plains"] * 4 + ["Swamp"], hand=["Archangel of Wrath"])
    _cast(
        scenario,
        "Archangel of Wrath",
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Swamp"),
        announce=lambda casting: casting.pay_kicker(1, which="{B}"),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Archangel of Wrath's triggered ability"]


def test_each_kicker_cost_may_be_paid_only_once():
    """CR 702.33a: each kicker is "an additional [cost]" - not multikicker."""
    scenario = _board(["Plains"] * 4 + ["Swamp", "Swamp"], hand=["Archangel of Wrath"])
    casting = scenario.cast("Archangel of Wrath")
    casting.pay_kicker(1, which="{B}")
    with pytest.raises(ValueError, match="already"):
        casting.pay_kicker(1, which="{B}")


def test_kicked_with_a_named_kicker():
    """Thornscape Battlemage: "Kicker {R} and/or {W}" - kicked with {W} only,
    only the {W} kicker's trigger ("destroy target artifact")."""
    scenario = _board(
        ["Forest", "Forest", "Forest", "Plains"], ["Mind Stone"], hand=["Thornscape Battlemage"]
    )
    _cast(
        scenario,
        "Thornscape Battlemage",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Plains"),
        announce=lambda casting: casting.pay_kicker(1, which="{W}"),
    )
    scenario.resolve_top()
    scenario.will_choose_targets(scenario.creature("Mind Stone", "bob"))
    assert _triggers(scenario) == ["Thornscape Battlemage's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.find("Mind Stone", Zone.GRAVEYARD, "bob") is not None


def test_kicked_with_a_named_kicker_on_a_second_printing():
    """Ana Battlemage: "Kicker {2}{U} and/or {1}{B}" - the {2}{U} kicker's
    "target player discards three cards"."""
    scenario = _board(
        ["Forest", "Forest", "Forest", "Island", "Island", "Island"], hand=["Ana Battlemage"]
    )
    _cast(
        scenario,
        "Ana Battlemage",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island", "Island"),
        announce=lambda casting: casting.pay_kicker(1, which="{2}{U}"),
    )
    scenario.resolve_top()
    scenario.will_choose_targets("bob")
    assert _triggers(scenario) == ["Ana Battlemage's triggered ability"]


# -- bargain -------------------------------------------------------------------------


def test_bargained_by_sacrificing_an_artifact():
    """Troublemaker Ouphe: "Bargain ... When this creature enters, if it was
    bargained, exile target artifact or enchantment an opponent controls." """
    scenario = _board(
        ["Forest", "Forest", "Ornithopter"], ["Mind Stone"], hand=["Troublemaker Ouphe"]
    )
    thopter = scenario.creature("Ornithopter")
    spell = _cast(
        scenario,
        "Troublemaker Ouphe",
        *scenario.untapped_sources("Forest", "Forest"),
        announce=lambda casting: casting.pay_bargain(thopter),
    )
    assert thopter.zone is Zone.GRAVEYARD
    assert scenario.game.cast_record(spell).bargained
    scenario.resolve_top()
    scenario.will_choose_targets(scenario.creature("Mind Stone", "bob"))
    assert _triggers(scenario) == ["Troublemaker Ouphe's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.find("Mind Stone", Zone.EXILE) is not None


def test_not_bargained_never_triggers():
    scenario = _board(["Forest", "Forest"], ["Mind Stone"], hand=["Troublemaker Ouphe"])
    _cast(scenario, "Troublemaker Ouphe", *scenario.untapped_sources("Forest", "Forest"))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_bargain_refuses_a_nontoken_creature():
    """CR 702.166a: an artifact, enchantment, or token - Grizzly Bears is none."""
    scenario = _board(["Forest", "Forest", "Grizzly Bears"], hand=["Troublemaker Ouphe"])
    casting = scenario.cast("Troublemaker Ouphe")
    with pytest.raises(ValueError, match="artifact, enchantment, or token"):
        casting.pay_bargain(scenario.creature("Grizzly Bears"))


def test_bargained_with_a_token_on_a_second_printing():
    """Agatha's Champion, bargaining a Spirit token from Spectral Procession
    (CR 702.166a: a token of any kind will do)."""
    scenario = _board(
        ["Plains"] * 3 + ["Forest"] * 5, hand=["Spectral Procession", "Agatha's Champion"]
    )
    scenario.cast_and_resolve("Spectral Procession", *scenario.untapped_sources(*["Plains"] * 3))
    spirit = next(s for s in scenario.game.permanents_controlled_by("alice") if s.token)
    spell = _cast(
        scenario,
        "Agatha's Champion",
        *scenario.untapped_sources(*["Forest"] * 5),
        announce=lambda casting: casting.pay_bargain(spirit),
    )
    assert scenario.game.cast_record(spell).bargained
    scenario.resolve_top()
    assert _triggers(scenario) == ["Agatha's Champion's triggered ability"]


# -- alternative costs -----------------------------------------------------------


def test_surge_after_another_spell_this_turn():
    """Reckless Bushwhacker: "Surge {1}{R} ... When this creature enters, if
    its surge cost was paid, other creatures you control get +1/+0 and gain
    haste until end of turn." (CR 702.117a)."""
    scenario = _board(
        ["Mountain"] * 3 + ["Grizzly Bears"], hand=["Lightning Bolt", "Reckless Bushwhacker"]
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _cast(
        scenario,
        "Reckless Bushwhacker",
        *scenario.untapped_sources("Mountain", "Mountain"),
        announce=lambda casting: casting.use_keyword("Surge"),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Reckless Bushwhacker's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.power_of(scenario.creature("Grizzly Bears")) == 3


def test_surge_is_refused_before_any_other_spell():
    scenario = _board(["Mountain"] * 3, hand=["Reckless Bushwhacker"])
    casting = scenario.cast("Reckless Bushwhacker")
    with pytest.raises(ValueError, match="another spell this turn"):
        casting.use_keyword("Surge")


def test_cast_for_its_mana_cost_surge_was_not_paid():
    scenario = _board(["Mountain"] * 4, hand=["Lightning Bolt", "Reckless Bushwhacker"])
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _cast(scenario, "Reckless Bushwhacker", *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_surge_on_a_second_printing():
    """Tyrant of Valakut: "Surge {3}{R}{R} ... if its surge cost was paid, it
    deals 3 damage to any target."."""
    scenario = _board(["Mountain"] * 6, hand=["Lightning Bolt", "Tyrant of Valakut"])
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _cast(
        scenario,
        "Tyrant of Valakut",
        *scenario.untapped_sources(*["Mountain"] * 5),
        announce=lambda casting: casting.use_keyword("Surge"),
    )
    scenario.resolve_top()
    scenario.will_choose_targets("bob")
    assert _triggers(scenario) == ["Tyrant of Valakut's triggered ability"]


def test_web_slinging_returns_a_tapped_creature():
    """Spiders-Man, Heroic Horde: "Web-slinging {4}{G}{G} ... When
    Spiders-Man enters, if they were cast using web-slinging, you gain 3 life
    and create two 2/1 green Spider creature tokens with reach." (CR
    702.188a)."""
    scenario = _board(["Forest"] * 6 + ["Grizzly Bears"], hand=["Spiders-Man, Heroic Horde"])
    bears = scenario.creature("Grizzly Bears")
    scenario.game.tap_permanent(bears)
    _cast(
        scenario,
        "Spiders-Man, Heroic Horde",
        *scenario.untapped_sources(*["Forest"] * 6),
        announce=lambda casting: casting.use_keyword("Web-slinging", choosing=[bears]),
    )
    assert bears.zone is Zone.HAND
    scenario.resolve_top()
    assert _triggers(scenario) == ["Spiders-Man, Heroic Horde's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 23


def test_web_slinging_refuses_an_untapped_creature():
    scenario = _board(["Forest"] * 6 + ["Grizzly Bears"], hand=["Spiders-Man, Heroic Horde"])
    casting = scenario.cast("Spiders-Man, Heroic Horde")
    with pytest.raises(ValueError):
        casting.use_keyword("Web-slinging", choosing=[scenario.creature("Grizzly Bears")])
        casting.begin_paying().pay()


def test_web_slinging_cast_normally_does_not_trigger():
    scenario = _board(["Forest"] * 2, hand=["Spiders-Man, Heroic Horde"])
    _cast(scenario, "Spiders-Man, Heroic Horde", *scenario.untapped_sources("Forest", "Forest"))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_prowl_cost_was_paid():
    """Latchkey Faerie: "Prowl {2}{U} ... When this creature enters, if its
    prowl cost was paid, draw a card." - Faerie Miscreant (a Faerie Rogue)
    dealt bob combat damage."""
    scenario = _board(["Faerie Miscreant", "Island", "Island", "Island"], hand=["Latchkey Faerie"])
    miscreant = scenario.creature("Faerie Miscreant")
    miscreant.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(miscreant)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    _cast(
        scenario,
        "Latchkey Faerie",
        *scenario.untapped_sources("Island", "Island", "Island"),
        announce=lambda casting: casting.use_keyword("Prowl"),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Latchkey Faerie's triggered ability"]


def test_spectacle_cost_was_paid():
    """Rafter Demon: "Spectacle {3}{B}{R} ... When this creature enters, if
    its spectacle cost was paid, each opponent discards a card." """
    scenario = _board(
        ["Swamp", "Swamp", "Swamp", "Mountain", "Mountain", "Mountain"],
        hand=["Lightning Bolt", "Rafter Demon"],
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _cast(
        scenario,
        "Rafter Demon",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Mountain", "Mountain"),
        announce=lambda casting: casting.use_keyword("Spectacle"),
    )
    scenario.resolve_top()
    assert _triggers(scenario) == ["Rafter Demon's triggered ability"]


def test_madness_cost_was_paid():
    """Grave Scrabbler: "Madness {1}{B} ... When this creature enters, if its
    madness cost was paid, you may return target creature card from a
    graveyard to its owner's hand." - discarded to Wild Mongrel, cast out of
    the madness exile."""
    scenario = _board(
        ["Wild Mongrel", "Swamp", "Swamp"], hand=["Grave Scrabbler"], graveyard=["Grizzly Bears"]
    )
    scrabbler = scenario.find("Grave Scrabbler", Zone.HAND, "alice")
    scenario.activate(scenario.creature("Wild Mongrel"), discarding=[scrabbler])
    assert scrabbler.zone is Zone.EXILE
    _cast(
        scenario,
        "Grave Scrabbler",
        *scenario.untapped_sources("Swamp", "Swamp"),
        announce=lambda casting: casting.use_keyword("Madness"),
        zone=Zone.EXILE,
    )
    scenario.resolve_top()
    scenario.will_choose_targets(scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice"))
    assert "Grave Scrabbler's triggered ability" in _triggers(scenario)


def test_cast_normally_its_madness_cost_was_not_paid():
    scenario = _board(["Swamp"] * 4, hand=["Grave Scrabbler"])
    _cast(scenario, "Grave Scrabbler", *scenario.untapped_sources(*["Swamp"] * 4))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_sneak_cost_was_paid():
    """Leonardo, Leader in Blue: "When Leonardo enters, if his sneak cost was
    paid, creatures you control get +2/+0 until end of turn." """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Leonardo, Leader in Blue"],
            battlefield=["Grizzly Bears", *["Plains"] * 5],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    card = scenario.find("Leonardo, Leader in Blue", Zone.HAND, "alice")
    scenario.game.cast(
        card,
        "alice",
        keyword="Sneak",
        choosing=[bears],
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    scenario.resolve_top()
    assert "Leonardo, Leader in Blue's triggered ability" in _triggers(scenario)


# -- optional additional costs printed as a sentence ------------------------------------


def test_evidence_was_collected():
    """Vitu-Ghazi Inspector: "As an additional cost to cast this spell, you
    may collect evidence 6. ... When this creature enters, if evidence was
    collected, put a +1/+1 counter on target creature and you gain 2 life." """
    scenario = _board(["Forest", "Forest"], hand=["Vitu-Ghazi Inspector"], graveyard=["Craw Wurm"])
    _cast(
        scenario,
        "Vitu-Ghazi Inspector",
        *scenario.untapped_sources("Forest", "Forest"),
        announce=lambda casting: casting.collect_evidence(),
    )
    assert scenario.find("Craw Wurm", Zone.EXILE) is not None
    scenario.resolve_top()
    scenario.will_choose_targets(scenario.creature("Vitu-Ghazi Inspector"))
    assert _triggers(scenario) == ["Vitu-Ghazi Inspector's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22


def test_evidence_below_the_threshold_cannot_be_collected():
    """CR 701.59a: total mana value 6 or greater - Grizzly Bears is 2."""
    scenario = _board(
        ["Forest", "Forest"], hand=["Vitu-Ghazi Inspector"], graveyard=["Grizzly Bears"]
    )
    casting = scenario.cast("Vitu-Ghazi Inspector")
    with pytest.raises(ValueError):
        casting.collect_evidence()
        casting.begin_paying().pay()


def test_no_evidence_collected_never_triggers():
    scenario = _board(["Forest", "Forest"], hand=["Vitu-Ghazi Inspector"], graveyard=["Craw Wurm"])
    _cast(scenario, "Vitu-Ghazi Inspector", *scenario.untapped_sources("Forest", "Forest"))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_revealed_a_dragon_card():
    """Orator of Ojutai: "As an additional cost to cast this spell, you may
    reveal a Dragon card from your hand. ... When this creature enters, if you
    revealed a Dragon card or controlled a Dragon as you cast this spell,
    draw a card." """
    scenario = _board(["Plains", "Plains"], hand=["Orator of Ojutai", "Siege Dragon"])
    dragon = scenario.find("Siege Dragon", Zone.HAND, "alice")
    _cast(
        scenario,
        "Orator of Ojutai",
        *scenario.untapped_sources("Plains", "Plains"),
        announce=lambda casting: casting.reveal_for_cost(dragon),
    )
    assert dragon.zone is Zone.HAND
    scenario.resolve_top()
    assert _triggers(scenario) == ["Orator of Ojutai's triggered ability"]


def test_controlled_a_dragon_as_you_cast_it():
    scenario = _board(["Plains", "Plains", "Siege Dragon"], hand=["Orator of Ojutai"])
    _cast(scenario, "Orator of Ojutai", *scenario.untapped_sources("Plains", "Plains"))
    scenario.resolve_top()
    assert _triggers(scenario) == ["Orator of Ojutai's triggered ability"]


def test_neither_revealed_nor_controlled():
    scenario = _board(["Plains", "Plains"], hand=["Orator of Ojutai", "Siege Dragon"])
    _cast(scenario, "Orator of Ojutai", *scenario.untapped_sources("Plains", "Plains"))
    scenario.resolve_top()
    _no_trigger(scenario)


def test_revealing_a_card_that_is_not_a_dragon_is_refused():
    scenario = _board(["Plains", "Plains"], hand=["Orator of Ojutai", "Grizzly Bears"])
    casting = scenario.cast("Orator of Ojutai")
    with pytest.raises(ValueError):
        casting.reveal_for_cost(scenario.find("Grizzly Bears", Zone.HAND, "alice"))


# -- tribute ----------------------------------------------------------------------------


def test_tribute_not_paid_triggers():
    """Snake of the Golden Grove: "Tribute 3 ... When this creature enters, if
    tribute wasn't paid, you gain 4 life." - bob declines."""
    scenario = _board(["Forest"] * 5, hand=["Snake of the Golden Grove"])
    scenario.will_take_the_may(False, username="bob")
    scenario.cast_and_resolve(
        "Snake of the Golden Grove", *scenario.untapped_sources(*["Forest"] * 5)
    )
    snake = scenario.creature("Snake of the Golden Grove")
    assert snake.counter_count("+1/+1") == 0
    assert _triggers(scenario) == ["Snake of the Golden Grove's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 24


def test_tribute_paid_puts_the_counters_and_never_triggers():
    """Bob puts the three counters on it: tribute was paid."""
    scenario = _board(["Forest"] * 5, hand=["Snake of the Golden Grove"])
    scenario.will_take_the_may(True, username="bob")
    scenario.cast_and_resolve(
        "Snake of the Golden Grove", *scenario.untapped_sources(*["Forest"] * 5)
    )
    snake = scenario.creature("Snake of the Golden Grove")
    assert snake.counter_count("+1/+1") == 3
    _no_trigger(scenario)


def test_tribute_on_a_creature_put_onto_the_battlefield():
    """CR 702.104a functions as the creature enters, cast or not."""
    scenario = _board([], hand=["Ornitharch"])
    scenario.will_take_the_may(False, username="bob")
    scenario.put_onto_battlefield("Ornitharch", "alice")
    assert _triggers(scenario) == ["Ornitharch's triggered ability"]
    scenario.pass_until_resolved()
    birds = [s for s in scenario.game.permanents_controlled_by("alice") if s.token]
    assert len(birds) == 2


def test_the_controllers_own_counters_are_not_tribute():
    """Alice's own +1/+1 counters are not an opponent's tribute: still not
    paid."""
    scenario = _board(["Forest"] * 5, hand=["Snake of the Golden Grove"])
    scenario.will_take_the_may(False, username="bob")
    scenario.cast_and_resolve(
        "Snake of the Golden Grove", *scenario.untapped_sources(*["Forest"] * 5)
    )
    scenario.game.add_counters(scenario.creature("Snake of the Golden Grove"), "+1/+1", 3)
    assert _triggers(scenario) == ["Snake of the Golden Grove's triggered ability"]
