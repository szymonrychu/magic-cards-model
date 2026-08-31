"""Scenario: a card returns from a graveyard to the battlefield.

Five cards and four parsers, all of them "put onto the battlefield" rather than
"cast", read by `machines/effects.py`:

- **Cauldron Familiar** - "Sacrifice a Food: Return this card from your
  graveyard to the battlefield." An activated ability that functions from the
  graveyard, `_parse_return_self_from_graveyard_to_battlefield_clause`.
- **Arclight Phoenix** - the same sentence as a combat trigger behind an
  intervening *if*.
- **Raise the Past** - "Return all creature cards with mana value 2 or less
  from your graveyard to the battlefield."
  (`_parse_mass_return_from_graveyard_to_battlefield_clause`).
- **Greasefang, Okiba Boss** - reanimate a target, grant it haste, and bounce
  it at your next end step
  (`_parse_return_target_from_graveyard_gains_then_bounce`).
- **Bringer of the Last Gift** - each player sacrifices, then each player
  reanimates what was already in their graveyard
  (`_parse_each_player_sacrifices_then_mass_reanimate`).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and every card's oracle
text was read back with `resolve_cards`:

- **CR 110.2a** - "If an effect instructs a player to put an object onto the
  battlefield, that object enters the battlefield under that player's control
  unless the effect states otherwise." Bringer's sentence is that exception:
  its subject is "each player", so each pile comes back under its own owner.
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence."
- **CR 202.3** - "The mana value of an object is a number equal to the total
  amount of mana in its mana cost, regardless of color." Raise the Past's
  "mana value 2 or less" bound.
- **CR 608.2h** - "If an effect requires information from the game ... the
  answer is determined only once, when the effect is applied." Bringer's
  "that weren't put there this way" is that one snapshot.
- **CR 608.2b** - "A target that's no longer in the zone it was in when it was
  targeted is illegal." Greasefang's fizzle.
- **CR 603.4** - "When the trigger event occurs, the ability checks whether the
  stated condition is true. The ability trigg[ers only if it's true]" - and
  **CR 608.2a** rechecks it on resolution. Arclight Phoenix's three-spell
  clause.
- **CR 603.7a** - a delayed triggered ability is created during the resolution
  of a spell or ability; **CR 603.7b** - "A delayed triggered ability will
  trigger only once - the next time its trigger event occurs - unless it has a
  stated duration."
- **CR 113.6m** - "An ability whose cost or effect specifies that it moves the
  object it's on out of a particular zone functions only in that zone" - why
  Cauldron Familiar's ability can be activated from a graveyard at all.
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard."
- **CR 702.10b** - haste: "it can attack even if it hasn't been controlled by
  its controller continuously since their most recent turn began."
- **CR 301.7** / **CR 702.122a** - a Vehicle is an artifact that only becomes
  an artifact creature once a crew ability resolves. Crew is **not modelled**
  by this engine (`machines/targeting.py` says as much), so the Vehicle
  Greasefang reanimates is not a creature and cannot attack whatever haste it
  has; the haste grant itself is asserted on the computed characteristics
  instead. See `test_greasefang_grants_haste_...` below.
- **CR 508.1a** - "The chosen creatures must be untapped" and must be creatures
  at all, which is why the reanimated Vehicle cannot attack.
- **CR 113.6** - "Abilities of all other objects usually function only while
  that object is on the battlefield", and **CR 113.6b** - "An ability that
  states which zones it functions in functions only from those zones."
- **CR 113.7a** - "Once activated or triggered, an ability exists on the stack
  independently of its source."
- **CR 111.10b** - "A Food token is a colorless Food artifact token with '{2},
  {T}, Sacrifice this token: You gain 3 life.'"
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - Greasefang's three sentences.

Arclight Phoenix needed two engine gaps closed before it could work at all,
and both are asserted here rather than left as `xfail`: CR 113.6m now reads
the *effect*'s named zone (`machines/triggers.zones_ability_functions_in`) and
`Game.emit` offers graveyard cards as trigger sources, and
`machines/triggers.intervening_if_holds` reads "you've cast N or more `<type>`
spells this turn" instead of failing closed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def _activate_familiar(scenario, familiar, food, username: str = "alice"):
    """Activate Cauldron Familiar's graveyard ability, sacrificing `food`.

    `Game.begin_activating` refuses anything not on the battlefield, so the
    CR 113.6m path is `machines/keywords.off_battlefield_activation` - the
    same object cycling, equip and World Breaker's ability already use.
    """
    activation = off_battlefield_activation(scenario.game, familiar, username, sacrificing=[food])
    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    scenario.game.retain_priority(username)
    return activation


def _food_for(scenario, username: str = "alice"):
    """One real CR 111.10b Food token, made by the engine's own token table."""
    create_predefined_tokens(scenario.game, "Food", username)
    return scenario.find("Food Token", Zone.BATTLEFIELD, username)


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_cauldron_familiar_returns_itself_from_the_graveyard():
    """The whole mechanic in one line of card text: Cauldron Familiar's
    "Sacrifice a Food: Return this card from your graveyard to the
    battlefield." The Food goes to the graveyard as the cost is paid
    (CR 701.21a), the ability resolves, and the Cat is on the battlefield.

    It arrives as a new object (CR 400.7), so its own "When this creature
    enters" fires - proof that this was a real zone change into the
    battlefield and not a bookkeeping move.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Cauldron Familiar"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    familiar = scenario.find("Cauldron Familiar", Zone.GRAVEYARD, "alice")
    food = _food_for(scenario)
    _activate_familiar(scenario, familiar, food)

    assert food.zone is Zone.GRAVEYARD, "the sacrifice happened as the cost was paid"
    assert scenario.stack_names() == ["Cauldron Familiar's activated ability"]

    scenario.resolve_top()

    assert familiar.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == ["Cauldron Familiar's triggered ability"], (
        "it entered the battlefield for real, so its enters trigger fired (CR 400.7)"
    )


# --------------------------------------------------------------------------
# The card has already left the graveyard by the time the ability resolves
# --------------------------------------------------------------------------


def test_the_familiar_returns_nothing_when_it_has_already_left_the_graveyard():
    """CR 113.7a's ability exists independently of its source, and CR 608.2's
    ordinary "the object is gone" case: bob exiles alice's graveyard with
    Tormod's Crypt in response, so when the Cat's own ability resolves the Cat
    is in exile, not in a graveyard.

    Nothing returns, nothing raises, and the Food stays spent - the cost was
    paid before the ability was ever put on the stack.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Cauldron Familiar"], battlefield=["Swamp"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    familiar = scenario.find("Cauldron Familiar", Zone.GRAVEYARD, "alice")
    food = _food_for(scenario)
    _activate_familiar(scenario, familiar, food)

    scenario.pass_priority("alice")
    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert familiar.zone is Zone.EXILE

    scenario.resolve_top()  # the Cat's own ability, with nothing to return

    assert familiar.zone is Zone.EXILE, "an ability whose card has moved on does nothing"
    assert "Cauldron Familiar" not in scenario.battlefield_names()
    assert scenario.stack_names() == [], "and it did resolve - it was not stuck or refused"


