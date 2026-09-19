"""Scenario: Prepare / preparation cards (CR 722), Reality Fracture's own new
mechanic.

CR 722.1: "Preparation cards have a two-part card frame, with a smaller frame
inset within their text box." CR 722.2a: "The inset frame of a preparation
card is called a 'prepare spell.'" CR 722.3a: "Some spells and abilities
cause a permanent with a prepare spell to become prepared or state that a
permanent enters prepared. If that permanent has the alternative
characteristics of a prepare spell, this gives the permanent the 'prepared'
designation ... A permanent can't gain this designation unless it has a
prepare spell. Additionally, a permanent can't gain this designation if the
permanent already has it." CR 722.3b: "A rule or effect may cause a permanent
to become 'unprepared.' This removes the prepared designation from that
permanent." CR 722.3c: "As a permanent with a prepare spell gains the
prepared designation ..., its controller creates a copy of that object in
exile, except that copy has only the characteristics of that permanent's
prepare spell ... This copy remains in exile for as long as the prepared
permanent remains on the battlefield and has the prepared designation ...
For as long as the copy remains in exile, the prepared permanent's
controller may cast the copy. That permanent loses the prepared designation
at the time the spell becomes cast (see rule 601.2i)." CR 722.3d: "If a
prepare spell is copied, the copy is also a prepare spell."

Every CR number here was verified this session with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models.card import Color, Layout, Type
from magic_cards_model.models.zone import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- reading the card --------------------------------------------------


def test_a_prepare_card_s_inset_frame_is_its_prepare_spell():
    """CR 722.2a: the inset frame - `card_faces[1]` on a real Scryfall
    printing, the same shape every other multifaced layout uses."""
    printing = card("Emergency Phytomedic")
    assert printing.layout is Layout.PREPARE
    face = printing.prepare_spell
    assert face is not None
    assert face.name == "Seed Suture"
    assert face.mana_cost == "{G/W}"


def test_a_non_prepare_card_has_no_prepare_spell():
    assert card("Grizzly Bears").prepare_spell is None


# -- CR 722.3a/722.3c: enters prepared ----------------------------------


def _phytomedic_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Emergency Phytomedic"], battlefield=["Plains", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_a_creature_that_enters_prepared_gets_the_designation_and_an_exile_copy():
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )

    assert phytomedic.zone is Zone.BATTLEFIELD
    assert phytomedic.prepared is True, "CR 722.3a: enters prepared"
    assert phytomedic.prepared_copy_id is not None

    copies = [state for state in scenario.game.exile if state.id == phytomedic.prepared_copy_id]
    assert len(copies) == 1, "CR 722.3c: a copy of that object in exile"
    (copy,) = copies
    assert copy.name == "Seed Suture", "the copy's characteristics are the prepare spell's"
    assert copy.mana_cost == "{G/W}"
    assert Type.SORCERY in copy.types
    assert copy.is_copy is True

    permission = scenario.game.play_permission_for(copy, "alice")
    assert permission is not None, "CR 722.3c: the controller may cast the copy"
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.EXILE


def test_a_permanent_that_already_has_the_designation_cannot_gain_it_again():
    """CR 722.3a's second sentence: a no-op, not a second copy."""
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    before = phytomedic.prepared_copy_id

    made = scenario.game.become_prepared(phytomedic)

    assert made is None
    assert phytomedic.prepared_copy_id == before
    assert len([s for s in scenario.game.exile if s.card.name == phytomedic.card.name]) == 1


def test_a_permanent_with_no_prepare_spell_cannot_become_prepared():
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")

    made = scenario.game.become_prepared(bears)

    assert made is None
    assert bears.prepared is False


# -- CR 722.3c/601.2i: casting the copy ----------------------------------


