"""An instruction gated on what the sentence before it just discarded or
milled - "If you discarded a <quality> card this way, ..." / "If at least one
<quality> card is milled this way, ...", with an optional "Otherwise, ..."
else-branch for when the condition does not hold.

- **Vohar, Vodalian Desecrator** - "{T}: Draw a card, then discard a card. If
  you discarded an instant or sorcery card this way, each opponent loses 1
  life and you gain 1 life."
- **Liliana, Untouched by Death** - "+1: Mill three cards. If at least one
  Zombie card is milled this way, each opponent loses 2 life and you gain 2
  life."
- **Lorehold Excavation** - "At the beginning of your end step, mill a card.
  If a land card was milled this way, you gain 1 life. Otherwise, this
  enchantment deals 1 damage to each opponent." The "Otherwise" sentence used
  to be silently dropped: `_THEN_IF_MOVED_THIS_WAY_RE`'s old `rest` group was
  fully greedy, so it swallowed "you gain 1 life. Otherwise, ..." as one
  ordinary multi-sentence clause, whose bare-period split quietly ignores
  whichever half no per-clause parser reads (`support.ignored_rider`'s
  ablation probe on the pool caught it: removing the "Otherwise" sentence
  from the printed text left `card_support` giving back the identical
  closure, i.e. it never ran). Fixed by capturing the else-branch as its own
  group and running it only when the condition is false.

Vohar and Liliana are second printings brought in to prove an earlier task's
graveyard permissions (their other abilities are in
`test_graveyard_cast_permission_exile.py`); these are their remaining lines,
read by one reader for two verbs, two phrasings of the condition and two
kinds of quality (card types, a subtype). A pool-wide sweep with `support.
classify_clauses` for every in-format printing whose text contains "otherwise"
found no other card with this same swallow - Klothys, God of Destiny and
Cling to Dust use a different reader (`_parse_if_it_was_quality_card_
otherwise_triple`, gated on a "target" antecedent) that already ran both
branches correctly. No second Modern/Pioneer/Standard-legal printing of this
reader's own "mill/discard ... if a <quality> card was <moved> this way, X.
Otherwise, Y." template exists on Scryfall either (checked with a full-text
search this session: `o:"this way" o:otherwise`, `o:milled o:otherwise`,
`o:discarded o:otherwise` and several verb/tense variants all return either
nothing else or only the not-legal-everywhere Predict) - generality is instead
proven by the reader's own regex still handling Vohar's and Liliana's two
verbs, two condition phrasings and two quality kinds with no "Otherwise" at
all, unaffected by this fix.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 608.2c** - the instructions are followed in order, so the condition
  looks at what the first sentence actually moved; later text (the
  "Otherwise" sentence) modifies the meaning of earlier text rather than
  being an independent instruction.
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


def _lorehold_excavation(library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lorehold Excavation"], library=list(library))
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.resolve_top()  # the end-step mill trigger
    return scenario


def test_a_land_milled_this_way_gains_life_instead_of_the_otherwise_branch():
    scenario = _lorehold_excavation(["Swamp", "Swamp"])

    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 20


def test_a_nonland_milled_this_way_runs_the_otherwise_branch_instead():
    scenario = _lorehold_excavation(["Lightning Bolt", "Swamp"])

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 19
