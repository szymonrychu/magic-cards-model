"""Sneak-paid riders (CR 702.190a-b): a card's own body reads "if [its/this
creature's/this spell's] sneak cost was paid[ this turn], instead ...".

Sneak itself (the alternative cost, and the sneak permanent's own tapped-and-
attacking entrance) is already engine-tested in `test_sneak.py`; this file is
about the four *rider* shapes tmt prints on top of it, each closing a
different gap:

- **Karai, Future of the Foot** - a triggered ability's own destination
  changes (return to hand, or instead to the battlefield) - CR 614.1a's
  "instead" on an *ability*, with CR 400.7's "that card" naming the same
  already-chosen target rather than a second one. The "this turn" qualifier
  (verified CR 122.6/CR 603.2h are not it - there is no numbered rule for
  this specific English phrase beyond CR 601.2i's cast-record write; the
  point being tested is `CardState.turn_entered` scoping) is its own corner
  case: a sneak-paid permanent that survives to a *later* turn's combat
  damage must fall back to the base branch.
- **Turncoat Kunoichi** - CR 610.3's temporary exile-until-leaves becomes
  permanent (no return-on-leaving watcher at all) when the rider fires.
- **Shredder's Technique** - a spell's own rider, keyed not on sneak at all
  but on the *type* of the single thing its own first sentence destroyed
  ("if an enchantment was destroyed this way") - proving the sneak line
  above it does not interfere with an unrelated "this way" rider.
- **The Last Ronin's Technique** - CR 702.190b extended from the sneak spell
  itself to tokens a resolving *instant* creates, entering tapped and
  attacking the same defender the returned creature was attacking.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState

from .harness import Scenario


def _sneak_cast(scenario, name, returning, username="alice", *, extra_sources=()):
    card = scenario.find(name, Zone.HAND, username)
    sources = [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state not in extra_sources
    ] + list(extra_sources)
    return scenario.game.cast(
        card,
        username,
        keyword="Sneak",
        choosing=[returning],
        mana_sources=sources,
    )


# -- Karai, Future of the Foot -----------------------------------------------


def _karai_board(*, graveyard=("Hill Giant",)):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Karai, Future of the Foot"],
            battlefield=[
                "Grizzly Bears",
                "Plains",
                "Plains",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
            graveyard=list(graveyard),
            library=["Plains", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob", library=["Plains", "Plains", "Plains", "Plains", "Plains"])
    )


def test_combat_damage_returns_to_hand_when_karai_was_cast_for_mana():
    """The base branch: no rider, Karai just returns the graveyard card to
    hand (CR 608.2c's ordinary "return target ... to your hand"). Karai
    starts already on the battlefield (CR 302.6: no summoning sickness),
    cast for her mana cost - not sneak - so CR 702.190b never applies."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Karai, Future of the Foot", "Plains"],
            graveyard=["Hill Giant"],
        )
        .player("bob")
    ).build()
    karai = scenario.creature("Karai, Future of the Foot", "alice")
    assert not karai.tapped

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(karai)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    hill_giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Karai, Future of the Foot", [hill_giant])
    scenario.combat_damage()
    scenario.pass_until_resolved()  # the combat damage trigger

    assert hill_giant.zone is Zone.HAND


def test_combat_damage_returns_to_the_battlefield_when_sneak_was_paid_this_turn():
    """CR 702.190a/b: Karai enters tapped and attacking by sneak, then deals
    combat damage in that very declare blockers step - "her sneak cost was
    paid this turn" holds, and the instead-branch puts the graveyard card
    onto the battlefield instead of into hand."""
    scenario = _karai_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    karai_spell = _sneak_cast(scenario, "Karai, Future of the Foot", bears)
    assert bears.zone is Zone.HAND
    scenario.pass_until_resolved()
    karai = scenario.find("Karai, Future of the Foot", Zone.BATTLEFIELD, "alice")
    assert karai.tapped
    attack = scenario.game.combat.attack_by(karai.id)
    assert attack is not None and attack.defender.username == "bob"
    assert scenario.game.cast_record(karai_spell).keyword == "Sneak"

    hill_giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Karai, Future of the Foot", [hill_giant])
    scenario.combat_damage()
    scenario.pass_until_resolved()  # the combat damage trigger

    assert hill_giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(hill_giant).username == "alice"


