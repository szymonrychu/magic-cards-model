"""Token copies with CR 707.9b's "except ... isn't legendary" exception - The
Notary Hobbits: "When The Notary Hobbits enter, if they're not a token,
create two tokens that are copies of them, except the tokens aren't
legendary."

CR 707.9b: a copy effect that modifies a characteristic as part of copying
makes the modified value part of the copy's copiable values - so each token
is a nonlegendary "The Notary Hobbits", and the legend rule (CR 704.5j)
never compares it with the legendary original. CR 603.4: the intervening
"if they're not a token" is checked as the ability triggers and as it
resolves, so a token copy entering does not make more copies.

Off-set proofs, not in any deck list:

- Impostor Syndrome: "Whenever a nontoken creature you control deals combat
  damage to a player, create a token that's a copy of it, except it isn't
  legendary." - "it" is the creature that dealt the damage, not the
  enchantment.
- Multiversal Incursion: "For each nontoken creature you control, create a
  token that's a copy of that creature, except it isn't legendary."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype

from .harness import Scenario

HOBBITS = "The Notary Hobbits"


def _named(scenario, name):
    return [card for card in scenario.game.battlefield if card.name == name]


def _legendary(scenario, permanent):
    return Supertype.LEGENDARY in scenario.game.computed_board().of(permanent).supertypes


def test_the_notary_hobbits_make_two_nonlegendary_copies():
    scenario = Scenario().player("alice", hand=[HOBBITS]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    original = scenario.put_onto_battlefield(HOBBITS, "alice")
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    hobbits = _named(scenario, HOBBITS)
    assert len(hobbits) == 3
    tokens = [card for card in hobbits if card.token]
    assert len(tokens) == 2
    assert original.zone is Zone.BATTLEFIELD
    assert _legendary(scenario, original)
    for token in tokens:
        assert not _legendary(scenario, token)
        chars = scenario.game.computed_board().of(token)
        assert "Halfling" in chars.subtypes
        assert (chars.power, chars.toughness) == (1, 1)


def test_the_token_copies_do_not_copy_themselves_again():
    """Each token has the same ETB, but "if they're not a token" is false
    for it - exactly two tokens, not an endless chain."""
    scenario = Scenario().player("alice", hand=[HOBBITS]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(HOBBITS, "alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert scenario.game.stack == []
    assert len([card for card in _named(scenario, HOBBITS) if card.token]) == 2


def test_the_copies_still_come_if_the_original_left_first():
    """CR 608.2h: an object no longer where the effect expects it is read by
    its last known information - the trigger is already on the stack, and
    the copies are of the Hobbits as they last existed."""
    scenario = Scenario().player("alice", hand=[HOBBITS]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    original = scenario.put_onto_battlefield(HOBBITS, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack

    scenario.game.destroy(original)
    scenario.pass_until_resolved()

    tokens = [card for card in _named(scenario, HOBBITS) if card.token]
    assert len(tokens) == 2
    assert all(not _legendary(scenario, token) for token in tokens)


def test_a_second_nontoken_notary_hobbits_is_still_subject_to_the_legend_rule():
    """Only the tokens lost "legendary"; two legendary originals still meet
    the legend rule (CR 704.5j)."""
    scenario = (
        Scenario().player("alice", hand=[HOBBITS], battlefield=[HOBBITS]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(HOBBITS, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.state_based_actions()

    originals = [card for card in _named(scenario, HOBBITS) if not card.token]
    assert len(originals) == 1


# -- Impostor Syndrome (off-set proof) --------------------------------------


def test_impostor_syndrome_copies_the_creature_that_dealt_the_damage_nonlegendary():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Impostor Syndrome", "Galion, Elvenking's Butler"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    galion = scenario.creature("Galion, Elvenking's Butler", "alice")
    scenario.choose_trigger_targets("Galion, Elvenking's Butler", [])
    scenario.attack_with(galion)
    scenario.pass_until_resolved()  # Galion's own attack trigger, no target
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()  # Impostor Syndrome
    scenario.state_based_actions()

    galions = _named(scenario, "Galion, Elvenking's Butler")
    assert len(galions) == 2
    token = next(card for card in galions if card.token)
    assert not _legendary(scenario, token)
    assert galion.zone is Zone.BATTLEFIELD
    assert _named(scenario, "Impostor Syndrome")  # the enchantment was not copied


def test_impostor_syndrome_ignores_noncombat_damage():
    """ "deals combat damage" - a nontoken creature's noncombat hit on a player
    makes no copy."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Impostor Syndrome", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.deal_damage(scenario.player("bob"), 1, source=bears)

    assert scenario.pending_triggers == []
    assert len(_named(scenario, "Grizzly Bears")) == 1


# -- Multiversal Incursion (off-set proof) ----------------------------------


def test_multiversal_incursion_copies_each_nontoken_creature_once():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Multiversal Incursion"],
            battlefield=[*["Island"] * 7, "Galion, Elvenking's Butler", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Multiversal Incursion", *scenario.untapped_sources(*["Island"] * 7))
    scenario.state_based_actions()

    galions = _named(scenario, "Galion, Elvenking's Butler")
    bears = _named(scenario, "Grizzly Bears")
    assert len(galions) == 2
    assert len(bears) == 2
    assert all(not _legendary(scenario, card) for card in galions if card.token)
    assert len(_named(scenario, "Hill Giant")) == 1  # bob's creature is not "you control"
