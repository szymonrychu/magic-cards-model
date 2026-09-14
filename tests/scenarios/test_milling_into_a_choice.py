"""Milling, and the choice the mill hands you.

Four printings, four different answers to "and then what?". All four oracle
texts were verified with `resolve_cards` in the session that wrote this file,
against `tests/fixtures/cards/rapid_rescue.json`,
`.../overlord_of_the_balemurk.json`, `.../tablet_of_discovery.json` and
`.../interdimensional_web_watch.json`:

- **Rapid Rescue** - "Mill two cards. You may put a permanent card from among
  the milled cards into your hand. You gain 2 life."
- **Overlord of the Balemurk** - "Whenever this permanent enters or attacks,
  mill four cards, then you may return a non-Avatar creature card or a
  planeswalker card from your graveyard to your hand."
- **Tablet of Discovery** - "When this artifact enters, mill a card. You may
  play that card this turn."
- **Interdimensional Web Watch** - "When this artifact enters, exile the top
  two cards of your library. Until the end of your next turn, you may play
  those cards."

The interesting axis is the *pool* each choice draws from. Rapid Rescue says
"from among the milled cards" - narrower than the graveyard. Overlord says
"from your graveyard" - wider, and it includes what this same resolution just
milled. Tablet and the Web Watch choose nothing at all at resolution: they hand
out CR 601.3 permission and let the choice happen later.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 701.17c** - "An effect that refers to a milled card can find that card
  in the zone it moved to from the library, as long as that zone is a public
  zone" - which is what makes "from among the milled cards" answerable at all.
- **CR 608.2d** - the resolving spell's own choices, and the fact that an
  option with no legal answer is not offered.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly."
- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it."
- **CR 601.1a** - "'Playing a card' means playing that card as a land or
  casting that card as a spell, whichever is appropriate" - both cards here
  say *play*, not *cast*.
- **CR 514.2** - "all 'until end of turn' and 'this turn' effects end" in the
  cleanup step: Tablet of Discovery's whole window.
- **CR 400.7** - a card that changes zones becomes a new object, which is why a
  permission is stamped to the object it was granted over.
- **CR 205.3m** - creature types, of which Avatar is one; Overlord names it to
  exclude itself and its kin.

Rapid Rescue's own quantity is fixed at "a" (one card, CR 608.2d's "may").
Vorinclex // The Grand Evolution's chapter I - "Mill ten cards. Put up to two
creature cards from among the milled cards onto the battlefield." - reads the
same family off a Saga's own triggered ability rather than a spell, with
CR 107.1c's own "up to two" in place of the fixed "a", and no printed "you
may" at all (the "up to" already carries the optionality). The chapter
ability is reached the ordinary way, by transforming a permanent already on
the battlefield and adding a lore counter directly (`Game.saga_lore_step`) -
CR 701.27a: to transform a permanent is to "turn it over so that its other
face is up", not a zone change (CR 400.7 only makes a new object of one),
so CR 714.3a's own intrinsic "enters with a lore counter" never applies and
`CardState.transform()` on its own adds no counter here. One has to be
added the way CR 714.3c's precombat main phase turn-based action would on a
later turn.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    """Put everything that has triggered onto the stack (CR 603.3) and resolve
    it. Nothing does this on its own here: a permanent put onto the battlefield
    leaves its enters trigger pending until a player would receive priority."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _end_turn(scenario) -> None:
    """Run the active player's cleanup (CR 514.1, 514.2) and cross into the
    next turn. `manual_turn_based_actions()` never runs the cleanup on its own,
    and `start_at` stops at the step it was aimed at, so both calls are needed.
    """
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()


def _questions_from(scenario, source: str):
    return [asked for asked in scenario.questions_asked() if asked.source == source]


# -- Rapid Rescue: the pool is the milled cards, not the graveyard ----------


def _rescue_board(*, library: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Rapid Rescue"],
            battlefield=["Forest"],
            library=list(library),
            graveyard=list(graveyard or []),
        )
        .player("bob", library=["Island"])
    )


