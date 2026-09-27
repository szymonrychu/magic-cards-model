"""Map (CR 111.10s) and the two riders this task owns that ride along with
tokens and searches, but that no existing reader's shape already covers:

- **The explore-keyword credit.** `PREDEFINED["Map"]` (`models/token.py`)
  and the ordinary "create ... token(s)" family already dispatched off it
  (`effects._parse_token_clause`'s bare-name branch, `effects.
  _parse_referent_clause`'s own token branch) are enough to make every card
  in this task's own pool actually create a working, exploring Map token -
  no new reader is needed for that half at all. What is missing is
  `support.py`'s own static credit for the Scryfall "Explore" keyword on a
  card whose *own* printed text never says "explores" anywhere outside a
  reminder parenthetical (Spyglass Siren's "When this creature enters,
  create a Map token." is the whole sentence; the explore clause lives on
  the token, not on the card). `credits_explore_via_created_token` reads
  that reminder the same structural way `effects._parse_create_named_
  permanent_token_clause` already does for real resolution - by finding a
  quoted ability inside a "(it's a[n] X with '...')"/"(they're Xs with
  '...')" parenthetical and checking *that* text for an explore clause -
  never by the card's own name.
- **Fabled Passage's own rider**: "Then if you control four or more lands,
  untap that land." - CR 611.2c's own magnitude, read only once the search
  has actually resolved and the found land has already entered (so the
  found land itself counts toward the threshold).
- **Magmatic Hellkite's own rider**: "Destroy target nonbasic land an
  opponent controls. Its controller searches their library for a basic
  land card, puts it onto the battlefield tapped[ with a stun counter on
  it], then shuffles." Read whole, ahead of `effects.split_effect_clauses`:
  that splitter cuts the second sentence apart at its own internal comma
  ("... tapped with a stun counter on it" / "then shuffles"), so `effects.
  _parse_anaphoric_clause_pair`'s own `clauses[index]`/`clauses[index + 1]`
  pairing can never see the whole rider - the identical "read the paragraph
  whole" fix `effects._parse_destroy_then_amass_by_referent_then_draw_if_
  controlled_clause` already takes for Azog's own three-sentence rider.

Every rule number here was looked up this session with `mise run rules:find
<n>` against `.rules/MagicCompRules.txt` (effective 2026-09-25).

Registered additively into `machines/effects.py`'s existing dispatch chains
(`_ability_effect_or_notice`'s whole-text shapes, `_parse_mixed_clauses`'s
own whole-text-pair shapes) - this module is imported by `effects.py` at
module load, and, following `token_riders.py`'s own one-way rule, never
imports `effects` back at module load; any function here that needs one of
`effects`'s own private per-clause readers imports `effects` locally, inside
the function that needs it.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import Counter
from ..numbers import COUNT, parse_count

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, Player
    from .effects import AbilityEffect, TargetedClause


# --------------------------------------------------------------------------
# The explore-keyword credit (support.py's own static sweep, not gameplay)
# --------------------------------------------------------------------------

#: "(it's a[n] `<type>` with '`<ability>`'[ and '`<ability>`'])" or "(they're
#: `<type>`s with '`<ability>`')" - the same CR 111.4 reminder-parenthetical
#: shape `effects._CREATE_NAMED_PERMANENT_TOKEN_RE` reads structurally for a
#: real resolution, loosened here to only what this credit needs: the quoted
#: ability text(s) inside it, regardless of how many tokens the sentence in
#: front of it creates ("a Map token" singular, "two Map tokens" plural).
_TOKEN_REMINDER_ABILITIES_RE = re.compile(
    r"\((?:it'?s an? [a-z]+|they'?re [a-z]+s)(?: and [a-z]+s?)? with (?P<abilities>.+?)\)",
    re.IGNORECASE | re.DOTALL,
)
_QUOTED_ABILITY_SPAN_RE = re.compile(r'["“]([^"”]+)["”]')


def credits_explore_via_created_token(oracle_text: str) -> bool:
    """Whether `oracle_text` creates a token whose own reminder-spelled
    ability is CR 701.44a's explore clause - the credit for a card whose
    Scryfall "Explore" keyword names an ability that lives on the token it
    creates, not on its own printed sentence.

    Reads only the quoted ability text(s) inside a CR 111.4 reminder
    parenthetical, structurally - never the creating card's name. A future
    card that creates some other reminder-described token with a real
    explore ability reaches this the identical way Spyglass Siren does.
    """
    for reminder in _TOKEN_REMINDER_ABILITIES_RE.finditer(oracle_text or ""):
        for ability_text in _QUOTED_ABILITY_SPAN_RE.findall(reminder.group("abilities")):
            if _token_ability_text_explores(ability_text):
                return True
    return False


def _token_ability_text_explores(ability_text: str) -> bool:
    """One token's own printed ability ("{1}, {T}, Sacrifice this token:
    Target creature you control explores. Activate only as a sorcery."),
    stripped of its cost and CR 602.5d timing restriction the identical way
    `effects.activated_effect_for` already does for a real activation, then
    checked against `effects._parse_explores_clause` - imported locally, per
    this module's own one-way rule."""
    from . import effects  # noqa: PLC0415 - see module docstring: one-way import rule

    body = ability_text.split(":", 1)[-1] if ":" in ability_text else ability_text
    body = effects._TRAILING_ACTIVATION_TIMING_RESTRICTION_RE.sub("", body).strip()  # noqa: SLF001
    return effects._parse_explores_clause(body, for_spell=False) is not None  # noqa: SLF001


