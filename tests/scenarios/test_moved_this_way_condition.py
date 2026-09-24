"""An instruction gated on what the sentence before it just discarded or
milled - "If you discarded a <quality> card this way, ..." / "If at least one
<quality> card is milled this way, ...".

- **Vohar, Vodalian Desecrator** - "{T}: Draw a card, then discard a card. If
  you discarded an instant or sorcery card this way, each opponent loses 1
  life and you gain 1 life."
- **Liliana, Untouched by Death** - "+1: Mill three cards. If at least one
  Zombie card is milled this way, each opponent loses 2 life and you gain 2
  life."

Both are second printings brought in to prove this task's graveyard
permissions (their other abilities are in
`test_graveyard_cast_permission_exile.py`); these are their remaining lines,
read by one reader for two verbs, two phrasings of the condition and two
kinds of quality (card types, a subtype).

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 608.2c** - the instructions are followed in order, so the condition
  looks at what the first sentence actually moved.
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 701.17a** / **CR 701.17c** - milling puts cards from the top of the
  library into the graveyard, and "an effect that refers to a milled card can
  find that card in the zone it moved to".
- **CR 701.17b** - an empty library mills nothing, so nothing was milled
  "this way".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _vohar(*, hand, library=("Swamp", "Swamp")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Vohar, Vodalian Desecrator"],
            library=list(library),
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _loot_discarding(scenario, name):
    vohar = scenario.find("Vohar, Vodalian Desecrator", Zone.BATTLEFIELD, "alice")
    scenario.activate(vohar, index=0, username="alice")
    player = scenario.player("alice")
    discard = next(card for card in [*player.hand, *player.library] if card.name == name)
    scenario.will_discard(discard, username="alice")
    scenario.pass_until_resolved()


def test_discarding_an_instant_drains_each_opponent():
    scenario = _vohar(hand=["Lightning Bolt"])
    _loot_discarding(scenario, "Lightning Bolt")

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_discarding_a_land_does_nothing_more():
    scenario = _vohar(hand=["Lightning Bolt", "Swamp"])
    _loot_discarding(scenario, "Swamp")

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_the_card_just_drawn_counts_when_it_is_the_one_discarded():
    """The loot draws first (CR 608.2c): an instant drawn off the top and
    discarded straight away is "discarded this way"."""
    scenario = _vohar(hand=["Swamp"], library=["Mind Rot"])
    _loot_discarding(scenario, "Mind Rot")

    assert scenario.player("bob").life == 19


def _liliana(library):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Liliana, Untouched by Death"],
            library=list(library),
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana, Untouched by Death", Zone.BATTLEFIELD, "alice")
    scenario.activate(liliana, index=0, username="alice")
    scenario.pass_until_resolved()
    return scenario


def test_a_zombie_among_the_three_milled_drains():
    scenario = _liliana(["Swamp", "Carrion Feeder", "Swamp", "Swamp"])

    assert len(scenario.player("alice").graveyard) == 3
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_two_zombies_drain_only_once():
    """ "At least one" is a yes-or-no question, not a count."""
    scenario = _liliana(["Carrion Feeder", "Rank Rat", "Swamp"])

    assert scenario.player("bob").life == 18


def test_no_zombie_milled_means_no_drain():
    scenario = _liliana(["Swamp", "Swamp", "Swamp", "Carrion Feeder"])

    assert scenario.player("bob").life == 20
    assert scenario.find("Carrion Feeder", Zone.LIBRARY, "alice") is not None


def test_a_zombie_already_in_the_graveyard_was_not_milled_this_way():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Liliana, Untouched by Death"],
            graveyard=["Carrion Feeder"],
            library=["Swamp"] * 4,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana, Untouched by Death", Zone.BATTLEFIELD, "alice")
    scenario.activate(liliana, index=0, username="alice")
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
