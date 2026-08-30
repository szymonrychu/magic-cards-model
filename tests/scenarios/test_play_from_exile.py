"""CR 601.3: a time-boxed permission to play specific cards out of exile.

`machines/casting.KeywordCastOption` is the *static* half of CR 601.3 - a grant
read off a card's own printed keyword, true of every copy of that printing
forever (flashback, plot, foretell, madness, warp, Adventure). This file is
about the other half: a permission a **resolving ability** hands out, naming
particular objects, for a particular player, until end of turn.

Two real printings in the pool print it, and they differ in every way that
matters, which is why the primitive is built generally rather than per card:

- **Ugin, Eye of the Storms**, `−11: Search your library for any number of
  colorless nonland cards, exile them, then shuffle. Until end of turn, you may
  cast those cards without paying their mana costs.` - any number of cards,
  from the controller's own library, cast for nothing.
- **Ragavan, Nimble Pilferer**, `Whenever Ragavan deals combat damage to a
  player, create a Treasure token and exile the top card of that player's
  library. Until end of turn, you may cast that card.` - one card, from an
  **opponent's** library, cast for its own mana cost. Its owner is the opponent
  (CR 108.3); the permission is the Ragavan controller's.

Both oracle texts were verified with `resolve_cards` in the session that wrote
this file, and against `tests/fixtures/cards/`. Note Ugin says **cast**, not
"play", and adds "without paying their mana costs" - the play-versus-cast
distinction is still modelled and tested below, through
`Game.grant_play_permission`'s own `PlayAction`, because it is the primitive's
contract and not every future card will say *cast*.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it and no rule or effect prohibits that player
  from casting it."
- **CR 601.1a** / **CR 701.18b** - "'Playing a card' means playing that card as
  a land or casting that card as a spell, whichever is appropriate", and
  **CR 701.5b** - "To cast a card is to cast it as a spell." Cast is the
  narrower word.
- **CR 701.18a** - "To play a land means to put it onto the battlefield from
  the zone it's in (usually the hand)."
- **CR 305.1 / 305.2a / 305.2b / 305.3** - the land drop: one per turn, on your
  own turn, main phase, empty stack. A permission to *play* a land from exile
  changes the zone, not the allowance.
- **CR 117.1a** - "A player may cast an instant spell any time they have
  priority. A player may cast a noninstant spell during their main phase any
  time they have priority and the stack is empty." A permission to cast is not
  a permission to ignore this.
- **CR 118.9** / **CR 118.9c** / **CR 107.3b** - "without paying its mana cost"
  is an alternative cost of nothing, and it does not change the spell's mana
  cost.
- **CR 514.2** - "all 'until end of turn' and 'this turn' effects end" in the
  cleanup step, alongside the marked damage.
- **CR 400.7** - "an object that moves from one zone to another becomes a new
  object", which is why the permission is stamped with the object's
  `zone_change_stamp` and dies when the card moves.
- **CR 108.3** - a card's owner is the player it started the game under, which
  is a different question from who is allowed to cast it.
- **CR 107.1c** - "If a rule or ability instructs a player to choose 'any
  number,' that player may choose any positive number or zero."
- **CR 701.23b** - searching a hidden zone for cards with a stated quality
  never *requires* finding them.
- **CR 606.3 / 606.6** - a loyalty ability once per turn per permanent, and a
  negative one only with the counters to pay it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction, why_cannot_cast_from
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _ugin_board(library: list[str] | None = None) -> Scenario:
    """Alice with Ugin on the battlefield and a library worth searching.

    Ugin enters with 7 loyalty (CR 306.5b) and his −11 needs eleven (CR 606.6),
    so every test that reaches the ultimate puts the missing counters on by
    hand - `add_counters` is the same call `Game` makes, not a stand-in for
    one.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=library if library is not None else ["Sol Ring", "All Is Dust", "Forest"],
            battlefield=["Ugin, Eye of the Storms", "Mountain", "Mountain"],
        )
        .player("bob", library=["Island", "Island"])
    )


