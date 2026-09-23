"""Sneak: CR 702.190a-b, an alternative cost cast in its own combat window.

CR 702.190a: "Sneak is a keyword that represents a static ability that
functions while the spell with sneak is on the stack. 'Sneak [cost]' means
'Any time you could cast an instant during your declare blockers step, you
may cast this spell by paying [cost] and returning an unblocked creature you
control to its owner's hand rather than paying this spell's mana cost.'"

CR 702.190b: "A permanent spell whose sneak cost was paid enters the
battlefield tapped and attacking (see rule 506.3a). It will be attacking the
same player, planeswalker, or battle as the creature that was returned to its
owner's hand to pay the sneak cost of the spell that became that permanent."

Three things follow, and each has its own tests below:

- **the window** - the caster's own declare blockers step, at instant timing
  (CR 117.1a), for *any* card type carrying sneak. A sorcery is castable
  there through sneak and only through sneak;
- **the cost** - [cost] plus returning an unblocked creature (CR 509.1h), a
  cost paid at CR 601.2h, before the spell is cast;
- **the defender** - read off the returned creature before the return takes
  it out of combat (CR 506.4), then used as the permanent enters (CR 508.4).

Proved on Foot Ninjas (a creature with an enters trigger) and Michelangelo's
Technique (the reported sorcery).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind

from .harness import Scenario

FOOT_NINJAS_MANA = ["Plains", "Swamp", "Swamp", "Swamp"]


def _in_declare_blockers(alice_hand, alice_battlefield, bob_battlefield=(), attackers=None):
    """Alice attacks with `attackers` (default: every creature named), bob
    declares no blockers, and the game sits in alice's declare blockers step
    with alice holding priority."""
    scenario = (
        Scenario()
        .player("alice", hand=list(alice_hand), battlefield=list(alice_battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    chosen = [scenario.creature(name, "alice") for name in (attackers or ["Grizzly Bears"])]
    scenario.attack_with(*chosen)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    return scenario


def _sneak(scenario, name, returning, username="alice"):
    card = scenario.find(name, Zone.HAND, username)
    return scenario.game.cast(
        card,
        username,
        keyword="Sneak",
        choosing=[returning],
        mana_sources=scenario.game.permanents_controlled_by(username),
    )


# -- CR 702.190b: a permanent spell enters tapped and attacking -------------


def test_foot_ninjas_sneaks_in_tapped_attacking_and_its_enters_trigger_fires():
    """Foot Ninjas: "Sneak {3}{W/B} ... When this creature enters, you gain 3
    life." The returned Grizzly Bears goes to hand as the cost is paid; the
    Ninjas enter tapped, attacking bob, trigger, and deal combat damage."""
    scenario = _in_declare_blockers(["Foot Ninjas"], ["Grizzly Bears", *FOOT_NINJAS_MANA])
    bears = scenario.creature("Grizzly Bears", "alice")

    spell = _sneak(scenario, "Foot Ninjas", bears)

    assert bears.zone is Zone.HAND, "the return is a cost, paid before the spell is cast"
    assert spell.zone is Zone.STACK
    assert scenario.game.cast_record(spell).keyword == "Sneak"

    scenario.pass_until_resolved()
    ninjas = scenario.find("Foot Ninjas", Zone.BATTLEFIELD, "alice")
    assert ninjas.tapped
    attack = scenario.game.combat.attack_by(ninjas.id)
    assert attack is not None
    assert attack.defender.username == "bob"
    assert not attack.blocked, "CR 508.4d: entered during declare blockers, so unblocked"

    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 23, "the enters trigger resolved"

    scenario.combat_damage()
    assert scenario.player("bob").life == 15


def test_foot_ninjas_attacks_the_planeswalker_the_returned_creature_was_attacking():
    """CR 702.190b's second sentence: the same player, planeswalker or battle
    as the returned creature - here a planeswalker, while another attacker is
    attacking bob himself, so the defender is not merely a default."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Foot Ninjas"],
            battlefield=["Grizzly Bears", "Hill Giant", *FOOT_NINJAS_MANA],
        )
        .player("bob", battlefield=["Ajani, Nacatl Pariah"])
        .build()
    )
    ajani = scenario.creature("Ajani, Nacatl Pariah", "bob")
    ajani.transform()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.game.declare_attackers([(bears, ajani), (giant, "bob")])
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    _sneak(scenario, "Foot Ninjas", bears)
    scenario.pass_until_resolved()

    ninjas = scenario.find("Foot Ninjas", Zone.BATTLEFIELD, "alice")
    attack = scenario.game.combat.attack_by(ninjas.id)
    assert attack is not None
    assert attack.defender.card_id == ajani.id