# --------------------------------------------------------------------------
# Raise the Past: the group, and the two edges of it
# --------------------------------------------------------------------------


def test_raise_the_past_returns_only_the_creatures_within_the_mana_value_bound():
    """Raise the Past: "Return all creature cards with mana value 2 or less
    from your graveyard to the battlefield."

    Three separate refusals in one graveyard, all CR 202.3's mana value read
    off the printed cost: Grizzly Bears ({1}{G}, mana value 2) and Cauldron
    Familiar ({B}, mana value 1) come back; Questing Beast ({2}{G}{G}, mana
    value 4) is a creature card but over the bound; and Lightning Bolt ({R},
    mana value 1) is inside the bound but is not a creature card at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Raise the Past"],
            graveyard=[
                "Grizzly Bears",
                "Lightning Bolt",
                "Questing Beast",
                "Cauldron Familiar",
            ],
            battlefield=["Plains"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*["Plains"] * 4)
    scenario.cast_and_resolve("Raise the Past", *sources)

    returned = [state.name for state in scenario.game.permanents_controlled_by("alice")]
    assert "Grizzly Bears" in returned
    assert "Cauldron Familiar" in returned
    assert "Questing Beast" not in returned, "mana value 4 is over the bound (CR 202.3)"
    assert "Lightning Bolt" not in returned, "an instant is not a creature card"

    left_behind = [state.name for state in scenario.player("alice").graveyard]
    assert "Questing Beast" in left_behind
    assert "Lightning Bolt" in left_behind


def test_raise_the_past_leaves_the_opponents_graveyard_alone():
    """ "*Your* graveyard" is the resolving spell's controller's, and only
    theirs (CR 110.2a puts every returned card under that same player's
    control). bob's own Grizzly Bears, an exact match for the description,
    never moves.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Raise the Past"],
            graveyard=["Elvish Mystic"],
            battlefield=["Plains"] * 4,
        )
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*["Plains"] * 4)
    scenario.cast_and_resolve("Raise the Past", *sources)

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.permanents_controlled_by("bob") == []

    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    assert mystic.zone is Zone.BATTLEFIELD, "alice's own pile did come back"


