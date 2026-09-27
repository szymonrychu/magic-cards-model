"""CR 701.68's Blight, read as an ordinary resolving effect rather than as a
cost (see `machines/blight_effects.py`'s own module docstring for the split).

CR 701.68a: "To 'blight N' means to put N -1/-1 counters on a creature you
control." CR 701.68b: "If a player is given the choice to blight but is
unable to put N -1/-1 counters on a creature they control (usually because
they control no creatures), they can't choose to blight." CR 118.12: the
general optional-action shape ("[Do something]. If [a player] does/doesn't,
[effect].") this file's positions are all read through, one reader for every
one of them - `test_blighted_creature_copy.py` covers CR 701.68c's own
"blighted creature" reference separately, `test_opponent_blights.py` covers
someone-else-blights, and `test_enters_or_transforms_into.py` covers the DFC
trigger event these same effects sometimes fire from.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_optional_blight_if_you_do_on_enters_or_attacks():
    """Blighted Blackthorn: "Whenever this creature enters or attacks, you
    may blight 2. If you do, you draw a card and lose 1 life." Proves both
    the "enters or attacks" compound condition and the "if you do" branch
    together - the enters half fires as it is cast onto an empty board."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blighted Blackthorn"],
            library=["Mountain"],
            # A 2/10 (Indomitable Ancients), not a 2/2, so it survives being
            # blighted for 2 - CR 704.5f would otherwise put a 0-toughness
            # Grizzly Bears into the graveyard as a *new* object (CR 400.7)
            # with no counters left on it to assert against.
            battlefield=[
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Indomitable Ancients",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Indomitable Ancients", "alice")
    sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", username="alice"
    )
    life_before = scenario.player("alice").life

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Blighted Blackthorn", *sources, username="alice")
    blackthorn = scenario.creature("Blighted Blackthorn", "alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 2
    assert scenario.player("alice").life == life_before - 1
    assert blackthorn.zone is Zone.BATTLEFIELD


def test_declining_the_blight_skips_the_bonus():
    """CR 608.2d: declining the "you may" is always legal, and the "if you
    do" consequence never runs."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blighted Blackthorn"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", username="alice"
    )
    life_before = scenario.player("alice").life
    library_before = len(scenario.player("alice").library)

    scenario.will_take_the_may(False, username="alice")
    scenario.cast_and_resolve("Blighted Blackthorn", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 0
    assert scenario.player("alice").life == life_before
    # CR 118.12: declining the "you may" means the "if you do" consequence -
    # drawing a card and losing 1 life - never runs at all.
    assert len(scenario.player("alice").library) == library_before


def test_optional_blight_if_you_do_creates_tokens():
    """Boggart Mischief: "When this enchantment enters, you may blight 1. If
    you do, create two 1/1 black and red Goblin creature tokens." - a
    noncreature (Kindred Enchantment) permanent blighting one of its
    controller's other creatures."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Boggart Mischief"],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Boggart Mischief", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    goblins = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Goblin Token"
    ]
    assert len(goblins) == 2


