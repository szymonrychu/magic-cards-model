"""Scenario: decayed (CR 702.147a).

Read out of the Comprehensive Rules on disk this session with `mise run
rules:find 702.147`, `mise run rules:find 122.1`, `mise run rules:find 509.1`,
`mise run rules:find 603.7` and `mise run rules:find 511`:

- **CR 702.147a** - "Decayed represents a static ability and a triggered
  ability. 'Decayed' means 'This creature can't block' and 'When this
  creature attacks, sacrifice it at end of combat.'"
- **CR 122.1b** - "A keyword counter on a permanent or on a card in a zone
  other than the battlefield causes that object to gain that keyword. The
  keywords that a keyword counter can be are flying, first strike, double
  strike, deathtouch, decayed, exalted, haste, hexproof, indestructible,
  lifelink, menace, reach, shadow, trample, and vigilance, as well as any
  variants of those keywords."
- **CR 509.1b** - "The defending player checks each creature they control to
  see whether it's affected by any restrictions (effects that say a creature
  can't block, or that it can't block unless some condition is met). If any
  restrictions are being disobeyed, the declaration of blockers is illegal."
- **CR 603.7c** - "if that object is no longer in the zone it's expected to be
  in at the time the delayed triggered ability resolves, the ability won't
  affect it."
- **CR 511.2** - "Abilities that trigger 'at end of combat' trigger as the end
  of combat step begins."

Two printings, both already in the pool: Rot-Curse Rakshasa (Trample, Decayed;
"Renew — {X}{B}{B}, Exile this card from your graveyard: Put a decayed
counter on each of X target creatures. Activate only as a sorcery." - CR
122.1b's keyword counter) and Jadar, Ghoulcaller of Nephalia ("At the
beginning of your end step, if you control no creatures with decayed, create
a 2/2 black Zombie creature token with decayed." - the printed keyword, a
keyword counter, and a token's own keyword all read the same way).

The static half ("can't block") is `machines/combat.py::block_refusal`'s own
`has_keyword` check; the triggered half ("sacrifice it at end of combat") is
`machines/keywords.py::_decayed_ability` (`_TRIGGER_EXPANSIONS`), whose effect
text `machines/effects.py::_parse_delayed_single_clause` reads as a CR 603.7
delayed trigger waiting for the end of combat step.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import executes
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import TargetRef
from magic_cards_model.models.zone import Zone

from ..cards import card
from .harness import PlayedScenario, Scenario

RAKSHASA = "Rot-Curse Rakshasa"
JADAR = "Jadar, Ghoulcaller of Nephalia"


def _resolve_everything(scenario: PlayedScenario) -> None:
    """Put whatever has triggered on the stack (CR 603.3) and resolve it all,
    including anything those resolutions trigger in turn."""
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def walk_to(scenario: PlayedScenario, step: Step) -> None:
    """Advance - never jump - to `step`, resolving whatever fires on the way.
    `start_at` emits no step events, so a delayed "at end of combat" trigger
    (or Jadar's "at the beginning of your end step") is only proven by walking
    there (CR 511.2)."""
    while scenario.step is not step:
        scenario.advance()
        _resolve_everything(scenario)


# -- the keyword is executed, and no longer reported as ignored -------------


def test_decayed_is_reported_as_executed_by_the_keyword_module():
    assert executes("decayed")


def test_support_no_longer_lists_decayed_as_ignored_for_rot_curse_rakshasa():
    from magic_cards_model.support import ignored_keywords

    assert "Decayed" not in ignored_keywords(card(RAKSHASA))


def test_card_support_classifies_the_decayed_line_as_handled():
    from magic_cards_model.support import card_support

    support = card_support(card(RAKSHASA))
    decayed_clauses = [c for c in support.clauses if c.kind == "keyword" and c.text == "Decayed"]
    assert len(decayed_clauses) == 1
    assert decayed_clauses[0].outcome == "handled"


# -- static half: a decayed creature can't block (CR 509.1b) ----------------


def test_a_printed_decayed_creature_cannot_be_declared_as_a_blocker():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=["Grizzly Bears"])
        .player("bob", library=["Island"] * 4, battlefield=[RAKSHASA])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    rakshasa = scenario.creature(RAKSHASA, "bob")

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)

    refusal = scenario.game.why_cannot_block(rakshasa, attacker)
    assert refusal is not None
    assert "decayed" in refusal.lower()
    assert "702.147a" in refusal

    with pytest.raises(ValueError, match="decayed"):
        scenario.block(attacker, rakshasa)


def test_a_decayed_creature_is_not_offered_as_a_legal_blocker():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=["Grizzly Bears"])
        .player("bob", library=["Island"] * 4, battlefield=[RAKSHASA])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    rakshasa = scenario.creature(RAKSHASA, "bob")

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)

    actions = legal_actions(scenario.game, "bob")
    block_actions = [a for a in actions if a.kind is ActionKind.DECLARE_BLOCKER]
    assert all(a.card_id != rakshasa.id for a in block_actions)


def test_a_decayed_creature_can_still_attack():
    """CR 702.147a's static half is "can't block" only - nothing stops a
    decayed creature attacking (it can't block *and* is sacrificed later, but
    neither restricts declaring it as an attacker, CR 508.1a)."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=[RAKSHASA])
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rakshasa = scenario.creature(RAKSHASA, "alice")

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(rakshasa)
    scenario.attack_with(rakshasa)
    assert rakshasa in scenario.attackers()


# -- triggered half: sacrificed at end of combat (CR 603.7, CR 511.2) -------


def test_attacking_deals_combat_damage_then_sacrifices_it_at_end_of_combat():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=[RAKSHASA])
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rakshasa = scenario.creature(RAKSHASA, "alice")

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(rakshasa)
    _resolve_everything(scenario)

    walk_to(scenario, Step.COMBAT_DAMAGE)
    assert rakshasa.zone is Zone.BATTLEFIELD, "still deals its combat damage"
    assert scenario.player("bob").life == 15  # 20 - 5 power, unblocked

    walk_to(scenario, Step.END_OF_COMBAT)
    assert rakshasa.zone is Zone.GRAVEYARD
    assert rakshasa.owner == "alice"


