"""The adjective in front of a targeting requirement's noun (CR 115, 601.2c).

"Target creature" names a type. Every card here narrows that further with an
adjective, and the three kinds of adjective are answered from three different
places:

- **A negated type** - "counter target noncreature spell", "target nonland
  permanent card". The CR has no numbered rule for the "non-" prefix; it simply
  uses it (CR 110.3's "nontoken permanent", CR 702.108a's "noncreature spell")
  and CR 300.1 is the list of types it goes in front of. What the description
  *reaches* is CR 109.2: a type with no zone and no "card" or "spell" means a
  permanent on the battlefield, CR 109.2a's "card" plus a zone means a card
  there, CR 109.2b's "spell" means a spell on the stack. An artifact creature
  is both types at once (CR 300.2), so it is a creature spell too.

- **A token** - "target token you control". CR 111.1: "a token is a marker used
  to represent any permanent that isn't represented by a card". CR 108.2b and
  CR 111.6 both say a token is not a card, and CR 205.2c says it has card types
  anyway. `CardState` is built around a `Card` and has no way to say a permanent
  is a token, so that half of the restriction is read and then fails open - the
  xfail below is the case it cannot answer.

- **Being in combat** - "target attacking creature". This is not a
  characteristic at all (CR 109.3 lists them and combat is not among them). A
  creature "becomes an attacking creature ... until it's removed from combat or
  the combat phase ends" (CR 508.1k), a blocker likewise (CR 509.1g), CR 506.4
  says what removes one and CR 511.3 ends it for everybody as the end of combat
  step ends. That state is on `Game.combat`, so `TargetingProfile.check` has to
  be handed the game before it can enforce it.

CR 608.2b is why the last one matters after announcement as well: "other changes
to the game state may cause a target to no longer be legal".
"""

import re

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import (
    CombatState,
    profile_for_text,
    targeting_profile,
)
from magic_cards_model.models import Type, Zone
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario


def ability_text(name: str, containing: str) -> str:
    """The one line of a real printing that carries this ability.

    Read off the Scryfall oracle text rather than retyped, so a test only holds
    if the printed card really says it. `profile_for_text` is the way in for an
    ability's own targeting requirement - `targeting_profile` answers for the
    spell, and a triggered or activated ability chooses its targets when it
    goes on the stack instead (CR 113.1c).
    """
    lines = [line for line in (card(name).oracle_text or "").splitlines() if containing in line]
    (line,) = lines
    return line.split(":", 1)[1].strip() if ":" in line else line


# -- a negated type: "counter target noncreature spell" --------------------


def counterspell_board() -> Scenario:
    """Bob's turn, so his sorcery-speed spells are castable; alice responds.

    Force of Negation is an instant, so alice can answer whatever bob puts on
    the stack without the timing rules getting in the way of the mechanic under
    test (CR 117.1a).
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Lightning Bolt", "Grizzly Bears", "Memnite"],
            battlefield=["Mountain", "Forest", "Forest"],
        )
        .player(
            "alice",
            hand=["Force of Negation"],
            battlefield=["Island", "Island", "Island"],
        )
    )


def test_force_of_negation_reads_the_negation_off_its_own_text():
    """ "Counter target noncreature spell": creature is what it may *not* be."""
    (requirement,) = targeting_profile(card("Force of Negation")).requirements

    assert requirement.excluded_card_types == frozenset({Type.CREATURE})
    assert requirement.card_types == frozenset()  # every other type is fine
    assert requirement.zones == frozenset({Zone.STACK})  # CR 109.2b


def test_a_noncreature_spell_may_be_announced_as_the_target():
    """The happy path, cast and paid for on a real board.

    Force of Negation has no entry in `machines/effects.py`, so it resolves
    doing nothing - the assertion is about the announcement (CR 601.2c), which
    is what `machines/targeting.py` decides.
    """
    scenario = counterspell_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain", username="bob"), username="bob"
    )
    scenario.pass_priority("bob")  # CR 117.3c: bob keeps priority after casting
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    force = scenario.cast_onto_stack(
        "Force of Negation", *islands, username="alice", targets=[bolt]
    )

    assert force.targets[0].card_id == bolt.id


def test_a_creature_spell_cannot_be_countered_by_force_of_negation():
    """CR 601.2c: the announcement is refused, so the cast never happens."""
    scenario = counterspell_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )

    with pytest.raises(ValueError, match="cannot target a creature"):
        scenario.cast("Force of Negation", username="alice", targets=[bears])
    assert scenario.find("Force of Negation", Zone.HAND, "alice") is not None


def test_an_artifact_creature_spell_is_still_a_creature_spell():
    """CR 300.2: an object with two card types is subject to both.

    Memnite is an Artifact Creature, so the artifact half does not save it from
    a spell that refuses creature spells.
    """
    scenario = counterspell_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    memnite = scenario.cast_onto_stack("Memnite", username="bob")

    with pytest.raises(ValueError, match="cannot target a creature"):
        scenario.cast("Force of Negation", username="alice", targets=[memnite])


def test_a_creature_on_the_battlefield_is_not_a_spell_either():
    """The zone check bites first: CR 109.2b's "spell" is on the stack."""
    scenario = counterspell_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "bob")

    with pytest.raises(ValueError, match="needs a target in the stack"):
        scenario.cast("Force of Negation", username="alice", targets=[forest])