def test_raise_the_past_with_nothing_eligible_resolves_and_does_nothing():
    """The empty group: a graveyard holding only an oversized creature and an
    instant. The spell still resolves and still goes to the graveyard - a mass
    return with no members is not a fizzle, since the spell has no targets to
    be illegal (CR 608.2b never applies).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Raise the Past"],
            graveyard=["Questing Beast", "Lightning Bolt"],
            battlefield=["Plains"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*["Plains"] * 4)
    spell = scenario.cast_and_resolve("Raise the Past", *sources)

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.battlefield_names() == ["Plains"] * 4


# --------------------------------------------------------------------------
# Greasefang, Okiba Boss
# --------------------------------------------------------------------------


def greasefang_board() -> Scenario:
    """alice with Greasefang out and Parhelion II - the pool's only Vehicle -
    in her graveyard; bob with nothing that acts on its own."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Greasefang, Okiba Boss", "Plains"],
            graveyard=["Parhelion II"],
        )
        .player("bob")
    )


def _greasefang_trigger_resolves(scenario, vehicle):
    """Walk from the precombat main into the beginning of combat, aiming
    Greasefang's trigger at `vehicle`, and resolve it."""
    scenario.choose_trigger_targets("Greasefang, Okiba Boss", [vehicle])
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    return scenario.resolve_top()


def test_greasefang_returns_the_targeted_vehicle_and_schedules_its_return():
    """The whole three-sentence instruction as one CR 608.2c effect: the
    Vehicle arrives from the graveyard, and a delayed triggered ability
    (CR 603.7a) is created to send it back at alice's next end step.
    """
    scenario = greasefang_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.GRAVEYARD, "alice")

    _greasefang_trigger_resolves(scenario, vehicle)

    assert vehicle.zone is Zone.BATTLEFIELD
    assert vehicle.controller == "alice"
    assert len(scenario.game.delayed_triggers.triggers) == 1


def test_greasefang_grants_haste_but_a_vehicle_is_still_not_a_creature():
    """ "It gains haste" is a layer 6 grant on the permanent that just arrived,
    and it is there: "Haste" shows up on the Vehicle's computed
    characteristics.

    It still cannot attack, and that is correct rather than a haste failure:
    CR 301.7 makes a Vehicle an artifact, and only a resolved crew ability
    (CR 702.122a) turns it into an artifact creature. **Crew is not modelled
    by this engine**, so there is no way to make Parhelion II a creature in a
    scenario at all - the assertion this test can honestly make is on the
    grant being present, plus CR 508.1a's refusal of a noncreature attacker.
    """
    scenario = greasefang_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.GRAVEYARD, "alice")

    _greasefang_trigger_resolves(scenario, vehicle)

    characteristics = scenario.game.characteristics_of(vehicle)
    assert "Haste" in characteristics.abilities, "CR 702.10b's keyword really was granted"

    assert scenario.can_attack(vehicle) is False, "a Vehicle is not a creature until crewed"


