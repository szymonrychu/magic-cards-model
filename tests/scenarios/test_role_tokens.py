"""Role tokens: CR 111.10k, CR 303.7, and the state-based actions that police them.

A Role is a token (CR 111), an Aura (CR 303), and a predefined token whose
characteristics the rules themselves supply (CR 111.10). Every one of those three
brings a rule of its own, which is why they are a file rather than a case in
`test_tokens.py`.

The rules cited here were looked up with `knowledge_search(type="rules")` and read
in full out of the 2026-08-19 Comprehensive Rules. Two of the numbers are ones a
guess would have got wrong: the Role state-based action is **CR 704.5z**, not one
of the earlier Aura letters, and the Aura-attachment one is **CR 704.5m**.

Monstrous Rage is the metagame card that prints one: "Target creature gets +2/+0
until end of turn. Create a Monster Role token attached to it."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import (
    MONSTER_ROLE,
    create_tokens,
    is_token,
    tokens_that_cease_to_exist,
)
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Generality: a second Role card, differently shaped from Monstrous Rage
# (CR 111.10j's Cursed rather than 111.10k's Monster; a triggered ability
# naming its own "target creature you control" rather than a spell's
# anaphoric "it"; a characteristic-setting grant rather than a P/T pump).
# --------------------------------------------------------------------------


def test_spiteful_hexmage_creates_a_cursed_role_on_its_own_target():
    """Spiteful Hexmage: "When this creature enters, create a Cursed Role token
    attached to target creature you control." (Enchanted creature is 1/1.)

    Unlike Monstrous Rage, this clause names its own target directly - there is
    no earlier sentence for "it" to refer back to - and CR 111.10j's grant sets
    base power and toughness rather than adding to it, so the same generic
    Role-token reader has to carry a target-word phrase, not just an anaphor,
    and a different predefined token's own text.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Spiteful Hexmage"], battlefield=["Swamp", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.choose_trigger_targets("Spiteful Hexmage", [bears])
    scenario.cast_and_resolve("Spiteful Hexmage", swamp, username="alice")
    scenario.pass_until_resolved()

    role = scenario.find("Cursed", Zone.BATTLEFIELD)
    assert is_token(role)
    assert role.attached_to == bears.id
    assert role.card.subtypes == ["Aura", "Role"]
    assert scenario.game.power_of(bears) == 1
    assert scenario.game.toughness_of(bears) == 1


def board() -> Scenario:
    """A bear to enrage and a Mountain to pay for it."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Monstrous Rage", "Monstrous Rage"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _enrage(scenario, creature):
    """Cast one Monstrous Rage at `creature` and let it resolve."""
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]
    return scenario.cast_and_resolve(
        "Monstrous Rage", mountain, username="alice", targets=[creature]
    )


# --------------------------------------------------------------------------
# What a Role is
# --------------------------------------------------------------------------


def test_monstrous_rage_pumps_and_leaves_a_monster_role_behind():
    """Monstrous Rage: "Target creature gets +2/+0 until end of turn. Create a
    Monster Role token attached to it."

    Two things in printed order (CR 608.2c), from two different objects. The
    +2/+0 is a continuous effect from the resolving spell (CR 611.2), sublayer 7c
    (CR 613.4c). The +1/+1 is the *Role's* static ability, which is a different
    effect with a different timestamp (CR 613.7a against CR 613.7b) and lasts as
    long as the Role does rather than until end of turn.

    CR 111.10k, in full: "A Monster Role token is a colorless Aura Role
    enchantment token named Monster with enchant creature and 'Enchanted creature
    gets +1/+1 and has trample.'" So a 2/2 bear ends up 5/3.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)

    role = scenario.find("Monster", Zone.BATTLEFIELD)
    assert is_token(role)
    assert role.attached_to == bears.id
    assert scenario.game.power_of(bears) == 5
    assert scenario.game.toughness_of(bears) == 3


