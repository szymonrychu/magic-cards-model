"""Scenario: `Game.choose_trigger_targets`/`why_cannot_target_with_trigger`
can pre-declare the target of a CR 603.12 *reflexive* triggered ability -
the sub-ability an "`<action>`. When you do, `<consequence with a
target>`." (or "... this way, `<consequence>`.") sentence creates only once
the action has happened, not the target of the outer ability whose text
prints the sentence.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Earthbender Ascension** (the follow-up's own named card): "Landfall -
  Whenever a land you control enters, put a quest counter on this
  enchantment. When you do, if it has four or more quest counters on it,
  put a +1/+1 counter on target creature you control. It gains trample
  until end of turn." A *triggered* ability's own reflexive consequence.
- **Agatha's Soul Cauldron** (off-pool, proves the parser generalises
  rather than reading Earthbender Ascension's exact sentence, and across a
  different *kind* of parent ability): "{T}: Exile target card from a
  graveyard. When a creature card is exiled this way, put a +1/+1 counter
  on target creature you control." An *activated* ability's own reflexive
  consequence, using CR 603.12's other template ("... this way," rather
  than "When you do,").

CR 603.12: "Some triggered abilities are written, '[Do something]. When you
do, [effect].' ... the ability that instructs the action also creates a
second, reflexive triggered ability." CR 603.3d: the reflexive ability
chooses its own target, following CR 601.2c, when *it* goes on the stack -
a separate announcement from whatever text it was carved out of.

The bug this fixes: `profile_for_text(ability.text)` deliberately drops the
"When you do, ..."/"... this way, ..." tail (correctly - that target
belongs to the *reflexive* ability CR 603.12 creates later, not to the
outer trigger's own announcement), but nothing in
`Game.why_cannot_target_with_trigger` ever consulted the reflexive tail's
*own* targeting shape either, so `choose_trigger_targets` refused to record
any target for the reflexive half at all - a scenario could only supply it
through a live `DecisionKind.CHOOSE_TARGETS` question at resolution.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_earthbender_ascensions_reflexive_target_is_pre_declared_with_the_shortcut():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Earthbender Ascension", "Grizzly Bears"] + ["Forest"] * 3,
            hand=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ascension = scenario.find("Earthbender Ascension", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(ascension, "quest", 3)  # one land away from the threshold

    # The shortcut: name the card, not the (not-yet-created) reflexive ability.
    scenario.choose_trigger_targets("Earthbender Ascension", [bears])

    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()  # Landfall
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()  # the reflexive ability CR 603.12 creates
    scenario.pass_until_resolved()

    assert ascension.counters["quest"] == 4
    assert bears.counters[Counter.PLUS_ONE] == 1
    board = scenario.game.computed_board()
    assert "Trample" in board.of(bears).abilities


def test_off_pool_agathas_soul_cauldron_reflexive_target_is_pre_declared_too():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Agatha's Soul Cauldron", "Grizzly Bears"],
            graveyard=["Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cauldron = scenario.find("Agatha's Soul Cauldron", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")

    # The shortcut, again: the reflexive target for the second, "this way,"
    # ability - not Agatha's Soul Cauldron's own outer graveyard target.
    scenario.choose_trigger_targets("Agatha's Soul Cauldron", [bears])

    scenario.activate(cauldron, targets=[mystic])
    scenario.pass_until_resolved()  # the activated ability: exiles Elvish Mystic
    scenario.game.put_triggers_on_stack()  # the reflexive ability
    scenario.pass_until_resolved()

    assert mystic.zone is Zone.EXILE
    assert bears.counters[Counter.PLUS_ONE] == 1


def test_off_pool_agathas_soul_cauldron_refuses_an_illegal_reflexive_target():
    """ "target creature you control" - an opponent's creature is refused at
    announcement (CR 601.2c), the same recheck a legal target gets. Before
    this fix, `printed` only ever looked at *triggered* abilities, so
    Agatha's Soul Cauldron's activated ability contributed no profile at all
    and `choose_trigger_targets` accepted anything, silently."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Agatha's Soul Cauldron"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    try:
        scenario.choose_trigger_targets("Agatha's Soul Cauldron", [bears])
    except ValueError as refusal:
        assert "target creature" in str(refusal)
    else:
        raise AssertionError("an opponent's creature should have been refused")
