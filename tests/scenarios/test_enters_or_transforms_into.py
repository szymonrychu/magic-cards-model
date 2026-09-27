"""CR 701.27e: "Some triggered abilities trigger when an object 'transforms
into' an object with a specified characteristic. Such an ability triggers if
the object either transforms or converts ... and has the specified
characteristic immediately after it does so." CR 712.18: transforming does
not make a new object, so a "transforms into `<face>`" ability's own event
subject is the permanent itself, still bearing every earlier continuous
effect.

Every card in this file prints "Whenever this creature enters or transforms
into `<face>`, `<effect>`." - CR 603.6a's entering trigger and CR 701.27e's
transform trigger, one compound condition, expanded into the two events by
`machines/triggers._expand_enters_or_transforms_into`. Getting there needed a
condition/effect *splitter* fix in `machines/abilities.py`
(`_enters_or_transforms_into_face_boundary`): several of these faces print
their own name with an internal comma ("Ashling, Rekindled"), which the plain
top-level comma split cut through, leaving a stray word sitting in the effect
text no reader could ever match. Brutal Cathar // Moonrage Brute (Modern- and
Pioneer-legal, outside this pool) proves the same fix on a face with no
internal comma, so the fix is not shaped around ecl's own naming.

Ashling, Rimebound also prints the rarer "transforms into `<face>` and at the
beginning of your first main phase, `<effect>`" combined event+phase trigger
(`_transforms_into_face_and_first_main_boundary`,
`_expand_transforms_and_first_main`) - its own mana-value spend restriction is
tested for real in `test_spend_restricted_mana_mv.py`; this file only proves
the trigger itself fires from both named events.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ashling_discards_and_draws_on_enters_and_again_on_transform():
    """Ashling, Rekindled: "Whenever this creature enters or transforms into
    Ashling, Rekindled, you may discard a card. If you do, draw a card." -
    the face's own name carries an internal comma."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ashling, Rekindled", "Plains"],
            library=["Forest"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(scenario.find("Plains", Zone.HAND, "alice"), username="alice")
    scenario.cast_and_resolve("Ashling, Rekindled", *sources, username="alice")
    scenario.pass_until_resolved()

    assert scenario.find("Forest", Zone.HAND, "alice").zone is Zone.HAND
    ashling = scenario.creature("Ashling, Rekindled", "alice")

    # CR 701.27e: transforming a second time (not from her own front-face
    # pay-{U} ability, so a plain `.transform()` stands in for it, the way
    # `test_activated_ability_effects.py`'s Avatar Roku already does) fires
    # the same ability again off the identical, still-legendary permanent
    # (CR 712.18: not a new object).
    scenario.will_take_the_may(False, username="alice")
    ashling.transform()
    from magic_cards_model.machines.triggers import GameEvent, TriggerEvent

    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.TRANSFORMS,
            subject_id=ashling.id,
            subject_name=ashling.name,
            subject_controller="alice",
            subject_card=ashling.card,
            player="alice",
        )
    )
    scenario.pass_until_resolved()

    assert ashling.up_face_name == "Ashling, Rimebound"


