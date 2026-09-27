"""Three keyword grants gated on something other than an ordinary "you
control" subject:

- **Lavaleaper** - "All creatures have haste." CR 613.1f's grant to *every*
  creature on the battlefield, both players' alike - the one shape in
  `machines/layers.py`'s whole anthem family whose subject names no
  controller at all. `EveryCreature` (`every_creature`) already existed for
  "other creatures are `<type>`"; `_ALL_CREATURES_KEYWORD_GRANT_RE` is the new
  reader that hands a keyword grant to it. **Smoke Bomb** (proof printing,
  Modern-legal, not a listed card, not in any `decks/*.txt`) proves the
  reader past Lavaleaper's own "haste": identical sentence, a different
  keyword ("shroud"), so this is not merely re-confirming the one word the
  reader was built against.
- **Adept Watershaper** - "Other tapped creatures you control have
  indestructible." `TappedCreaturesControlledBy` (`machines/layers.py`) reads
  a snapshot of tapped ids off `LayerContext.tapped_ids`
  (`Game._compute_board`'s own read of `CardState.tapped`) the identical way
  `AttackingGroupControlledBy` already reads `LayerContext.attacking` - a
  creature stops being selected the instant it untaps. **Saryth, the Viper's
  Fang** (proof printing, Modern/Pioneer-legal) proves it with a different
  keyword ("deathtouch").
- **Illusion Spinners** - "This creature has hexproof as long as it's
  untapped." Read straight off `CardState.tapped` at build time
  (`_context_gated_self_static_builder`), the identical live-recompute choice
  `_SELF_MONSTROUS_GATED_RE`'s sibling already makes for `source.monstrous`.
  No second Modern/Pioneer/Standard-legal printing of this exact self-line
  was found this session (Scryfall search, dated MEMORY.md line) - Giant's
  Amulet prints the identical sentence but only as a *quoted* grant inside
  another static ("Equipped creature ... has '...'"), and this engine does
  not yet re-derive a fresh continuous effect from a granted ability's own
  quoted text (a separate, larger gap than this task's own scope), so it
  cannot stand in as a functional proof.

CR numbers verified this session with `mise run rules:find`:

- **CR 613.1f** - layer 6: ability-adding and ability-removing effects.
- **CR 110.5** - a permanent's tapped/untapped status.
- **CR 702.11b** - hexproof: can't be the target of an opponent's spells or
  abilities.
- **CR 702.12b** - indestructible: can't be destroyed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from tests.scenarios.harness import Scenario

# -- Lavaleaper: "All creatures have haste." -----------------------------------


def test_all_creatures_have_haste_including_an_opponents():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lavaleaper"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    lavaleaper = scenario.creature("Lavaleaper", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    assert has_keyword(lavaleaper, Keyword.HASTE, scenario.game), "the source itself, too"
    assert has_keyword(bears, Keyword.HASTE, scenario.game), "an opponent's creature as well"


def test_haste_is_gone_once_lavaleaper_leaves():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lavaleaper"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(scenario.creature("Lavaleaper", "alice"))

    assert not has_keyword(bears, Keyword.HASTE, scenario.game)


def test_smoke_bomb_off_pool_proof_grants_shroud_to_every_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Smoke Bomb"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.game.shroud_refusal(bears) is not None, "every creature has shroud"


# -- Adept Watershaper: "Other tapped creatures you control have -------------
# -- indestructible." ---------------------------------------------------------


def test_other_tapped_creatures_get_indestructible_but_untapped_ones_do_not():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Adept Watershaper", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    watershaper = scenario.creature("Adept Watershaper", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears.tap()

    assert is_indestructible(bears, scenario.game), "tapped - other creature"
    assert not is_indestructible(giant, scenario.game), "untapped"
    assert not is_indestructible(watershaper, scenario.game), '"other" excludes the source itself'


def test_indestructibility_is_gone_the_instant_a_creature_untaps():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Adept Watershaper", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears.tap()
    assert is_indestructible(bears, scenario.game)

    bears.untap()
    assert not is_indestructible(bears, scenario.game), "CR 611.3a: re-asked live, not locked in"


def test_saryth_off_pool_proof_grants_deathtouch_to_other_tapped_creatures():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Saryth, the Viper's Fang", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears.tap()

    assert has_keyword(bears, Keyword.DEATHTOUCH, scenario.game)


# -- Illusion Spinners: "This creature has hexproof as long as it's ----------
# -- untapped." ----------------------------------------------------------------


def test_illusion_spinners_has_hexproof_only_while_untapped():
    scenario = Scenario().player("alice", battlefield=["Illusion Spinners"]).player("bob").build()
    spinners = scenario.creature("Illusion Spinners", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.hexproof_refusal(spinners, "bob", None) is not None, "untapped - hexproof"

    spinners.tap()
    assert scenario.game.hexproof_refusal(spinners, "bob", None) is None, "tapped - no hexproof"

    spinners.untap()
    assert scenario.game.hexproof_refusal(spinners, "bob", None) is not None, "untapped again"
