"""Scenario: prevention effects, and the damage source they ask about (CR 615).

Prevention is a rule of its own, not a flavour of replacement. CR 615.1 says the
two behave alike - "Like replacement effects (see rule 614), prevention effects
apply continuously as events happen" - and then CR 615.3 through CR 615.12 add a
half-dozen things replacement effects have no equivalent of: a shield with an
amount that counts down, a shield that spends itself on one instance, a recheck
of the source's properties every time, and a rule for damage that can't be
prevented at all.

Almost all of it turns on one fact the damage event did not carry until now: who
is dealing the damage. CR 120.1 - "An object that deals damage is the source of
that damage" - and with the source on the event, CR 609.7b, CR 615.8 and
CR 702.16e all become writable.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and read in full out of the
`2026-08-19` Comprehensive Rules release that
`knowledge_search(type="cr_versions")` names as current, downloaded from its
`source_url` and verified against its published sha256.

- **CR 120.1 / CR 120.7** - the source of damage is the object that dealt it.
- **CR 615.1 / CR 615.1a** - prevention effects are continuous effects that use
  the word "prevent" to say what damage will not be dealt.
- **CR 615.3** - "Such effects last until they're used up or their duration has
  expired."
- **CR 615.4** - "Prevention effects must exist before the appropriate damage
  event occurs - they can't 'go back in time'."
- **CR 615.7** - a shield of N damage: "Each 1 damage that would be dealt ... is
  prevented. Preventing 1 damage reduces the remaining shield by 1 ... Once the
  shield has been reduced to 0, any remaining damage is dealt normally."
- **CR 615.8** - the next-instance shield: "prevent the next instance of damage
  from that source, regardless of how much damage that is."
- **CR 615.9 / CR 609.7b** - "the shield rechecks the source's properties. If the
  properties no longer match, the damage isn't prevented ... If for any reason
  the shield prevents no damage ... the shield isn't used up."
- **CR 702.16e** - "Any damage that would be dealt by sources that have the
  stated quality to a permanent or player with protection is prevented."
- **CR 514.2** - the cleanup step ends every "this turn" effect, a shield among
  them.
- **CR 704.5g** - lethal damage is a state-based action, checked after the fact,
  which is why prevented damage never kills anything.

The engine side is `Game.create_prevention_shield` and the `PreventionShield`
model in `models/game.py`; the shields are gathered into the same CR 616.1
ordering as replacement effects by `machines/replacement.py`.

Fog, Angelsong, Bandage and Awe Strike are all in the card pool and all parse as
prevention effects. Most of this file builds the shields directly, so that one
rule of CR 615 is under test at a time; the section at the bottom casts the
cards, which have `machines/effects.py` entries now.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import PreventionShield, ShieldKind
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    """Alice with a Bolt and a Mountain; Bob with a bear and a wall."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"])
        .player("bob", battlefield=["Grizzly Bears", "Fog Bank"], library=["Island"])
    )


def _bolt_state(scenario):
    """The Lightning Bolt as a real object, so it can be a damage source.

    CR 120.7 lets a source be "a spell on the stack", and a Bolt in hand is the
    same card - what matters here is that the source is the real printing, with
    its real colours and card types, and not a stand-in.
    """
    return scenario.find("Lightning Bolt", Zone.HAND, "alice")


# -- the source on the event ----------------------------------------------


def test_damage_dealt_with_a_source_still_lands_normally():
    """CR 120.1: naming the source changes nothing on its own.

    The regression guard for the whole file. Adding a source to the event must
    not make ordinary damage behave differently; it must only make the rules
    that ask about the source answerable.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    dealt = scenario.game.deal_damage(bears, 2, source=_bolt_state(scenario))

    assert dealt == 2
    assert bears.damage == 2


def test_deal_damage_reports_how_much_actually_landed():
    """CR 702.2b's deathtouch and CR 702.15b's lifelink both key off damage that
    was *dealt*, and prevented damage was not dealt.

    Reporting it is what lets a caller stop measuring a life-total delta to find
    out: `machines/combat._deal_combat_damage` reads this return value and
    applies deathtouch and lifelink only when it is above zero.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to target creature this turn",
            controller="bob",
            card_id=bears.id,
        )
    )

    dealt = scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario))

    assert dealt == 0
    assert bears.damage == 0