def test_the_types_a_spell_is_judged_by_are_the_printed_ones():
    """CR 608.2b rechecks characteristics, and here they can never change.

    "A creature spell that stopped being one" has no test in this file because
    it cannot be written without hand-writing card data: nothing computes the
    characteristics of an object on the stack - `machines/layers.py` computes a
    board of permanents - so the recheck reads `Card.types` and gets the
    printing every time. Recorded in `docs/engine-coverage.md` rather than
    faked here.
    """
    bolt = card_state("Lightning Bolt", Zone.STACK, controller="bob")
    (requirement,) = targeting_profile(card("Force of Negation")).requirements

    assert requirement.rejects(bolt, caster="alice") is None
    assert Type.CREATURE not in bolt.card.types


# -- a negated type on a card in a graveyard (CR 109.2a) -------------------


def tamiyo_requirement_profile(x_value: int = 2):
    """Tamiyo's -X: "Exile target nonland permanent card ... from your graveyard".

    X is announced when the loyalty ability is activated (CR 606.3, same
    timing CR 601.2b gives a spell's X), before its target is chosen - so by
    the time this requirement is checked in a real game, X is already a plain
    number. Substituted here the same way, rather than left as the literal
    "X" `machines/targeting.py` cannot evaluate on its own and correctly
    refuses every target for (`ComparisonAttribute` fails closed on an unbound
    X, per the mana-value/power/toughness comparison this profile now reads).
    Default of 2 matches Grizzly Bears' printed mana value in the tests below
    that expect it to be a legal target.
    """
    text = ability_text("Tamiyo, Compleated Sage", "nonland")
    return profile_for_text(re.sub(r"\bX\b", str(x_value), text))


def test_a_nonland_permanent_card_is_read_as_a_card_in_your_graveyard():
    """CR 109.2a: "card" plus a zone means a card in that zone, not a permanent."""
    (requirement,) = tamiyo_requirement_profile().requirements

    assert requirement.excluded_card_types == frozenset({Type.LAND})
    assert requirement.zones == frozenset({Zone.GRAVEYARD})


def test_a_land_card_in_your_graveyard_is_not_a_nonland_permanent_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Mountain", "Grizzly Bears"])
        .build()
    )
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "alice")

    with pytest.raises(ValueError, match="cannot target a land"):
        tamiyo_requirement_profile().check([mountain], caster="alice", game=scenario.game)


def test_a_creature_card_in_your_graveyard_is_a_nonland_permanent_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Mountain", "Grizzly Bears"])
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    tamiyo_requirement_profile().check([bears], caster="alice", game=scenario.game)