def test_casting_the_copy_pays_its_own_mana_cost_and_resolves_as_the_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emergency Phytomedic"],
            battlefield=["Plains", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    copy = scenario.game.find_by_id(phytomedic.prepared_copy_id)
    target = scenario.creature("Grizzly Bears", "bob")
    life_before = scenario.player("alice").life

    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([target])
    (forest,) = scenario.untapped_sources("Forest")
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert target.counters.counts.get("+1/+1", 0) == 1, (
        "Seed Suture: a +1/+1 counter on target creature"
    )
    assert scenario.player("alice").life == life_before + 1, "Seed Suture: gain 1 life"


def test_casting_the_copy_removes_the_prepared_designation_cr_601_2i():
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    copy = scenario.game.find_by_id(phytomedic.prepared_copy_id)
    target = scenario.creature("Grizzly Bears", "bob")

    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)

    assert phytomedic.prepared is False, "CR 601.2i: lost as the spell becomes cast"
    assert phytomedic.prepared_copy_id is None
    assert copy.zone is Zone.STACK
    assert copy not in scenario.game.exile


# -- CR 722.3a: "becomes prepared" self triggers -------------------------


def test_an_upkeep_intervening_if_becomes_prepared_and_is_idempotent():
    """Woodwork Prodigy: "At the beginning of your upkeep, if this creature
    isn't prepared, it becomes prepared." CR 603.4's intervening if refuses
    a second copy the next upkeep, since the creature is already prepared."""
    scenario = (
        Scenario().player("alice", library=["Forest"] * 5, battlefield=["Woodwork Prodigy"]).build()
    )
    prodigy = scenario.creature("Woodwork Prodigy")
    assert prodigy.prepared is False

    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert prodigy.prepared is True
    (copy,) = [s for s in scenario.game.exile if s.id == prodigy.prepared_copy_id]
    assert copy.name == "Soul Tether"

    # A second upkeep: the intervening if is now false, so no second copy.
    while scenario.step is Step.UPKEEP:
        scenario.advance()
    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert prodigy.prepared_copy_id == copy.id
    assert len([s for s in scenario.game.exile if s.card.id == prodigy.card.id]) == 1


def test_an_end_step_intervening_if_reuses_the_this_turn_history_predicate():
    """Bloodline Recollector: "At the beginning of each end step, if three or
    more creatures died this turn, this creature becomes prepared." Proves
    the mechanic generalizes off a different trigger event, a different
    intervening-if predicate (S5's `creatures_died_this_turn`), and explicit
    "this creature" rather than anaphoric "it"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            battlefield=["Bloodline Recollector"] + ["Raging Goblin"] * 3,
        )
        .build()
    )
    recollector = scenario.creature("Bloodline Recollector")
    goblins = scenario.creatures("Raging Goblin", "Raging Goblin", "Raging Goblin")
    for goblin in goblins:
        scenario.game.destroy(goblin)
    assert scenario.game.creatures_died_this_turn == 3

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert recollector.prepared is True
    (copy,) = [s for s in scenario.game.exile if s.id == recollector.prepared_copy_id]
    assert copy.name == "Ancestral Craving"


# -- CR 722.3a: targeted and group "becomes prepared" --------------------


def test_codie_s_activated_ability_prepares_only_creatures_with_a_prepare_spell():
    """Codie, Ravenous Codex: "{W}{U}{B}{R}{G}, {T}: Each creature you control
    becomes prepared." CR 722.3a's own refusal (no prepare spell) is what
    keeps Grizzly Bears untouched - not a filter this clause's own parser
    has to apply."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Codie, Ravenous Codex",
                "Emergency Phytomedic",
                "Grizzly Bears",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    codie = scenario.creature("Codie, Ravenous Codex")
    codie.summoning_sick = False
    phytomedic = scenario.creature("Emergency Phytomedic")
    bears = scenario.creature("Grizzly Bears")

    scenario.activate(codie, auto=True)
    scenario.pass_until_resolved()

    assert phytomedic.prepared is True
    assert bears.prepared is False