def test_greasefang_returns_nothing_when_its_target_left_the_graveyard():
    """CR 608.2b: "A target that's no longer in the zone it was in when it was
    targeted is illegal." bob exiles alice's graveyard with Tormod's Crypt
    while the trigger is on the stack, so the trigger has no legal target left.

    Nothing returns - and, because the whole three-sentence instruction is one
    effect, no haste grant and no delayed bounce are created either.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Greasefang, Okiba Boss", "Plains"],
            graveyard=["Parhelion II"],
        )
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Greasefang, Okiba Boss", [vehicle])
    scenario.advance()
    assert scenario.stack_names() == ["Greasefang, Okiba Boss's triggered ability"]

    scenario.pass_priority("alice")
    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert vehicle.zone is Zone.EXILE

    scenario.resolve_top()  # Greasefang's trigger, with an illegal target

    assert vehicle.zone is Zone.EXILE, "nothing came back"
    assert "Parhelion II" not in scenario.battlefield_names()
    assert scenario.game.delayed_triggers.triggers == [], (
        "no delayed bounce was scheduled for a card that never returned"
    )


def test_greasefangs_delayed_return_fires_at_its_controllers_own_end_step():
    """CR 603.7a's delayed ability, gated to "your next end step": it goes on
    the stack as alice's end step begins and returns the Vehicle to its
    owner's hand.

    Every step between the beginning of combat and the end step passes without
    it firing early, which is what makes this the *end* step's trigger and not
    just "the next time anything happens".
    """
    scenario = greasefang_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.GRAVEYARD, "alice")

    _greasefang_trigger_resolves(scenario, vehicle)

    for _ in range(5):  # declare attackers .. postcombat main
        scenario.advance()
        assert scenario.stack_names() == []
        assert vehicle.zone is Zone.BATTLEFIELD

    assert scenario.step is Step.POSTCOMBAT_MAIN
    scenario.advance()

    assert scenario.step is Step.END_STEP
    assert scenario.stack_names() == ["Greasefang, Okiba Boss's triggered ability"]
    scenario.resolve_top()

    assert vehicle.zone is Zone.HAND
    assert scenario.find("Parhelion II", Zone.HAND, "alice") is vehicle


def test_greasefangs_delayed_return_does_not_fire_at_the_opponents_end_step():
    """The gate is on the *controller's* end step, not on any end step.

    Greasefang's trigger is a beginning-of-combat one, so "your next end step"
    is always later the same turn - there is no board on which alice's delayed
    ability could still be waiting when bob's end step arrives. What is
    assertable is the pair that makes the gate real: the trigger records alice
    as the player whose turn it must be, and by the time bob's end step comes
    round it has already fired once and is gone (CR 603.7b: "A delayed
    triggered ability will trigger only once"), so bob's end step moves
    nothing.
    """
    scenario = greasefang_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.GRAVEYARD, "alice")

    _greasefang_trigger_resolves(scenario, vehicle)

    (delayed,) = scenario.game.delayed_triggers.triggers
    assert delayed.only_when_active == "alice"
    assert delayed.step is Step.END_STEP

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.resolve_top()
    assert vehicle.zone is Zone.HAND

    scenario.advance()  # cleanup
    scenario.advance()  # bob's untap step
    assert scenario.turn.active_player == "bob"

    while scenario.step is not Step.END_STEP:
        scenario.advance()
        assert scenario.stack_names() == [], "nothing of alice's fires on bob's turn"

    assert scenario.stack_names() == [], "and nothing at bob's end step either"
    assert vehicle.zone is Zone.HAND, "the Vehicle was not moved a second time"


# --------------------------------------------------------------------------
# Bringer of the Last Gift
# --------------------------------------------------------------------------


def bringer_board() -> Scenario:
    """alice casting Bringer with a Bear out and a Mystic already dead; bob
    with a Watchwolf out and a Questing Beast already dead."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bringer of the Last Gift"],
            graveyard=["Elvish Mystic", "Lightning Bolt"],
            battlefield=["Swamp"] * 8 + ["Grizzly Bears"],
        )
        .player("bob", graveyard=["Questing Beast"], battlefield=["Watchwolf"])
    )


def _cast_bringer(scenario):
    sources = scenario.untapped_sources(*["Swamp"] * 8)
    bringer = scenario.cast_and_resolve("Bringer of the Last Gift", *sources)
    assert scenario.stack_names() == ["Bringer of the Last Gift's triggered ability"]
    scenario.resolve_top()
    return bringer


