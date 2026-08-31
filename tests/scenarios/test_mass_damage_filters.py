"""Scenario: mass damage aimed at a *subset* of a card type.

"Deals N damage to each creature" was already read. The three shapes here
filter that group, and each one used to leave the whole card silent - the
spell resolved and the board was untouched:

- a negated card type, "each nonartifact creature" (Whipflare);
- a keyword, "each creature with flying" / "each creature without flying"
  (Rough // Tumble);
- a controller group that includes the players, "each opponent and each
  creature and planeswalker they control" (End the Festivities).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 120.1** - "Objects can deal damage to battles, creatures,
  planeswalkers, and players. ... An object that deals damage is the source of
  that damage."
- **CR 119.2** - "Damage dealt to a player normally causes that player to lose
  that much life."
- **CR 608.2f** - "Some spells and abilities include actions taken on multiple
  players and/or objects. In most cases, each such action is processed
  simultaneously." The whole board is hit at once, so nothing dying part-way
  through changes who else is hit.
- **CR 120.5** - "Damage dealt to a creature, planeswalker, or battle doesn't
  destroy it ... state-based actions may destroy a creature", which is why the
  dead ones are only in the graveyard once the game checks.
- **CR 205.2a** - the card types, which is what "nonartifact" negates.
- **CR 613.5** - the layer system is applied continually and automatically, so
  the filter reads the computed board rather than the printing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_whipflare_spares_artifact_creatures():
    """ "Each nonartifact creature" - CR 205.2a's type, negated. The artifact
    creature takes nothing at all, not merely less."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Whipflare"],
            battlefield=["Mountain", "Mountain", "Elvish Mystic", "Icehide Golem"],
        )
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    golem = scenario.find("Icehide Golem", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Whipflare", *scenario.untapped_sources("Mountain", "Mountain"))

    assert golem.zone is Zone.BATTLEFIELD, "an artifact creature is not a nonartifact creature"
    assert golem.damage == 0
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None


def test_rough_hits_only_the_ground_and_tumble_only_the_sky():
    """The two halves of Rough // Tumble filter on the same keyword in
    opposite senses, off the computed board (CR 613.5)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rough // Tumble"],
            battlefield=["Mountain", "Mountain", "Elvish Mystic", "Birds of Paradise"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    from magic_cards_model.machines.effects import effect_for

    rough = effect_for("Rough", "Rough deals 2 damage to each creature without flying.")
    tumble = effect_for("Tumble", "Tumble deals 6 damage to each creature with flying.")
    assert rough is not None and tumble is not None

    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    birds = scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "alice")
    spell = scenario.find("Rough", Zone.HAND, "alice")

    rough(scenario.game, spell)
    scenario.game.check_state_based_actions()

    assert mystic.zone is Zone.GRAVEYARD, "a 1/1 without flying takes 2"
    assert birds.zone is Zone.BATTLEFIELD, "Birds of Paradise flies; Rough never reaches it"

    tumble(scenario.game, spell)
    scenario.game.check_state_based_actions()

    assert birds.zone is Zone.GRAVEYARD, "Tumble is the half that hits the sky"


def test_end_the_festivities_hits_the_opponent_and_their_board_but_not_yours():
    """CR 119.2 for the player half and CR 120.1 for the permanent half, in one
    instruction the engine used to cut into three unreadable fragments."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["End the Festivities"],
            battlefield=["Mountain", "Elvish Mystic"],
        )
        .player("bob", life=20, battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mine = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve("End the Festivities", *scenario.untapped_sources("Mountain"))

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20, "'each opponent' never includes the controller"
    assert theirs.zone is Zone.GRAVEYARD, "a 1/1 an opponent controls dies to 1 damage"
    assert mine.zone is Zone.BATTLEFIELD, "'they control' is the opponent, not you"