def test_the_role_gets_the_name_and_types_the_rules_give_it():
    """CR 111.10k names the token itself, so CR 111.4's "subtypes plus the word
    'Token'" never applies: it is called Monster, not "Aura Role Token".

    CR 303.7 is what makes Role a subtype of Aura at all: "Some Aura enchantments
    also have the subtype 'Role.'" Colorless, so `colors` is empty (CR 105.2), and
    an enchantment rather than a creature.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)

    role = scenario.find("Monster", Zone.BATTLEFIELD)
    assert role.name == "Monster"
    assert role.card.types == [Type.ENCHANTMENT]
    assert role.card.subtypes == ["Aura", "Role"]
    assert role.card.colors == []
    assert not role.is_creature


def test_the_role_arrives_already_attached():
    """CR 701.3a: "To attach an Aura, Equipment, or Fortification to an object or
    player means to take it from where it currently is and put it onto that
    object or player."

    Monstrous Rage says "attached to it", so the Role never spends a moment
    unattached and CR 704.5m - "If an Aura is attached to an illegal object or
    player, or is not attached to an object or player, that Aura is put into its
    owner's graveyard" - has nothing to act on the instant it enters.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)

    role = scenario.find("Monster", Zone.BATTLEFIELD)
    assert role.is_attached
    assert scenario.state_based_actions() == [], "nothing for CR 704.5m to do"
    assert role.zone is Zone.BATTLEFIELD


def test_a_role_can_be_put_on_an_opponents_creature():
    """ "Target creature" is any creature, so alice's Role can enchant bob's bear.

    CR 111.2 keeps the token alice's - "the player who creates a token is its
    owner. The token enters the battlefield under that player's control" - even
    though what it is attached to is not. That distinction is the whole of
    CR 704.5z's "more than one Role **controlled by the same player**".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    _enrage(scenario, theirs)

    role = scenario.find("Monster", Zone.BATTLEFIELD)
    assert role.controller == "alice"
    assert role.attached_to == theirs.id
    assert scenario.game.power_of(theirs) == 5


def test_the_pump_ends_at_cleanup_and_the_role_does_not():
    """CR 514.2: in the cleanup step "all damage marked on permanents ... is
    removed and all 'until end of turn' and 'this turn' effects end", as the one
    turn-based action of CR 703.4p.

    Monstrous Rage's +2/+0 has that duration (CR 611.2a) and goes. The Role's
    +1/+1 is a static ability of a permanent (CR 611.3) with no duration at all,
    so it stays for as long as the Role is on the battlefield - which is why the
    bear is 3/3 afterwards rather than 2/2.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enrage(scenario, bears)
    assert scenario.game.power_of(bears) == 5

    scenario.game.cleanup_step()

    assert scenario.game.power_of(bears) == 3
    assert scenario.game.toughness_of(bears) == 3


def test_a_role_whose_target_is_gone_is_never_created():
    """CR 608.2b: "If all its targets, for every instance of the word 'target,'
    are now illegal, the spell doesn't resolve."

    Monstrous Rage has one target and it is the target of both sentences, so a
    bear that died in response takes the whole card with it - no pump, and no
    Role token either. CR 111.5's other route to the same outcome (a rule
    forbidding a permanent with the token's characteristics from entering) is not
    modelled; this one is CR 608.2b and is.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]
    scenario.cast_onto_stack("Monstrous Rage", mountain, username="alice", targets=[bears])
    scenario.game.destroy(bears)
    scenario.resolve_top()

    assert "Monster" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# The state-based actions Roles bring with them
# --------------------------------------------------------------------------


def test_a_role_falls_off_when_the_creature_it_enchants_dies():
    """CR 704.5m: "If an Aura is attached to an illegal object or player, or is
    not attached to an object or player, that Aura is put into its owner's
    graveyard."

    And then, because it is a token, CR 704.5d takes it from there: it ceases to
    exist rather than sitting in a graveyard. Two state-based actions in
    sequence, both in the same CR 704.3 loop.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enrage(scenario, bears)
    role = scenario.find("Monster", Zone.BATTLEFIELD)

    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert role.zone is not Zone.BATTLEFIELD
    assert "Monster" not in scenario.battlefield_names()


def test_a_second_role_on_one_creature_replaces_the_first():
    """CR 303.7a, and CR 704.5z which states it as a state-based action: "If a
    permanent has more than one Role controlled by the same player attached to
    it, each of those Roles except the one with the most recent timestamp is put
    into its owner's graveyard."

    That is the parenthesised reminder on Monstrous Rage - "If you control
    another Role on it, put that one into the graveyard" - and it is why two
    Monstrous Rages on one creature give +1/+1 once, not twice. The +2/+0 halves
    are separate spell effects and do stack, so the right answer is 2/2 plus
    +2/+0 twice plus +1/+1 once: a 7/3.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)
    _enrage(scenario, bears)
    scenario.state_based_actions()

    roles = [state for state in scenario.game.battlefield if state.name == "Monster"]
    assert len(roles) == 1, "the older Role went to the graveyard (CR 704.5z)"
    assert scenario.game.power_of(bears) == 7


def test_the_role_that_survives_is_the_newest_one():
    """CR 704.5z bins "each of those Roles **except the one with the most recent
    timestamp**", so which one lives is decided, not arbitrary.

    The timestamp is CR 613.7a's: "a continuous effect generated by a static
    ability has the same timestamp as the object the static ability is on",
    which for a permanent is the moment it entered the battlefield (CR 613.7b's
    sibling rule). The second Monstrous Rage's Role entered later, so it is the
    survivor.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)
    first = scenario.find("Monster", Zone.BATTLEFIELD)
    _enrage(scenario, bears)
    second = next(
        state
        for state in scenario.game.battlefield
        if state.name == "Monster" and state.id != first.id
    )

    scenario.state_based_actions()

    assert first.zone is not Zone.BATTLEFIELD, "the older one went"
    assert second.zone is Zone.BATTLEFIELD, "the most recent timestamp survives"


