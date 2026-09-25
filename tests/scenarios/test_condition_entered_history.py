"""Turn-history conditions about permanents entering the battlefield (EC4
cluster H3): how many permanents of a quality entered under a player's
control this turn or last turn, whether a named source or "that creature"
entered this turn, and which kinds of permanent a player "had enter" - read
by an intervening "if" (CR 603.4) and by an "Activate only if" restriction
(CR 602.5b).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** / **CR 602.5b** - see the other history files; CR 602.5b's
  restriction "continues to apply to that object even if its controller
  changes", and its "you" is then the new controller (CR 109.5).
- **CR 110.4** - "permanent" is a card or token on the battlefield; "nonland"
  permanents are the ones without the land type.
- **CR 708.2** - a face-down permanent's characteristics.
- **CR 109.5** - "you" is the controller of the ability's source.

Every clause here failed closed before `machines/conditions/history.py` read
it.
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


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep
    scenario.game.put_triggers_on_stack()


# -- "you had a <quality> enter the battlefield under your control this turn" ---


def _decoy_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Zhalfirin Decoy"], hand=["Grizzly Bears", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Zhalfirin Decoy", "alice")


def test_zhalfirin_decoy_is_refused_until_a_creature_entered():
    """Zhalfirin Decoy: "{T}: Tap target creature. Activate only if you had a
    creature enter the battlefield under your control this turn." """
    scenario, decoy = _decoy_board()
    assert (
        scenario.why_cannot_activate(decoy, 0, "alice")
        == "Zhalfirin Decoy's activation restriction is not met (CR 602.5b)"
    )


def test_a_land_entering_is_not_a_creature_entering():
    scenario, decoy = _decoy_board()
    scenario.put_onto_battlefield("Forest", "alice")
    refusal = scenario.why_cannot_activate(decoy, 0, "alice")
    assert refusal is not None and "not met" in refusal


def test_zhalfirin_decoy_taps_once_a_creature_entered():
    scenario, decoy = _decoy_board()
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    assert scenario.why_cannot_activate(decoy, 0, "alice") is None

    bobs_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(decoy, targets=[bobs_bears], username="alice")
    scenario.pass_until_resolved()
    assert bobs_bears.tapped