def test_your_graveyard_is_not_your_opponents_graveyard():
    """ "from your graveyard" says whose graveyard, and that is ownership."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Mountain"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    theirs = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    with pytest.raises(ValueError, match="illegal target"):
        tamiyo_requirement_profile().check([theirs], caster="alice", game=scenario.game)


# -- "target token you control" (CR 111.1) ---------------------------------


def talent_profile():
    """Caretaker's Talent's level 2 trigger: "a copy of target token you control"."""
    return profile_for_text(ability_text("Caretaker's Talent", "target token"))


def test_target_token_is_read_as_a_permanent_you_control():
    """CR 111.1 makes a token a permanent, so the battlefield is where it is."""
    (requirement,) = talent_profile().requirements

    assert requirement.must_be_token is True
    assert requirement.zones == frozenset({Zone.BATTLEFIELD})
    assert requirement.allows_cards and not requirement.allows_players


def test_a_permanent_an_opponent_controls_is_not_a_token_you_control():
    """The half of the restriction the model *can* answer still bites."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    theirs = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="illegal target"):
        talent_profile().check([theirs], caster="alice", game=scenario.game)


def test_a_nontoken_permanent_cannot_be_chosen_for_target_token():
    """CR 108.2b, CR 111.6: a token is not a card, and a card is not a token."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="needs a token"):
        talent_profile().check([bears], caster="alice", game=scenario.game)


# -- being in combat: "target attacking creature" (CR 508.1k) --------------


def guide_profile():
    """Guide of Souls' reflexive "When you do" clause: "target attacking creature".

    CR 603.12 makes this text a *second*, independent triggered ability's own
    - not the outer "Whenever you attack" trigger's - and `profile_for_text`
    now cuts everything from "when you do" onward before reading the outer
    ability, so `ability_text`'s raw line can no longer be profiled whole (see
    `machines/targeting.py::profile_for_text` and `test_the_outer_attack_
    trigger_has_no_target_of_its_own` below, which is the regression test for
    that cut). This reads the reflexive clause's own substring instead - the
    text `Game.create_reflexive_trigger` would actually hand to `profile_for_
    text` once Guide's `{E}{E}{E}` were payable (it is not yet - see
    `docs/engine-coverage.md` - so today this ability resolves as a
    `ReflexiveClauseNotice` rather than ever reaching the stack). The
    "attacking creature" adjective machinery under test here does not care
    which ability the text came from, so testing it against this substring
    stays a faithful check of real printed words.
    """
    whole = ability_text("Guide of Souls", "attacking")
    _, _, consequence = whole.partition("When you do,")
    assert consequence, "Guide of Souls' attack trigger no longer reads 'When you do,'"
    return profile_for_text(consequence.strip())


def combat_board() -> Scenario:
    """Alice with a Guide and two creatures to attack with, bob with a blocker."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Guide of Souls", "Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Watchwolf"])
    )


def test_the_requirement_reads_attacking_off_the_ability():
    (requirement,) = guide_profile().requirements

    assert requirement.combat_states == frozenset({CombatState.ATTACKING})
    assert requirement.card_types == frozenset({Type.CREATURE})


def test_a_declared_attacker_is_a_legal_target():
    """CR 508.1k: the chosen creature "becomes an attacking creature"."""
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)

    guide_profile().check([bears], caster="alice", game=scenario.game)


def test_a_creature_that_stayed_home_is_not_an_attacking_creature():
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant", username="alice")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="needs a creature that is attacking"):
        guide_profile().check([giant], caster="alice", game=scenario.game)


def test_a_blocking_creature_is_not_an_attacking_creature():
    """CR 509.1g is a different state from CR 508.1k, and the card names one."""
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.pass_until_resolved()  # Guide of Souls' attack trigger; advance refuses mid-stack
    scenario.advance()  # declare blockers
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.block(bears, wolf)

    assert scenario.game.is_blocking(wolf)
    with pytest.raises(ValueError, match="needs a creature that is attacking"):
        guide_profile().check([wolf], caster="alice", game=scenario.game)


