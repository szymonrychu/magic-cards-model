"""Turn-history conditions about objects changing zones (EC4 cluster H2):
creatures dying under a given player's control, permanents put into a
graveyard or a hand from the battlefield, and cards put into exile - read by
an intervening "if" (CR 603.4) and by an "Activate only if" restriction
(CR 602.5b).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 700.4** - "The term dies means 'is put into a graveyard from the
  battlefield.'"
- **CR 603.10a** - a leaves-the-battlefield event looks back in time: who
  controlled the creature, and what it was, is judged as it last existed on
  the battlefield.
- **CR 400.7** - an object that moves from one zone to another becomes a new
  object; a card already in exile when the turn began was not put there this
  turn.
- **CR 603.4** and **CR 602.5b** as above.

Every clause here failed closed before `machines/conditions/history.py` read
it: the triggers recorded `InterveningIfNotice` and never fired, and Cult
Conscript's activation was refused whatever had died.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_end_step(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    if scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
        scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    scenario.game.put_triggers_on_stack()


def _triggered(scenario, name: str) -> bool:
    return f"{name}'s triggered ability" in scenario.stack_names()


# -- "a [non-<quality>] creature died under your control this turn" -------------


def _conscript_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Cult Conscript"],
            battlefield=["Grizzly Bears", "Manor Skeleton", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    conscript = scenario.find("Cult Conscript", Zone.GRAVEYARD, "alice")
    return scenario, conscript


def test_cult_conscript_is_refused_before_anything_died():
    """Cult Conscript: "{1}{B}: Return this card from your graveyard to the
    battlefield. Activate only if a non-Skeleton creature died under your
    control this turn." """
    scenario, conscript = _conscript_board()
    refusal = scenario.why_cannot_activate(conscript, 0, "alice")
    assert refusal == "Cult Conscript's activation restriction is not met (CR 602.5b)"


def test_cult_conscript_returns_once_a_non_skeleton_of_yours_died():
    scenario, conscript = _conscript_board()
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))

    assert scenario.why_cannot_activate(conscript, 0, "alice") is None
    scenario.activate(conscript, *scenario.untapped_sources("Swamp", "Swamp"), username="alice")
    scenario.pass_until_resolved()
    assert scenario.find("Cult Conscript", Zone.BATTLEFIELD, "alice") is not None


def test_a_skeleton_dying_does_not_meet_the_non_skeleton_restriction():
    scenario, conscript = _conscript_board()
    scenario.game.destroy(scenario.creature("Manor Skeleton", "alice"))

    refusal = scenario.why_cannot_activate(conscript, 0, "alice")
    assert refusal is not None and "not met" in refusal


def test_an_opponents_creature_dying_does_not_meet_under_your_control():
    scenario, conscript = _conscript_board()
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))

    refusal = scenario.why_cannot_activate(conscript, 0, "alice")
    assert refusal is not None and "not met" in refusal


def _died_under(card: str, dying_owner: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=[card, "Grizzly Bears"], library=["Plains"] * 4)
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature("Grizzly Bears", dying_owner))
    _to_end_step(scenario)
    return scenario


def test_essenceknit_scholar_draws_after_a_creature_of_yours_died():
    """Essenceknit Scholar (a second printing, on a trigger): "At the beginning
    of your end step, if a creature died under your control this turn, draw a
    card." """
    scenario = _died_under("Essenceknit Scholar", "alice")
    assert _triggered(scenario, "Essenceknit Scholar")
    assert scenario.game.intervening_if_notices == []


def test_an_opponents_creature_dying_is_not_under_your_control():
    scenario = _died_under("Essenceknit Scholar", "bob")
    assert not _triggered(scenario, "Essenceknit Scholar")
    assert scenario.game.intervening_if_notices == []


def test_under_an_opponents_control_reads_the_other_side():
    """Sidequest: Hunt the Mark: "At the beginning of your end step, if a
    creature died under an opponent's control this turn, create a Treasure
    token. ..." """
    card = "Sidequest: Hunt the Mark // Yiazmat, Ultimate Mark"
    name = "Sidequest: Hunt the Mark"
    assert _triggered(_died_under(card, "bob"), name)
    assert not _triggered(_died_under(card, "alice"), name)


# -- "a permanent was put into your hand from the battlefield this turn" --------