def test_the_restriction_follows_a_control_change():
    """CR 602.5b: bob's Decoy, taken by alice with Hijack, is judged by alice's
    own history - bob having had a creature enter does not let alice
    activate it, and alice's own creature entering does."""
    scenario = (
        Scenario()
        .player("alice", hand=["Hijack", "Grizzly Bears"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Zhalfirin Decoy"], hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    decoy = scenario.creature("Zhalfirin Decoy", "bob")
    scenario.put_onto_battlefield("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Hijack", *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=[decoy]
    )
    assert scenario.game.controller_of(decoy).username == "alice"
    refusal = scenario.why_cannot_activate(decoy, 0, "alice")
    assert refusal is not None and "not met" in refusal

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    assert scenario.why_cannot_activate(decoy, 0, "alice") is None


def _reaper_after(entering: str):
    scenario = (
        Scenario()
        .player("alice", graveyard=["Cleaving Reaper"], hand=[entering])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(entering, "alice")
    return scenario, scenario.find("Cleaving Reaper", Zone.GRAVEYARD, "alice")


def test_cleaving_reaper_reads_a_subtype_list():
    """Cleaving Reaper (a second printing, from the graveyard): "Pay 3 life:
    Return this card from your graveyard to your hand. Activate only if you had
    an Angel or Berserker enter the battlefield under your control this
    turn." """
    scenario, reaper = _reaper_after("Serra Angel")
    assert scenario.why_cannot_activate(reaper, 0, "alice") is None

    scenario, reaper = _reaper_after("Grizzly Bears")
    refusal = scenario.why_cannot_activate(reaper, 0, "alice")
    assert refusal is not None and "not met" in refusal


def test_this_artifact_or_another_artifact_entered():
    """Master's Manufactory: "{T}: Create a 4/4 ... Golem artifact creature
    token. Activate only if this artifact or another artifact entered the
    battlefield under your control this turn." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Guide-Mural // Master's Manufactory"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manufactory = scenario.find("Master's Guide-Mural", Zone.BATTLEFIELD, "alice")
    manufactory.transformed = True
    refusal = scenario.why_cannot_activate(manufactory, 0, "alice")
    assert refusal is not None and "not met" in refusal

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Master's Guide-Mural // Master's Manufactory"],
            hand=["Ornithopter"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manufactory = scenario.find("Master's Guide-Mural", Zone.BATTLEFIELD, "alice")
    manufactory.transformed = True
    scenario.put_onto_battlefield("Ornithopter", "alice")
    assert scenario.why_cannot_activate(manufactory, 0, "alice") is None


# -- "N or more <quality> entered the battlefield under your control" -----------


def _entered(card: str, entering: list[str], *, whose: str = "alice"):
    scenario = (
        Scenario()
        .player("alice", battlefield=[card], hand=entering, library=["Plains"] * 4)
        .player("bob", hand=list(entering))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name in entering:
        scenario.put_onto_battlefield(name, whose)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    return scenario


def test_two_nonland_permanents_entering_is_a_celebration():
    """Lady of Laughter: "Celebration - At the beginning of your end step, if
    two or more nonland permanents entered the battlefield under your control
    this turn, draw a card." """
    scenario = _entered("Lady of Laughter", ["Grizzly Bears", "Ornithopter"])
    _to_end_step(scenario)
    assert _triggered(scenario, "Lady of Laughter")
    assert scenario.game.intervening_if_notices == []


def test_a_land_does_not_count_towards_nonland_permanents():
    scenario = _entered("Lady of Laughter", ["Grizzly Bears", "Forest"])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Lady of Laughter")
    assert scenario.game.intervening_if_notices == []


def test_an_opponents_permanents_do_not_count():
    scenario = _entered("Lady of Laughter", ["Grizzly Bears", "Ornithopter"], whose="bob")
    _to_end_step(scenario)
    assert not _triggered(scenario, "Lady of Laughter")


def test_pests_of_honor_reads_the_same_clause_at_beginning_of_combat():
    """A second printing, on a different trigger: Pests of Honor's
    "Celebration - At the beginning of combat on your turn, ..." """
    scenario = _entered("Pests of Honor", ["Grizzly Bears", "Ornithopter"])
    scenario.advance()  # beginning of combat
    scenario.game.put_triggers_on_stack()
    assert _triggered(scenario, "Pests of Honor")

    scenario = _entered("Pests of Honor", ["Grizzly Bears"])
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Pests of Honor")


def test_three_or_more_artifacts():
    """Malcator, Purity Overseer: "... if three or more artifacts entered the
    battlefield under your control this turn, ..." """
    scenario = _entered("Malcator, Purity Overseer", ["Ornithopter", "Memnite", "Tormod's Crypt"])
    _to_end_step(scenario)
    assert _triggered(scenario, "Malcator, Purity Overseer")

    scenario = _entered("Malcator, Purity Overseer", ["Ornithopter", "Memnite"])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Malcator, Purity Overseer")


def test_two_or_more_creatures():
    """Spider-UK: "... if two or more creatures entered the battlefield under
    your control this turn, you draw a card and gain 2 life." """
    scenario = _entered("Spider-UK", ["Grizzly Bears", "Memnite"])
    _to_end_step(scenario)
    assert _triggered(scenario, "Spider-UK")

    scenario = _entered("Spider-UK", ["Grizzly Bears", "Tormod's Crypt"])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Spider-UK")


def test_a_face_down_creature_entered():
    """Tunnel Tipster: "At the beginning of your end step, if a face-down
    creature entered the battlefield under your control this turn, put a
    +1/+1 counter on this creature." - manifested by Mastery of the Unseen
    (CR 701.40a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tunnel Tipster", "Mastery of the Unseen"] + ["Plains"] * 4,
            library=["Grizzly Bears", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mastery = scenario.find("Mastery of the Unseen", Zone.BATTLEFIELD, "alice")
    scenario.activate(mastery, index=0, username="alice", auto=True)
    scenario.pass_until_resolved()
    _to_end_step(scenario)
    assert _triggered(scenario, "Tunnel Tipster")

    scenario = _entered("Tunnel Tipster", ["Grizzly Bears"])
    _to_end_step(scenario)
    assert not _triggered(scenario, "Tunnel Tipster")


# -- "<source> entered this turn" / "didn't enter the battlefield this turn" ----


def test_a_source_that_did_not_enter_this_turn_triggers():
    """Cactuar: "At the beginning of your end step, if this creature didn't
    enter the battlefield this turn, return it to its owner's hand." """
    scenario = Scenario().player("alice", battlefield=["Cactuar"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert _triggered(scenario, "Cactuar")
    assert scenario.game.intervening_if_notices == []

    scenario.pass_until_resolved()  # true at both checks (CR 608.2a): it resolves
    assert scenario.find("Cactuar", Zone.HAND, "alice") is not None
    assert "Cactuar" not in scenario.battlefield_names()


def test_a_source_flickered_in_response_is_a_new_object_and_stays():
    """True as the end step began; in response Cactuar is exiled and returned
    - a new object that entered this turn (CR 400.7). On resolution the
    ability's "it" no longer exists on the battlefield (CR 608.2a, CR 113.7a),
    so the Cactuar that is there now stays."""
    scenario = Scenario().player("alice", battlefield=["Cactuar"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert _triggered(scenario, "Cactuar")

    cactuar = scenario.creature("Cactuar", "alice")
    exiled = scenario.game.exile_permanent(cactuar)
    scenario.game.put_onto_battlefield(exiled, "alice")
    scenario.pass_until_resolved()

    assert "Cactuar" in scenario.battlefield_names()


def test_a_source_that_entered_this_turn_does_not():
    scenario = Scenario().player("alice", hand=["Cactuar"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Cactuar", "alice")
    _to_end_step(scenario)
    assert not _triggered(scenario, "Cactuar")
    assert scenario.game.intervening_if_notices == []


def test_a_named_source_that_entered_this_turn():
    """Kaito Shizuki (a second printing, by name): "At the beginning of your
    end step, if Kaito entered this turn, he phases out." """
    scenario = Scenario().player("alice", hand=["Kaito Shizuki"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Kaito Shizuki", "alice")
    _to_end_step(scenario)
    assert _triggered(scenario, "Kaito Shizuki")
    assert scenario.game.intervening_if_notices == []

    scenario = Scenario().player("alice", battlefield=["Kaito Shizuki"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)
    assert not _triggered(scenario, "Kaito Shizuki")
    assert scenario.game.intervening_if_notices == []


def _samut_attack(*, entered: bool):
    builder = Scenario()
    if entered:
        builder = builder.player(
            "alice", hand=["Samut, Vizier of Naktamun"], library=["Plains"] * 3
        )
    else:
        builder = builder.player(
            "alice", battlefield=["Samut, Vizier of Naktamun"], library=["Plains"] * 3
        )
    scenario = builder.player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if entered:
        scenario.put_onto_battlefield("Samut, Vizier of Naktamun", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Samut, Vizier of Naktamun", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    return scenario


def test_that_creature_entered_this_turn_reads_the_event_subject():
    """Samut, Vizier of Naktamun: "Whenever a creature you control deals combat
    damage to a player, if that creature entered this turn, draw a card." -
    "that creature" is the trigger event's own creature."""
    scenario = _samut_attack(entered=True)
    assert _triggered(scenario, "Samut, Vizier of Naktamun")
    assert scenario.game.intervening_if_notices == []

    scenario = _samut_attack(entered=False)
    assert not _triggered(scenario, "Samut, Vizier of Naktamun")
    assert scenario.game.intervening_if_notices == []


# -- "that player had another land enter the battlefield under their control" ---


def _lands_for_bob(card: str, lands: int):
    scenario = (
        Scenario()
        .player("alice", battlefield=[card], library=["Island"] * 3)
        .player("bob", hand=["Forest"] * lands, battlefield=["Forest"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(lands):
        scenario.put_onto_battlefield("Forest", "bob")
    scenario.game.put_triggers_on_stack()
    return scenario


def test_the_second_land_an_opponent_had_enter_triggers():
    """Tunnel Ignus: "Whenever a land enters under an opponent's control, if
    that player had another land enter the battlefield under their control
    this turn, this creature deals 3 damage to that player." """
    assert not _triggered(_lands_for_bob("Tunnel Ignus", 1), "Tunnel Ignus")
    scenario = _lands_for_bob("Tunnel Ignus", 2)
    assert scenario.stack_names().count("Tunnel Ignus's triggered ability") == 1
    assert scenario.game.intervening_if_notices == []


def test_confounding_conundrum_reads_the_same_clause():
    """A second printing of "that player had another land enter"."""
    name = "Confounding Conundrum"
    assert not _triggered(_lands_for_bob(name, 1), name)
    assert _triggered(_lands_for_bob(name, 2), name)


# -- "... last turn" ------------------------------------------------------------


def _ephara(entering: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Ephara, God of the Polis"],
            hand=list(entering),
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name in entering:
        scenario.put_onto_battlefield(name, "alice")
    _next_turn(scenario)  # bob's upkeep: "each upkeep"
    return scenario


def test_ephara_draws_in_the_upkeep_after_a_creature_entered():
    """Ephara, God of the Polis: "At the beginning of each upkeep, if you had
    another creature enter the battlefield under your control last turn, draw
    a card." """
    scenario = _ephara(["Grizzly Bears"])
    assert _triggered(scenario, "Ephara, God of the Polis")
    assert scenario.game.intervening_if_notices == []


def test_ephara_does_not_draw_after_a_turn_with_no_creature_entering():
    scenario = _ephara([])
    assert not _triggered(scenario, "Ephara, God of the Polis")
    assert scenario.game.intervening_if_notices == []


def test_ephara_ignores_an_opponents_creature_last_turn():
    """ "under your control" - bob's creature entering does not count for
    alice's Ephara."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ephara, God of the Polis"], library=["Plains"] * 4)
        .player("bob", hand=["Grizzly Bears"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "bob")
    _next_turn(scenario)
    assert not _triggered(scenario, "Ephara, God of the Polis")
    assert scenario.game.intervening_if_notices == []
