"""Edicts (CR 701.21a) with a "greatest mana value" qualifier and a
sacrifice-then-conditional-consequence shape, and two library-placement
templates: an owner's May choice between the top of their library (with a
consequence) and the bottom, and a target's owner shuffling it into their
own library.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.21a** - to sacrifice a permanent, its controller moves it to the
  graveyard; the sacrificing player chooses which one, among a description.
- **CR 115.10a** - being affected by an edict's description is not being
  targeted.
- **CR 118.12** - "[A player] may [do something]. If [that player] [does],
  [effect]."
- **CR 401.2** - a library's top and bottom are opposite ends of one pile.
- **CR 701.20a** - to shuffle a library puts it in a random order.
- **CR 108.3** - a card's owner, distinct from its controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_break_under_pressure_sacrifices_the_greatest_mana_value_permanent() -> None:
    """ "Target opponent sacrifices a creature or planeswalker with the
    greatest mana value among creatures and planeswalkers they control." -
    only the highest-mana-value candidate is eligible; a land is never in
    the pool at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Break Under Pressure"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Serra Angel", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    life_before = scenario.game.player("alice").life

    scenario.cast_and_resolve(
        "Break Under Pressure",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=["bob"],
    )

    assert angel.zone is Zone.GRAVEYARD, "Serra Angel (MV 6) is strictly higher than Bears (MV 2)"
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.player("alice").life == life_before + 2


def test_riveteers_charm_off_set_reads_the_same_greatest_mv_grammar() -> None:
    """Riveteers Charm (not in this pool, not the reported card): mode one,
    "Target opponent sacrifices a creature or planeswalker they control with
    the greatest mana value among creatures and planeswalkers they control."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Riveteers Charm"], battlefield=["Swamp", "Mountain", "Forest"])
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast("Riveteers Charm")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_garruk_minus_two_sacrifices_then_makes_a_beast_if_alice_sacrificed() -> None:
    """ "Each player sacrifices a creature of their choice. If you sacrificed
    a creature this way, create a 4/4 green Beast creature token with
    trample." - the token is conditional on the *controller's own* sacrifice,
    not merely on anyone's.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Garruk, Veiled Butcher", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find("Garruk, Veiled Butcher", Zone.BATTLEFIELD, "alice")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")

    scenario.activate(garruk, index=1)  # -2, no mana cost beyond the loyalty
    scenario.resolve_top()

    assert alice_bears.zone is Zone.GRAVEYARD
    assert bob_angel.zone is Zone.GRAVEYARD
    beasts = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Beast Token"
    ]
    assert len(beasts) == 1
    assert beasts[0].counters is not None  # exists; power/toughness asserted next
    assert scenario.game.characteristics_of(beasts[0]).power_toughness == (4, 4)


# Rise of the Witch-king (not in this pool) reads the identical "Each player
# sacrifices a creature of their choice. If you sacrificed a creature this
# way, <consequence>." antecedent Garruk, Veiled Butcher's own -2 does - the
# real off-set proof that `_parse_each_sacrifices_then_if_you_did_clause` is
# not fitted to one card. Its own consequence, "you may return another
# permanent card from your graveyard to the battlefield", needs a graveyard-
# reanimation-choice reader this stream does not build (no existing "return a
# chosen card from your own graveyard" primitive, only "return *this* card
# from your graveyard"), so it is not a passing scenario test here - noted
# rather than silently dropped.


def test_clash_of_elements_puts_the_permanent_on_top_and_deals_damage() -> None:
    """ "Choose target nonland permanent. Its owner may put it on the top of
    their library. If they do, Clash of Elements deals 2 damage to them."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Clash of Elements"], battlefield=["Island", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_life_before = scenario.game.player("bob").life
    scenario.will_take_the_may(True, source="Clash of Elements")

    scenario.cast_and_resolve(
        "Clash of Elements",
        *scenario.untapped_sources("Island", "Mountain", "Mountain"),
        targets=[bears],
    )

    assert bears.zone is Zone.LIBRARY
    assert scenario.game.player("bob").library[0] is bears
    assert scenario.game.player("bob").life == bob_life_before - 2


def test_clash_of_elements_bottoms_the_card_when_the_owner_declines() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Clash of Elements"], battlefield=["Island", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_life_before = scenario.game.player("bob").life
    scenario.will_take_the_may(False, source="Clash of Elements")

    scenario.cast_and_resolve(
        "Clash of Elements",
        *scenario.untapped_sources("Island", "Mountain", "Mountain"),
        targets=[bears],
    )

    assert bears.zone is Zone.LIBRARY
    assert scenario.game.player("bob").library[-1] is bears
    assert scenario.game.player("bob").life == bob_life_before


def test_living_library_shuffles_the_targeted_permanent_into_its_owners_library() -> None:
    """ "{6}, Sacrifice this creature: Choose target creature or planeswalker
    an opponent controls. Its owner shuffles it into their library."
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Living Library"] + ["Forest"] * 6)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library = scenario.creature("Living Library", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(library, *scenario.untapped_sources(*["Forest"] * 6), targets=[bears])
    scenario.resolve_top()

    assert library.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.LIBRARY
    assert bears in scenario.game.player("bob").library


def test_deglamer_off_set_reads_the_same_shuffle_shape() -> None:
    """Deglamer (not in this pool, not the reported card): "Choose target
    artifact or enchantment. Its owner shuffles it into their library."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Deglamer"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Witch's Oven"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    oven = scenario.find("Witch's Oven", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Deglamer", *scenario.untapped_sources("Forest", "Forest"), targets=[oven]
    )

    assert oven.zone is Zone.LIBRARY
    assert oven in scenario.game.player("bob").library