def _ultimate(scenario):
    """Activate Ugin's −11 and resolve it. Returns the cards it exiled."""
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)
    ugin.add_counters(Counter.LOYALTY, 4)  # CR 606.6: 7 printed + 4 = 11
    before = {state.id for state in scenario.game.exile}
    scenario.activate(ugin, index=2)
    scenario.pass_until_resolved()
    return [state for state in scenario.game.exile if state.id not in before]


# -- Ugin, Eye of the Storms: the many-card, free-cast shape ---------------


def test_the_ultimate_exiles_the_colorless_nonland_cards_and_lets_them_be_cast():
    """CR 601.3, CR 118.9: the whole paragraph, in one resolution.

    Sol Ring and All Is Dust are colorless nonland cards; the Forest is a land
    and the Island belongs to bob, so neither is found. Each exiled card gets
    its own permission, and both say "no mana cost" (CR 118.9's alternative
    cost of nothing, which CR 107.3b keeps distinct from a cheaper cost).
    """
    scenario = _ugin_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _ultimate(scenario)

    assert sorted(state.name for state in exiled) == ["All Is Dust", "Sol Ring"]
    assert [state.name for state in scenario.player("alice").library] == ["Forest"]
    for state in exiled:
        permission = scenario.game.play_permission_for(state, "alice")
        assert permission is not None
        assert permission.pays_mana_cost is False
        assert permission.action is PlayAction.CAST
        assert permission.source_name == "Ugin, Eye of the Storms"