# --------------------------------------------------------------------------
# Fabled Passage: search, put tapped, shuffle, then a land-count-gated untap
# --------------------------------------------------------------------------

#: "Search your library for a basic land card, put it onto the battlefield
#: tapped, then shuffle. Then if you control `<n>` or more lands, untap that
#: land." - Fabled Passage's whole activated-ability effect text (its own
#: "{T}, Sacrifice this land:" cost is stripped before this ever sees it).
#: The nearest existing shape is `effects._SEARCH_PUT_BATTLEFIELD_TAPPED_
#: THEN_BEHOLD_UNTAP_RE` (Elven Passage's own "you may behold a `<quality>`.
#: if you do, untap that land."); this is the same search-and-conditional-
#: untap family with a board-count threshold in place of a behold.
_SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_COUNT_LANDS_UNTAP_RE = re.compile(
    r"^search (?:your|their) library for "
    rf"(?:(?P<n>{COUNT}) )?"
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r", put it onto the battlefield tapped, then shuffle\.\s*"
    rf"then if you control (?P<count>{COUNT}) or more lands, untap that land\.?$",
    re.IGNORECASE,
)


def parse_search_put_battlefield_tapped_then_count_lands_untap_clause(
    text: str,
) -> "AbilityEffect | None":
    """`_SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_COUNT_LANDS_UNTAP_RE`'s shape, or
    `None`. Registered additively in `effects._ability_effect_or_notice`'s
    own whole-text-shapes block, next to the behold-untap reader it mirrors.

    - **CR 701.23a** - the search itself; **CR 701.24a** - the shuffle.
    - **CR 611.2c** - the magnitude ("four or more lands") is read only once,
      right here, after the found land has already entered the battlefield
      (CR 608.2h): the just-fetched land counts toward its own threshold,
      the same way a real game reads it.
    """
    from . import effects  # noqa: PLC0415 - see module docstring: one-way import rule

    stripped = effects._strip_non_effect_preamble(text).strip()  # noqa: SLF001
    match = _SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_COUNT_LANDS_UNTAP_RE.fullmatch(stripped)
    if match is None:
        return None
    quality_text = (match.group("quality") or "").strip()
    if quality_text:
        base_matcher = effects._quality_matcher(quality_text)  # noqa: SLF001
    else:

        def base_matcher(state) -> bool:  # noqa: ANN001
            return True

    with_basic_land_type = bool(match.group("basic_land_type"))
    if with_basic_land_type:

        def search_matches(state, base=base_matcher):  # noqa: ANN001, ANN202
            return base(state) and effects._has_a_basic_land_type(state)  # noqa: SLF001
    else:
        search_matches = base_matcher
    n = parse_count(match.group("n")) if match.group("n") else 1
    threshold = parse_count(match.group("count"))
    if n is None or threshold is None:
        return None

    def effect(game: "Game", ability) -> None:  # noqa: ANN001
        controller = game.player(ability.controller)
        source = ability.source_name
        source_id = effects.source_id_of(ability)
        found = game.search_library(
            controller,
            search_matches,
            count=n,
            optional=False,
            shuffle=True,
            source=source,
            source_id=source_id,
        )
        if not found:
            return
        land = found[0]
        game.put_onto_battlefield(land, controller.username, tapped=True)
        count_lands = effects.count_expression("lands you control")
        if count_lands is not None and count_lands(game, controller.username) >= threshold:
            land.untap()

    return effect


# --------------------------------------------------------------------------
# Magmatic Hellkite: the mandatory, third-person "searches ... puts ...,
# then shuffles" referent clause
# --------------------------------------------------------------------------

#: "searches their library for a basic land card, puts it onto the
#: battlefield tapped[ with a stun counter on it], then shuffles." - the
#: subject ("its controller"/"that player") already stripped by the whole-
#: text destroy reader below before this ever sees `rest`, the identical
#: tail shape `effects._REFERENT_SEARCH_RE`'s own "may search ... put ..."
#: reads (Ghost Quarter, Boseiju) - but this verb is mandatory (no "may")
#: and third person, because CR 400.7's referent, not the caster, is the one
#: performing it.
#:
#: Read only from the *whole-paragraph* reader below, never through
#: `effects._parse_anaphoric_clause_pair`'s own `clauses[index]`/
#: `clauses[index + 1]` split: that splitter cuts this exact tail apart at
#: its own internal comma ("... tapped[ with a stun counter on it]" /
#: "then shuffles"), so a fragment-by-fragment match against it would never
#: see the whole rider - see the whole-text reader's own docstring below.
_REFERENT_SEARCH_MANDATORY_TAPPED_RE = re.compile(
    rf"^searches (?:your|their) library for "
    rf"(?:(?P<n>{COUNT}) )?"
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r", puts? (?:it|them) onto the battlefield tapped"
    r"(?P<stun> with a stun counter on it)?"
    r", then shuffles\.?$",
    re.IGNORECASE,
)