# -- protection as a prevention effect (CR 702.16e) ------------------------


def test_protection_prevents_damage_from_a_source_with_the_stated_quality():
    """CR 702.16e: "Any damage that would be dealt by sources that have the
    stated quality to a permanent or player with protection is prevented."

    Emrakul, the Promised End has "protection from instants" and Lightning Bolt
    is an Instant. Note this damage never targeted anything - CR 702.16b's
    targeting half would not have caught it - so the prevention half is doing
    all the work.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"])
        .player("bob", battlefield=["Emrakul, the Promised End"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    dealt = scenario.game.deal_damage(emrakul, 3, source=_bolt_state(scenario))

    assert dealt == 0
    assert emrakul.damage == 0


def test_protection_does_not_prevent_damage_from_a_source_without_the_quality():
    """CR 702.16a: the quality is what the ability names, and nothing wider.

    Grizzly Bears is a Creature, not an Instant, so protection from instants has
    nothing to say about it. A protection implementation that prevented
    everything would pass the test above and fail this one.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"], library=["Island"])
        .player("bob", battlefield=["Emrakul, the Promised End"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    dealt = scenario.game.deal_damage(emrakul, 2, source=bears)

    assert dealt == 2
    assert emrakul.damage == 2


def test_protection_does_not_prevent_damage_from_an_unnamed_source():
    """CR 702.16e asks about the *source's* qualities, and an anonymous damage
    event has no source to ask about.

    Failing open here is the honest behaviour and it is a documented gap, not a
    rule. `machines/combat._deal_combat_damage` does name its source now, so
    combat damage *is* checked against protection; what remains anonymous is
    damage from `machines/effects.py` and from a direct `deal_damage` call with
    no `source=`, which is what this test makes. Written down as a test so the
    gap is tracked rather than silent.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"])
        .player("bob", battlefield=["Emrakul, the Promised End"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    dealt = scenario.game.deal_damage(emrakul, 3)

    assert dealt == 3, "not a rule - the gap where the caller says nothing"


# -- CR 615.7: a shield with an amount -------------------------------------


def test_a_shield_of_one_lets_the_rest_of_the_damage_through():
    """CR 615.7: "Once the shield has been reduced to 0, any remaining damage is
    dealt normally."

    Bandage's shape - "prevent the next 1 damage that would be dealt to any
    target this turn" - against a Bolt. Two of the three land.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label="prevent the next 1 damage that would be dealt to any target this turn",
            controller="bob",
            card_id=bears.id,
            amount=1,
        )
    )

    dealt = scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario))

    assert dealt == 2
    assert bears.damage == 2


def test_a_shield_counts_down_across_separate_damage_events():
    """CR 615.7: "Such effects count only the amount of damage; the number of
    events or sources dealing it doesn't matter."

    A shield of 2 spread over two 1-damage events is used up by them together,
    and the third point lands.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bolt = _bolt_state(scenario)
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label="prevent the next 2 damage that would be dealt to this creature this turn",
            controller="bob",
            card_id=bears.id,
            amount=2,
        )
    )

    assert scenario.game.deal_damage(bears, 1, source=bolt) == 0
    assert scenario.game.deal_damage(bears, 1, source=bolt) == 0
    assert scenario.game.deal_damage(bears, 1, source=bolt) == 1
    assert bears.damage == 1


def test_a_shield_keeps_a_creature_alive_through_lethal_damage():
    """CR 615.6: "If damage that would be dealt is prevented, it never happens."

    So there is no marked damage for CR 704.5g to find, and the state-based
    action does not destroy the creature. Prevented damage is not damage dealt
    and then undone.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to this creature this turn",
            controller="bob",
            card_id=bears.id,
        )
    )

    scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario))
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_a_shield_on_a_player_stops_the_life_loss():
    """CR 615.7 shields "the 'shielded' permanent *or player*".

    CR 120.3a: "Damage dealt to a player by a source without infect causes that
    player to lose that much life." So a prevented event costs no life at all,
    rather than costing it and giving it back.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label="prevent the next 3 damage that would be dealt to you this turn",
            controller="bob",
            player="bob",
            amount=3,
        )
    )

    scenario.game.deal_damage(scenario.player("bob"), 3, source=_bolt_state(scenario))

    assert scenario.player("bob").life == 20


def test_a_shield_on_one_creature_does_not_protect_another():
    """A shield is around "whatever they're affecting" (CR 615.1), and no more."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wall = scenario.creature("Fog Bank", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label="prevent the next 2 damage that would be dealt to target creature this turn",
            controller="bob",
            card_id=bears.id,
            amount=2,
        )
    )

    assert scenario.game.deal_damage(wall, 2, source=_bolt_state(scenario)) == 2