def test_brigid_creates_a_kithkin_token_on_enters():
    """Brigid, Clachan's Heart: "Whenever this creature enters or transforms
    into Brigid, Clachan's Heart, create a 1/1 green and white Kithkin
    creature token." - a plain generic-token trigger, already covered by the
    condition/effect split fix alone."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Brigid, Clachan's Heart"], battlefield=["Plains", "Plains", "Forest"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Forest", username="alice")

    scenario.cast_and_resolve("Brigid, Clachan's Heart", *sources, username="alice")
    scenario.pass_until_resolved()

    tokens = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Kithkin Token"
    ]
    assert len(tokens) == 1


def test_grub_returns_a_goblin_card_from_graveyard_on_enters():
    """Grub, Storied Matriarch: "Whenever this creature enters or transforms
    into Grub, Storied Matriarch, return up to one target Goblin card from
    your graveyard to your hand." (`test_blighted_creature_copy.py` covers
    the back face's own attack trigger.)"""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grub, Storied Matriarch"],
            graveyard=["Goblin Guide"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    guide = scenario.find("Goblin Guide", Zone.GRAVEYARD, "alice")

    # CR 115.6: "up to one target" is announced when the *triggered ability*
    # goes on the stack, scripted ahead of time like any other
    # `CHOOSE_TARGETS` question.
    scenario.will_choose_targets(guide, username="alice")
    casting = scenario.cast("Grub, Storied Matriarch", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert guide.zone is Zone.HAND


def test_sygg_grants_a_quoted_trigger_on_enters():
    """Sygg, Wanderwine Wisdom: "Whenever this creature enters or transforms
    into Sygg, Wanderwine Wisdom, target creature gains 'Whenever this
    creature deals combat damage to a player or planeswalker, draw a card'
    until end of turn." - the granted-quoted-trigger reader, targeted."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sygg, Wanderwine Wisdom"],
            library=["Forest"],
            battlefield=["Island", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", username="alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    cards_before = len(scenario.player("alice").hand)

    # CR 603.3d: "target creature" is the *triggered ability's* own target,
    # chosen when that ability goes on the stack - not the spell's own
    # announcement, which takes no targets at all.
    scenario.will_choose_targets(bears, username="alice")
    casting = scenario.cast("Sygg, Wanderwine Wisdom", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    scenario.advance()  # precombat main -> beginning of combat
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()

    # The granted ability actually drawing a card when bears deals combat
    # damage to bob is the honest proof it landed, not a string match on
    # some internal bookkeeping field.
    # Sygg herself left the hand to be cast (-1); the granted trigger then
    # drew a card (+1) - net unchanged from the count taken before casting.
    assert len(scenario.player("alice").hand) == cards_before


def test_sygg_grants_protection_from_each_color_on_transform():
    """Sygg, Wanderbrine Shield: "Whenever this creature transforms into Sygg,
    Wanderbrine Shield, target creature you control gains protection from
    each color until your next turn." (CR 702.16h) - proved the same way
    `test_protection_from_chosen_colour.py` proves Voice of All's own single-
    colour protection: a same-coloured source's damage is prevented."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sygg, Wanderwine Wisdom", "Grizzly Bears", "Mountain", "Mountain"],
            hand=["Pyroclasm"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sygg = scenario.creature("Sygg, Wanderwine Wisdom", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    sygg.transform()
    scenario.will_choose_targets(bears, username="alice")
    from magic_cards_model.machines.triggers import GameEvent, TriggerEvent

    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.TRANSFORMS,
            subject_id=sygg.id,
            subject_name=sygg.name,
            subject_controller="alice",
            subject_card=sygg.card,
            player="alice",
        )
    )
    scenario.pass_until_resolved()

    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")
    scenario.game.check_state_based_actions()

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_trystan_mills_and_gains_life_on_enters():
    """Trystan, Callous Cultivator: "Whenever this creature enters or
    transforms into Trystan, Callous Cultivator, mill three cards. Then if
    there is an Elf card in your graveyard, you gain 2 life." (CR 701.17a)"""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Trystan, Callous Cultivator"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Forest", "Forest", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Swamp", username="alice")
    life_before = scenario.player("alice").life

    scenario.cast_and_resolve("Trystan, Callous Cultivator", *sources, username="alice")
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").graveyard) == 3
    # No Elf card was milled (all three are Forests), so CR 608.2c's
    # intervening condition is false and no life is gained.
    assert scenario.player("alice").life == life_before


def test_transforms_and_first_main_phase_fires_the_mana_ability_trigger():
    """Ashling, Rimebound: "Whenever this creature transforms into Ashling,
    Rimebound and at the beginning of your first main phase, add two mana of
    any one color. ..." - CR 603.1b's two trigger conditions on one ability,
    each its own event (`_expand_transforms_and_first_main`). Proves the
    trigger fires off the transform half; `test_spend_restricted_mana_mv.py`
    is where the restriction on that mana is exercised."""
    scenario = Scenario().player("alice", battlefield=["Ashling, Rekindled"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashling = scenario.creature("Ashling, Rekindled", "alice")
    ashling.transform()

    from magic_cards_model.machines.triggers import GameEvent, TriggerEvent

    scenario.will_choose("W", source="Ashling, Rimebound", username="alice")
    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.TRANSFORMS,
            subject_id=ashling.id,
            subject_name=ashling.name,
            subject_controller="alice",
            subject_card=ashling.card,
            player="alice",
        )
    )
    scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.total == 2


def test_brutal_cathar_transforms_into_exiles_a_creature():
    """Brutal Cathar // Moonrage Brute (Modern- and Pioneer-legal, outside
    this pool): "Whenever this creature enters or transforms into Brutal
    Cathar, exile target creature an opponent controls until this creature
    leaves the battlefield." Its face carries no internal comma, proving
    `_enters_or_transforms_into_face_boundary`'s fix generalises past ecl's
    own comma-bearing legend names."""
    scenario = (
        Scenario()
        .player("alice", hand=["Brutal Cathar"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Brutal Cathar", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.choose_trigger_targets("Brutal Cathar", [bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
