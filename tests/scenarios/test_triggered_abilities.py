"""CR 603: triggered abilities actually firing, going on the stack, and resolving.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file. The spine of it:

- **CR 603.2** - an ability triggers when a game event matches its trigger
  condition, and "the ability doesn't do anything at this point".
- **CR 603.3** - the controller puts it on the stack "as an object that's not a
  card the next time a player would receive priority".
- **CR 603.3b** - several at once go on in APNAP order, the active player first,
  so the active player's resolves last.
- **CR 603.4 / 608.2a** - an intervening *if* is checked when the event happens
  and again as the ability resolves.
- **CR 113.7a** - once triggered, the ability is independent of its source.
- **CR 608.2n** - as the final part of resolution the ability is removed from the
  stack and ceases to exist; it never reaches a graveyard.

One mechanic per file, so the activated half is in `test_activated_abilities.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _four_forests(name: str, opponent_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest", "Island"], hand=[name], battlefield=["Forest"] * 4)
        .player("bob", library=["Grizzly Bears"], battlefield=opponent_battlefield or [])
        .build()
    )


# -- enters the battlefield (CR 603.6a) -----------------------------------


def test_an_enters_trigger_goes_on_the_stack_and_fetches_a_land():
    """Solemn Simulacrum's enters trigger is a separate object that resolves later.

    CR 603.6a: "Enters-the-battlefield abilities trigger when a permanent enters
    the battlefield." CR 603.3 keeps it off the stack until the next time a
    player would receive priority, which here is once the creature spell has
    finished resolving - so the creature is already on the battlefield while its
    own trigger is still waiting.
    """
    scenario = _four_forests("Solemn Simulacrum")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)

    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    assert scenario.stack_names() == ["Solemn Simulacrum"], "no trigger yet - nothing has entered"

    scenario.pass_until_resolved()
    assert "Solemn Simulacrum" in scenario.battlefield_names()
    assert scenario.stack_names() == ["Solemn Simulacrum's triggered ability"]

    scenario.pass_until_resolved()
    assert scenario.battlefield_names().count("Forest") == 5, "the fetched Forest arrived"
    assert scenario.game.stack_is_empty


def test_the_fetched_land_arrives_tapped():
    """ "put that card onto the battlefield tapped" - the card says tapped, so it is."""
    scenario = _four_forests("Solemn Simulacrum")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    fetched = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Forest" and state not in sources
    ]
    assert len(fetched) == 1
    assert fetched[0].tapped


def test_an_ability_on_the_stack_is_not_a_card():
    """CR 405.1, 113.1c: an ability goes on the stack with no card behind it.

    It is not a `CardState`, it has no zone to be moved between, and CR 608.2n
    has it cease to exist rather than go to a graveyard.
    """
    scenario = _four_forests("Solemn Simulacrum")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()

    (ability,) = scenario.game.abilities_on_stack
    assert isinstance(ability, AbilityOnStack)
    assert ability.source_name == "Solemn Simulacrum"
    assert ability.controller == "alice"

    scenario.pass_until_resolved()
    graveyard = [state.name for state in scenario.player("alice").graveyard]
    assert graveyard == [], "an ability is not a card, so it goes to no zone at all"


def test_a_trigger_can_be_responded_to_before_it_resolves():
    """CR 117.7: a spell cast while the trigger sits on the stack resolves first.

    The trigger is an ordinary object on the stack, so the window above it is a
    real one. Bolting the Solemn Simulacrum in response does not stop the trigger
    - CR 113.7a: "Destruction or removal of the source after that time won't
    affect the ability."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Island"],
            hand=["Solemn Simulacrum"],
            battlefield=["Forest"] * 4,
        )
        .player("bob", library=["Grizzly Bears"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()

    solemn = scenario.creature("Solemn Simulacrum", "alice")
    scenario.pass_priority("alice")  # alice passes with the trigger on the stack
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[solemn])

    assert scenario.stack_names() == [
        "Solemn Simulacrum's triggered ability",
        "Lightning Bolt",
    ], "the response sits above the trigger"

    scenario.pass_until_resolved()  # the Bolt
    assert solemn.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == [
        "Solemn Simulacrum's triggered ability",
        "Solemn Simulacrum's triggered ability",
    ], "dying triggered the second ability, on top of the first"

    hand_before = len(scenario.player("alice").hand)
    scenario.pass_until_resolved()  # the dies trigger
    assert len(scenario.player("alice").hand) == hand_before + 1

    scenario.pass_until_resolved()  # the enters trigger, source long gone
    # The dies trigger drew the Forest off the top, so the only basic left to
    # fetch is the Island - and it still gets fetched.
    assert "Island" in scenario.battlefield_names()


def test_a_trigger_whose_source_died_still_resolves():
    """CR 113.7a: once triggered, an ability exists independently of its source.

    Solemn Simulacrum's *dies* trigger is the sharpest case: the source is
    already in a graveyard when the ability is put on the stack, and it still
    draws the card.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Island", "Forest"], battlefield=["Solemn Simulacrum"])
        .player("bob", library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    solemn = scenario.creature("Solemn Simulacrum", "alice")

    scenario.game.destroy(solemn)  # CR 700.4: it dies
    assert solemn.zone is Zone.GRAVEYARD
    assert [t.source_name for t in scenario.pending_triggers] == ["Solemn Simulacrum"]

    hand_before = len(scenario.player("alice").hand)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_one_card_can_carry_two_different_triggers():
    """Solemn Simulacrum triggers on entering and again on dying, separately."""
    scenario = _four_forests("Solemn Simulacrum")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)
    scenario.cast_onto_stack("Solemn Simulacrum", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()  # the enters trigger fetches a land

    solemn = scenario.creature("Solemn Simulacrum", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.game.destroy(solemn)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.battlefield_names().count("Forest") == 5, "the enters trigger already happened"
    assert len(scenario.player("alice").hand) == hand_before + 1, "and the dies trigger now has"


# -- cast triggers (CR 601.2, 603.2g) -------------------------------------


def test_a_cast_trigger_fires_when_a_spell_is_cast():
    """Guttersnipe: "Whenever you cast an instant or sorcery spell".

    CR 601.2a puts the card on the stack as the first step of casting, so the
    trigger has already happened while the spell is still waiting. CR 603.3 then
    puts the ability on the stack *above* the spell that caused it, which is why
    the two damage lands before the Bolt does.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Guttersnipe", "Mountain"],
        )
        .player("bob", library=["Grizzly Bears"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt", "Guttersnipe's triggered ability"]

    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18, "the trigger resolved before the Bolt"
    assert bears.zone is Zone.BATTLEFIELD

    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD


def test_a_card_with_no_registry_row_gets_the_each_opponent_damage_shape_too():
    """Impact Tremors: "Whenever a creature you control enters, this
    enchantment deals 1 damage to each opponent."

    Guttersnipe's trigger used to need its own `TRIGGER_EFFECTS` row; deleting
    it in favour of `_DAMAGE_EACH_OPPONENT_RE` (`machines/effects.py`) is only
    real if a *different* card printing the same shape works with no row of
    its own at all - Impact Tremors has never had one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Grizzly Bears"],
            battlefield=["Impact Tremors"] + ["Forest"] * 2,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_and_resolve("Grizzly Bears", *sources)
    assert scenario.stack_names() == ["Impact Tremors's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


def test_a_creature_spell_does_not_fire_an_instant_or_sorcery_cast_trigger():
    """The condition names a type, so a Grizzly Bears is not one (CR 603.2)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Grizzly Bears"],
            battlefield=["Guttersnipe", "Forest", "Forest"],
        )
        .player("bob", library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("Grizzly Bears", *sources)

    assert scenario.stack_names() == ["Grizzly Bears"]
    assert scenario.player("bob").life == 20


def test_a_permanent_put_onto_the_battlefield_never_fires_its_cast_trigger():
    """The Tooth and Nail case, with Devourer of Destiny standing in for Emrakul.

    "When you cast this spell, exile target permanent that's one or more colors."
    CR 601.2 defines casting as moving a card to the stack and paying its costs;
    a permanent put straight onto the battlefield does neither, so the casting
    event never happens and CR 603.2g's "an ability triggers only if its trigger
    event actually occurs" leaves the ability alone. The enters-the-battlefield
    event *did* happen - the creature really is on the battlefield.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Devourer of Destiny"])
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Devourer of Destiny", [bears])

    devourer = scenario.put_onto_battlefield("Devourer of Destiny")

    assert devourer.zone is Zone.BATTLEFIELD
    assert scenario.game.stack_is_empty, "nothing was cast, so nothing triggered"
    assert scenario.pending_triggers == []
    assert bears.zone is Zone.BATTLEFIELD, "the exile never happened"


def test_the_same_card_cast_normally_does_fire_its_cast_trigger():
    """The control for the case above: cast it and the trigger fires and targets.

    CR 603.3d chooses the ability's targets as it is put on the stack, following
    the same rules as CR 601.2c-d for a spell.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring"] + ["Forest"] * 5,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Devourer of Destiny", [bears])

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)

    assert scenario.stack_names() == [
        "Devourer of Destiny",
        "Devourer of Destiny's triggered ability",
    ], "the trigger sits above the spell that caused it"

    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE
    assert scenario.stack_names() == ["Devourer of Destiny"], "the spell is still waiting"