def test_a_creature_removed_from_combat_stops_being_a_legal_target():
    """CR 511.3: everything leaves combat as the end of combat step ends.

    The creature is still on the battlefield and still a creature - the only
    thing that changed is the game state CR 109.3 says is not a characteristic,
    which is exactly the change CR 608.2b covers with "other changes to the game
    state may cause a target to no longer be legal".
    """
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    guide_profile().check([bears], caster="alice", game=scenario.game)
    scenario.pass_until_resolved()  # Guide of Souls' attack trigger; advance refuses mid-stack

    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()  # start_at walks the turn machine and skips CR 511.3

    assert bears.zone is Zone.BATTLEFIELD
    assert not scenario.game.is_attacking(bears)
    with pytest.raises(ValueError, match="needs a creature that is attacking"):
        guide_profile().check([bears], caster="alice", game=scenario.game)


def test_a_creature_that_left_the_battlefield_is_refused_for_the_plainer_reason():
    """CR 506.4 removes it from combat, but CR 115.2 has already refused it."""
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD
    with pytest.raises(ValueError, match="needs a target in the battlefield"):
        guide_profile().check([bears], caster="alice", game=scenario.game)


def test_without_a_game_the_combat_restriction_is_not_checked():
    """Fail open, as everywhere else the parser cannot settle a question.

    Whether a creature is attacking lives on `Game.combat`, so a caller with no
    game gets the rest of the requirement checked and this part skipped. A
    false rejection would be worse than an unchecked one.
    """
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")

    guide_profile().check([bears], caster="alice")

    with pytest.raises(ValueError, match="needs a creature"):
        guide_profile().check([card_state("Mountain", Zone.BATTLEFIELD, controller="alice")], "a")


def test_the_outer_attack_trigger_has_no_target_of_its_own():
    """CR 603.3d: the target belongs to the *reflexive* ability CR 603.12
    creates once {E}{E}{E} is paid, not to "Whenever you attack" itself.

    Before `profile_for_text` learned to cut a "when you do" tail (see its
    own docstring in `machines/targeting.py`), this call raised - the outer
    trigger's announcement had harvested "target attacking creature" out of
    its own reflexive clause and enforced it here, which is the live defect
    the fix closes. Guide's outer trigger prints no target of its own at all,
    so naming one for it is simply not refused - there is nothing to check,
    the same "an ability with no targeting requirement at all is not asked
    anything" shape `Game._ask_trigger_targets` already documents.
    """
    scenario = combat_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant", username="alice")
    scenario.attack_with(bears)

    scenario.choose_trigger_targets("Guide of Souls", [giant])  # not attacking, and not refused


# --------------------------------------------------------------------------
# A colour-*count* adjective - CR 105.2's "multicolored"/"monocolored"/
# "colorless" - as opposed to `required_colors`' membership check for a
# specific named colour ("target black or red permanent"). Psychotic Fury's
# "Target multicolored creature gains double strike until end of turn." used
# to come back `understood=False` even for the bare "target multicolored
# creature" phrase alone: `_COLOR_WORDS` correctly does not carry
# "multicolored" (CR 105.4: "'Multicolored' is not a color"), and nothing
# else in `machines/targeting.py` read it either, so the card's own
# announcement could never legally choose a target at all. `TargetRequirement.
# color_count` and `_Adjectives.color_count` fix this generally, for the
# whole CR 105.2 family, not for Psychotic Fury by name.
# --------------------------------------------------------------------------


def test_multicolored_is_read_as_two_or_more_colors():
    """CR 105.2b: "A multicolored object is two or more of the five colors" -
    verified with `knowledge_search` this session."""
    profile = profile_for_text("target multicolored creature")
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.color_count == "multicolored"


def test_a_multicolored_creature_satisfies_psychotic_furys_own_target():
    """Fiend Artisan is black *and* green - CR 105.2b's two-or-more."""
    fiend_artisan = card_state("Fiend Artisan", Zone.BATTLEFIELD, controller="alice")
    requirement = profile_for_text("target multicolored creature").requirements[0]
    assert requirement.rejects(fiend_artisan, caster="alice") is None


