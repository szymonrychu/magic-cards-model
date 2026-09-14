"""Per-turn activation limits: "Activate only once each turn" and "Activate no
more than twice each turn".

- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated."
- **CR 602.5b** - "If an activated ability has a restriction on its use (for
  example, 'Activate only once each turn'), the restriction continues to apply
  to that object even if its controller changes."

The count in the restriction is read from the printed sentence, not assumed
to be one: Vampire Bats and Fire-Belly Changeling print "no more than twice",
Blazing Rootwalla prints "only once". Every CR number above was read with
`mise run rules:find` in the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(creature: str, land: str, lands: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", library=[land], battlefield=[creature, *([land] * lands)])
        .player("bob", library=[land])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_no_more_than_twice_allows_the_second_activation_and_refuses_the_third():
    """Vampire Bats: "{B}: This creature gets +1/+0 until end of turn. Activate
    no more than twice each turn." """
    scenario = _board("Vampire Bats", "Swamp", 3)
    bats = scenario.creature("Vampire Bats", "alice")

    scenario.activate(bats, *scenario.untapped_sources("Swamp"))
    assert scenario.why_cannot_activate(bats) is None
    scenario.activate(bats, *scenario.untapped_sources("Swamp"))

    refusal = scenario.why_cannot_activate(bats)
    assert refusal is not None
    assert "already been activated twice this turn" in refusal
    assert "CR 602.5b" in refusal
    with pytest.raises(ValueError, match="already been activated twice this turn"):
        scenario.activate(bats, *scenario.untapped_sources("Swamp"))


def test_no_more_than_twice_on_a_second_printing():
    """Fire-Belly Changeling prints the same restriction on a red ability."""
    scenario = _board("Fire-Belly Changeling", "Mountain", 3)
    changeling = scenario.creature("Fire-Belly Changeling", "alice")

    scenario.activate(changeling, *scenario.untapped_sources("Mountain"))
    scenario.activate(changeling, *scenario.untapped_sources("Mountain"))
    while scenario.game.stack:
        scenario.pass_until_resolved()

    # Printed 1/1, two +1/+0 activations resolved.
    assert changeling.power == 3
    assert "twice" in (scenario.why_cannot_activate(changeling) or "")


def test_only_once_still_refuses_the_second_activation():
    """Blazing Rootwalla: "{R}: This creature gets +2/+0 until end of turn.
    Activate only once each turn." - the limit of one read the same way."""
    scenario = _board("Blazing Rootwalla", "Mountain", 2)
    rootwalla = scenario.creature("Blazing Rootwalla", "alice")

    assert scenario.why_cannot_activate(rootwalla) is None
    scenario.activate(rootwalla, *scenario.untapped_sources("Mountain"))

    assert scenario.why_cannot_activate(rootwalla) == (
        "Blazing Rootwalla's ability has already been activated this turn"
    )


def test_no_more_than_three_times_refuses_the_fourth_activation():
    """Sewer Rats: "{B}, Pay 1 life: This creature gets +1/+0 until end of
    turn. Activate no more than three times each turn." """
    scenario = _board("Sewer Rats", "Swamp", 4)
    rats = scenario.creature("Sewer Rats", "alice")

    for _ in range(3):
        assert scenario.why_cannot_activate(rats) is None
        scenario.activate(rats, *scenario.untapped_sources("Swamp"))

    with pytest.raises(ValueError, match="already been activated three times this turn"):
        scenario.activate(rats, *scenario.untapped_sources("Swamp"))
    assert scenario.player("alice").life == 17
