"""Scenario: "Whenever a permanent [you control] is turned face up, ..."
(CR 702.37e, CR 708.8) - a *general* trigger that watches every permanent
turned face up, not only the source's own morph/manifest, read off the
condition the same way every other trigger-event branch in
`machines/triggers.py` reads its own "mine" (self-referential) vs. general
split.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Mastery of the Unseen** (the follow-up's own named card): "Whenever a
  permanent you control is turned face up, you gain 1 life for each
  creature you control." - controller-filtered.
- **Aven Farseer** (off-pool, proves the parser generalises rather than
  reading Mastery of the Unseen's exact sentence): "Whenever a permanent is
  turned face up, put a +1/+1 counter on this creature." - no controller
  word at all, so CR 608.2's own default ("nothing named, nothing
  required") applies: it fires for *anybody's* permanent turning face up,
  including an opponent's.
- **Brine Elemental** is the face-down permanent both tests turn face up
  (Morph {5}{U}{U}), the same real printing `tests/scenarios/test_morph.py`
  already exercises for the self-referential case this file does not repeat.

CR 603.1: "Whenever an event or game state matches a triggered ability's
trigger condition, that ability automatically triggers." The bug this fixes:
`TriggerEvent.TURNED_FACE_UP`'s branch unconditionally required
`event.subject_id == source.id`, so a non-self-referential condition like
Mastery of the Unseen's own could never see any event fire, because the
`mine` check it was ANDed with was already `False` and the branch never
consulted the condition's actual wording after that.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _cast_face_down(scenario, name: str, *mana_sources, username: str | None = None):
    casting = scenario.cast(name, username=username)
    casting.use_keyword("Morph")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *mana_sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_mastery_of_the_unseen_gains_life_when_another_permanent_turns_face_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Brine Elemental"],
            battlefield=["Mastery of the Unseen"] + ["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    morph_mana = scenario.untapped_sources(*["Island"] * 3)
    brine = _cast_face_down(scenario, "Brine Elemental", *morph_mana)
    assert brine.name != "Brine Elemental"  # face down (CR 708.2)

    alice_life_before = scenario.player("alice").life
    face_up_mana = scenario.untapped_sources(*["Island"] * 7)
    scenario.turn_face_up(brine, *face_up_mana)
    while scenario.game.stack:
        scenario.resolve_top()

    assert brine.name == "Brine Elemental"
    # One creature controlled (Brine Elemental itself): +1 life.
    assert scenario.player("alice").life == alice_life_before + 1


def test_off_pool_aven_farseer_grows_when_an_opponents_permanent_turns_face_up():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aven Farseer"])
        .player("bob", hand=["Brine Elemental"], battlefield=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    morph_mana = scenario.untapped_sources(*["Island"] * 3, username="bob")
    brine = _cast_face_down(scenario, "Brine Elemental", *morph_mana, username="bob")

    farseer = scenario.creature("Aven Farseer", "alice")
    assert farseer.counters[Counter.PLUS_ONE] == 0

    face_up_mana = scenario.untapped_sources(*["Island"] * 7, username="bob")
    scenario.turn_face_up(brine, *face_up_mana, username="bob")
    while scenario.game.stack:
        scenario.resolve_top()

    assert brine.name == "Brine Elemental"
    assert farseer.counters[Counter.PLUS_ONE] == 1
