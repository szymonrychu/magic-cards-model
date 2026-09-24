"""Connive: CR 701.50, the keyword action, in every position it is printed.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 701.50a** - "Certain spells and abilities instruct a permanent to
  connive. To do so, that permanent's controller draws a card, then discards a
  card. If a nonland card is discarded this way, that player puts a +1/+1
  counter on the conniving permanent."
- **CR 701.50b** - "If a permanent is no longer on the battlefield as an effect
  instructs it to connive, its last known information is used to determine
  which object connived and who controlled it." Its controller still draws and
  discards; there is no permanent left to put the counter on.
- **CR 701.50f** - it "connives" after the process is complete "even if some
  or all of those actions were impossible" - an empty library still discards.
- **CR 603.2h** - "Do this only once each turn": the ability "triggers only if
  its source's controller has not yet taken the indicated action that turn".
- **CR 602.5d** - "Activate only as a sorcery" is the sorcery timing rule.

The connive reader is `machines/connive.py`'s `parse_connive_clause`, one
template for every subject a card prints in front of "connives": the ability's
own source by pronoun ("it", "he", "she") or by name, the object the trigger
event named ("another Villain ... enters, you may have it connive", "an
equipped creature ... attacks, it connives"), and a target ("target creature
you control", "target Villain you control", "up to one target creature you
control").

Proof printings, none of them a listed Marvel card and none in
`magic-cards-model-api/decks/*.txt`, legality and oracle text checked with
Scryfall on 2026-09-24:

- Hypnotic Grifter (Modern, Pioneer) - "{3}: This creature connives.", an
  activated self-connive with a mana cost and no timing restriction.
- Mob Lookout (Modern, Pioneer, Standard) - "When this creature enters, target
  creature you control connives.", a targeted trigger.
- Doc Ock's Henchmen (Modern, Pioneer, Standard) - "Whenever this creature
  attacks, it connives.".
- Unstable Experiment (Modern, Pioneer, Standard) - "Target player draws a
  card, then up to one target creature you control connives.", a spell.
- Psionic Snoop (Modern, Pioneer) - "When this creature enters, it connives."
  cast at instant speed with flash.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _settle(scenario) -> None:
    """Resolve everything on the stack, including whatever triggers on the way."""
    for _ in range(20):
        if scenario.game.stack_is_empty and not scenario.pending_triggers:
            return
        scenario.pass_until_resolved()


def _names(cards) -> list[str]:
    return [state.card.name for state in cards]


def _plus_ones(state) -> int:
    return state.counter_count(Counter.PLUS_ONE)


# --------------------------------------------------------------------------
# The keyword action itself (CR 701.50a), off an enters trigger
# --------------------------------------------------------------------------


def _scientists(library: list[str], hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=library,
            hand=["A.I.M. Scientists", *(hand or [])],
            battlefield=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_discarding_a_nonland_card_puts_a_counter_on_the_conniver():
    """CR 701.50a's happy path: draw the Bolt, discard it, +1/+1 counter."""
    scenario = _scientists(["Lightning Bolt", "Island"])
    bolt = scenario.top_of_library(1)[0]
    scenario.will_discard(bolt)

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    _settle(scenario)

    scientists = scenario.creature("A.I.M. Scientists", "alice")
    assert _plus_ones(scientists) == 1
    assert scenario.game.power_of(scientists) == 4
    assert bolt.zone is Zone.GRAVEYARD
    assert _names(scenario.player("alice").library) == ["Island"]


def test_discarding_a_land_card_puts_no_counter():
    """The counter is conditional on a *nonland* card - a land discard adds none."""
    scenario = _scientists(["Island", "Lightning Bolt"])
    island = scenario.top_of_library(1)[0]
    scenario.will_discard(island)

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    _settle(scenario)

    scientists = scenario.creature("A.I.M. Scientists", "alice")
    assert _plus_ones(scientists) == 0
    assert scenario.game.power_of(scientists) == 3
    assert island.zone is Zone.GRAVEYARD


def test_the_controller_may_discard_a_card_other_than_the_one_drawn():
    """The discard is any card in hand: keep the drawn Bolt, pitch an old Forest."""
    scenario = _scientists(["Lightning Bolt"], hand=["Forest"])
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_discard(forest)

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    _settle(scenario)

    scientists = scenario.creature("A.I.M. Scientists", "alice")
    assert _plus_ones(scientists) == 0
    assert forest.zone is Zone.GRAVEYARD
    assert _names(scenario.player("alice").hand) == ["Lightning Bolt"]