def test_a_sneak_paid_karai_falls_back_to_hand_on_a_later_turn():
    """ "This turn" is a real scope, not decoration: Karai sneaks in during
    turn 1, survives untouched, and only deals combat damage on her *next*
    turn (turn 3 - bob's turn 2 sits between). `CastRecord.keyword` still
    says Sneak, but `CardState.turn_entered` no longer matches the current
    turn, so the base branch (return to hand) runs, not the instead branch.
    """
    scenario = _karai_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    _sneak_cast(scenario, "Karai, Future of the Foot", bears)
    scenario.pass_until_resolved()
    karai = scenario.find("Karai, Future of the Foot", Zone.BATTLEFIELD, "alice")
    assert karai.tapped
    sneak_turn = karai.turn_entered

    # Finish the turn Karai sneaked in on, all of the next turn, and into the
    # one after that - alice's own next turn, whichever number it lands on.
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    assert scenario.turn.active_player == "alice"
    assert scenario.turn.turn_number != sneak_turn

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(karai)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    hill_giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Karai, Future of the Foot", [hill_giant])
    scenario.combat_damage()
    scenario.pass_until_resolved()

    assert hill_giant.zone is Zone.HAND, "sneak was paid turn 1, not this (turn 3) turn"


def test_a_sneak_paid_on_a_later_own_turn_still_counts_as_this_turn():
    """Karai sneaks in on alice's *second* turn (the game's third turn, round
    two): "this turn" is that turn whatever the round counter says, so the
    instead branch puts the card onto the battlefield. `CardState.turn_entered`
    is stamped in `TurnMachine.turns_taken`, so the reader must compare
    against that, not the round number."""
    scenario = _karai_board().build()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    assert scenario.turn.active_player == "alice"
    assert scenario.turn.turns_taken != scenario.turn.turn_number

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    _sneak_cast(scenario, "Karai, Future of the Foot", bears)
    scenario.pass_until_resolved()
    hill_giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Karai, Future of the Foot", [hill_giant])
    scenario.combat_damage()
    scenario.pass_until_resolved()

    assert hill_giant.zone is Zone.BATTLEFIELD


# -- Turncoat Kunoichi --------------------------------------------------------


def _kunoichi_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Turncoat Kunoichi"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
    )


def test_exile_returns_when_turncoat_kunoichi_leaves_if_sneak_was_not_paid():
    scenario = _kunoichi_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Turncoat Kunoichi", Zone.HAND, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Turncoat Kunoichi", [giant])
    scenario.game.cast(card, "alice", mana_sources=scenario.game.permanents_controlled_by("alice"))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()  # the ETB trigger: exile Hill Giant
    kunoichi = scenario.find("Turncoat Kunoichi", Zone.BATTLEFIELD, "alice")

    assert giant.zone is Zone.EXILE

    scenario.game.destroy(kunoichi)
    scenario.pass_until_resolved()  # the delayed return trigger

    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(giant).username == "bob"


def test_the_exile_is_permanent_when_sneak_was_paid():
    """CR 614.1a's instead: sneak-paid, so no delayed return trigger is ever
    created - Hill Giant stays exiled even after Turncoat Kunoichi itself
    leaves the battlefield."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turncoat Kunoichi"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
    ).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    scenario.choose_trigger_targets("Turncoat Kunoichi", [giant])
    _sneak_cast(scenario, "Turncoat Kunoichi", bears)
    scenario.pass_until_resolved()  # Turncoat Kunoichi itself enters
    scenario.pass_until_resolved()  # its own ETB trigger

    assert giant.zone is Zone.EXILE
    kunoichi = scenario.find("Turncoat Kunoichi", Zone.BATTLEFIELD, "alice")
    assert kunoichi.tapped

    scenario.game.destroy(kunoichi)
    scenario.pass_until_resolved()
    assert scenario.game.delayed_triggers.triggers == []

    assert giant.zone is Zone.EXILE, "the sneak-paid exile never comes back"


# -- Shredder's Technique -----------------------------------------------------


def test_destroying_a_creature_this_way_costs_no_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shredder's Technique"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Shredder's Technique",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_destroying_an_enchantment_this_way_costs_two_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shredder's Technique"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Pacifism", "Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    pacifism.attach_to(bears)  # CR 704.5m: an unattached Aura would be an SBA, not this test
    scenario.cast_and_resolve(
        "Shredder's Technique",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=[pacifism],
    )

    assert pacifism.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


# -- The Last Ronin's Technique -----------------------------------------------


def test_tokens_enter_untapped_and_not_attacking_when_cast_for_mana():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Last Ronin's Technique"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "The Last Ronin's Technique",
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"),
    )

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.name == "Ninja Turtle Spirit Token" and isinstance(state, CardState)
    ]
    assert len(tokens) == 3
    assert all(not token.tapped for token in tokens)
    assert scenario.game.combat.attacks == []


def test_tokens_enter_tapped_and_attacking_the_sneak_defender_when_sneak_was_paid():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Last Ronin's Technique"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob")
    ).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    _sneak_cast(scenario, "The Last Ronin's Technique", bears)
    assert bears.zone is Zone.HAND
    scenario.pass_until_resolved()

    tokens = [
        state for state in scenario.game.battlefield if state.name == "Ninja Turtle Spirit Token"
    ]
    assert len(tokens) == 3
    assert all(token.tapped for token in tokens)
    for token in tokens:
        attack = scenario.game.combat.attack_by(token.id)
        assert attack is not None
        assert attack.defender.username == "bob"