def test_milling_two_puts_a_permanent_card_into_hand_and_gains_two_life():
    """The happy path, all three sentences at once (CR 701.17a, CR 119.3)."""
    scenario = _rescue_board(
        library=["Grizzly Bears", "Lightning Bolt", "Forest", "Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    milled = scenario.top_of_library(2)
    bears = milled[0]
    scenario.will_choose_cards(bears, source="Rapid Rescue")
    (forest,) = scenario.untapped_sources("Forest")
    spell = scenario.cast_and_resolve("Rapid Rescue", forest)

    assert spell.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.HAND
    assert milled[1].zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22
    assert len(scenario.player("alice").library) == 2


def test_a_permanent_card_already_in_the_graveyard_is_not_offered():
    """ "From among the milled cards" is a narrower pool than "from your
    graveyard" (CR 701.17c). Hill Giant was in the graveyard before this
    resolved and is a permanent card, and it is still not a candidate."""
    scenario = _rescue_board(
        library=["Forest", "Lightning Bolt", "Island"], graveyard=["Hill Giant"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hill_giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    milled = scenario.top_of_library(2)
    forest = milled[0]
    scenario.will_choose_cards(forest, source="Rapid Rescue")
    (mana,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Rapid Rescue", mana)

    (question,) = [
        asked
        for asked in _questions_from(scenario, "Rapid Rescue")
        if asked.kind is DecisionKind.CHOOSE_CARDS
    ]
    assert question.cards == (forest.id,)
    assert hill_giant.id not in question.cards
    assert hill_giant.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.HAND


def test_milling_two_nonpermanent_cards_offers_no_choice_but_still_gains_life():
    """CR 608.2d: with no legal candidate there is nothing to ask, and the
    third sentence happens regardless - the life gain is not conditional on
    the "you may" (CR 119.3)."""
    scenario = _rescue_board(
        library=["Lightning Bolt", "Lightning Bolt", "Island", "Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    milled = scenario.top_of_library(2)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Rapid Rescue", forest)

    assert _questions_from(scenario, "Rapid Rescue") == []
    assert all(state.zone is Zone.GRAVEYARD for state in milled)
    assert scenario.player("alice").life == 22


def test_declining_the_may_leaves_both_milled_cards_in_the_graveyard():
    """The "you may" is a real question and "no" is a real answer - neither
    card moves, and the mill itself is not undone."""
    scenario = _rescue_board(library=["Grizzly Bears", "Forest", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    milled = scenario.top_of_library(2)
    scenario.will_take_the_may(False, source="Rapid Rescue")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Rapid Rescue", forest)

    assert [state.zone for state in milled] == [Zone.GRAVEYARD, Zone.GRAVEYARD]
    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 22
    asked = _questions_from(scenario, "Rapid Rescue")
    assert [question.kind for question in asked] == [DecisionKind.MAY], (
        "the question was put and answered no; nothing followed it"
    )


# -- Vorinclex // The Grand Evolution: the quantity is read, not fixed at "a",
# and the pool moves onto the battlefield rather than to hand --------------


def _grand_evolution_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Vorinclex // The Grand Evolution"], library=list(library))
        .player("bob")
    )


def _transform_and_add_a_lore_counter(scenario) -> None:
    """`CardState.transform` alone adds no lore counter - CR 714.3a's
    intrinsic "enters with a lore counter" is a replacement effect tied to
    *entering* (CR 614.1c), and CR 701.27a's transform ("turn it over so
    that its other face is up") is not that. `Game.saga_lore_step` is the
    same turn-based action CR 714.3c's own precombat main phase would run on
    alice's *next* turn; calling it once here is production behaviour
    brought forward, not a shortcut around it."""
    vorinclex = scenario.find("Vorinclex", Zone.BATTLEFIELD)
    vorinclex.transform()
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_chapter_one_puts_up_to_two_milled_creatures_onto_the_battlefield():
    scenario = _grand_evolution_board(
        [
            "Grizzly Bears",
            "Lightning Bolt",
            "Forest",
            "Mishra's Bauble",
            "Sol Ring",
            "Island",
            "Swamp",
            "Grizzly Bears",
            "Opt",
            "Counterspell",
        ]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library = scenario.player("alice").library[:10]
    bears = [state for state in library if state.name == "Grizzly Bears"]
    assert len(bears) == 2
    scenario.will_choose_cards(*bears, source="The Grand Evolution")

    _transform_and_add_a_lore_counter(scenario)

    for bear in bears:
        assert bear.zone is Zone.BATTLEFIELD
    nonbears = [state for state in library if state.name != "Grizzly Bears"]
    assert all(state.zone is Zone.GRAVEYARD for state in nonbears)
    assert scenario.player("alice").library == []


def test_chapter_one_may_take_only_one_of_two_milled_creatures():
    """CR 608.2d: "up to two" permits any count from zero through two -
    taking only one is as legal as taking both."""
    scenario = _grand_evolution_board(
        [
            "Grizzly Bears",
            "Lightning Bolt",
            "Forest",
            "Mishra's Bauble",
            "Sol Ring",
            "Island",
            "Swamp",
            "Grizzly Bears",
            "Opt",
            "Counterspell",
        ]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library = scenario.player("alice").library[:10]
    bears = [state for state in library if state.name == "Grizzly Bears"]
    scenario.will_choose_cards(bears[0], source="The Grand Evolution")

    _transform_and_add_a_lore_counter(scenario)

    assert bears[0].zone is Zone.BATTLEFIELD
    assert bears[1].zone is Zone.GRAVEYARD


def test_chapter_one_with_no_creatures_milled_asks_no_question():
    scenario = _grand_evolution_board(
        [
            "Lightning Bolt",
            "Forest",
            "Mishra's Bauble",
            "Sol Ring",
            "Island",
            "Swamp",
            "Opt",
            "Counterspell",
            "Lightning Bolt",
            "Forest",
        ]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library = scenario.player("alice").library[:10]

    _transform_and_add_a_lore_counter(scenario)

    assert _questions_from(scenario, "The Grand Evolution") == []
    assert all(state.zone is Zone.GRAVEYARD for state in library)


# -- Overlord of the Balemurk: the pool is the whole graveyard --------------


def _overlord_board(*, library: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Overlord of the Balemurk"],
            battlefield=["Swamp"],
            library=list(library),
            graveyard=list(graveyard or []),
        )
        .player("bob", library=["Island"])
    )


def _land_the_overlord(scenario):
    """Put the Overlord onto the battlefield and resolve its enters trigger.

    Put, not cast: the trigger under test is "whenever this permanent enters",
    and CR 601.2's announcement has nothing to do with it.
    """
    overlord = scenario.put_onto_battlefield("Overlord of the Balemurk", "alice")
    _resolve_all(scenario)
    return overlord


def test_an_avatar_creature_card_is_no_candidate_but_a_planeswalker_card_is():
    """CR 205.3m: North Wind Avatar is "Creature - Dragon Spirit Avatar", so
    the subtype negation excludes it; Teferi is a planeswalker card, which the
    second half of the description admits."""
    scenario = _overlord_board(
        library=["Lightning Bolt"] * 4 + ["Island"],
        graveyard=["North Wind Avatar", "Teferi, Time Raveler"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    avatar = scenario.find("North Wind Avatar", Zone.GRAVEYARD, "alice")
    teferi = scenario.find("Teferi, Time Raveler", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(teferi, source="Overlord of the Balemurk")
    _land_the_overlord(scenario)

    (question,) = [
        asked
        for asked in _questions_from(scenario, "Overlord of the Balemurk")
        if asked.kind is DecisionKind.CHOOSE_CARDS
    ]
    assert question.cards == (teferi.id,)
    assert avatar.zone is Zone.GRAVEYARD
    assert teferi.zone is Zone.HAND


def test_a_card_milled_by_this_same_resolution_is_itself_a_candidate():
    """CR 701.17a puts the four cards into the graveyard and nothing in the
    sentence excludes them, so the pool is read *after* the mill - Grizzly
    Bears was in the library when this began resolving."""
    scenario = _overlord_board(
        library=["Lightning Bolt", "Grizzly Bears", "Lightning Bolt", "Island", "Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    milled = scenario.top_of_library(4)
    bears = next(state for state in milled if state.name == "Grizzly Bears")
    scenario.will_choose_cards(bears, source="Overlord of the Balemurk")
    _land_the_overlord(scenario)

    (question,) = [
        asked
        for asked in _questions_from(scenario, "Overlord of the Balemurk")
        if asked.kind is DecisionKind.CHOOSE_CARDS
    ]
    assert bears.id in question.cards
    assert bears.zone is Zone.HAND


def test_an_empty_candidate_pool_never_puts_the_question():
    """CR 608.2d: the "you may" is only asked once a legal candidate exists.
    Four instants milled onto an empty graveyard leaves nothing to return, and
    the ability asks nothing at all rather than asking and being answered no.
    """
    scenario = _overlord_board(library=["Lightning Bolt"] * 4 + ["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    milled = scenario.top_of_library(4)
    _land_the_overlord(scenario)

    assert _questions_from(scenario, "Overlord of the Balemurk") == []
    assert all(state.zone is Zone.GRAVEYARD for state in milled)
    assert scenario.player("alice").hand == []


# -- Tablet of Discovery: mill one, and permission to play it this turn -----


def _tablet_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tablet of Discovery"],
            battlefield=["Mountain"],
            library=list(library),
        )
        .player("bob", library=["Island", "Island"])
    )


def test_the_milled_card_can_be_played_out_of_the_graveyard_this_turn():
    """CR 601.3 permission, over the graveyard rather than exile - and it is a
    permission, not an instruction, so nothing is asked as the trigger
    resolves (there is no `may` here at all)."""
    scenario = _tablet_board(["Lightning Bolt", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.top_of_library(1)[0]
    scenario.put_onto_battlefield("Tablet of Discovery", "alice")
    _resolve_all(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.PLAY
    assert permission.pays_mana_cost is True
    assert permission.source_name == "Tablet of Discovery"
    assert _questions_from(scenario, "Tablet of Discovery") == []

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_the_permission_is_gone_on_the_following_turn():
    """CR 514.2: "this turn" ends at the casting turn's own cleanup, so the
    card is still in the graveyard next turn with no way to play it."""
    scenario = _tablet_board(["Lightning Bolt", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.top_of_library(1)[0]
    scenario.put_onto_battlefield("Tablet of Discovery", "alice")
    _resolve_all(scenario)
    assert scenario.game.play_permission_for(bolt, "alice") is not None

    _end_turn(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.game.play_permission_for(bolt, "alice") is None


# -- Interdimensional Web Watch: two exiled cards, until your next turn -----


def _web_watch_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Interdimensional Web Watch"],
            battlefield=["Mountain"],
            library=["Lightning Bolt", "Forest", "Island"],
        )
        .player("bob", library=["Island", "Island"])
    )


def _land_the_web_watch(scenario):
    before = {state.id for state in scenario.game.exile}
    scenario.put_onto_battlefield("Interdimensional Web Watch", "alice")
    _resolve_all(scenario)
    return [state for state in scenario.game.exile if state.id not in before]


def test_both_exiled_cards_are_playable_and_a_land_among_them_is_played_as_one():
    """CR 601.1a: the sentence says *play*, so the Forest is a land drop and
    the Bolt is a cast - one permission covers both."""
    scenario = _web_watch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _land_the_web_watch(scenario)

    assert sorted(state.name for state in exiled) == ["Forest", "Lightning Bolt"]
    for state in exiled:
        permission = scenario.game.play_permission_for(state, "alice")
        assert permission is not None
        assert permission.action is PlayAction.PLAY
        assert permission.source_name == "Interdimensional Web Watch"

    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert scenario.game.lands_played["alice"] == 1


def test_the_permission_survives_into_alices_own_next_turn_and_no_further():
    """ "Until the end of your next turn" outlives the turn the artifact
    entered on and every turn that is not alice's own next one, and drops at
    the cleanup of that turn (CR 514.2 on the later of the two)."""
    scenario = _web_watch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    exiled = _land_the_web_watch(scenario)
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")

    _end_turn(scenario)  # alice's turn ends; bob's begins
    assert scenario.turn.active_player == "bob"
    assert scenario.game.play_permission_for(bolt, "alice") is not None

    _end_turn(scenario)  # bob's turn ends; alice's own next turn begins
    assert scenario.turn.active_player == "alice"
    assert scenario.game.play_permission_for(bolt, "alice") is not None

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert bolt.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bolt, "alice") is None