def test_foot_ninjas_cast_in_a_main_phase_enters_untapped_and_not_attacking():
    """CR 702.190b applies only when the sneak cost was paid: cast for its
    mana cost, Foot Ninjas is an ordinary creature spell."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Foot Ninjas"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Foot Ninjas", Zone.HAND, "alice")
    scenario.game.cast(card, "alice", mana_sources=scenario.game.permanents_controlled_by("alice"))
    scenario.pass_until_resolved()

    ninjas = scenario.find("Foot Ninjas", Zone.BATTLEFIELD, "alice")
    assert not ninjas.tapped
    assert scenario.game.combat.attack_by(ninjas.id) is None


# -- CR 702.190a: an instant or sorcery with sneak just resolves ------------


def test_michelangelos_technique_is_castable_by_sneak_in_the_declare_blockers_step():
    """The reported card: a sorcery, cast at instant timing during alice's own
    declare blockers step because of sneak. It resolves like any sorcery and
    enters nothing attacking - CR 702.190b is about permanent spells only."""
    scenario = _in_declare_blockers(
        ["Michelangelo's Technique"], ["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    spell = _sneak(scenario, "Michelangelo's Technique", bears)
    assert bears.zone is Zone.HAND
    assert spell.zone is Zone.STACK

    scenario.pass_until_resolved()
    assert scenario.find("Michelangelo's Technique", Zone.GRAVEYARD, "alice")
    assert scenario.game.combat.attacks == [], "the only attacker was returned; nothing entered"


def test_michelangelos_technique_cannot_be_cast_for_its_mana_cost_in_that_step():
    """Sneak opens the window for itself only: the same sorcery cast for its
    mana cost in the same step is refused by CR 117.1a / CR 307.1."""
    scenario = _in_declare_blockers(
        ["Michelangelo's Technique"],
        ["Grizzly Bears", "Forest", "Forest", "Forest", "Forest", "Forest"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    card = scenario.find("Michelangelo's Technique", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="CR 117.1a"):
        scenario.game.cast(
            card, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )
    assert card.zone is Zone.HAND
    assert bears.zone is Zone.BATTLEFIELD


def test_foot_ninjas_cannot_be_cast_for_its_mana_cost_during_combat():
    """A creature without flash is no more castable for its mana cost in the
    declare blockers step than a sorcery is."""
    scenario = _in_declare_blockers(
        ["Foot Ninjas"],
        ["Grizzly Bears", "Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"],
    )
    card = scenario.find("Foot Ninjas", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="CR 117.1a"):
        scenario.game.cast(
            card, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
        )
    assert card.zone is Zone.HAND


def test_sneak_is_instant_timing_so_it_can_respond_to_its_own_stack():
    """ "Any time you could cast an instant" (CR 117.1a) - the stack need not
    be empty. With two unblocked attackers, a second sneak spell is cast while
    the first is still on the stack."""
    scenario = _in_declare_blockers(
        ["Foot Ninjas", "Michelangelo's Technique"],
        [
            "Grizzly Bears",
            "Hill Giant",
            *FOOT_NINJAS_MANA,
            "Forest",
            "Forest",
            "Forest",
            "Forest",
        ],
        attackers=["Grizzly Bears", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    forests = [
        land for land in scenario.game.permanents_controlled_by("alice") if land.name == "Forest"
    ]
    card = scenario.find("Michelangelo's Technique", Zone.HAND, "alice")
    scenario.game.cast(card, "alice", keyword="Sneak", choosing=[giant], mana_sources=forests)

    ninjas_card = scenario.find("Foot Ninjas", Zone.HAND, "alice")
    others = [
        land
        for land in scenario.game.permanents_controlled_by("alice")
        if land.name in {"Plains", "Swamp"}
    ]
    scenario.game.cast(ninjas_card, "alice", keyword="Sneak", choosing=[bears], mana_sources=others)
    assert scenario.stack_names() == ["Michelangelo's Technique", "Foot Ninjas"]


# -- Refusals ----------------------------------------------------------------


def test_sneak_is_refused_in_the_declare_attackers_step():
    """Before blockers are declared no creature is unblocked (CR 509.1h), and
    it is not the declare blockers step CR 702.190a names."""
    scenario = (
        Scenario()
        .player("alice", hand=["Foot Ninjas"], battlefield=["Grizzly Bears", *FOOT_NINJAS_MANA])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="declare blockers step"):
        _sneak(scenario, "Foot Ninjas", bears)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find("Foot Ninjas", Zone.HAND, "alice")


def test_sneak_is_refused_in_a_main_phase():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Michelangelo's Technique"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="declare blockers step"):
        _sneak(scenario, "Michelangelo's Technique", bears)


def test_sneak_is_refused_in_the_combat_damage_step():
    scenario = _in_declare_blockers(["Foot Ninjas"], ["Grizzly Bears", *FOOT_NINJAS_MANA])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.COMBAT_DAMAGE)
    with pytest.raises(ValueError, match="declare blockers step"):
        _sneak(scenario, "Foot Ninjas", bears)


def test_sneak_is_refused_on_the_opponents_turn():
    """ "During **your** declare blockers step": bob, the defending player,
    holds Foot Ninjas during alice's declare blockers step and cannot sneak it
    - and has no attacker to return in any case."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Foot Ninjas"], battlefield=["Hill Giant", *FOOT_NINJAS_MANA])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    giant = scenario.creature("Hill Giant", "bob")
    card = scenario.find("Foot Ninjas", Zone.HAND, "bob")

    with pytest.raises(ValueError, match="your own declare blockers step|declare blockers step"):
        scenario.game.cast(
            card,
            "bob",
            keyword="Sneak",
            choosing=[giant],
            mana_sources=scenario.game.permanents_controlled_by("bob"),
        )
    assert card.zone is Zone.HAND