def _barrin_after_bounce(whose: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Barrin, Tolarian Archmage", "Grizzly Bears"],
            library=["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.return_to_hand(scenario.creature("Grizzly Bears", whose))
    _to_end_step(scenario)
    return scenario


def test_barrin_draws_after_a_permanent_went_to_your_hand():
    """Barrin, Tolarian Archmage: "At the beginning of your end step, if a
    permanent was put into your hand from the battlefield this turn, draw a
    card." """
    scenario = _barrin_after_bounce("alice")
    assert _triggered(scenario, "Barrin, Tolarian Archmage")
    assert scenario.game.intervening_if_notices == []


def test_barrin_does_not_draw_when_the_permanent_went_to_an_opponents_hand():
    """ "your hand" is the owner's hand the card went to (CR 108.3)."""
    scenario = _barrin_after_bounce("bob")
    assert not _triggered(scenario, "Barrin, Tolarian Archmage")
    assert scenario.game.intervening_if_notices == []


# -- "one or more cards were put into exile this turn" --------------------------


def _ennis_board(**alice):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Ennis, Debate Moderator"],
            library=["Island"] * 4,
            **alice,
        )
        .player("bob", battlefield=["Grizzly Bears"], graveyard=["Lightning Bolt"])
        .build()
    )


def test_ennis_grows_after_a_permanent_was_exiled():
    """Ennis, Debate Moderator: "At the beginning of your end step, if one or
    more cards were put into exile this turn, put a +1/+1 counter on Ennis." """
    scenario = _ennis_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.exile_permanent(scenario.creature("Grizzly Bears", "bob"))

    _to_end_step(scenario)

    assert _triggered(scenario, "Ennis, Debate Moderator")
    scenario.pass_until_resolved()
    ennis = scenario.find("Ennis, Debate Moderator", Zone.BATTLEFIELD, "alice")
    assert ennis.counter_count("+1/+1") == 1


def test_ennis_counts_a_graveyard_card_exiled():
    scenario = _ennis_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.exile_cards([scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")])

    _to_end_step(scenario)

    assert _triggered(scenario, "Ennis, Debate Moderator")


def test_ennis_does_not_count_a_card_already_in_exile():
    """CR 400.7: a card in exile before the turn began was not put there this
    turn."""
    scenario = _ennis_board(exile=["Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _to_end_step(scenario)

    assert not _triggered(scenario, "Ennis, Debate Moderator")
    assert scenario.game.intervening_if_notices == []


def test_ennis_still_counts_a_card_that_has_since_left_exile():
    """The history is of the move, not of where the card is now."""
    scenario = _ennis_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.exile_permanent(bears)
    scenario.game.put_onto_battlefield(bears, "bob")

    _to_end_step(scenario)

    assert _triggered(scenario, "Ennis, Debate Moderator")


# -- "an <quality> was put into a/your graveyard from the battlefield" ----------


def _ichor_shade_after(destroyed: str | None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ichor Shade", "Ornithopter", "Glorious Anthem"],
            hand=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if destroyed is not None:
        scenario.game.destroy(scenario.find(destroyed, Zone.BATTLEFIELD, "alice"))
    return scenario


def test_ichor_shade_grows_after_an_artifact_went_to_a_graveyard():
    """Ichor Shade: "At the beginning of your end step, if an artifact or
    creature was put into a graveyard from the battlefield this turn, put a
    +1/+1 counter on this creature." """
    scenario = _ichor_shade_after("Ornithopter")
    _to_end_step(scenario)
    assert _triggered(scenario, "Ichor Shade")
    assert scenario.game.intervening_if_notices == []


def test_ichor_shade_does_not_count_an_enchantment():
    scenario = _ichor_shade_after("Glorious Anthem")
    _to_end_step(scenario)
    assert not _triggered(scenario, "Ichor Shade")


def test_ichor_shade_does_not_count_a_creature_card_discarded():
    """A discarded creature card reached the graveyard, but not from the
    battlefield (CR 700.4)."""
    scenario = _ichor_shade_after(None)
    scenario.game.discard_cards("alice", [scenario.find("Grizzly Bears", Zone.HAND, "alice")])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Ichor Shade")
    assert scenario.game.intervening_if_notices == []


def _kami_after(whose: str):
    scenario = (
        Scenario()
        .player("alice", graveyard=["Kami of Transience"], battlefield=["Glorious Anthem"])
        .player("bob", battlefield=["Glorious Anthem"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.find("Glorious Anthem", Zone.BATTLEFIELD, whose))
    _to_end_step(scenario)
    return scenario


def test_kami_of_transience_returns_after_your_enchantment_went_to_your_graveyard():
    """Kami of Transience (a second printing, from the graveyard): "At the
    beginning of each end step, if an enchantment was put into your graveyard
    from the battlefield this turn, you may return this card from your
    graveyard to your hand." """
    scenario = _kami_after("alice")
    assert _triggered(scenario, "Kami of Transience")
    assert scenario.game.intervening_if_notices == []


def test_kami_of_transience_ignores_an_opponents_graveyard():
    scenario = _kami_after("bob")
    assert not _triggered(scenario, "Kami of Transience")
    assert scenario.game.intervening_if_notices == []