# -- CR 615.8: the next instance from a source -----------------------------


def test_a_next_instance_shield_prevents_one_whole_instance_whatever_its_size():
    """CR 615.8: "These effects prevent the next instance of damage from that
    source, regardless of how much damage that is."

    Awe Strike's shape. Three damage is one instance, so all three go, and the
    shield is spent by the one instance rather than by three points.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bolt = _bolt_state(scenario)
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="the next time this source would deal damage this turn, prevent it",
            controller="bob",
            source_id=bolt.id,
        )
    )

    assert scenario.game.deal_damage(bears, 3, source=bolt) == 0


def test_a_next_instance_shield_lets_the_instance_after_it_through():
    """CR 615.8: "Once an instance of damage from that source has been
    prevented, any subsequent instances of damage that would be dealt by that
    source are dealt normally."
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bolt = _bolt_state(scenario)
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="the next time this source would deal damage this turn, prevent it",
            controller="bob",
            source_id=bolt.id,
        )
    )

    scenario.game.deal_damage(bears, 3, source=bolt)

    assert scenario.game.deal_damage(bears, 1, source=bolt) == 1


def test_a_shield_naming_one_source_ignores_damage_from_another():
    """CR 615.8 names "a specific source", and CR 609.7a fixes it when the effect
    is created. Damage from anything else is simply not this shield's business.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wall = scenario.creature("Fog Bank", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="the next time Lightning Bolt would deal damage this turn, prevent it",
            controller="bob",
            source_id=_bolt_state(scenario).id,
        )
    )

    assert scenario.game.deal_damage(bears, 2, source=wall) == 2


# -- CR 615.9 / CR 609.7b: rechecking the source's properties --------------


def test_a_shield_against_a_red_source_prevents_a_red_source():
    """CR 615.9: a shield "from a source of a player's choice with certain
    properties", rechecked when the damage would be dealt.

    Lightning Bolt is red, so a shield against red sources catches it.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="the next time a red source would deal damage to you this turn, prevent it",
            controller="bob",
            source_quality="red",
        )
    )

    assert scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario)) == 0


def test_a_shield_against_a_red_source_is_not_used_up_by_a_blue_one():
    """CR 609.7b, both sentences: "If the properties no longer match, the damage
    isn't prevented or replaced. If for any reason the shield prevents no damage
    ... the shield isn't used up."

    Fog Bank is blue, so it goes straight through and leaves the shield intact
    for the red source that follows. A shield that spent itself on the miss
    would pass the first assertion and fail the second.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wall = scenario.creature("Fog Bank", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="the next time a red source would deal damage this turn, prevent it",
            controller="bob",
            source_quality="red",
        )
    )

    assert scenario.game.deal_damage(bears, 1, source=wall) == 1
    assert scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario)) == 0


# -- CR 615.3 / CR 514.2: the duration -------------------------------------


def test_an_unused_shield_ends_in_the_cleanup_step():
    """CR 514.2 ends "all 'until end of turn' and 'this turn' effects", and
    CR 615.3 gives a prevention effect a duration like any other.

    A shield that survived the turn would quietly make a Fog permanent.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all combat damage that would be dealt this turn",
            controller="alice",
            card_id=bears.id,
        )
    )

    scenario.start_at(Step.CLEANUP)
    scenario.game.cleanup_step()

    assert scenario.game.active_prevention_shields() == []
    assert scenario.game.deal_damage(bears, 2, source=_bolt_state(scenario)) == 2


