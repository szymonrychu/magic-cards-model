""" "Whenever you earthbend / firebend" - the bending actions as trigger events.

Avatar Aang: "Whenever you waterbend, earthbend, firebend, or airbend, draw a
card. Then if you've done all four this turn, transform Avatar Aang." Each verb
is its own rule for when that trigger fires:

- CR 701.66b: "An ability that triggers whenever a player earthbends triggers
  when the delayed triggered ability described in rule 701.66a is created."
- CR 702.189b: "An ability that triggers whenever a player firebends triggers
  whenever a firebending ability they control resolves." (Firebending N is CR
  702.189a's "Whenever this creature attacks, add N {R}. ...")
- Waterbend is CR 701.67c (`test_waterbend.py`) and airbend CR 701.65b
  (`test_airbend_any_number.py`).

Every CR number here was read whole with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_earthbending_draws_a_card_off_avatar_aang():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=["Badgermole Cub"],
            battlefield=["Avatar Aang", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pay, target = (
        scenario.untapped_sources("Forest", "Forest", "Forest")[:2],
        scenario.untapped_sources("Forest", "Forest", "Forest")[2],
    )
    scenario.choose_trigger_targets("Badgermole Cub", [target])
    scenario.cast_and_resolve("Badgermole Cub", *pay)
    _resolve_all(scenario)

    assert target.counters["+1/+1"] == 1
    assert len(scenario.player("alice").hand) == 1  # Avatar Aang's draw
    assert "alice" in scenario.game.turn_facts.get("earthbent", set())


def test_firebending_resolving_draws_a_card_off_avatar_aang():
    """Avatar Aang's own firebending 2: attacking adds {R}{R}, and that
    ability resolving is a firebend - Aang draws."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, battlefield=["Avatar Aang"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    aang = scenario.creature("Avatar Aang", "alice")
    scenario.attack_with(aang)
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == 1
    assert "alice" in scenario.game.turn_facts.get("firebent", set())


def test_no_bending_no_draw():
    """Casting a creature with no bending in it does not fire the trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=["Grizzly Bears"],
            battlefield=["Avatar Aang", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _resolve_all(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_the_draw_trigger_targets_nothing():
    """The verb "earthbend" in a trigger *condition* is the event (CR 701.66b),
    not the instruction - Avatar Aang's draw trigger announces no target, so
    it is never removed for want of a land (CR 603.3d)."""
    from magic_cards_model.machines.targeting import profile_for_text

    profile = profile_for_text(
        "Whenever you waterbend, earthbend, firebend, or airbend, draw a card. "
        "Then if you've done all four this turn, transform Avatar Aang."
    )
    assert profile.requirements == ()


def test_all_four_real_bends_in_one_turn_transform_avatar_aang():
    """Every bend done for real, none staged: earthbend (Badgermole Cub),
    airbend (Airbending Lesson), waterbend (Geyser Leaper's Waterbend {4}),
    then firebend (Aang's own attack) - the fourth one's draw trigger sees all
    four this turn and transforms him."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 10,
            hand=["Badgermole Cub", "Airbending Lesson", "Llanowar Elves"],
            battlefield=[
                "Avatar Aang",
                "Geyser Leaper",
                "Grizzly Bears",
                "Welding Jar",
                "Forest",
                "Forest",
                "Forest",
                "Plains",
                "Island",
                "Island",
                "Island",
                "Island",
            ],
        )
        .player("bob", library=["Island"] * 5, battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    aang = scenario.creature("Avatar Aang", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.choose_trigger_targets("Badgermole Cub", [forests[2]])
    scenario.cast_and_resolve("Badgermole Cub", *forests[:2])
    _resolve_all(scenario)
    scenario.cast_and_resolve(
        "Airbending Lesson",
        *scenario.untapped_sources("Plains", "Island", "Island"),
        targets=[scenario.creature("Runeclaw Bear", "bob")],
    )
    _resolve_all(scenario)
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    scenario.will_discard(elves)
    scenario.activate(
        scenario.creature("Geyser Leaper", "alice"),
        *scenario.untapped_sources("Island", "Island"),
        tapping=[scenario.creature("Grizzly Bears", "alice"), scenario.creature("Welding Jar")],
    )
    _resolve_all(scenario)
    for fact in ("earthbent", "airbent", "waterbent"):
        assert "alice" in scenario.game.turn_facts.get(fact, set())
    assert aang.name == "Avatar Aang"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(aang)
    _resolve_all(scenario)

    assert aang.name == "Aang, Master of Elements"