def test_not_attacking_does_not_sacrifice_it():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=[RAKSHASA])
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rakshasa = scenario.creature(RAKSHASA, "alice")

    walk_to(scenario, Step.END_OF_COMBAT)
    assert rakshasa.zone is Zone.BATTLEFIELD


def test_a_creature_that_left_the_battlefield_before_end_of_combat_is_not_sacrificed_again():
    """CR 603.7c: bounced by Unsummon after combat damage but before the end
    of combat step begins - a new object in alice's hand already, so the
    delayed trigger finds nothing on the battlefield to sacrifice and does
    nothing else."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            hand=["Unsummon"],
            battlefield=[RAKSHASA, "Island"],
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rakshasa = scenario.creature(RAKSHASA, "alice")

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(rakshasa)
    _resolve_everything(scenario)
    walk_to(scenario, Step.COMBAT_DAMAGE)
    assert scenario.player("bob").life == 15

    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Unsummon", island, targets=[TargetRef.coerce(rakshasa)])
    assert rakshasa.zone is Zone.HAND

    walk_to(scenario, Step.END_OF_COMBAT)
    assert rakshasa.zone is Zone.HAND
    assert rakshasa not in scenario.player("alice").graveyard


# -- CR 122.1b: a decayed keyword counter (Rot-Curse Rakshasa's Renew) ------


def _renew_a_decayed_counter_onto(scenario: PlayedScenario, target) -> None:
    rakshasa = scenario.find(RAKSHASA, Zone.GRAVEYARD, "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.activate(
        rakshasa, *swamps, exiling=[rakshasa], x_value=1, targets=[TargetRef.coerce(target)]
    )
    scenario.pass_until_resolved()


def test_renew_puts_a_decayed_counter_on_the_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            graveyard=[RAKSHASA],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _renew_a_decayed_counter_onto(scenario, bears)

    assert bears.counters["decayed"] == 1
    assert has_keyword(bears, Keyword.DECAYED, scenario.game)


def test_a_renewed_creature_cannot_block():
    # Bob is registered first, so his is the first turn - Renew is "activate
    # only as a sorcery" (Rot-Curse Rakshasa's own line), which needs it to be
    # bob's own turn. Combat happens the turn after, when alice attacks and
    # bob's now-decayed Grizzly Bears tries to block it.
    scenario = (
        Scenario()
        .player(
            "bob",
            library=["Island"] * 6,
            graveyard=[RAKSHASA],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("alice", library=["Island"] * 6, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blocker = scenario.creature("Grizzly Bears", "bob")
    attacker = scenario.creature("Grizzly Bears", "alice")

    rakshasa = scenario.find(RAKSHASA, Zone.GRAVEYARD, "bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="bob")
    scenario.activate(
        rakshasa,
        *swamps,
        exiling=[rakshasa],
        username="bob",
        x_value=1,
        targets=[TargetRef.coerce(blocker)],
    )
    scenario.pass_until_resolved()
    assert blocker.counters["decayed"] == 1

    walk_to(scenario, Step.CLEANUP)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)

    refusal = scenario.game.why_cannot_block(blocker, attacker)
    assert refusal is not None
    assert "decayed" in refusal.lower()


def test_a_renewed_creature_is_sacrificed_after_attacking():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            graveyard=[RAKSHASA],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _renew_a_decayed_counter_onto(scenario, bears)
    assert bears.counters["decayed"] == 1

    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_everything(scenario)

    walk_to(scenario, Step.COMBAT_DAMAGE)
    assert bears.zone is Zone.BATTLEFIELD, "still deals its combat damage"
    assert scenario.player("bob").life == 18  # 20 - 2 power, unblocked

    walk_to(scenario, Step.END_OF_COMBAT)
    assert bears.zone is Zone.GRAVEYARD


# -- Jadar's own decayed Zombie token ----------------------------------------


def _jadar_token(scenario: PlayedScenario):
    return next(c for c in scenario.game.battlefield if c.token)


def test_jadar_creates_a_decayed_zombie_token_at_its_controllers_end_step():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 10, battlefield=[JADAR])
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walk_to(scenario, Step.END_STEP)
    _resolve_everything(scenario)

    tokens = [c for c in scenario.game.battlefield if c.token]
    assert len(tokens) == 1
    token = tokens[0]
    assert token.power == 2
    assert token.toughness == 2
    assert has_keyword(token, Keyword.DECAYED, scenario.game)


def test_jadar_token_cannot_block_and_is_sacrificed_after_attacking():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 10, battlefield=[JADAR])
        .player("bob", library=["Island"] * 10, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walk_to(scenario, Step.END_STEP)
    _resolve_everything(scenario)
    token = _jadar_token(scenario)

    # The token can't block (CR 702.147a) - proven the turn it entered play,
    # against bob's own attack.
    walk_to(scenario, Step.CLEANUP)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_ATTACKERS)
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bob_bears, defending="alice")
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_BLOCKERS)
    assert scenario.game.why_cannot_block(token, bob_bears) is not None
    walk_to(scenario, Step.END_OF_COMBAT)

    # Now alice attacks with her own token and it is sacrificed after damage.
    walk_to(scenario, Step.CLEANUP)
    _resolve_everything(scenario)
    walk_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(token)
    _resolve_everything(scenario)
    walk_to(scenario, Step.COMBAT_DAMAGE)
    assert token.zone is Zone.BATTLEFIELD
    walk_to(scenario, Step.END_OF_COMBAT)
    assert token.zone is Zone.GRAVEYARD


def test_jadar_does_not_create_a_second_token_while_it_controls_a_decayed_creature():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 10, battlefield=[JADAR])
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walk_to(scenario, Step.END_STEP)
    _resolve_everything(scenario)
    assert len([c for c in scenario.game.battlefield if c.token]) == 1

    walk_to(scenario, Step.CLEANUP)
    _resolve_everything(scenario)
    # Bob's whole turn, uneventfully, back around to alice's next end step.
    walk_to(scenario, Step.END_STEP)
    _resolve_everything(scenario)

    tokens = [c for c in scenario.game.battlefield if c.token]
    assert len(tokens) == 1, "CR 702.147a's own token still has decayed, so the condition is false"