# -- attacking and blocking (CR 508, 509) ---------------------------------


def test_an_attack_trigger_fires_once_for_each_attacking_creature():
    """Hellrider: "Whenever a creature you control attacks".

    CR 508.2b: the abilities that triggered on attackers being declared go on the
    stack "before the active player gets priority", after the whole declaration -
    so two attackers make two separate abilities, not one.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Hellrider", "Raging Goblin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hellrider, goblin = scenario.creatures("Hellrider", "Raging Goblin", username="alice")

    scenario.attack_with(hellrider, goblin)
    assert scenario.stack_names() == [
        "Hellrider's triggered ability",
        "Hellrider's triggered ability",
    ]

    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18, "one damage per attacker, before combat damage"


def test_a_you_attack_trigger_fires_once_regardless_of_attacker_count():
    """Guide of Souls: "Whenever you attack, you may pay {E}{E}{E}. ..."

    CR 508.3d: "An ability that reads 'Whenever [a player] attacks, . . .'
    triggers if one or more creatures that player controls are declared as
    attackers" - once for the declaration, unlike Hellrider's per-creature
    "a creature you control attacks" above. Two attackers still make one
    ability, not two.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Guide of Souls", "Raging Goblin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide, goblin = scenario.creatures("Guide of Souls", "Raging Goblin", username="alice")

    scenario.attack_with(guide, goblin)

    assert scenario.stack_names() == ["Guide of Souls's triggered ability"]