def test_two_players_roles_on_one_creature_both_stay():
    """CR 704.5z's other condition, and the one a paraphrase drops: "more than one
    Role **controlled by the same player** attached to it".

    alice and bob each put a Monster Role on the same bear. Neither player
    controls two, so the rule does not apply and the creature carries both -
    +1/+1 twice, which on top of one Monstrous Rage's +2/+0 is a 2/2 bear at 6/4.

    CR 111.2 is what keeps the two Roles on different sides: "the player who
    creates a token is its owner. The token enters the battlefield under that
    player's control", whoever the enchanted creature belongs to (CR 303.4e).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)
    # bob's half is created directly rather than cast: it is alice's turn and
    # bob does not hold priority, and the mechanic under test is CR 704.5z, not
    # the timing of an instant. `create_tokens` is the same call Monstrous Rage's
    # effect makes, with the same predefined definition (CR 111.10k).
    create_tokens(scenario.game, MONSTER_ROLE, "bob", attached_to=bears)

    scenario.state_based_actions()

    roles = [state for state in scenario.game.battlefield if state.name == "Monster"]
    assert len(roles) == 2
    assert {role.controller for role in roles} == {"alice", "bob"}
    assert scenario.game.power_of(bears) == 6, "2/2, +2/+0 once, +1/+1 twice"


def test_one_players_roles_on_two_different_creatures_both_stay():
    """The first condition: the Roles must be attached to **one** permanent.

    Two bears, two Monstrous Rages, one player. Nothing has more than one Role on
    it, so CR 704.5z has nothing to act on.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Monstrous Rage", "Monstrous Rage"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Monstrous Rage", first, username="alice", targets=[mine])
    scenario.cast_and_resolve("Monstrous Rage", second, username="alice", targets=[theirs])

    scenario.state_based_actions()

    roles = [state for state in scenario.game.battlefield if state.name == "Monster"]
    assert len(roles) == 2
    assert {role.attached_to for role in roles} == {mine.id, theirs.id}


def test_the_binned_role_ceases_to_exist_rather_than_filling_a_graveyard():
    """CR 704.5z then CR 704.5d, in that order and in the same CR 704.3 loop.

    "If any state-based actions are performed as a result of a check, the check
    is repeated" (CR 704.3), so the older Role is put into its owner's graveyard
    by one check and ceases to exist on the next. Nothing is left behind, which
    matters for everything that counts a graveyard - delirium's card types
    (CR 205.2a), threshold, a Tarmogoyf's power.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)
    _enrage(scenario, bears)
    scenario.state_based_actions()

    graveyard = [state.name for state in scenario.player("alice").graveyard]
    assert graveyard == ["Monstrous Rage", "Monstrous Rage"], "no Role is left in it"


def test_an_unattached_role_is_binned_and_then_ceases_to_exist():
    """CR 704.5m reaches a Role like any other Aura - it is one, by CR 303.7 -
    and CR 704.5d finishes the job because it is also a token.

    Two state-based actions in sequence on one object, which is the interaction
    that makes a Role different from both a plain Aura and a plain token.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (role,) = create_tokens(scenario.game, MONSTER_ROLE, "alice")
    assert not role.is_attached

    scenario.state_based_actions()

    assert role.zone is Zone.GRAVEYARD, "CR 704.5m put it there"
    assert role not in scenario.player("alice").graveyard, "CR 704.5d took it from there"
    assert "Monster" not in scenario.battlefield_names()