def test_a_card_exiled_by_the_ultimate_is_cast_for_nothing():
    """CR 118.9c: the alternative cost replaces what is paid, not the printed
    mana cost, so Sol Ring's `{1}` is still `{1}` on the card and `{}` at the
    register. Alice's two Mountains stay untapped, which is the whole point.
    """
    scenario = _ugin_board(["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (sol_ring,) = _ultimate(scenario)

    casting = scenario.cast("Sol Ring", from_zone=Zone.EXILE)
    casting.use_permission()
    assert str(casting.base_cost) == "{1}"
    assert str(casting.total_cost.mana) == ""

    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert sol_ring.zone is Zone.BATTLEFIELD
    assert scenario.untapped_sources("Mountain", "Mountain"), "nothing was paid"


def test_searching_for_zero_cards_is_legal_and_grants_nothing():
    """CR 107.1c: "any number" may be zero, and CR 701.23b never forces a find.

    Declining every find leaves the library alone, exiles nothing, and hands
    out no permission - as opposed to an implementation that quietly requires
    at least one card and would either exile a Sol Ring nobody asked for or
    raise.
    """
    scenario = _ugin_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)

    exiled = _ultimate(scenario)

    assert exiled == []
    assert [state.name for state in scenario.player("alice").library] == [
        "Sol Ring",
        "All Is Dust",
        "Forest",
    ] or sorted(state.name for state in scenario.player("alice").library) == [
        "All Is Dust",
        "Forest",
        "Sol Ring",
    ], "the library is shuffled (CR 701.24a) but nothing left it"
    assert scenario.game.play_permissions == []


def test_a_sorcery_cannot_be_cast_from_exile_at_instant_speed():
    """CR 117.1a: permission to cast is not permission to ignore the timing.

    All Is Dust is a colorless sorcery, exiled by the ultimate during the main
    phase. In the end step - alice's own turn, but not a main phase - the
    announcement is refused before anything is paid.
    """
    scenario = _ugin_board(["All Is Dust", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (all_is_dust,) = _ultimate(scenario)

    scenario.start_at(Step.END_STEP)
    with pytest.raises(ValueError, match="main phase"):
        scenario.cast("All Is Dust", from_zone=Zone.EXILE)

    assert all_is_dust.zone is Zone.EXILE


def test_the_permission_ends_with_the_turn_and_the_card_stays_exiled():
    """CR 514.2: "all 'until end of turn' ... effects end" in the cleanup step.

    The card does not go anywhere - CR 406.1's exile is a holding area and
    nothing returns it - it simply stops being castable. This is the case a
    blanket "cards in exile are castable" gets wrong forever.
    """
    scenario = _ugin_board(["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (sol_ring,) = _ultimate(scenario)
    assert scenario.game.play_permission_for(sol_ring, "alice") is not None

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert sol_ring.zone is Zone.EXILE
    assert scenario.game.play_permission_for(sol_ring, "alice") is None
    refusal = why_cannot_cast_from(sol_ring, "alice", Zone.EXILE, scenario.game)
    assert refusal is not None and "CR 601.3" in refusal


def test_a_card_exiled_last_turn_is_not_castable_this_turn():
    """The same expiry seen from the next turn, without relying on a cleanup
    step having been run: `PlayPermission.granted_turns_taken` compares against
    `TurnMachine.turns_taken`, so a game driven step by step still refuses.
    """
    scenario = _ugin_board(["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (sol_ring,) = _ultimate(scenario)

    while scenario.turn.active_player != "alice" or scenario.turn.turn_number == 1:
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert sol_ring.zone is Zone.EXILE
    assert scenario.game.play_permission_for(sol_ring, "alice") is None
    with pytest.raises(ValueError, match="until end of turn and that turn is over"):
        scenario.cast("Sol Ring", from_zone=Zone.EXILE).use_permission()


def test_the_permission_does_not_reach_a_card_exiled_by_something_else():
    """CR 601.3 attaches to objects, not to the zone.

    A second colorless card put into exile by an unrelated effect - a plain
    `Game.exile_permanent`, the same call every exile in this engine makes -
    is in exile alongside Ugin's finds and is castable by nobody.
    """
    scenario = _ugin_board(["Sol Ring", "Mishra's Bauble", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=1)  # find the Sol Ring, decline the rest
    scenario.will_take_the_may(False, times=None)

    exiled = _ultimate(scenario)
    assert [state.name for state in exiled] == ["Sol Ring"]

    bauble = scenario.find("Mishra's Bauble", Zone.LIBRARY, "alice")
    scenario.game.exile_permanent(bauble)

    assert scenario.game.play_permission_for(bauble, "alice") is None
    with pytest.raises(ValueError, match="nothing allows"):
        scenario.cast("Mishra's Bauble", from_zone=Zone.EXILE).use_permission()


def test_the_permission_does_not_survive_the_card_leaving_exile():
    """CR 400.7: "an object that moves from one zone to another becomes a new
    object", so the card that comes back is not the card the permission named.

    `zone_change_stamp` is what says so - this engine keeps a `CardState`'s id
    across a zone change on purpose, so an id-only permission would follow the
    card around the game forever.
    """
    scenario = _ugin_board(["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (sol_ring,) = _ultimate(scenario)

    scenario.game.put_into_graveyard(sol_ring)
    scenario.game.exile_permanent(sol_ring)

    assert sol_ring.zone is Zone.EXILE
    assert scenario.game.play_permission_for(sol_ring, "alice") is None


def test_casting_without_announcing_the_permission_still_owes_the_mana_cost():
    """CR 118.9b: "Alternative costs are generally optional."

    The permission is what allows the cast (CR 601.3); *paying nothing* is a
    separate announcement (CR 601.2b), made by `use_permission`. Skipping it
    leaves the printed cost owing, which is the difference between "may cast
    this" and "may cast this for free" - two cards could differ on exactly
    that, and this engine does not collapse them.
    """
    scenario = _ugin_board(["Sol Ring", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _ultimate(scenario)

    casting = scenario.cast("Sol Ring", from_zone=Zone.EXILE)
    assert str(casting.total_cost.mana) == "{1}"


# -- play versus cast (CR 601.1a, CR 701.18b, CR 305.2a) -------------------


def test_a_permission_to_cast_is_not_permission_to_play_a_land():
    """CR 701.5b's "cast it as a spell" against CR 701.18b's wider "play".

    Ugin's own ultimate finds only nonland cards, so this is the primitive's
    contract rather than his: a `PlayAction.CAST` permission over an exiled
    land refuses the land drop outright.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Mountain"], library=["Forest"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.EXILE, "alice")
    scenario.game.grant_play_permission(
        mountain, "alice", action=PlayAction.CAST, source_name="a cast-only effect"
    )

    with pytest.raises(ValueError, match="not permission to play it as a land"):
        scenario.play_land("Mountain", from_zone=Zone.EXILE)

    assert mountain.zone is Zone.EXILE


def test_playing_an_exiled_land_uses_the_land_drop():
    """CR 701.18a puts the land onto the battlefield "from the zone it's in",
    and CR 305.2a counts it against the same one-per-turn allowance as a land
    played from hand - "lands played as special actions" is one number, not one
    per zone.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Mountain"], hand=["Forest"], library=["Island"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.EXILE, "alice")
    scenario.game.grant_play_permission(
        mountain, "alice", action=PlayAction.PLAY, source_name="a play effect"
    )

    scenario.play_land("Mountain", from_zone=Zone.EXILE)
    assert mountain.zone is Zone.BATTLEFIELD
    assert scenario.game.lands_played["alice"] == 1

    with pytest.raises(ValueError, match="already used"):
        scenario.play_land("Forest")


def test_a_land_in_exile_with_no_permission_cannot_be_played():
    """CR 305.1 plays a land from the hand; nothing else opens another zone."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Mountain"], library=["Forest"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="nothing allows"):
        scenario.play_land("Mountain", from_zone=Zone.EXILE)


# -- Ragavan, Nimble Pilferer: the one-card, opponent's-library shape ------


def _ragavan_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer", "Mountain"], library=["Forest"])
        .player("bob", library=["Lightning Bolt", "Island"])
    )


def _connect(scenario):
    """Ragavan deals combat damage to bob; returns the card he exiled."""
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return scenario.find("Lightning Bolt", Zone.EXILE)


def test_ragavans_exiled_card_is_cast_by_ragavans_controller_not_its_owner():
    """CR 108.3 keeps the card bob's; CR 601.3 gives alice the permission.

    The trap this is aimed at: a two-player test that never checks ownership
    passes just as happily with the permission on the wrong player, because
    "somebody may cast it" looks the same from the outside.
    """
    scenario = _ragavan_board().build()
    bolt = _connect(scenario)

    assert bolt.owner == "bob"
    assert scenario.game.play_permission_for(bolt, "bob") is None
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.player == "alice"

    with pytest.raises(ValueError, match="let alice cast"):
        scenario.cast("Lightning Bolt", username="bob", from_zone=Zone.EXILE).use_permission()


def test_ragavans_exiled_card_is_cast_for_its_own_mana_cost():
    """Ragavan says "you may cast that card" and nothing about paying nothing,
    so CR 601.2f's total cost is the printed one - the difference from Ugin's
    ultimate, and the reason `pays_mana_cost` is a field rather than an
    assumption.
    """
    scenario = _ragavan_board().build()
    bolt = _connect(scenario)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    assert str(casting.total_cost.mana) == "{R}"

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "CR 608.2m: it is bob's card and bob's graveyard"
    assert bolt in scenario.player("bob").graveyard


def test_ragavans_permission_ends_with_the_turn():
    """CR 514.2 again, on the other card - the expiry is the primitive's, not
    a per-card rule either printing carries.
    """
    scenario = _ragavan_board().build()
    bolt = _connect(scenario)

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert bolt.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bolt, "alice") is None