def test_hexhaven_dueling_arena_prepares_a_target_creature():
    """Hexhaven Dueling Arena's "{4}, {T}: Target creature becomes
    prepared." - the plain, unconditional targeted shape."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hexhaven Dueling Arena", "Emergency Phytomedic"] + ["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    arena = scenario.find("Hexhaven Dueling Arena", Zone.BATTLEFIELD, "alice")
    phytomedic = scenario.creature("Emergency Phytomedic")

    scenario.activate(
        arena,
        *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"),
        index=2,
        targets=[phytomedic],
    )
    scenario.pass_until_resolved()

    assert phytomedic.prepared is True


def test_hexhaven_dueling_arena_s_sorcery_speed_ability_needs_an_attacker():
    """Hexhaven Dueling Arena's "{2}, {T}: Target creature that attacked this
    turn becomes prepared." - `machines/targeting.py`'s own per-turn
    `must_have_attacked_this_turn`, proven against a *different* card and
    mechanism than Hexhaven's own: Emergency Phytomedic attacking in plain
    combat, no cast or upkeep trigger involved. It has to actually have a
    prepare spell too (CR 722.3a) - a vanilla attacker could attack all day
    and never gain the designation, which is not what this clause tests."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Hexhaven Dueling Arena", "Emergency Phytomedic"] + ["Plains"] * 2
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    arena = scenario.find("Hexhaven Dueling Arena", Zone.BATTLEFIELD, "alice")
    attacker = scenario.creature("Emergency Phytomedic", "alice")
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.no_blocks()
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    scenario.activate(
        arena, *scenario.untapped_sources("Plains", "Plains"), index=1, targets=[attacker]
    )
    scenario.pass_until_resolved()

    assert attacker.prepared is True


# -- CR 722.3b: becomes unprepared ---------------------------------------


