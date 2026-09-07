"""Scenario: CR 702.47's splice, as a `CAST` cast option (`legal_actions`).

`machines/legal_actions.py` names five "one entry per cast option" shapes in
CR 601.2's own enumeration: pitch costs, adventures, split halves, MDFC land
faces, and splice. The first four are alternative *ways to cast the same
card* - one `Action` per alternative, mutually exclusive (`spell_face`/
`alternative_cost` each name which). Splice is not that shape at all, and CR
702.47b is explicit about why: "If you're splicing more than one card onto a
spell, reveal them all at once and choose the order in which their effects
will happen" - several splice cards can apply to the *same* cast, so it is a
candidate pool a caller chooses a subset from, the same "parameter space, not
an enumeration" treatment `Action.modes` already gives a modal spell's
bullets, not a family of mutually exclusive `Action`s the way `spell_face`
is.

CR 702.47a (`mise run rules:find 702.47`, verified this session): "Splice is
a static ability that functions while a card is in your hand. 'Splice onto
[quality] [cost]' means 'You may reveal this card from your hand as you cast
a [quality] spell. If you do, that spell gains the text of this card's rules
text and you pay [cost] as an additional cost to cast that spell.'"

`machines/casting.py`'s `CastingStep.splice(name)` already implements the
whole mechanic end to end (revealing, the CR 702.47c text-changing effect,
folding the splice cost into `additional_costs`) - this file's own defect is
narrower: `legal_actions` never told a caller such a thing was possible at
all. `Action.splice_options` (new) and `casting.splice_candidates` (new) are
what this file exercises; nothing about `Casting.splice` itself changes.

Desperate Ritual ("Splice onto Arcane {1}{R}") and Lava Spike (a plain
Arcane sorcery, no splice ability of its own) are the real printings
(`tests/fixtures/cards/desperate_ritual.json`, `lava_spike.json`) - both
already in the fixture pool, so no `add_card.py` run was needed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import Action, ActionKind

from .harness import Scenario


def _casts(actions: list[Action]) -> list[Action]:
    return [action for action in actions if action.kind is ActionKind.CAST]


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_splice_option_names_the_matching_arcane_card_in_hand():
    """Lava Spike (Arcane sorcery, no splice of its own) with Desperate
    Ritual (Splice onto Arcane {1}{R}) in the same hand: Lava Spike's plain
    `CAST` action lists Desperate Ritual as a splice candidate, at its own
    printed cost - a pool, not a substitute for Lava Spike's own `{R}`."""
    scenario = Scenario().player("alice", hand=["Lava Spike", "Desperate Ritual"]).build()
    _to_main(scenario)
    ritual = scenario.find("Desperate Ritual", Zone.HAND, "alice")

    (spike_cast,) = [
        action
        for action in _casts(legal_actions(scenario.game, "alice"))
        if scenario.game.find_by_id(action.card_id).name == "Lava Spike"
    ]

    assert len(spike_cast.splice_options) == 1
    (option,) = spike_cast.splice_options
    assert option.card_id == ritual.id
    assert option.cost == "{1}{R}"
    # splicing is optional, so Lava Spike's own reported cost is untouched.
    assert spike_cast.mana_cost == "{R}"


def test_splice_option_excludes_a_non_matching_quality_and_never_offers_self():
    """Grizzly Bears is neither Arcane nor an instant or sorcery, so
    Desperate Ritual's splice ability does not match it (CR 702.47a's own
    "[quality]"). And Desperate Ritual can never splice onto its own cast -
    it would have to be revealed from hand while it is the card leaving
    hand for the stack."""
    scenario = Scenario().player("alice", hand=["Grizzly Bears", "Desperate Ritual"]).build()
    _to_main(scenario)

    (bears_cast,) = [
        action
        for action in _casts(legal_actions(scenario.game, "alice"))
        if scenario.game.find_by_id(action.card_id).name == "Grizzly Bears"
    ]
    assert bears_cast.splice_options == ()

    (ritual_cast,) = [
        action
        for action in _casts(legal_actions(scenario.game, "alice"))
        if scenario.game.find_by_id(action.card_id).name == "Desperate Ritual"
    ]
    assert ritual_cast.splice_options == ()


def test_splicing_lava_spike_adds_desperate_rituals_text_and_pays_its_cost():
    """The direct demonstration: cast the `Action` the previous test found,
    for real, and show the engine does what it advertised - CR 702.47c's
    text-changing effect actually lands on the resolved spell, and CR
    702.47a's additional cost is actually paid (`{R}` for Lava Spike plus
    `{1}{R}` splice = `{1}{R}{R}`, three mana with at least two red)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lava Spike", "Desperate Ritual"], battlefield=["Mountain"] * 3)
        .player("bob")
        .build()
    )
    _to_main(scenario)
    ritual = scenario.find("Desperate Ritual", Zone.HAND, "alice")

    (spike_cast,) = [
        action
        for action in _casts(legal_actions(scenario.game, "alice"))
        if scenario.game.find_by_id(action.card_id).name == "Lava Spike"
    ]
    (option,) = spike_cast.splice_options
    assert option.card_id == ritual.id

    spike = scenario.find("Lava Spike", Zone.HAND, "alice")
    casting = Casting(spell=spike, caster="alice", origin_zone=Zone.HAND, game=scenario.game)
    casting.choose_targets(["bob"])
    casting.splice(ritual.name)
    payment = casting.determine_cost()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    resolving = scenario.put_on_stack(casting)

    assert resolving.spliced_text == ("Add {R}{R}{R}.",)
    assert ritual.zone is Zone.HAND, "CR 701.20a: revealed, never moved"

    bob = scenario.game.player("bob")
    life_before = bob.life
    scenario.resolve_top()
    assert bob.life == life_before - 3, "Lava Spike's own printed effect still ran"
