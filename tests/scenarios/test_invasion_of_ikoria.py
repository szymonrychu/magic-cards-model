"""Invasion of Ikoria // Zilortha, Apex of Ikoria.

Verified this session with `mise run rules:find` against the current CR:

- **CR 701.23a** - "To search for a card in a zone, look at all cards in
  that zone (even if it's a hidden zone) and find a card that matches the
  given description."
- **CR 701.23b** - a stated-quality search never has to find a card that is
  actually present.
- **CR 701.24a** - "To shuffle a library ... randomize the cards within it."
- **CR 109.2** - a description naming a card type or subtype with no zone/
  "card" word means a permanent of that type on the battlefield - the same
  "non-Human" negation this ETB's own "non-Human creature card" reads is CR
  109.2's ordinary negation of CR 205.3m's creature type.
- **CR 510.1b** - "An unblocked creature assigns its combat damage to the
  player, planeswalker, or battle it's attacking."
- **CR 510.1c** - "A blocked creature assigns its combat damage to the
  creatures blocking it ... If exactly one creature is blocking it, it
  assigns all its combat damage to that creature."

Front face: "When this Siege enters, search your library and/or graveyard
for a non-Human creature card with mana value X or less and put it onto the
battlefield. If you search your library this way, shuffle." Back face
(Zilortha, Apex of Ikoria): "For each non-Human creature you control, you
may have that creature assign its combat damage as though it weren't
blocked."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

IKORIA = "Invasion of Ikoria"


def _cast_ikoria_for_x(scenario, x: int, *lands):
    casting = scenario.cast(IKORIA)
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    scenario.put_on_stack(casting)


def test_etb_search_finds_a_non_human_creature_and_excludes_a_human_one():
    """The stated quality "non-Human creature card" excludes Elite Vanguard
    (a Human) and accepts Llanowar Elves (an Elf) at the same mana value,
    then shuffles the library it searched (CR 701.24a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Forest", "Forest", "Mountain"],
            library=["Elite Vanguard", "Llanowar Elves", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    lands = scenario.untapped_sources("Forest", "Forest", "Mountain")
    llanowar = scenario.find("Llanowar Elves", Zone.LIBRARY, "alice")
    elite_vanguard = scenario.find("Elite Vanguard", Zone.LIBRARY, "alice")
    shuffles_before = scenario.game.shuffles_performed

    _cast_ikoria_for_x(scenario, 1, *lands)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(llanowar, username="alice")
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert llanowar.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(llanowar).username == "alice"
    assert elite_vanguard.zone is Zone.LIBRARY, "the Human creature was never a legal find"
    assert elite_vanguard in alice.library
    assert scenario.game.shuffles_performed == shuffles_before + 1


def test_etb_search_reaches_the_graveyard_too():
    """ "Search your library and/or graveyard" (CR 701.23a's single search
    over two named zones): with nothing eligible in the library, the same
    search still finds a non-Human creature card sitting in the graveyard,
    and the library is still shuffled because it was searched either way."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Forest", "Forest", "Mountain"],
            library=["Swamp", "Swamp"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest", "Mountain")
    llanowar = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    shuffles_before = scenario.game.shuffles_performed

    _cast_ikoria_for_x(scenario, 1, *lands)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(llanowar, username="alice")
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert llanowar.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(llanowar).username == "alice"
    assert scenario.game.shuffles_performed == shuffles_before + 1


def test_etb_search_respects_the_mana_value_ceiling():
    """ "With mana value X or less" (CR 107.3a's X) refuses a creature above
    the announced X even though it is otherwise a legal, non-Human find."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Forest", "Forest", "Mountain", "Mountain", "Mountain"],
            library=["Goblin Guide", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    lands = scenario.untapped_sources("Forest", "Forest", "Mountain", "Mountain")
    goblin_guide = scenario.find("Goblin Guide", Zone.LIBRARY, "alice")

    # X=0: Goblin Guide is mana value 1, above the ceiling, so nothing in
    # the library qualifies and the search legally finds nothing (CR 701.23b).
    _cast_ikoria_for_x(scenario, 0, *lands[:2])
    scenario.will_take_the_may(True, username="alice")
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert goblin_guide.zone is Zone.LIBRARY
    assert goblin_guide in alice.library


def test_back_face_may_assign_damage_as_though_unblocked_for_non_human_only():
    """Zilortha's back face grants "you may have this creature assign its
    combat damage as though it weren't blocked" (CR 510.1b in place of CR
    510.1c) to each non-Human creature its controller controls - Goblin
    Guide gets the option, Elite Vanguard (a Human) does not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Goblin Guide", "Elite Vanguard"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    ikoria_card = scenario.find(IKORIA, Zone.HAND, "alice")
    zilortha = scenario.game.put_onto_battlefield(ikoria_card, "alice", transformed=True)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    goblin_guide, elite_vanguard = scenario.creatures(
        "Goblin Guide", "Elite Vanguard", username="alice"
    )
    bear_1, bear_2 = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    bob = scenario.player("bob")

    scenario.attack_with(goblin_guide, elite_vanguard, defending="bob")
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(goblin_guide, bear_1)
    scenario.block(elite_vanguard, bear_2)

    scenario.will_take_the_may(True, username="alice", source="Goblin Guide")
    life_before = bob.life
    goblin_power = goblin_guide.power
    vanguard_power = elite_vanguard.power

    # Every creature here dies in the trade (two 2/2s, a 2/1 into a 2/2), so
    # `CardState.damage` is reset by the state-based action that follows
    # combat damage - the assignment itself is read off `combat_damage`'s own
    # return value instead (its own docstring: "assert on how the damage was
    # split rather than only on what died").
    result = scenario.combat_damage()
    to_bob = sum(amount for recipient, amount in result if recipient is bob)
    to_bear_1 = sum(amount for recipient, amount in result if recipient is bear_1)
    to_bear_2 = sum(amount for recipient, amount in result if recipient is bear_2)

    # Goblin Guide (non-Human, the option taken): all its power went to
    # bob's face instead of to Grizzly Bears #1 (CR 510.1b).
    assert to_bob == goblin_power
    assert to_bear_1 == 0
    assert bob.life == life_before - goblin_power
    # Elite Vanguard (Human, no option ever granted): the ordinary CR
    # 510.1c blocked assignment, straight to its own blocker.
    assert to_bear_2 == vanguard_power
    assert zilortha.name == "Zilortha, Apex of Ikoria"