def test_infinite_coursework_taps_and_unprepares_the_enchanted_creature():
    """Infinite Coursework: "When this Aura enters, tap enchanted creature.
    It becomes unprepared." CR 400.7/603.10's anaphoric "it" is the
    enchanted permanent, read off `CardState.attached_to` - a shape no
    other card in the pool exercises (`enchanted creature` had no reader at
    all before this)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Infinite Coursework"],
            battlefield=["Emergency Phytomedic", "Plains", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.creature("Emergency Phytomedic")
    scenario.game.become_prepared(phytomedic)
    assert phytomedic.prepared is True
    phytomedic.untap()

    scenario.cast_and_resolve(
        "Infinite Coursework",
        *scenario.untapped_sources("Plains", "Island", "Island"),
        targets=[phytomedic],
    )
    scenario.pass_until_resolved()  # the Aura's own "When this Aura enters" trigger

    assert phytomedic.tapped is True, "tap enchanted creature"
    assert phytomedic.prepared is False, "it becomes unprepared"
    assert phytomedic.prepared_copy_id is None
    assert not any(
        state.id != phytomedic.id and state.card.id == phytomedic.card.id
        for state in scenario.game.exile
    ), "the exile copy is gone with the designation"


# -- the five dead inset spells -------------------------------------------


def test_soul_tether_creates_a_heartwood_token():
    """Soul Tether (Heartwood Crafter's inset): "Create a Heartwood token."
    Already generalized by FRA stream S3's predefined-token table; this
    proves the merge carried it through the prepare-copy casting path."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Heartwood Crafter"],
            battlefield=["Forest", "Mountain", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crafter = scenario.cast_and_resolve("Heartwood Crafter", *scenario.untapped_sources("Forest"))
    scenario.game.become_prepared(crafter)
    copy = scenario.game.find_by_id(crafter.prepared_copy_id)
    assert copy.name == "Soul Tether"

    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    heartwoods = [state for state in scenario.game.battlefield if state.name == "Heartwood Token"]
    assert len(heartwoods) == 1
    assert set(heartwoods[0].colors) == {Color.RED, Color.GREEN}


def test_enroot_mills_a_land_from_library_to_graveyard():
    """Enroot (Carnivorous Cultivator's inset): "Search your library for a
    land card, put it into your graveyard, then shuffle." - the new
    `Zone.GRAVEYARD` destination on `Game.search_and_put`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Carnivorous Cultivator"],
            library=["Forest", "Island", "Mountain"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cultivator = scenario.cast_and_resolve(
        "Carnivorous Cultivator", *scenario.untapped_sources("Forest", "Forest")
    )
    assert cultivator.prepared is True, "Carnivorous Cultivator enters prepared"
    copy = scenario.game.find_by_id(cultivator.prepared_copy_id)
    assert copy.name == "Enroot"
    graveyard_before = len(scenario.player("alice").graveyard)

    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    scenario.state_based_actions()  # CR 704.5e: Enroot's own copy ceases to exist

    graveyard = scenario.player("alice").graveyard
    # Only the searched land - Enroot's own copy ceased to exist instead of
    # also reaching the graveyard (CR 704.5e; see test_copies_cease_to_exist.py
    # for the state-based action itself).
    assert len(graveyard) == graveyard_before + 1
    lands = [state for state in graveyard if state.card.is_land]
    assert len(lands) == 1
    assert lands[0].name == "Forest"


def test_arc_of_fortune_lets_each_player_loot_their_hand():
    """Arc of Fortune (Variable Chaser's inset): "Each player may discard
    their hand and draw seven cards." Alice declines, Bob accepts."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Variable Chaser", "Mountain"],
            library=["Forest"] * 10,
            battlefield=["Island"] * 6,
        )
        .player("bob", hand=["Mountain", "Swamp"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chaser = scenario.cast_and_resolve(
        "Variable Chaser", *scenario.untapped_sources("Island", "Island", "Island")
    )
    copy = scenario.game.find_by_id(chaser.prepared_copy_id)
    assert copy.name == "Arc of Fortune"
    bob_hand_before = [c.name for c in scenario.player("bob").hand]

    scenario.will_take_the_may(False, username="alice")
    scenario.will_take_the_may(True, username="bob")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    # Variable Chaser's own Prowess triggers off casting a noncreature spell
    # and sits above Arc of Fortune on the stack - resolve it first.
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]
    assert len(scenario.player("bob").hand) == 7
    assert all(c.name not in bob_hand_before for c in scenario.player("bob").hand)


def test_molten_tide_cast_from_the_prepared_copy_doubles_a_mountain_tap():
    """Pyre Rhymer enters prepared; its copy (Molten Tide) is cast for real
    through the CR 722.3c permission, and resolving it - "Until end of
    turn, whenever you tap a Mountain for mana, add an additional {R}." -
    creates the CR 603.7 delayed trigger FRA S10 built. CR 605.1b/605.4a:
    that delayed trigger is itself a mana ability, so the very next Mountain
    tap adds the extra {R} immediately, with no stack and no
    `put_triggers_on_stack`/`resolve_top` step in between - the two streams'
    own work meeting at the one place both had to agree on.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pyre Rhymer"],
            library=["Forest"] * 5,
            battlefield=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rhymer = scenario.cast_and_resolve(
        "Pyre Rhymer", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    assert rhymer.prepared is True
    copy = scenario.game.find_by_id(rhymer.prepared_copy_id)
    assert copy.name == "Molten Tide"
    assert copy.mana_cost == "{R}"

    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, mountain)
    scenario.put_on_stack(casting)
    # Pyre Rhymer's own Prowess triggers off casting a noncreature spell and
    # sits above Molten Tide on the stack - resolve it first, then the spell.
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.expires_end_of_turn
    assert trigger.remaining is None, "fires on every tap this turn, not only the next one"

    (second_mountain,) = scenario.untapped_sources("Mountain")
    scenario.activate(second_mountain, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 2}
    assert scenario.game.pending_triggers == []
    assert scenario.game.stack_is_empty


# -- CR 722.3d/Codie: "cast a prepared spell" ------------------------------


def test_codie_copies_a_cast_prepared_spell():
    """Codie, Ravenous Codex: "Whenever you cast a prepared spell, copy it.
    You may choose new targets for the copy." - `TriggerEvent.CAST_SPELL`'s
    own "prepared spell" restriction, and the general "copy it" template."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emergency Phytomedic"],
            battlefield=["Codie, Ravenous Codex", "Plains", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    copy = scenario.game.find_by_id(phytomedic.prepared_copy_id)
    target = scenario.creature("Grizzly Bears", "bob")

    scenario.will_take_the_may(False)  # decline new targets for Codie's copy
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([target])
    (forest,) = scenario.untapped_sources("Forest")
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()  # Codie's own cast trigger
    scenario.pass_until_resolved()  # the copy
    scenario.pass_until_resolved()  # the original spell

    assert target.counters.counts.get("+1/+1", 0) == 2, "the original and Codie's copy both hit"