def test_sneak_is_refused_when_the_only_attacker_was_blocked():
    """CR 509.1h: a blocked creature is not unblocked, so it cannot pay."""
    scenario = (
        Scenario()
        .player("alice", hand=["Foot Ninjas"], battlefield=["Grizzly Bears", *FOOT_NINJAS_MANA])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, scenario.creature("Hill Giant", "bob"))

    with pytest.raises(ValueError, match="unblocked"):
        _sneak(scenario, "Foot Ninjas", bears)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find("Foot Ninjas", Zone.HAND, "alice")


def test_sneak_is_refused_with_a_creature_that_is_not_attacking():
    scenario = _in_declare_blockers(
        ["Foot Ninjas"], ["Grizzly Bears", "Hill Giant", *FOOT_NINJAS_MANA]
    )
    giant = scenario.creature("Hill Giant", "alice")
    with pytest.raises(ValueError, match="not attacking"):
        _sneak(scenario, "Foot Ninjas", giant)
    assert giant.zone is Zone.BATTLEFIELD


def test_sneak_needs_a_creature_chosen_to_return():
    scenario = _in_declare_blockers(["Foot Ninjas"], ["Grizzly Bears", *FOOT_NINJAS_MANA])
    card = scenario.find("Foot Ninjas", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="unblocked"):
        scenario.game.cast(
            card,
            "alice",
            keyword="Sneak",
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )
    assert card.zone is Zone.HAND


def test_an_unaffordable_sneak_leaves_the_attacker_in_combat():
    """CR 601.2h/CR 733.1: partial payments are not allowed, and a cast that
    cannot be paid rewinds - the creature chosen to return stays attacking."""
    scenario = _in_declare_blockers(["Foot Ninjas"], ["Grizzly Bears", "Plains"])
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        _sneak(scenario, "Foot Ninjas", bears)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.combat.attack_by(bears.id) is not None


# -- The enumerator offers it exactly when it is legal -----------------------


def _sneak_casts(scenario, username="alice"):
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST and action.keyword == "Sneak"
    ]


def _plain_casts_of(scenario, name, username="alice"):
    card = scenario.find(name, Zone.HAND, username)
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST and action.card_id == card.id and action.keyword is None
    ]


def test_legal_actions_offer_sneak_in_the_window_and_no_plain_cast():
    scenario = _in_declare_blockers(
        ["Michelangelo's Technique"],
        ["Grizzly Bears", "Forest", "Forest", "Forest", "Forest", "Forest"],
    )
    assert len(_sneak_casts(scenario)) == 1
    assert _plain_casts_of(scenario, "Michelangelo's Technique") == []


def test_legal_actions_do_not_offer_sneak_without_an_unblocked_attacker():
    scenario = (
        Scenario()
        .player("alice", hand=["Foot Ninjas"], battlefield=["Grizzly Bears", *FOOT_NINJAS_MANA])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, scenario.creature("Hill Giant", "bob"))
    assert _sneak_casts(scenario) == []


def test_legal_actions_do_not_offer_sneak_in_a_main_phase():
    scenario = (
        Scenario()
        .player("alice", hand=["Foot Ninjas"], battlefield=["Grizzly Bears", *FOOT_NINJAS_MANA])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _sneak_casts(scenario) == []


def test_legal_actions_offer_sneak_after_the_real_declare_blockers_turn_based_action():
    """CR 509.1's declare-blockers turn-based action runs even when nobody
    blocks - the declaration is still "which creatures, if any, will block".
    `no_blocks()` (used by every other test here) calls
    `Game.declare_blockers([])` directly, which always sets
    `Combat.blockers_declared`; this test instead reaches the step the way a
    real game does, through `Game.turn_based_actions()`, to prove the
    turn-based action itself sets it too when the defending player's answer
    to `ask_blockers` is empty."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Michelangelo's Technique"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    scenario.turn_based_actions()

    assert scenario.game.combat.blockers_declared, (
        "the declare-blockers turn-based action must set blockers_declared "
        "even when the answer to ask_blockers is empty (CR 509.1)"
    )
    assert len(_sneak_casts(scenario)) == 1
