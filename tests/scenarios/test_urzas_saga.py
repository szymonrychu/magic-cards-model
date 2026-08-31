"""Urza's Saga: a Saga *land* (CR 303.5, CR 305) whose three chapters grant
it a mana ability, then an activated ability, then fetch a construct - a
`test_sagas.py`'s own History of Benalia mechanic, extended for the two
things that mechanic never needed: a chapter that *grants an ability to its
own source* rather than making a token or pumping a team, and a search whose
mana bound is spelled "with mana cost {0} or {1}" instead of the usual
"with mana value N or less".

"(As this Saga enters and after your draw step, add a lore counter. Sacrifice
after III.) I — This Saga gains "{T}: Add {C}." II — This Saga gains "{2},
{T}: Create a 0/0 colorless Construct artifact creature token with 'This
token gets +1/+1 for each artifact you control.'" III — Search your library
for an artifact card with mana cost {0} or {1}, put it onto the battlefield,
then shuffle."

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file (`test_sagas.py`'s own
header already covers the shared chapter/lore-counter mechanics and is not
re-verified here):

- **CR 113.10** - "An effect that adds an ability will state that the object
  'gains' ... that ability." Chapters I and II are exactly this shape.
- **CR 113.10a** - "An effect that adds an activated ability may include
  activation instructions for that ability. These instructions become part
  of the ability that's added to the object" - chapter II's own `{2}, {T}:`
  cost travels with the grant.
- **CR 605.1a** - an activated ability with `{T}` in its cost, no target,
  that could add mana, and is not a loyalty ability, is a mana ability -
  chapter I's own grant, once on the Saga, is exactly this and skips the
  stack (CR 605.3b).
- **CR 202.3a** - "The mana value of an object with no mana cost is 0" - the
  Construct token has none printed, so it starts at 0/0 before any static
  ability adds to it.
- **CR 613.4c** - a static ability that "modif[ies] power and/or toughness
  ... but ... don't set them to a specific number or value" is sublayer 7c -
  the Construct's own "+1/+1 for each artifact you control" counts the board
  live, itself included once it exists.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import granted_mana_abilities
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario, mana_from


def _saga_at_chapter_one(*, battlefield=(), hand=(), **extra):
    """Urza's Saga played from hand, with chapter I already resolved -
    CR 714.3a's own intrinsic lore counter fires the instant it enters
    (CR 122.6), the moment `play_land`'s own special action (CR 305.1, no
    stack) puts it there. Played rather than placed straight onto the
    battlefield: a card `Scenario` builds directly into `battlefield=[...]`
    never runs `Game.enter_the_battlefield` and so never emits the entering
    event chapter I's trigger needs to fire - `test_sagas.py`'s own
    `_cast_history_of_benalia` makes the identical choice, for the identical
    reason."""
    scenario = (
        Scenario()
        .player("alice", hand=["Urza's Saga", *hand], battlefield=list(battlefield), **extra)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.play_land("Urza's Saga")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario, saga


def _advance_a_chapter(scenario):
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_chapter_one_grants_a_usable_colorless_mana_ability():
    """The grant is not merely visible - it is *usable*: the Saga can be
    tapped for {C} the instant chapter I resolves, through the same
    `CostPayment.tap_for_mana` a real game uses."""
    scenario, saga = _saga_at_chapter_one()

    assert saga.granted_ability_texts == ("{T}: Add {C}.",)
    (ability,) = granted_mana_abilities(saga.granted_ability_texts)
    assert ability.produces() == [Color.COLORLESS]

    payment = scenario.game.begin_activating(saga, 0, "alice")
    payment.tap_for_mana(saga, mana_from(saga))
    assert payment.pool.floating == {Color.COLORLESS: 1}
    assert saga.tapped


def test_chapter_two_grants_an_activatable_construct_maker():
    """The Construct token's own pump - "+1/+1 for each artifact you
    control" - is a live sublayer 7c count (CR 613.4c), read off the board
    the moment the token exists: with Sol Ring as the only other artifact,
    the token counts itself and Sol Ring both, for +2/+2 on a printed 0/0."""
    scenario, saga = _saga_at_chapter_one(battlefield=["Sol Ring"])
    _advance_a_chapter(scenario)
    assert saga.granted_ability_texts == (
        "{T}: Add {C}.",
        "{2}, {T}: Create a 0/0 colorless Construct artifact creature token with "
        "'This token gets +1/+1 for each artifact you control.'",
    )

    (sol_ring,) = scenario.untapped_sources("Sol Ring")
    scenario.activate(saga, sol_ring, index=1)
    scenario.resolve_top()

    constructs = [p for p in scenario.game.battlefield if p.name == "Construct Token"]
    assert len(constructs) == 1
    characteristics = scenario.game.characteristics_of(constructs[0])
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    assert saga.tapped, "the {2}, {T} cost tapped the Saga along with the mana"


def test_the_constructs_pump_tracks_the_board_as_artifacts_change():
    """Not a snapshot at creation - the same live-recompute CR 613.5 gives
    every other sublayer 7c pump in this engine. Adding a second artifact
    after the Construct already exists grows it further."""
    scenario, saga = _saga_at_chapter_one(battlefield=["Sol Ring"], hand=["Mox Opal"])
    _advance_a_chapter(scenario)
    (sol_ring,) = scenario.untapped_sources("Sol Ring")
    scenario.activate(saga, sol_ring, index=1)
    scenario.resolve_top()
    (construct,) = [p for p in scenario.game.battlefield if p.name == "Construct Token"]
    before = scenario.game.characteristics_of(construct)
    assert (before.power, before.toughness) == (2, 2)

    scenario.cast_and_resolve("Mox Opal")
    after = scenario.game.characteristics_of(construct)
    assert (after.power, after.toughness) == (3, 3)


def test_chapter_three_finds_an_artifact_with_mana_cost_zero_or_one():
    """ "An artifact card with mana cost {0} or {1}" (not the usual "mana
    value N or less" phrasing) still bounds the search to the same set: Mox
    Opal (mana value 0) is found, and the Saga itself is swept to the
    graveyard by CR 714.4/704.5s the moment the ability finishes resolving,
    once it is at its final chapter with nothing left owed to it."""
    scenario, saga = _saga_at_chapter_one(library=["Mind Stone", "Mox Opal"])
    _advance_a_chapter(scenario)
    _advance_a_chapter(scenario)

    assert scenario.find("Mox Opal", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.find("Mind Stone", Zone.LIBRARY).zone is Zone.LIBRARY
    assert saga.zone is Zone.GRAVEYARD