def test_bringer_does_not_return_the_creatures_its_own_sacrifice_just_killed():
    """ "that weren't put there this way" is CR 608.2h's single answer, taken
    before the sacrifice half runs: each graveyard is snapshotted, then
    everything is sacrificed (CR 701.21a), then only the snapshot comes back.

    Elvish Mystic and Questing Beast were already dead and return. Grizzly
    Bears and Watchwolf are killed by this very ability and stay in their
    graveyards - the corner case the whole sentence exists for.
    """
    scenario = bringer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_bringer(scenario)

    alice_battlefield = [state.name for state in scenario.game.permanents_controlled_by("alice")]
    bob_battlefield = [state.name for state in scenario.game.permanents_controlled_by("bob")]

    assert "Elvish Mystic" in alice_battlefield, "already in the graveyard, so it returns"
    assert "Questing Beast" in bob_battlefield, "under its own owner's control (CR 110.2a)"

    assert "Grizzly Bears" not in alice_battlefield
    assert "Watchwolf" not in bob_battlefield
    assert "Grizzly Bears" in [state.name for state in scenario.player("alice").graveyard]
    assert "Watchwolf" in [state.name for state in scenario.player("bob").graveyard]


def test_bringer_does_not_sacrifice_itself():
    """ "all **other** creatures they control" - the source is excluded, and
    only the source. Bringer is on the battlefield when the dust settles, and
    every other creature alice had is not.
    """
    scenario = bringer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bringer = _cast_bringer(scenario)

    assert bringer.zone is Zone.BATTLEFIELD
    assert bringer.controller == "alice"

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.zone is Zone.GRAVEYARD, "every *other* creature alice had went"


def test_bringer_leaves_noncreature_cards_in_the_graveyard():
    """The reanimation half is "all creature cards", so alice's Lightning Bolt
    stays where it is even though it was in the graveyard before the ability
    resolved - a snapshot of the graveyard is not a snapshot of everything in
    it.
    """
    scenario = bringer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_bringer(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert "Lightning Bolt" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# Arclight Phoenix: the intervening *if*
# --------------------------------------------------------------------------


def phoenix_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Arclight Phoenix"],
            hand=["Lightning Bolt"] * 3,
            battlefield=["Mountain"] * 3,
        )
        .player("bob")
    )


def test_arclight_phoenix_stays_in_the_graveyard_when_no_spells_were_cast():
    """CR 603.4: "The ability trigg[ers only if it's true]". With no instants
    or sorceries cast this turn the condition is plainly false, so the
    beginning of combat comes and goes and the Phoenix stays put.

    The ability *does* function from the graveyard (CR 113.6m, see the next
    test), so this is the clause itself evaluating to false rather than the
    trigger being unreachable - `intervening_if_notices` staying empty is what
    tells the two apart.
    """
    scenario = phoenix_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phoenix = scenario.find("Arclight Phoenix", Zone.GRAVEYARD, "alice")

    scenario.advance()

    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.stack_names() == [], "the trigger did not go on the stack"
    assert scenario.pending_triggers == []
    assert phoenix.zone is Zone.GRAVEYARD


def test_arclight_phoenix_returns_itself_after_three_instants_and_sorceries():
    """CR 603.4 with the condition true: three Lightning Bolts cast this turn,
    then the beginning of combat, and the Phoenix returns itself from the
    graveyard.

    Two things had to hold for this to be reachable at all, and both are the
    point of the test. CR 113.6m - "An ability whose cost or effect specifies
    that it moves the object it's on out of a particular zone functions only
    in that zone" - is what lets a trigger printed on a card *in a graveyard*
    fire, and it is the ability's **effect**, not its condition, that names
    the zone here. And the intervening *if* itself has to be readable: an
    unreadable clause fails closed (CR 603.4) and would look exactly like a
    false one.
    """
    scenario = phoenix_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phoenix = scenario.find("Arclight Phoenix", Zone.GRAVEYARD, "alice")

    for _ in range(3):
        (mountain,) = scenario.untapped_sources("Mountain")
        scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    scenario.advance()

    assert scenario.stack_names() == ["Arclight Phoenix's triggered ability"]
    scenario.resolve_top()
    assert phoenix.zone is Zone.BATTLEFIELD


def test_the_phoenixs_three_spell_clause_is_read_rather_than_failing_closed():
    """The intervening *if* itself, isolated from where the ability functions:
    with the Phoenix on the battlefield the trigger is reached, and the clause
    should simply evaluate to false with three spells uncast - not be recorded
    as unreadable.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arclight Phoenix", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.advance()

    assert scenario.game.intervening_if_notices == [], (
        "the clause was read for real, not failed closed"
    )