def _run_mandatory_search_tapped(
    game: "Game",
    player: "Player",
    search_matches,  # noqa: ANN001
    n: int,
    stun: bool,
    source: str,
    source_id: str | None,
) -> None:
    """CR 701.23a's search plus CR 122.1d's stun counter, shared by the
    referent-clause branch above and the whole-text destroy-then-search
    reader below - the same body either way, because it is CR 400.7's
    referent performing it, never the caster, in both shapes."""
    found = game.search_library(
        player,
        search_matches,
        count=n,
        optional=False,
        shuffle=True,
        source=source,
        source_id=source_id,
    )
    if not found:
        return
    land = found[0]
    game.put_onto_battlefield(land, player.username, tapped=True)
    if stun:
        land.add_counters(Counter.STUN, 1)


#: "Destroy target `<phrase>`. Its controller searches their library for a
#: basic land card, puts it onto the battlefield tapped[ with a stun counter
#: on it], then shuffles." - Magmatic Hellkite's whole trigger, read once as
#: one paragraph, ahead of `effects.split_effect_clauses`'s own comma-based
#: cut: that splitter breaks the second sentence apart at its own internal
#: comma ("... tapped with a stun counter on it" / "then shuffles"), which
#: is exactly why `effects._parse_anaphoric_clause_pair`'s `clauses[index]`/
#: `clauses[index + 1]` pairing alone can never see the whole rider - the
#: identical "read the paragraph whole, ahead of the splitter" fix `effects.
#: _parse_destroy_then_amass_by_referent_then_draw_if_controlled_clause`
#: already takes for Azog's own three-sentence rider.
_DESTROY_THEN_REFERENT_MANDATORY_SEARCH_TAPPED_RE = re.compile(
    r"^destroy (?P<phrase>.*target.+?)\.\s*"
    r"(?:its controller|that player) (?P<rest>searches (?:your|their) library for .+? "
    r"then shuffles)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_destroy_then_referent_mandatory_search_tapped_clause(
    text: str, *, for_spell: bool
) -> "TargetedClause | None":
    """`_DESTROY_THEN_REFERENT_MANDATORY_SEARCH_TAPPED_RE`'s shape, or
    `None`. Registered additively in `effects._parse_mixed_clauses`, among
    the other whole-text-pair shapes tried ahead of the ordinary splitter.

    - **CR 701.8a** - the destroy; **CR 701.23a** - the search;
      **CR 701.24a** - the shuffle.
    - **CR 608.2b/CR 400.7** - the referent's controller and identity are
      read off the target *before* `Game.destroy` moves it, the same order
      `effects._parse_anaphoric_clause_pair` already takes, and the search
      still runs even when the destroy itself fails to move a legal target
      (an indestructible nonbasic land) - the printed Beast Within ruling
      that pair reader's own docstring quotes.
    """
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from . import effects  # noqa: PLC0415 - see module docstring: one-way import rule

    whole = effects._strip_non_effect_preamble(text).strip()  # noqa: SLF001
    match = _DESTROY_THEN_REFERENT_MANDATORY_SEARCH_TAPPED_RE.fullmatch(whole)
    if match is None:
        return None
    if not effects._targets_understood(  # noqa: SLF001
        match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None
    search_match = _REFERENT_SEARCH_MANDATORY_TAPPED_RE.fullmatch(match.group("rest") + ".")
    if search_match is None:
        return None
    quality_text = (search_match.group("quality") or "").strip()
    if quality_text:
        base_matcher = effects._quality_matcher(quality_text)  # noqa: SLF001
    else:

        def base_matcher(state) -> bool:  # noqa: ANN001
            return True

    with_basic_land_type = bool(search_match.group("basic_land_type"))
    if with_basic_land_type:

        def search_matches(state, base=base_matcher):  # noqa: ANN001, ANN202
            return base(state) and effects._has_a_basic_land_type(state)  # noqa: SLF001
    else:
        search_matches = base_matcher
    n = parse_count(search_match.group("n")) if search_match.group("n") else 1
    if n is None:
        return None
    stun = bool(search_match.group("stun"))

    def effect(game: "Game", stack_object) -> None:  # noqa: ANN001
        source = stack_object.name if for_spell else stack_object.source_name
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        referent = game.controller_of(target)
        game.destroy(target)
        _run_mandatory_search_tapped(
            game, referent, search_matches, n, stun, source, effects.source_id_of(stack_object)
        )

    return effect