def test_an_empty_library_still_discards_and_can_still_grow():
    """CR 701.50f: the draw is impossible, the discard is not - it still connives."""
    scenario = _scientists([], hand=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    scenario.pass_priority()  # the enters trigger goes on the stack
    scientists = scenario.creature("A.I.M. Scientists", "alice")
    scenario.resolve_top()  # resolved, and no state-based check has run yet

    assert bolt.zone is Zone.GRAVEYARD
    assert _plus_ones(scientists) == 1
    assert scenario.player("alice").tried_to_draw_from_empty_library is True


def test_the_discard_is_asked_of_the_conniving_permanents_controller():
    """Exactly one discard question, put to alice, sized one card."""
    scenario = _scientists(["Lightning Bolt"])

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    _settle(scenario)

    discards = [q for q in scenario.questions_asked() if q.prompt.startswith("discard")]
    assert len(discards) == 1
    assert discards[0].player == "alice"
    assert discards[0].amount == 1


def test_a_conniver_gone_before_resolution_still_draws_and_discards():
    """CR 701.50b: its last known information says it connived and who controlled it.

    Red Room Recruit's enters trigger is on the stack when the Recruit is
    destroyed. Its controller still draws and discards; the counter has no
    permanent to go on, and the card in the graveyard is a new object
    (CR 400.7) that gets none either.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"],
            hand=["Red Room Recruit"],
            battlefield=["Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Red Room Recruit", auto=True)
    scenario.pass_priority()  # the enters trigger goes on the stack
    recruit = scenario.find("Red Room Recruit", Zone.BATTLEFIELD, "alice")
    assert scenario.stack_names() == ["Red Room Recruit's triggered ability"]
    scenario.game.destroy(recruit)

    scenario.resolve_top()

    alice = scenario.player("alice")
    assert _names(alice.graveyard) == ["Red Room Recruit", "Lightning Bolt"]
    graveyard_recruit = scenario.find("Red Room Recruit", Zone.GRAVEYARD, "alice")
    assert _plus_ones(graveyard_recruit) == 0


# --------------------------------------------------------------------------
# Every subject form
# --------------------------------------------------------------------------


def test_she_connives_names_the_source():
    """Madame Masque: "When Madame Masque enters, she connives." """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"],
            hand=["Madame Masque"],
            battlefield=["Swamp"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Madame Masque", auto=True)
    _settle(scenario)

    masque = scenario.creature("Madame Masque", "alice")
    assert _plus_ones(masque) == 1


def test_he_connives_when_kang_attacks():
    """Kang, Temporal Tyrant: "Whenever Kang attacks, he connives." """
    scenario = (
        Scenario()
        .player("alice", library=["Lightning Bolt"], battlefield=["Kang, Temporal Tyrant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kang = scenario.creature("Kang, Temporal Tyrant", "alice")
    scenario.attack_with(kang)
    _settle(scenario)

    assert _plus_ones(kang) == 1
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def _zemo_board(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Lightning Bolt"],
            hand=hand,
            battlefield=["Baron Helmut Zemo", "Swamp", "Mountain", "Swamp"],
        )
        .player("bob", life=40)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_casting_a_black_spell_from_hand_makes_zemo_connive():
    """Baron Helmut Zemo: "Whenever you cast a black spell from your hand,
    Baron Helmut Zemo connives." - the printed name is the source."""
    scenario = _zemo_board(["Duress"])
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_onto_stack("Duress", swamp, targets=["bob"])
    _settle(scenario)

    zemo = scenario.creature("Baron Helmut Zemo", "alice")
    assert _plus_ones(zemo) == 1


def test_casting_a_red_spell_does_not_make_zemo_connive():
    scenario = _zemo_board(["Lightning Bolt"])
    mountain = scenario.untapped_sources("Mountain")[0]
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    _settle(scenario)

    zemo = scenario.creature("Baron Helmut Zemo", "alice")
    assert _plus_ones(zemo) == 0
    assert _names(scenario.player("alice").library) == ["Lightning Bolt", "Lightning Bolt"]


def _strucker_board(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
            hand=hand,
            battlefield=["Baron Strucker, HYDRA Overlord"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_strucker_may_have_the_entering_villain_connive():
    """Baron Strucker: "Whenever another Villain you control enters, you may
    have it connive." - "it" is the Villain that entered, so the counter lands
    on Kang, not on Strucker."""
    scenario = _strucker_board(["Kang, Temporal Tyrant"])
    scenario.will_take_the_may(True)

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    _settle(scenario)

    kang = scenario.creature("Kang, Temporal Tyrant", "alice")
    strucker = scenario.creature("Baron Strucker, HYDRA Overlord", "alice")
    assert _plus_ones(kang) == 1
    assert _plus_ones(strucker) == 0


def test_strucker_declined_draws_nothing():
    scenario = _strucker_board(["Kang, Temporal Tyrant"])
    scenario.will_take_the_may(False)

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    _settle(scenario)

    kang = scenario.creature("Kang, Temporal Tyrant", "alice")
    assert _plus_ones(kang) == 0
    assert len(scenario.player("alice").library) == 3


def test_strucker_connives_only_once_each_turn():
    """CR 603.2h: once the Villain has connived, the next Villain this turn
    does not trigger Strucker at all."""
    scenario = _strucker_board(["Kang, Temporal Tyrant", "Baron Helmut Zemo"])
    scenario.will_take_the_may(True, times=None)

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    _settle(scenario)
    scenario.put_onto_battlefield("Baron Helmut Zemo", "alice")
    _settle(scenario)

    zemo = scenario.creature("Baron Helmut Zemo", "alice")
    assert _plus_ones(zemo) == 0
    assert len(scenario.player("alice").library) == 2


def test_strucker_declined_once_can_still_connive_later_that_turn():
    """CR 603.2h reads the *action taken*, not the trigger: declining the first
    "you may" leaves the once-each-turn action untaken, so the next Villain
    triggers Strucker again."""
    scenario = _strucker_board(["Kang, Temporal Tyrant", "Baron Helmut Zemo"])
    scenario.will_take_the_may(False)

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    _settle(scenario)
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Baron Helmut Zemo", "alice")
    _settle(scenario)

    zemo = scenario.creature("Baron Helmut Zemo", "alice")
    assert _plus_ones(zemo) == 1


def test_strucker_ignores_a_non_villain():
    scenario = _strucker_board(["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _settle(scenario)

    assert len(scenario.player("alice").library) == 3


def _leader_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Lightning Bolt", "Island"],
            battlefield=["Leader, Super-Genius", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_leader_makes_a_target_creature_connive_at_the_beginning_of_combat():
    """Leader, Super-Genius: "At the beginning of combat on your turn, target
    creature you control connives." - the target gets the counter. Leader's
    own replacement also applies (see test_connive_replacement.py), so alice
    draws two and discards one."""
    scenario = _leader_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears)
    bolt = scenario.player("alice").library[1]
    scenario.will_discard(bolt)

    scenario.advance()
    _settle(scenario)

    assert _plus_ones(bears) == 1
    assert _plus_ones(scenario.creature("Leader, Super-Genius", "alice")) == 0


def _swordsman_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Swordsman, Sharp Scoundrel", "Grizzly Bears", "Bonesplitter"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_equipped_attacker_connives():
    """Swordsman: "Whenever an equipped creature you control attacks, it
    connives." - "it" is the attacker, not Swordsman."""
    from magic_cards_model.machines.effects import attach_permanent

    scenario = _swordsman_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    attach_permanent(scenario.game, scenario.find("Bonesplitter", Zone.BATTLEFIELD), bears)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    _settle(scenario)

    assert _plus_ones(bears) == 1
    assert _plus_ones(scenario.creature("Swordsman, Sharp Scoundrel", "alice")) == 0


def test_an_unequipped_attacker_does_not_connive():
    scenario = _swordsman_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    _settle(scenario)

    assert _plus_ones(bears) == 0
    assert len(scenario.player("alice").library) == 2


# --------------------------------------------------------------------------
# Activated abilities
# --------------------------------------------------------------------------


def _modok_board():
    return (
        Scenario()
        .player("alice", library=["Lightning Bolt", "Lightning Bolt"], battlefield=["M.O.D.O.K."])
        .player("bob", library=["Island"])
        .build()
    )


def test_modok_pays_three_life_to_connive():
    """M.O.D.O.K.: "Pay 3 life: M.O.D.O.K. connives. Activate only during your turn." """
    scenario = _modok_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    modok = scenario.creature("M.O.D.O.K.", "alice")

    scenario.activate(modok, index=0)
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert _plus_ones(modok) == 1


def test_modok_cannot_connive_on_an_opponents_turn():
    scenario = _modok_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    modok = scenario.creature("M.O.D.O.K.", "alice")
    while scenario.game.active_player.username != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.why_cannot_activate(modok, 0, "alice") is not None
    assert scenario.player("alice").life == 20


def _hideout_board(extra: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Villainous Hideout", "Island", "Island", "Island", *extra],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hideout_makes_a_target_villain_connive():
    """Villainous Hideout: "{3}, {T}: Target Villain you control connives.
    Activate only as a sorcery." """
    scenario = _hideout_board(["Kang, Temporal Tyrant"])
    hideout = scenario.find("Villainous Hideout", Zone.BATTLEFIELD)
    kang = scenario.creature("Kang, Temporal Tyrant", "alice")

    scenario.activate(
        hideout, *scenario.untapped_sources("Island", "Island", "Island"), index=2, targets=[kang]
    )
    scenario.resolve_top()

    assert _plus_ones(kang) == 1


def test_hideout_cannot_target_a_creature_that_is_not_a_villain():
    scenario = _hideout_board(["Grizzly Bears"])
    hideout = scenario.find("Villainous Hideout", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError):
        scenario.activate(
            hideout,
            *scenario.untapped_sources("Island", "Island", "Island"),
            index=2,
            targets=[bears],
        )


def test_hideout_is_sorcery_speed():
    scenario = _hideout_board(["Kang, Temporal Tyrant"])
    scenario.advance()  # beginning of combat
    hideout = scenario.find("Villainous Hideout", Zone.BATTLEFIELD)
    assert "sorcery" in (scenario.why_cannot_activate(hideout, 2) or "")


# --------------------------------------------------------------------------
# A spell: Trickster's Stratagem's "Then up to one target creature you
# control connives." (the library half is test_owner_library_placement.py's)
# --------------------------------------------------------------------------


def _stratagem_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Island"],
            hand=["Trickster's Stratagem"],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Llanowar Elves"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_stratagem_makes_its_second_target_connive():
    scenario = _stratagem_board()
    elves = scenario.creature("Llanowar Elves", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.top_of_library(1, "alice")[0]
    scenario.will_discard(bolt)

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves, bears])

    assert _plus_ones(bears) == 1
    assert bolt.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.LIBRARY


def test_stratagem_with_no_creature_of_yours_chosen_connives_nothing():
    """ "Up to one" (CR 115.6): zero is a legal number of targets."""
    scenario = _stratagem_board()
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    assert _names(scenario.player("alice").library) == ["Lightning Bolt", "Island"]
    assert _plus_ones(scenario.creature("Grizzly Bears", "alice")) == 0


# --------------------------------------------------------------------------
# Proof printings (none of them listed cards)
# --------------------------------------------------------------------------


def test_proof_hypnotic_grifter_activated_self_connive():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"],
            battlefield=["Hypnotic Grifter", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grifter = scenario.creature("Hypnotic Grifter", "alice")

    scenario.activate(grifter, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.resolve_top()

    assert _plus_ones(grifter) == 1


def test_proof_mob_lookout_targets_another_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"],
            hand=["Mob Lookout"],
            battlefield=["Grizzly Bears", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears)

    scenario.cast_and_resolve("Mob Lookout", auto=True)
    _settle(scenario)

    assert _plus_ones(bears) == 1
    assert _plus_ones(scenario.creature("Mob Lookout", "alice")) == 0


def test_proof_doc_ocks_henchmen_connives_on_attack():
    scenario = (
        Scenario()
        .player("alice", library=["Island"], battlefield=["Doc Ock's Henchmen"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    henchmen = scenario.creature("Doc Ock's Henchmen", "alice")
    scenario.attack_with(henchmen)
    _settle(scenario)

    # The drawn Island is the only card to discard: no counter.
    assert _plus_ones(henchmen) == 0
    assert _names(scenario.player("alice").graveyard) == ["Island"]


def test_proof_unstable_experiment_spell_connive():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Lightning Bolt"],
            hand=["Unstable Experiment"],
            battlefield=["Grizzly Bears", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Unstable Experiment", auto=True, targets=["alice", bears])

    assert _plus_ones(bears) == 1
    assert len(scenario.player("alice").hand) == 1
    assert len(scenario.player("alice").graveyard) == 2  # the spell and one discard


def test_proof_psionic_snoop_enters_and_connives():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt"],
            hand=["Psionic Snoop"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Psionic Snoop", auto=True)
    _settle(scenario)

    assert _plus_ones(scenario.creature("Psionic Snoop", "alice")) == 1