def test_a_you_attack_trigger_does_not_fire_for_the_opponents_attack():
    """Only the attacking player's own "whenever you attack" ability fires."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Raging Goblin"])
        .player("bob", library=["Forest"], battlefield=["Guide of Souls"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    goblin = scenario.creature("Raging Goblin", "alice")

    scenario.attack_with(goblin)

    assert scenario.stack_names() == []


def test_a_block_trigger_reads_the_creature_on_the_other_side():
    """Ashmouth Hound: "Whenever this creature blocks or becomes blocked by a
    creature, this creature deals 1 damage to that creature." (CR 509.1a)

    Two Hounds facing each other trigger twice, once from each side, and each one
    damages the other - which kills both, since a Hound is a 2/1.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Ashmouth Hound"])
        .player("bob", library=["Forest"], battlefield=["Ashmouth Hound"])
        .build()
    )
    scenario.start_at(Step.DECLARE_BLOCKERS)
    attacker = scenario.creature("Ashmouth Hound", "alice")
    blocker = scenario.creature("Ashmouth Hound", "bob")

    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)
    assert len(scenario.game.abilities_on_stack) == 2

    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert attacker.zone is Zone.GRAVEYARD
    assert blocker.zone is Zone.GRAVEYARD


def test_the_active_players_trigger_goes_on_the_stack_first():
    """CR 603.3b: APNAP order, so the active player's ability resolves last.

    "First, each player, in APNAP order, puts each triggered ability they control
    on the stack." The first one on is the lowest, so alice's Hound - alice being
    the active player - is the one that resolves second.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Ashmouth Hound"])
        .player("bob", library=["Forest"], battlefield=["Ashmouth Hound"])
        .build()
    )
    scenario.start_at(Step.DECLARE_BLOCKERS)
    attacker = scenario.creature("Ashmouth Hound", "alice")
    blocker = scenario.creature("Ashmouth Hound", "bob")

    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)

    assert [ability.controller for ability in scenario.game.abilities_on_stack] == ["alice", "bob"]


def test_re_declaring_the_same_block_does_not_trigger_twice():
    """One blocking pair is one event, however often the declaration is rebuilt.

    `Scenario.block` re-declares the whole block each time it is called
    (CR 509.1 makes the declaration legal or illegal as a whole), which must not
    turn one block into two triggers.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", library=["Forest"], battlefield=["Ashmouth Hound", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_BLOCKERS)
    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant", username="alice")
    hound = scenario.creature("Ashmouth Hound", "bob")
    other = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(bears, giant)
    scenario.block(bears, hound)
    scenario.block(giant, other)

    assert len(scenario.game.abilities_on_stack) == 1, "only the Hound has a block trigger"


# -- beginning of a step (CR 500.6) ---------------------------------------