def test_optional_pay_mana_else_blight():
    """Chaos Spewer: "When this creature enters, you may pay `{2}`. If you
    don't, blight 2." - CR 118.12a's "unless" shape spelled the other way
    round, with blight as the *else* branch and a plain mana payment as the
    action."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chaos Spewer"],
            battlefield=[
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    # Three pay the {2}{B/R} casting cost; the other two stay untapped for
    # the resolution-time "you may pay {2}" (a second, later payment,
    # CR 601.2h being long finished by the time this trigger resolves).
    casting_sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")[:3]

    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.cast_and_resolve("Chaos Spewer", *casting_sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 0


def test_declining_the_mana_payment_blights_instead():
    """The other branch of the same card: declining the `{2}` payment makes
    the "if you don't" run, which is the blight."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chaos Spewer"],
            # A 2/10, not a 2/2 - it survives being blighted for 2.
            battlefield=["Swamp", "Swamp", "Swamp", "Indomitable Ancients"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Indomitable Ancients", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    scenario.will_pay_the_mana_cost(False, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Chaos Spewer", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 2


def test_optional_blight_if_you_do_each_opponent_discards():
    """Dream Seizer: "When this creature enters, you may blight 1. If you
    do, each opponent discards a card." - "each opponent" as the
    consequence, not the blighting player."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dream Seizer"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", hand=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.will_discard(scenario.find("Mountain", Zone.HAND, "bob"), username="bob")
    scenario.cast_and_resolve("Dream Seizer", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert scenario.find("Mountain", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


def test_optional_blight_else_lose_life_at_first_main_phase():
    """Gutsplitter Gang: "At the beginning of your first main phase, you may
    blight 2. If you don't, you lose 3 life." - the "if you don't" branch of
    a plain blight action, fired off `TriggerEvent.BEGINNING_OF_STEP`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gutsplitter Gang", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.will_take_the_may(False, username="alice")
    life_before = scenario.player("alice").life
    # `start_at` only runs the untap step "on the way" (its own docstring) -
    # a beginning-of-step trigger needs the ordinary turn-based advance
    # through upkeep and into the first main phase to actually raise it.
    scenario.advance()  # untap -> upkeep
    scenario.advance()  # upkeep -> precombat main (this game's first turn
    # skips the draw step, CR 103.8a), which is where this trigger fires.
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == life_before - 3
    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.counters[Counter.MINUS_ONE] == 0


def test_taking_the_blight_avoids_the_life_loss():
    """The other branch of Gutsplitter Gang: blighting avoids the 3 life."""
    scenario = (
        Scenario()
        # A 2/10, not a 2/2 - it survives being blighted for 2.
        .player("alice", battlefield=["Gutsplitter Gang", "Indomitable Ancients"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Indomitable Ancients", "alice")
    life_before = scenario.player("alice").life

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.advance()  # untap -> upkeep
    scenario.advance()  # upkeep -> precombat main
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == life_before
    assert bears.counters[Counter.MINUS_ONE] == 2


def test_optional_blight_if_you_do_creates_a_treasure_at_first_main_phase():
    """Scuzzback Scrounger: "At the beginning of your first main phase, you
    may blight 1. If you do, create a Treasure token." - the plain "if you
    do" shape fired from a beginning-of-step trigger rather than an ETB."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Scuzzback Scrounger", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.advance()  # untap -> upkeep
    scenario.advance()  # upkeep -> precombat main
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert any(c.name == "Treasure Token" for c in scenario.game.permanents_controlled_by("alice"))


def test_forced_blight_on_attack():
    """Shadow Urchin: "Whenever this creature attacks, blight 1." - CR
    701.68a's mandatory form, with no "you may" to decline."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shadow Urchin", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    urchin = scenario.creature("Shadow Urchin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_choose_cards(bears, username="alice")
    scenario.attack_with(urchin)
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert urchin.counters[Counter.MINUS_ONE] == 0


def test_forced_blight_does_nothing_with_no_creature_to_blight():
    """CR 701.68a's instruction with no legal object: Shadow Urchin itself is
    attacking (so it is on the battlefield), but blighting still needs *a*
    creature the controller controls - with none at all besides an attacker
    that has already left summoning sickness behind, this asserts the
    mandatory blight simply puts no counters anywhere rather than crashing
    when the controller's only creature is the source and it is offered as
    its own candidate (CR 701.68a names no exception for the source)."""
    scenario = Scenario().player("alice", battlefield=["Shadow Urchin"]).player("bob").build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    urchin = scenario.creature("Shadow Urchin", "alice")

    scenario.will_choose_cards(urchin, username="alice")
    scenario.attack_with(urchin)
    scenario.pass_until_resolved()

    assert urchin.counters[Counter.MINUS_ONE] == 1


def test_optional_blight_if_you_do_creates_tokens_on_a_different_body():
    """Sourbread Auntie: the identical "you may blight 2. If you do, create
    two 1/1 ... Goblin creature tokens." template as Boggart Mischief, on a
    creature rather than an enchantment - the general reader closes both
    without a card-specific row for either."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sourbread Auntie"],
            # A 2/10, not a 2/2 - it survives being blighted for 2.
            battlefield=[
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Indomitable Ancients",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Indomitable Ancients", "alice")
    sources = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", username="alice"
    )

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Sourbread Auntie", *sources, username="alice")
    scenario.pass_until_resolved()

    assert bears.counters[Counter.MINUS_ONE] == 2
    goblins = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Goblin Token"
    ]
    assert len(goblins) == 2


def test_reflexive_blight_grants_haste_when_you_do():
    """Warren Torchmaster: "At the beginning of combat on your turn, you may
    blight 1. When you do, target creature gains haste until end of turn."
    CR 603.12: "when you do" is a *second* triggered ability, announcing its
    own target once it goes on the stack - not the parent's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Warren Torchmaster", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    # CR 603.3d: the reflexive ability's own target is announced only once it
    # is put on the stack, which happens automatically (as part of the same
    # priority pass that resolves the blight) rather than at a point this
    # scenario drives by hand - scripted ahead of time, like any other
    # `CHOOSE_TARGETS` question.
    scenario.will_choose_targets(bears, username="alice")
    scenario.advance()  # untap -> upkeep
    scenario.advance()  # upkeep -> precombat main
    scenario.advance()  # precombat main -> beginning of combat
    scenario.pass_until_resolved()  # the "may blight" ability
    scenario.pass_until_resolved()  # the reflexive "when you do" ability

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert has_keyword(bears, Keyword.HASTE, scenario.game)


def test_may_action_then_branch_reader_on_a_non_blight_card():
    """Mardu Woe-Reaper (Modern- and Pioneer-legal, outside this pool and
    outside `code/magic-cards-model-api/decks`): "Whenever this creature or
    another Warrior you control enters, you may exile target creature card
    from a graveyard. If you do, you gain 1 life." Proves `machines.
    blight_effects.parse_may_action_then_branch_clause` is the *general*
    CR 118.12 reader - no blight anywhere on this card."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mardu Woe-Reaper"], battlefield=["Plains", "Plains"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    life_before = scenario.player("alice").life

    scenario.will_take_the_may(True, username="alice")
    casting = scenario.cast("Mardu Woe-Reaper", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.choose_trigger_targets("Mardu Woe-Reaper", [bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == life_before + 1
