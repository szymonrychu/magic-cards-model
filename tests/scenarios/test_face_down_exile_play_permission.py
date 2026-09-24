"""Scenario: exile the top cards of a library face down, then "for as long as
they remain exiled, you may [look at and] play them[ if you control a
<type>]".

CR 406.3: cards "exiled face down" can't be examined, but "if a player is
instructed to look at a card and then exile it face down, or once a player
is allowed to look at a card exiled face down, that player may continue to
look at that card until it leaves the exile zone". CR 406.3a: "A card exiled
face down has no characteristics, but the spell or ability that exiled it
may allow it to be played from exile", and it is turned face up just before
it is played. The permission (CR 601.3) has no "this turn" - it lasts as long
as the card stays in exile (CR 400.7) - and Flameshape's "if you control a
Wizard" is a live condition checked whenever the card would be played.

Printings: Gandalf, Goblins' Bane // Flameshape (your library, "look at ...
and exile them face down", condition), off-set Decadent Dragon // Expensive
Taste (target opponent's library, "look at and play those cards", no
condition) - a different library, wording and duration position.

CR numbers verified with `mise run rules:find`: 406.3, 406.3a, 601.3, 400.7,
715.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.cards import card

from .harness import Scenario

GANDALF = "Gandalf, Goblins' Bane // Flameshape"
DRAGON = "Decadent Dragon // Expensive Taste"


def _face_text(name: str, face: str) -> str:
    printing = card(name)
    (found,) = [f for f in printing.card_faces or [] if f.name == face]
    return found.oracle_text or ""


def _exiled(scenario, name: str):
    """A face-down card has no name (CR 406.3a) - find it by its printing."""
    (found,) = [c for c in scenario.game.exile if c.card.name == name]
    return found


def _cast_exiled(scenario, name: str, caster: str = "alice") -> Casting:
    casting = Casting(
        spell=_exiled(scenario, name), caster=caster, origin_zone=Zone.EXILE, game=scenario.game
    )
    casting.use_permission()
    return casting


def test_both_adventure_faces_read():
    assert effect_for("Flameshape", _face_text(GANDALF, "Flameshape")) is not None
    assert effect_for("Expensive Taste", _face_text(DRAGON, "Expensive Taste")) is not None


def _flameshape(*, battlefield=("Mountain", "Mountain")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[GANDALF],
            battlefield=list(battlefield),
            library=["Grizzly Bears", "Forest", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Gandalf, Goblins' Bane")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_flameshape_exiles_the_top_two_face_down_and_its_caster_knows_them():
    scenario = _flameshape()
    bears = _exiled(scenario, "Grizzly Bears")
    forest = _exiled(scenario, "Forest")
    assert not bears.face_up and not forest.face_up
    known_to_alice = {known.card_id for known in scenario.game.known_to("alice")}
    known_to_bob = {known.card_id for known in scenario.game.known_to("bob")}
    assert {bears.id, forest.id} <= known_to_alice
    assert not ({bears.id, forest.id} & known_to_bob)


def test_without_a_wizard_the_cards_cannot_be_played():
    scenario = _flameshape()
    forest = _exiled(scenario, "Forest")
    with pytest.raises(ValueError):
        scenario.game.play_land(forest, "alice")


def test_with_a_wizard_a_land_is_played_and_a_spell_cast_face_up():
    scenario = _flameshape(
        battlefield=("Mountain", "Mountain", "Forest", "Forest", "Spellstutter Sprite")
    )
    forest = _exiled(scenario, "Forest")
    scenario.game.play_land(forest, "alice")
    assert forest.face_up
    casting = _cast_exiled(scenario, "Grizzly Bears")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.creature("Grizzly Bears", "alice")


def test_the_permission_lasts_past_the_turn_and_the_wizard_can_arrive_later():
    """Gandalf himself is a Wizard: cast from his Adventure exile on a later
    turn, he turns the permission on."""
    scenario = _flameshape(battlefield=("Mountain",) * 3)
    active = scenario.turn.active_player
    for _ in range(2):
        while scenario.turn.active_player == active or scenario.step is not Step.PRECOMBAT_MAIN:
            scenario.advance()
        active = scenario.turn.active_player
    assert scenario.turn.active_player == "alice"
    forest = _exiled(scenario, "Forest")
    with pytest.raises(ValueError):
        scenario.game.play_land(forest, "alice")
    gandalf = scenario.cast("Gandalf, Goblins' Bane", from_zone=Zone.EXILE)
    gandalf.use_keyword("Adventure")
    scenario.pay_with(gandalf.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(gandalf)
    scenario.resolve_top()
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD


# -- Decadent Dragon // Expensive Taste: an opponent's library, no condition -


def test_expensive_taste_exiles_an_opponents_cards_face_down_for_its_caster():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[DRAGON],
            battlefield=["Mountain", "Mountain", "Swamp", "Forest", "Forest"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Grizzly Bears", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Decadent Dragon")
    casting.cast_as_adventure()
    casting.choose_targets(["bob"])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", "Swamp")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    bears = _exiled(scenario, "Grizzly Bears")
    assert not bears.face_up
    assert bears.id in {known.card_id for known in scenario.game.known_to("alice")}
    # bob owns it but may not play it; alice may, for its own mana cost.
    assert scenario.game.play_permission_for(bears, "bob") is None
    cast = _cast_exiled(scenario, "Grizzly Bears")
    scenario.pay_with(cast.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(cast)
    scenario.resolve_top()
    assert scenario.creature("Grizzly Bears", "alice").owner == "bob"