def test_an_upkeep_trigger_fires_when_the_step_begins():
    """Delver of Secrets, with an instant on top of the library.

    CR 500.6: "When a phase or step begins, any abilities that trigger 'at the
    beginning of' that phase or step trigger. They are put on the stack the next
    time a player would receive priority." CR 701.27a then transforms it.

    The reveal is *not* an intervening *if* (CR 603.4): the condition sits inside
    the effect, so the ability triggers whatever is on top of the library.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Lightning Bolt", "Forest"], battlefield=["Delver of Secrets"])
        .player("bob", library=["Forest"])
        .build()
    )
    delver = scenario.creature("Delver of Secrets // Insectile Aberration", "alice")

    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP
    assert scenario.stack_names() == [
        "Delver of Secrets // Insectile Aberration's triggered ability"
    ]

    scenario.pass_until_resolved()
    assert delver.transformed


def test_the_upkeep_trigger_still_happens_when_the_reveal_misses():
    """A land on top: the ability triggers, resolves, and transforms nothing."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Forest"], battlefield=["Delver of Secrets"])
        .player("bob", library=["Forest"])
        .build()
    )
    delver = scenario.creature("Delver of Secrets // Insectile Aberration", "alice")

    scenario.advance()
    assert len(scenario.game.abilities_on_stack) == 1, "it triggered - the if is inside the effect"

    scenario.pass_until_resolved()
    assert not delver.transformed


def test_an_upkeep_trigger_belongs_to_its_controller_not_to_every_upkeep():
    """ "At the beginning of *your* upkeep" - bob's upkeep is not alice's."""
    scenario = (
        Scenario()
        .player("alice", library=["Lightning Bolt", "Forest", "Forest"])
        .player("bob", library=["Forest", "Forest"], battlefield=["Delver of Secrets"])
        .build()
    )
    scenario.advance()  # alice's upkeep
    assert scenario.game.stack_is_empty, "the Delver is bob's, and it is not bob's turn"


# -- the intervening if (CR 603.4, 608.2a) --------------------------------


def test_an_intervening_if_that_is_false_stops_the_ability_triggering():
    """Thopter Assembly: "if you control no Thopters other than this creature".

    CR 603.4: "When the trigger event occurs, the ability checks whether the
    stated condition is true. The ability triggers only if it's true." A second
    Thopter Assembly is itself a Thopter, so the clause is false and nothing goes
    on the stack at all - which is a different thing from triggering and fizzling.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Thopter Assembly"] * 2)
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.advance()  # untap -> upkeep

    assert scenario.game.stack_is_empty
    assert scenario.pending_triggers == []


def test_an_intervening_if_that_is_true_lets_the_ability_trigger():
    """The control: one Thopter Assembly, so the clause holds and it triggers.

    Both halves of the effect happen, in printed order (CR 608.2c): the
    Assembly returns to hand and five 1/1 colorless Thopter artifact creature
    tokens with flying are created (CR 111, CR 701.7a) - `create_tokens`/
    `THOPTER` were already load-bearing elsewhere in `machines/effects.py`
    (Hangarback Walker), so the old claim that tokens were unmodelled here was
    stale rather than a real gap. See `docs/engine-coverage.md`.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Thopter Assembly"])
        .player("bob", library=["Forest"])
        .build()
    )
    assembly = scenario.creature("Thopter Assembly", "alice")
    scenario.advance()

    assert scenario.stack_names() == ["Thopter Assembly's triggered ability"]
    scenario.pass_until_resolved()
    assert assembly.zone is Zone.HAND
    thopters = [state for state in scenario.game.battlefield if state.name == "Thopter Token"]
    assert len(thopters) == 5


def test_an_intervening_if_is_checked_again_on_resolution():
    """CR 608.2a: a clause that has since become false removes the ability.

    "If a triggered ability has an intervening 'if' clause, it checks whether the
    clause's condition is true. If it isn't, the ability is removed from the
    stack and does nothing." A second Thopter arriving while the trigger waits is
    exactly that, and the first Assembly stays put.
    """
    scenario = (
        Scenario()
        .player(
            "alice", library=["Forest"], hand=["Thopter Assembly"], battlefield=["Thopter Assembly"]
        )
        .player("bob", library=["Forest"])
        .build()
    )
    assembly = scenario.creature("Thopter Assembly", "alice")
    scenario.advance()
    assert scenario.stack_names() == ["Thopter Assembly's triggered ability"]

    scenario.put_onto_battlefield("Thopter Assembly")  # in response

    scenario.pass_until_resolved()
    assert assembly.zone is Zone.BATTLEFIELD, "the ability was removed and did nothing"
    assert scenario.game.stack_is_empty