def test_a_shield_without_a_duration_survives_the_cleanup_step():
    """Not every prevention effect is a "this turn" one - CR 615.3 says they last
    "until they're used up *or* their duration has expired", and an effect with
    no stated duration has none to expire.

    The flag exists so that the cleanup step ends what CR 514.2 names and
    nothing else.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to this creature",
            controller="bob",
            card_id=bears.id,
            until_end_of_turn=False,
        )
    )

    scenario.start_at(Step.CLEANUP)
    scenario.game.cleanup_step()

    assert scenario.game.deal_damage(bears, 2, source=_bolt_state(scenario)) == 0


def test_a_shield_created_after_the_damage_does_nothing_about_it():
    """CR 615.4: "Prevention effects must exist before the appropriate damage
    event occurs - they can't 'go back in time' and change something that's
    already happened."

    The rule reads as obvious and is the one a store of shields could most
    easily get wrong, by rebuilding the shield list from the board each time
    instead of from when each shield was made.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.deal_damage(bears, 2, source=_bolt_state(scenario))
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to this creature this turn",
            controller="bob",
            card_id=bears.id,
        )
    )

    assert bears.damage == 2


# -- combat-only prevention ------------------------------------------------


def test_a_combat_only_shield_ignores_a_spell_s_damage():
    """CR 510.2 makes combat damage a kind of its own, and Fog's "prevent all
    combat damage that would be dealt this turn" says so in as many words.

    A Bolt is not combat damage, so a Fog does nothing about it - the case that
    distinguishes a real reading of the card from "prevent everything".
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all combat damage that would be dealt this turn",
            controller="bob",
            card_id=bears.id,
            combat_only=True,
        )
    )

    assert scenario.game.deal_damage(bears, 3, source=_bolt_state(scenario)) == 3


# -- through the real cards ------------------------------------------------


def test_fog_prevents_the_whole_combat_damage_step():
    """Fog: "Prevent all combat damage that would be dealt this turn."

    Neither a permanent nor a player is named, so the shield protects everything
    - CR 615.1 calls a prevention effect a "shield around whatever [it is]
    affecting", and here that is the whole board. CR 615.3's other ending is the
    one that applies: an `ALL` shield is never used up, it expires.

    The attacker still attacked and still assigned its damage; CR 615.1a is
    explicit that "prevention effects use 'prevent' to indicate what damage will
    **not be dealt**", so nothing is dealt and undone.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fog"], battlefield=["Grizzly Bears", "Forest"], library=["Island"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Fog", forest, username="alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20


def test_fog_does_nothing_about_a_burn_spell():
    """The other half of "all **combat** damage" (CR 510.2), through the card.

    Cast for real this time, so it is the registry entry's `combat_only` and not
    a hand-built shield being checked.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fog", "Lightning Bolt"],
            battlefield=["Forest", "Mountain"],
            library=["Island"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Fog", forest, username="alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 17


def test_bandage_takes_one_off_the_next_damage_and_draws():
    """Bandage: "Prevent the next 1 damage that would be dealt to any target this
    turn. Draw a card."

    CR 615.7's counting shield, at its smallest: 1 damage is prevented, the
    shield drops to 0, and "any remaining damage is dealt normally" - so a Bolt
    aimed at the shielded creature deals 2 of its 3. The draw is the second
    instruction and happens in printed order (CR 608.2c).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bandage", "Lightning Bolt"],
            battlefield=["Plains", "Mountain"],
            library=["Island"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Bandage", plains, username="alice", targets=[dreadmaw])
    assert [state.card.name for state in scenario.player("alice").hand] == [
        "Lightning Bolt",
        "Island",
    ], "the draw happened"

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[dreadmaw])

    assert dreadmaw.damage == 2, "1 of the 3 was prevented (CR 615.7)"


def test_bandage_shields_a_player_too():
    """ "any target" is a permanent **or a player** (CR 115.1), and CR 615.7 says
    the shield goes around "the 'shielded' permanent or player" either way.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bandage", "Lightning Bolt"],
            battlefield=["Plains", "Mountain"],
            library=["Island"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Bandage", plains, username="alice", targets=["bob"])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 18


def test_awe_strike_prevents_the_next_damage_that_creature_would_deal():
    """Awe Strike: "The next time target creature would deal damage this turn,
    prevent that damage."

    CR 615.8: the shield names a **source**, not a shielded object, and prevents
    "the next instance of damage from that source, regardless of how much damage
    that is". So it is the attacker that is shielded against, and the damage is
    prevented wherever it was headed.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Awe Strike"], battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    dreadmaw.summoning_sick = False

    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Awe Strike", plains, username="alice", targets=[dreadmaw])

    scenario.game.turn.active_index = 1
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dreadmaw, defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    # All six were prevented (CR 615.8), so no life is lost - and Awe Strike's
    # own CR 615.5 rider gains it right back: 20 + 6.
    assert scenario.player("alice").life == 26, "all six were prevented (CR 615.8)"


def test_awe_strike_is_spent_on_one_instance():
    """CR 615.8's second sentence: "Once an instance of damage from that source
    has been prevented, any subsequent instances of damage that would be dealt by
    that source are dealt normally."

    One shield, two instances: the first is prevented whole and the second lands
    whole.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Awe Strike"], battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Awe Strike", plains, username="alice", targets=[dreadmaw])

    first = scenario.game.deal_damage(scenario.player("alice"), 6, source=dreadmaw)
    second = scenario.game.deal_damage(scenario.player("alice"), 6, source=dreadmaw)

    assert (first, second) == (0, 6)
    # The first instance is prevented and Awe Strike's rider gains 6 for it
    # (CR 615.5), the second lands whole: 20 + 6 - 6.
    assert scenario.player("alice").life == 20


def test_a_shield_records_how_much_it_actually_prevented():
    """CR 615.5's first half: "Some prevention effects also include an additional
    effect, **which may refer to the amount of damage that was prevented**."

    The amount has to be recorded before any rider can refer to it, and CR 609.7b
    says what "prevented" means when the shield was consulted and did nothing:
    "If for any reason the shield prevents no damage or replaces no damage, the
    shield isn't used up." A shield that ate three of five points prevented three;
    the two that got through are not its.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shield = scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.AMOUNT,
            label="prevent the next 3 damage that would be dealt to alice this turn",
            controller="alice",
            player="alice",
            amount=3,
        )
    )

    dealt = scenario.game.deal_damage(scenario.player("alice"), 5)

    assert dealt == 2, "three of the five were prevented (CR 615.7)"
    assert shield.prevented == 3
    assert shield.spent


