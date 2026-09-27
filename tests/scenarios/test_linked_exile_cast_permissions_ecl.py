"""Scenario: casting out of a permanent's own linked exile pile (CR 607.1,
CR 607.2a) and out of exile under a "for as long as" permission (ECL).

- **Maralen, Fae Ascendant** - "Whenever Maralen or another Elf or Faerie you
  control enters, exile the top two cards of target opponent's library." and
  "Once each turn, you may cast a spell with mana value less than or equal
  to the number of Elves and Faeries you control from among cards exiled
  with Maralen this turn without paying its mana cost." CR 607.2a links the
  exiled cards to Maralen; CR 118.9: without paying its mana cost. Proof
  printings: Ashiok, Nightmare Weaver's "+2: Exile the top three cards of
  target opponent's library." (the standalone exile) and Rona, Disciple of
  Gix's "You may cast spells from among cards exiled with Rona." (the linked
  permission).
- **Taster of Wares** - "When this creature enters, target opponent reveals X
  cards from their hand, where X is the number of Goblins you control. You
  choose one of those cards. That player exiles it. If an instant or sorcery
  card is exiled this way, you may cast it for as long as you control this
  creature, and mana of any type can be spent to cast that spell." CR
  701.20a: reveal; CR 601.3: the permission. Proof printing: Thieving
  Sprite's "target player reveals X cards from their hand, where X is the
  number of Faeries you control. You choose one of those cards. That player
  discards that card."
- **Dawnhand Dissident** - "{T}, Blight 2: Exile target card from a
  graveyard." and "During your turn, you may cast creature spells from among
  cards you own exiled with this creature by removing three counters from
  among creatures you control in addition to paying their other costs." CR
  601.2f: an additional cost; CR 118.3: the counters have to be there. Proof
  printing for the counter-removal cost: Quilled Greatwurm's "You may cast
  this card from your graveyard by removing six counters from among
  creatures you control in addition to paying its other costs."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 607.1, CR 607.2a, CR 118.9, CR 701.20a, CR 601.3,
CR 601.2f, CR 118.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _cast_from_exile(scenario, name, *, username="alice", targets=None, choosing=None):
    casting = scenario.cast(name, username=username, from_zone=Zone.EXILE)
    if choosing is not None:
        casting.use_keyword("Cast permission", choosing=choosing)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=username)
    return scenario.put_on_stack(casting)


# -- Maralen -----------------------------------------------------------------


def _maralen_board(bob_library, *, hand=("Llanowar Elves",), battlefield=("Forest",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Maralen, Fae Ascendant", *hand],
            battlefield=list(battlefield),
            library=["Island"] * 5,
        )
        .player("bob", library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _maralen_enters(scenario):
    scenario.will_choose_targets("bob", username="alice")
    maralen = scenario.put_onto_battlefield("Maralen, Fae Ascendant", "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return maralen


def test_maralen_entering_exiles_the_top_two_of_the_opponents_library():
    scenario = _maralen_board(["Lightning Bolt", "Hill Giant", "Opt"])
    maralen = _maralen_enters(scenario)

    exiled = sorted(c.name for c in scenario.game.exile)
    assert exiled == ["Hill Giant", "Lightning Bolt"]
    assert [c.name for c in scenario.player("bob").library] == ["Opt"]
    assert (
        sorted(
            c.name for c in scenario.game.cards_exiled_with(maralen.id, maralen.zone_change_stamp)
        )
        == exiled
    )


def test_another_elf_entering_triggers_it_again_but_a_bear_does_not():
    scenario = _maralen_board(
        ["Lightning Bolt", "Hill Giant", "Opt", "Island"],
        hand=("Llanowar Elves", "Grizzly Bears"),
        battlefield=("Forest", "Forest", "Forest"),
    )
    _maralen_enters(scenario)
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_onto_stack("Llanowar Elves", auto=True, username="alice")
    scenario.resolve_top()
    assert len(scenario.stack_names()) == 1, "the Elf's entering triggers Maralen"
    scenario.resolve_top()
    assert len(scenario.game.exile) == 4

    scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    scenario.resolve_top()
    assert scenario.stack_names() == []


def test_cast_a_spell_exiled_with_maralen_free_once_each_turn():
    scenario = _maralen_board(["Lightning Bolt", "Opt"])
    _maralen_enters(scenario)
    bolt = _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"], choosing=[])
    assert all(not c.tapped for c in scenario.game.battlefield if c.name == "Forest"), "free"
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.GRAVEYARD

    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Opt", choosing=[])


def test_the_mana_value_bound_counts_elves_and_faeries():
    """Maralen alone is one Elf Faerie: mana value 1 fits, 4 does not."""
    scenario = _maralen_board(["Hill Giant", "Opt"])
    _maralen_enters(scenario)
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Hill Giant", choosing=[])
    _cast_from_exile(scenario, "Opt", choosing=[])


def test_a_card_exiled_with_maralen_on_an_earlier_turn_is_not_castable():
    scenario = _maralen_board(["Opt", "Opt"])
    maralen = _maralen_enters(scenario)
    for card in scenario.game.cards_exiled_with(maralen.id, maralen.zone_change_stamp):
        card.exile_annotation = card.exile_annotation.model_copy(
            update={"turn_exiled": (card.exile_annotation.turn_exiled or 0) - 1}
        )
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Opt", choosing=[])


def test_ashiok_plus_two_exiles_the_top_three_and_links_them():
    """The proof printing for the standalone exile of the top N cards of
    target opponent's library - linked because Ashiok's -X reads "exiled
    with Ashiok"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ashiok, Nightmare Weaver"])
        .player("bob", library=["Opt", "Opt", "Hill Giant", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashiok = scenario.game.battlefield[0]
    scenario.activate(ashiok, username="alice", targets=[scenario.player("bob")])
    scenario.resolve_top()

    assert [c.name for c in scenario.player("bob").library] == ["Island"]
    assert len(scenario.game.cards_exiled_with(ashiok.id, ashiok.zone_change_stamp)) == 3


def test_rona_casts_a_linked_card_paying_its_cost():
    """The proof printing for the linked-pile cast permission: Rona exiles
    Ornithopter from Alice's graveyard, and Alice may cast it from exile."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rona, Disciple of Gix"],
            graveyard=["Ornithopter"],
            battlefield=["Island", "Swamp", "Island"],
            library=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(thopter, username="alice")
    scenario.cast_and_resolve("Rona, Disciple of Gix", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()
    assert thopter.zone is Zone.EXILE

    _cast_from_exile(scenario, "Ornithopter", choosing=[])
    scenario.resolve_top()
    assert thopter.zone is Zone.BATTLEFIELD


# -- Taster of Wares ---------------------------------------------------------


def _taster_board(bob_hand, *, goblins=1):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Taster of Wares"],
            battlefield=["Swamp", "Swamp", "Swamp", "Island", *["Raging Goblin"] * (goblins - 1)],
            library=["Island"] * 5,
        )
        .player("bob", hand=list(bob_hand), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_taster_exiles_the_chosen_instant_and_alice_may_cast_it_with_any_mana():
    scenario = _taster_board(["Lightning Bolt", "Hill Giant", "Opt"], goblins=2)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    giant = scenario.find("Hill Giant", Zone.HAND, "bob")
    scenario.will_choose_targets("bob", username="alice")
    scenario.will_choose_cards(bolt, giant, username="bob")  # Bob reveals two
    scenario.will_choose_cards(bolt, username="alice")  # Alice picks the Bolt
    scenario.cast_and_resolve("Taster of Wares", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert giant.zone is Zone.HAND

    _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 17, "paid with the Island's blue mana"


def test_a_creature_exiled_by_taster_cannot_be_cast():
    scenario = _taster_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.HAND, "bob")
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_and_resolve("Taster of Wares", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()
    assert giant.zone is Zone.EXILE
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Hill Giant")


def test_the_permission_ends_when_alice_no_longer_controls_taster():
    scenario = _taster_board(["Lightning Bolt"])
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_and_resolve("Taster of Wares", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.game.destroy(scenario.creature("Taster of Wares", "alice"))
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])


def test_x_counts_goblins_and_bob_reveals_that_many():
    """One Goblin (Taster itself): Bob reveals one card, his choice."""
    scenario = _taster_board(["Lightning Bolt", "Opt"])
    opt = scenario.find("Opt", Zone.HAND, "bob")
    scenario.will_choose_targets("bob", username="alice")
    scenario.will_choose_cards(opt, username="bob")
    scenario.cast_and_resolve("Taster of Wares", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()
    assert opt.zone is Zone.EXILE
    assert scenario.find("Lightning Bolt", Zone.HAND, "bob").zone is Zone.HAND


def test_thieving_sprite_makes_the_player_discard_the_chosen_card():
    """The proof printing: Faeries rather than Goblins, "target player", and
    a discard rather than an exile."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thieving Sprite"],
            battlefield=["Swamp", "Swamp", "Swamp", "Spellstutter Sprite"],
        )
        .player("bob", hand=["Lightning Bolt", "Hill Giant", "Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    giant = scenario.find("Hill Giant", Zone.HAND, "bob")
    scenario.will_choose_targets("bob", username="alice")
    scenario.will_choose_cards(bolt, giant, username="bob")
    scenario.will_choose_cards(giant, username="alice")
    scenario.cast_and_resolve("Thieving Sprite", auto=True, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert giant.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.HAND


# -- Dawnhand Dissident ------------------------------------------------------


def _dissident_board(*, alice_graveyard=("Grizzly Bears",), bob_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=list(alice_graveyard),
            battlefield=["Dawnhand Dissident", "Craw Wurm", "Hill Giant", "Forest", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", graveyard=list(bob_graveyard), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _dissident_exiles(scenario, target):
    dissident = scenario.creature("Dawnhand Dissident", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    scenario.will_choose_cards(wurm, username="alice")  # blight 2 onto the Wurm
    scenario.activate(dissident, index=1, targets=[target])
    scenario.resolve_top()
    return wurm


def test_dissident_exiles_a_graveyard_card_and_casts_it_by_removing_three_counters():
    scenario = _dissident_board()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    wurm = _dissident_exiles(scenario, bears)
    assert bears.zone is Zone.EXILE
    giant = scenario.creature("Hill Giant", "alice")
    scenario.game.add_counters(giant, Counter.PLUS_ONE, 1)

    _cast_from_exile(scenario, "Grizzly Bears", choosing=[wurm, giant])
    assert wurm.counters[Counter.MINUS_ONE] == 0
    assert giant.counters[Counter.PLUS_ONE] == 0
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD


def test_fewer_than_three_counters_cannot_pay():
    scenario = _dissident_board()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    wurm = _dissident_exiles(scenario, bears)
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Grizzly Bears", choosing=[wurm])


def test_a_noncreature_card_exiled_with_dissident_is_not_castable():
    scenario = _dissident_board(alice_graveyard=("Lightning Bolt",))
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    wurm = _dissident_exiles(scenario, bolt)
    scenario.game.add_counters(wurm, Counter.MINUS_ONE, 1)
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"], choosing=[wurm])


def test_a_card_alice_does_not_own_is_not_castable():
    """ "Cards you own" - Bob's exiled creature card stays."""
    scenario = _dissident_board(alice_graveyard=(), bob_graveyard=("Grizzly Bears",))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    wurm = _dissident_exiles(scenario, bears)
    scenario.game.add_counters(wurm, Counter.MINUS_ONE, 1)
    with pytest.raises(ValueError):
        _cast_from_exile(scenario, "Grizzly Bears", choosing=[wurm])


def test_quilled_greatwurm_casts_itself_from_the_graveyard_by_removing_six_counters():
    """The proof printing for the counter-removal additional cost: six
    counters, from the graveyard, on the card's own permission."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Quilled Greatwurm"],
            battlefield=["Craw Wurm", "Hill Giant", *["Forest"] * 6],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.game.add_counters(wurm, Counter.PLUS_ONE, 4)
    scenario.game.add_counters(giant, Counter.PLUS_ONE, 2)
    casting = scenario.cast("Quilled Greatwurm", username="alice", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Cast permission", choosing=[wurm, giant])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    greatwurm = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert greatwurm.zone is Zone.BATTLEFIELD
    assert wurm.counters[Counter.PLUS_ONE] == 0
    assert giant.counters[Counter.PLUS_ONE] == 0