def test_a_monocolored_creature_does_not_satisfy_it():
    """Grizzly Bears is green alone - CR 105.2a's exactly-one, not
    CR 105.2b's two-or-more."""
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")
    requirement = profile_for_text("target multicolored creature").requirements[0]
    assert requirement.rejects(bears, caster="alice") is not None


def test_psychotic_fury_grants_double_strike_and_draws_a_card():
    """The card end to end: Fiend Artisan gains double strike, and Alice
    draws the card the second sentence promises."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Psychotic Fury"],
            library=["Forest"],
            battlefield=["Fiend Artisan", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    fiend_artisan = scenario.creature("Fiend Artisan", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Psychotic Fury", *sources, targets=[fiend_artisan])

    assert "Double strike" in scenario.game.characteristics_of(fiend_artisan).abilities
    assert [state.name for state in alice.hand] == ["Forest"]


# --------------------------------------------------------------------------
# A colour-*presence* restriction, as opposed to a colour-*count* one -
# CR 105.2's "an object can be one or more of the five colors, or it can be
# no color at all". Devourer of Destiny's "exile target permanent that's one
# or more colors" is not "target multicolored permanent" (two or more,
# CR 105.2b) or "target monocolored permanent" (exactly one, CR 105.2a): it
# is the plain negation of CR 105.2c's colorless, sitting in a *trailing*
# relative clause rather than a leading adjective. This used to parse with
# no restriction at all - `_read_phrase` read "target permanent" as the
# whole noun phrase and had nothing that recognised "that's one or more
# colors" trailing it, so the clause was silently dropped and a colorless
# permanent was accepted as a legal target. That is an over-broad, actively
# wrong targeting list - a live correctness bug found in a real game, worse
# than refusing every target outright. `TargetRequirement.color_count`'s new
# "colored" value and `_extract_color_presence` fix it generally, for any
# card printing the same "that's one or more colors" clause - Ugin, Eye of
# the Storms prints the identical clause on both of its own cast triggers.
# --------------------------------------------------------------------------


def test_color_presence_is_read_as_the_negation_of_colorless():
    """CR 105.2: "An object can be one or more of the five colors, or it can
    be no color at all" - verified with `knowledge_search` this session."""
    profile = profile_for_text("exile target permanent that's one or more colors.")
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.color_count == "colored"


def test_a_colored_permanent_satisfies_devourer_of_destinys_own_target():
    """Grizzly Bears is green - CR 105.2's "one or more" - so it is a legal
    target."""
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    requirement = profile_for_text(
        "exile target permanent that's one or more colors."
    ).requirements[0]
    assert requirement.rejects(bears, caster="alice") is None


def test_a_colorless_permanent_does_not_satisfy_it():
    """Memnite has no colored mana symbols at all (CR 202.2b) and so is
    CR 105.2c's colorless - the exact case the old, over-broad parse used to
    wrongly accept."""
    memnite = card_state("Memnite", Zone.BATTLEFIELD, controller="bob")
    requirement = profile_for_text(
        "exile target permanent that's one or more colors."
    ).requirements[0]
    assert requirement.rejects(memnite, caster="alice") is not None


def test_devourer_of_destinys_cast_trigger_refuses_a_colorless_permanent():
    """End to end: `choose_trigger_targets` (CR 603.3d, CR 601.2c) refuses a
    colorless permanent for Devourer of Destiny's own cast trigger, the same
    announcement-time check `test_triggered_abilities.py`'s Devourer tests
    exercise for a legal, colored target.

    The trigger's source has to already be findable on the stack
    (`Game._trigger_source_named` only searches the battlefield and the
    stack, CR 603.6a/603.2g), so the spell is cast onto the stack first
    rather than choosing targets while it still sits in hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring"] + ["Forest"] * 5,
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)

    with pytest.raises(ValueError, match="colored"):
        scenario.game.choose_trigger_targets("Devourer of Destiny", [memnite])