def test_a_shield_that_prevented_nothing_records_nothing():
    """CR 609.7b, the sentence that decides both fields at once: "If for any
    reason the shield prevents no damage or replaces no damage, the shield isn't
    used up."

    A CR 615.8 next-instance shield naming a source that is not the one dealing
    the damage is consulted and does nothing, so it is neither used up nor
    credited with an amount - which is what stops a CR 615.5 rider firing for
    nought.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw", "Grizzly Bears"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    shield = scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="prevent the next damage Colossal Dreadmaw would deal this turn",
            controller="alice",
            source_id=dreadmaw.id,
        )
    )

    dealt = scenario.game.deal_damage(scenario.player("alice"), 2, source=bears)

    assert dealt == 2
    assert shield.prevented == 0
    assert not shield.used_up


def test_the_rider_gains_the_life_immediately_after_the_prevention():
    """CR 615.5's second half: "The prevention takes place at the time the
    original event would have happened; **the rest of the effect takes place
    immediately afterward**."

    Which is why the life cannot be gained when the spell resolves: at that
    moment the amount does not exist, because the damage event it refers to has
    not been offered yet. It is gained at the damage event, from what the shield
    actually ate.

    The shield is built here rather than cast off Awe Strike because
    `machines/effects.py` does not yet switch the rider on - see the xfail below.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    shield = scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.NEXT_INSTANCE,
            label="prevent the next damage Colossal Dreadmaw would deal this turn",
            controller="alice",
            source_id=dreadmaw.id,
            gains_life_when_prevented=True,
        )
    )
    before = scenario.player("alice").life

    scenario.game.deal_damage(scenario.player("alice"), 6, source=dreadmaw)

    assert shield.prevented == 6
    assert scenario.player("alice").life == before + 6


def test_awe_strike_gains_life_equal_to_the_damage_prevented():
    """CR 615.5: "Some prevention effects also include an additional effect,
    which may refer to the amount of damage that was prevented. The prevention
    takes place at the time the original event would have happened; the rest of
    the effect takes place immediately afterward."

    A 6/6 Dreadmaw prevented is 6 life, and it arrives *after* the prevention
    rather than when Awe Strike resolved - which is why nothing can be gained at
    resolution time even in principle.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Awe Strike"], battlefield=["Plains"], library=["Island"])
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_and_resolve("Awe Strike", plains, username="alice", targets=[dreadmaw])

    scenario.game.deal_damage(scenario.player("alice"), 6, source=dreadmaw)

    assert scenario.player("alice").life == 26