def test_a_role_on_a_creature_that_died_takes_both_actions_by_itself():
    """The everyday sequence, driven by the game rather than by hand: the bear
    dies to CR 704.5g, the Role loses its host and goes to CR 704.5m, and CR
    704.5d removes it from the graveyard - all inside one
    `check_state_based_actions` (CR 704.3's repeating check).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Monstrous Rage", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    (rage_source, bolt_source) = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Monstrous Rage", rage_source, username="alice", targets=[bears])
    role = scenario.find("Monster", Zone.BATTLEFIELD)

    scenario.cast_and_resolve("Lightning Bolt", bolt_source, username="alice", targets=[bears])
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD, "3 damage on a 5/3 is lethal (CR 704.5g)"
    assert role.zone is not Zone.BATTLEFIELD
    assert "Monster" not in scenario.battlefield_names()
    graveyard = [state.name for state in scenario.player("alice").graveyard]
    assert "Monster" not in graveyard


def test_a_role_that_reaches_a_graveyard_ceases_to_exist():
    """CR 704.5d: "If a token is in a zone other than the battlefield, it ceases
    to exist."

    A Role is a token, so it is subject to this like any other. Called by hand
    here rather than through `state_based_actions()`, so that the rule is tested
    on its own - the dispatched path is
    `test_the_game_makes_a_dead_token_cease_to_exist_by_itself` in
    `tests/scenarios/test_tokens.py`.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enrage(scenario, bears)
    role = scenario.find("Monster", Zone.BATTLEFIELD)

    scenario.game.destroy(role)
    assert role in scenario.player("alice").graveyard

    assert tokens_that_cease_to_exist(scenario.game) == [role]
    assert role not in scenario.player("alice").graveyard


def test_the_creature_shrinks_when_the_role_leaves():
    """CR 611.3b: a static ability's continuous effect "applies at all times that
    the permanent generating it is on the battlefield or the object generating it
    is in the appropriate zone" - and at no other time.

    Nothing has to remember to undo the +1/+1: CR 613.5 says the layer system is
    "continually and automatically performed by the game", so a Role that is no
    longer there is no longer applying.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _enrage(scenario, bears)
    role = scenario.find("Monster", Zone.BATTLEFIELD)
    assert scenario.game.toughness_of(bears) == 3

    scenario.game.destroy(role)

    assert scenario.game.power_of(bears) == 4, "the spell's +2/+0 is still running"
    assert scenario.game.toughness_of(bears) == 2


# --------------------------------------------------------------------------
# What the Role grants, and how far it reaches
# --------------------------------------------------------------------------


def test_the_role_grants_trample_in_layer_six():
    """CR 613.1f: "Layer 6: Ability-adding effects, keyword counters,
    ability-removing effects, and effects that say an object can't have an
    ability are applied."

    CR 113.10 is what makes the Role's wording an ability-adding effect: "An
    effect that adds an ability will state that the object 'gains' or 'has' that
    ability." Trample is CR 702.19a, "a static ability that modifies the rules
    for assigning an attacking creature's combat damage".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _enrage(scenario, bears)

    assert "Trample" in scenario.game.characteristics_of(bears).abilities


def test_the_granted_trample_reaches_combat_damage():
    """CR 702.19b: "The controller of an attacking creature with trample first
    assigns damage to the creature(s) blocking it. Once all those blocking
    creatures are assigned lethal damage, any excess damage is assigned as its
    controller chooses among those blocking creatures and the ... player."

    A 5/3 with trample blocked by a 2/2 assigns 2 to the blocker and 3 to bob.

    `has_keyword` needs the game to answer: CR 613.5 has the layer system, not
    the printing, decide which abilities a permanent has, and the Role's
    trample exists only on the computed board. Asked without one there is no
    board to compute and the printed Scryfall field is the honest answer -
    which for a Grizzly Bears is no trample at all.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    _enrage(scenario, bears)
    assert not has_keyword(bears, Keyword.TRAMPLE), "the printing has none"
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)

    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, blocker)
    assignment = scenario.combat_damage()

    assert ("bob", 3) in [
        (
            target if isinstance(target, str) else getattr(target, "username", None) or target.name,
            amount,
        )
        for target, amount in assignment
    ]


def test_a_role_created_on_nothing_grants_nothing():
    """CR 111.10k's grant is written "enchanted creature", and CR 704.5m is the
    rule that keeps an Aura from sitting there enchanting nobody.

    An unattached Role grants nothing while it is there - the layer builder in
    `machines/layers.py` returns no effects when there is nothing to attach them
    to - and it is not there for long: CR 704.5m bins it at the next check, which
    `test_an_unattached_role_is_binned_and_then_ceases_to_exist` covers. This
    test is the moment in between, before any player would receive priority
    (CR 704.3).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    (role,) = create_tokens(scenario.game, MONSTER_ROLE, "alice")

    assert not role.is_attached
    assert scenario.game.power_of(bears) == 2, "it enchants nothing, so it pumps nothing"
