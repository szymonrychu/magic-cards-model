"""A Saga that exiles a card and copies it on every chapter - The Cloning of
Shredder: "I - Exile target creature card from your graveyard. Create a
token that's a copy of it, except it isn't legendary and is a Mutant in
addition to its other types. / II, III - Create a token that's a copy of a
card exiled with this Saga, except it isn't legendary and is a Mutant in
addition to its other types."

- CR 607.2a: chapter I's exile and chapters II/III's "a card exiled with
  this Saga" are linked - II and III see only what chapter I exiled, never
  some other card that happens to be in exile.
- CR 707.9b: "Some copy effects modify a characteristic as part of the
  copying process. The final set of values for that characteristic becomes
  part of the copiable values of the copy." - the token is not legendary
  (so the legend rule never sees two of them) and is a Mutant as well as
  everything the card is.
- CR 608.2b: an illegal chapter I target means no exile and no token.
- CR 714.4: the Saga is sacrificed once chapter III has resolved.

Off-set proofs (legal, in no deck list):

- Ember Island Production: "Choose one - * Create a token that's a copy of
  target creature you control, except it's not legendary and it's a 4/4
  Hero in addition to its other types. * Create a token that's a copy of
  target creature an opponent controls, except it's not legendary and it's
  a 2/2 Coward in addition to its other types." - the same exception list
  worded "it's not legendary and it's a N/N `<Subtype>`", a P/T with it, and
  a target on the battlefield.
- Mimic Vat: "Imprint - Whenever a nontoken creature dies, you may exile
  that card. If you do, return each other card exiled with this artifact to
  its owner's graveyard. / {3}, {T}: Create a token that's a copy of a card
  exiled with this artifact. It gains haste. Exile it at the beginning of
  the next end step." - the linked-exile copy on an artifact's activated
  ability, the pile built by a different instruction.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Supertype, Zone

from .harness import Scenario

SAGA = "The Cloning of Shredder"
LEGEND = "Griselbrand"


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _tokens_named(scenario, name):
    return [p for p in scenario.game.battlefield if p.token and p.name == name]


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _saga_board(*, graveyard=(), exile=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[SAGA],
            battlefield=["Swamp"] * 6,
            graveyard=list(graveyard),
            exile=list(exile),
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def _cast_saga(scenario, target):
    scenario.choose_trigger_targets(SAGA, [target] if target is not None else [])
    scenario.cast_and_resolve(SAGA, *scenario.untapped_sources(*["Swamp"] * 6, username="alice"))
    _resolve_everything(scenario)
    return scenario.find(SAGA, Zone.BATTLEFIELD, "alice")


def _next_chapter(scenario):
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)


def test_chapter_one_exiles_the_card_and_copies_it():
    scenario = _saga_board(graveyard=[LEGEND])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    legend = scenario.find(LEGEND, Zone.GRAVEYARD, "alice")

    _cast_saga(scenario, legend)

    assert legend.zone is Zone.EXILE
    (token,) = _tokens_named(scenario, LEGEND)
    chars = _chars(scenario, token)
    # CR 707.9b: not legendary, a Mutant, and everything else it was.
    assert Supertype.LEGENDARY not in chars.supertypes
    assert "Mutant" in chars.subtypes
    assert "Demon" in chars.subtypes
    assert (chars.power, chars.toughness) == (7, 7)


def test_chapter_two_copies_the_card_exiled_with_the_saga():
    scenario = _saga_board(graveyard=[LEGEND])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    legend = scenario.find(LEGEND, Zone.GRAVEYARD, "alice")
    _cast_saga(scenario, legend)

    _next_chapter(scenario)

    tokens = _tokens_named(scenario, LEGEND)
    # Not legendary: the legend rule (CR 704.5j) leaves both.
    assert len(tokens) == 2
    for token in tokens:
        assert Supertype.LEGENDARY not in _chars(scenario, token).supertypes
        assert "Mutant" in _chars(scenario, token).subtypes


def test_chapter_three_copies_again_and_the_saga_is_sacrificed():
    scenario = _saga_board(graveyard=[LEGEND])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    legend = scenario.find(LEGEND, Zone.GRAVEYARD, "alice")
    saga = _cast_saga(scenario, legend)
    _next_chapter(scenario)

    _next_chapter(scenario)
    scenario.state_based_actions()

    assert len(_tokens_named(scenario, LEGEND)) == 3
    assert saga.zone is Zone.GRAVEYARD


def test_a_nonlegendary_card_is_copied_as_a_mutant():
    scenario = _saga_board(graveyard=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _cast_saga(scenario, bears)

    (token,) = _tokens_named(scenario, "Grizzly Bears")
    assert {"Bear", "Mutant"} <= set(_chars(scenario, token).subtypes)


def test_an_illegal_chapter_one_target_exiles_and_copies_nothing():
    """CR 608.2b: the card left the graveyard before chapter I resolved."""
    scenario = _saga_board(graveyard=[LEGEND])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    legend = scenario.find(LEGEND, Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets(SAGA, [legend])
    scenario.cast_and_resolve(SAGA, *scenario.untapped_sources(*["Swamp"] * 6, username="alice"))
    scenario.game.put_triggers_on_stack()

    scenario.game.exile_permanent(legend)
    _resolve_everything(scenario)

    assert _tokens_named(scenario, LEGEND) == []


def test_chapter_two_ignores_a_card_exiled_by_something_else():
    """CR 607.2a: only chapter I's exile is linked. With chapter I's target
    gone, a card already sitting in exile is not "exiled with this Saga"."""
    scenario = _saga_board(graveyard=[LEGEND], exile=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    legend = scenario.find(LEGEND, Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets(SAGA, [legend])
    scenario.cast_and_resolve(SAGA, *scenario.untapped_sources(*["Swamp"] * 6, username="alice"))
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_permanent(legend)
    _resolve_everything(scenario)

    _next_chapter(scenario)

    assert _tokens_named(scenario, "Hill Giant") == []
    assert _tokens_named(scenario, LEGEND) == []


def test_chapter_two_copies_only_the_linked_card():
    scenario = _saga_board(graveyard=["Grizzly Bears"], exile=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    _cast_saga(scenario, bears)

    _next_chapter(scenario)

    assert len(_tokens_named(scenario, "Grizzly Bears")) == 2
    assert _tokens_named(scenario, "Hill Giant") == []


# -- Ember Island Production ------------------------------------------------------


def _cast_production(scenario, mode, target):
    casting = scenario.cast("Ember Island Production", username="alice")
    casting.choose_modes([mode])
    casting.choose_targets([target])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 5, username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _production_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Ember Island Production"],
            battlefield=["Island"] * 5 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_production_copies_your_legend_as_a_nonlegendary_4_4_hero():
    scenario = _production_board(alice=["Isamaru, Hound of Konda"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")

    _cast_production(scenario, 1, isamaru)

    (token,) = _tokens_named(scenario, "Isamaru, Hound of Konda")
    chars = _chars(scenario, token)
    assert Supertype.LEGENDARY not in chars.supertypes
    assert "Hero" in chars.subtypes
    assert "Dog" in chars.subtypes
    assert (chars.power, chars.toughness) == (4, 4)
    # The original is still here: no legend rule between them.
    assert isamaru.zone is Zone.BATTLEFIELD


def test_production_copies_an_opponents_creature_as_a_2_2_coward():
    scenario = _production_board(bob=["Craw Wurm"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_production(scenario, 2, wurm)

    (token,) = _tokens_named(scenario, "Craw Wurm")
    chars = _chars(scenario, token)
    assert scenario.game.controller_of(token).username == "alice"
    assert {"Wurm", "Coward"} <= set(chars.subtypes)
    assert (chars.power, chars.toughness) == (2, 2)


# -- Mimic Vat -----------------------------------------------------------------


def _vat_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Mimic Vat", "Mountain", "Mountain", "Mountain", *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_mimic_vat_imprints_a_dying_creature():
    scenario = _vat_board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    vat = scenario.find("Mimic Vat", Zone.BATTLEFIELD, "alice")

    scenario.game.destroy(giant)
    _resolve_everything(scenario)

    assert giant.zone is Zone.EXILE
    assert scenario.game.cards_exiled_with(vat.id, vat.zone_change_stamp) == [giant]


def test_mimic_vat_declining_leaves_the_card_in_the_graveyard():
    scenario = _vat_board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, username="alice")

    scenario.game.destroy(giant)
    _resolve_everything(scenario)

    assert giant.zone is Zone.GRAVEYARD


def test_mimic_vat_returns_the_old_card_when_it_imprints_a_new_one():
    scenario = _vat_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    vat = scenario.find("Mimic Vat", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(giant)
    _resolve_everything(scenario)

    scenario.game.destroy(bears)
    _resolve_everything(scenario)

    assert giant.zone is Zone.GRAVEYARD
    assert giant in scenario.player("bob").graveyard
    assert scenario.game.cards_exiled_with(vat.id, vat.zone_change_stamp) == [bears]


def test_mimic_vat_makes_a_hasty_copy_exiled_at_the_next_end_step():
    scenario = _vat_board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    vat = scenario.find("Mimic Vat", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(giant)
    _resolve_everything(scenario)

    scenario.activate(vat, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    _resolve_everything(scenario)

    (token,) = _tokens_named(scenario, "Hill Giant")
    assert scenario.game.controller_of(token).username == "alice"
    assert "Haste" in _chars(scenario, token).abilities

    while scenario.step is not Step.END_STEP:
        _resolve_everything(scenario)
        scenario.advance()
    _resolve_everything(scenario)
    assert _tokens_named(scenario, "Hill Giant") == []


def test_mimic_vat_with_nothing_exiled_makes_nothing():
    scenario = _vat_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vat = scenario.find("Mimic Vat", Zone.BATTLEFIELD, "alice")

    scenario.activate(vat, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    _resolve_everything(scenario)

    assert [p for p in scenario.game.battlefield if p.token] == []
