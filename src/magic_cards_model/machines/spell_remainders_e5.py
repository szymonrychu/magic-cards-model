"""Spell sentences the clause splitter left as an unparsed remainder (EC7),
read here as a sequence of sentences each performed in printed order
(CR 608.2c): everything `_spell_effect_or_notice` already reads sentence by
sentence, plus the four sentence families below.

- **Several "up to one (other) target creature" sentences** (Dissection
  Practice, Hostile Takeover), each with its own pump or base power and
  toughness. CR 601.2c announces every target together in the order printed;
  CR 115.6 lets each "up to one" choose nothing; CR 608.2b skips a sentence
  whose target is gone and still performs the others.
- **"You may cast a spell with mana value N or less from your hand without
  paying its mana cost."** (the Expertise cycle). CR 608.2g: cast during
  resolution, no priority, the new spell above the resolving one; CR 118.9
  alternative cost; CR 608.2d the player may not choose an illegal option and
  may decline.
- **"You may search your library and/or graveyard for a card named X, reveal
  it, and put it into your hand. If you search your library this way,
  shuffle."** (Oko's Hospitality). CR 701.23a a search looks at a zone, and
  "and/or" is the player's choice of one zone or both; CR 701.24a the library
  is shuffled only when it was searched.
- **"Choose a <subtype> you control. Attach any number of Equipment you control
  to it."** (Armed and Armored). CR 608.2d the choice is made on resolution,
  not announcement; CR 701.3b attaching moves an Equipment off what it was on;
  CR 301.5 only a creature can be equipped.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..data.subtypes import canonical_subtype
from ..models.card import Type
from ..models.card_state import CardState, TargetKind
from ..models.zone import Zone
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import Effect

_Step = Callable[["Game", CardState], None]
#: Reads from `sentences[index]`; returns the step and how many sentences it used.
_Reader = Callable[[list[str], int], "tuple[_Step, int] | None"]

_THEN_PREFIX_RE = re.compile(r"^then\s+", re.IGNORECASE)

_SLOT_SENTENCE_RE = re.compile(
    r"^up to one (?:other )?target creature "
    r"(?:gets [+-]\d+/[+-]\d+|has base power and toughness \d+/\d+) until end of turn\.?$",
    re.IGNORECASE,
)

_FREE_CAST_RE = re.compile(
    r"^you may cast a spell with mana value (?P<limit>\d+) or less from your hand "
    r"without paying its mana cost\.?$",
    re.IGNORECASE,
)

_NAMED_SEARCH_RE = re.compile(
    r"^you may search your library and/or graveyard for a card named (?P<name>.+?), "
    r"reveal it, and put it into your hand\.?$",
    re.IGNORECASE,
)
_SHUFFLE_IF_SEARCHED_RE = re.compile(r"^if you search your library this way, shuffle\.?$", re.I)

_CHOOSE_ATTACH_RE = re.compile(r"^(?i:choose an?) (?P<subtype>[A-Z][a-z]+) you control\.?$")
_ATTACH_ANY_NUMBER_RE = re.compile(
    r"^attach any number of equipment you control to it\.?$", re.IGNORECASE
)

#: The zones an "and/or" search names, as the player's choice (CR 701.23a).
_LIBRARY, _GRAVEYARD, _BOTH = "library", "graveyard", "library and graveyard"


# --------------------------------------------------------------------------
# Several "up to one (other) target creature" sentences
# --------------------------------------------------------------------------


def _slot_step(sentence: str, slot: int) -> _Step:
    from .effects import continuous_effects, layer_context_for

    text = re.sub(r"^up to one (?:other )?target", "Target", sentence.strip(), flags=re.I)

    def creature_slot(game: Game, spell: CardState) -> None:
        refs = [t for t in spell.targets if t.kind is TargetKind.CARD]
        if slot >= len(refs):
            return  # CR 115.6: this "up to one" chose no target.
        target = game.legal_target(spell, refs[slot])
        if (
            not isinstance(target, CardState)
            or target.zone is not Zone.BATTLEFIELD
            or Type.CREATURE not in game.characteristics_of(target).types
        ):
            return  # CR 608.2b
        continuous_effects(game).create(
            spell,
            targets=[target],
            context=layer_context_for(game, game.controller_of(spell)),
            ability_text=text,
            game=game,
        )

    return creature_slot


# --------------------------------------------------------------------------
# "You may cast a spell with mana value N or less from your hand ..."
# --------------------------------------------------------------------------


def _free_cast_reader(sentences: list[str], index: int) -> tuple[_Step, int] | None:
    match = _FREE_CAST_RE.match(sentences[index].strip())
    if match is None:
        return None
    limit = int(match.group("limit"))

    def cast_from_hand_free(game: Game, spell: CardState) -> None:
        controller = game.controller_of(spell)
        caster = controller.username
        candidates = [
            card
            for card in controller.hand
            if game.can_cast_during_resolution(card, caster, mana_value_below=limit + 1)
        ]
        if not candidates:
            return  # CR 608.2d: nothing legal to choose.
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=caster,
                prompt=(
                    f"you may cast a spell with mana value {limit} or less from your hand "
                    "without paying its mana cost"
                ),
                source=spell.name,
                source_id=source_id_of(spell),
                amount=1,
                exact=False,
                cards=tuple(card.id for card in candidates),
                card_labels=tuple(card.name for card in candidates),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {card.id: card for card in candidates}
        picked = next((by_id[card_id] for card_id in chosen if card_id in by_id), None)
        if picked is None:
            return
        game.cast_during_resolution(
            picked,
            caster,
            source_name=f"{spell.name}'s free cast",
            rule="CR 608.2g",
            mana_value_below=limit + 1,
        )

    return cast_from_hand_free, 1


# --------------------------------------------------------------------------
# "You may search your library and/or graveyard for a card named X ..."
# --------------------------------------------------------------------------


def _named_search_reader(sentences: list[str], index: int) -> tuple[_Step, int] | None:
    match = _NAMED_SEARCH_RE.match(sentences[index].strip())
    if match is None:
        return None
    if index + 1 >= len(sentences) or not _SHUFFLE_IF_SEARCHED_RE.match(
        sentences[index + 1].strip()
    ):
        return None  # without its shuffle rider the sentence pair is not this shape
    name = match.group("name").strip()

    def search_library_and_or_graveyard(game: Game, spell: CardState) -> None:
        controller = game.controller_of(spell)
        player = controller.username
        if not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player,
                prompt=f"search your library and/or graveyard for a card named {name}",
                source=spell.name,
                source_id=source_id_of(spell),
            )
        ):
            return
        zones = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=player,
                prompt="which zones to search",
                source=spell.name,
                source_id=source_id_of(spell),
                options=(_BOTH, _LIBRARY, _GRAVEYARD),
                quality="zones to search",
            )
        )
        searched_library = zones in (_LIBRARY, _BOTH)
        candidates: list[CardState] = []
        if searched_library:
            candidates += [c for c in controller.library if c.name == name]
        if zones in (_GRAVEYARD, _BOTH):
            candidates += [c for c in controller.graveyard if c.name == name]
        if candidates:
            chosen = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player,
                    prompt=f"choose a card named {name}",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=1,
                    exact=False,
                    cards=tuple(c.id for c in candidates),
                    card_labels=tuple(c.name for c in candidates),
                    default_cards=(candidates[0].id,),
                )
            )
            assert isinstance(chosen, tuple)
            by_id = {c.id: c for c in candidates}
            found = next((by_id[i] for i in chosen if i in by_id), None)
            if found is not None:
                game.reveal(found, source=spell.name)
                controller.move(found, Zone.HAND)
        if searched_library:
            game.shuffle_library(controller)  # CR 701.24a

    return search_library_and_or_graveyard, 2


# --------------------------------------------------------------------------
# "Choose a Dwarf you control. Attach any number of Equipment you control to it."
# --------------------------------------------------------------------------


def _choose_and_attach_reader(sentences: list[str], index: int) -> tuple[_Step, int] | None:
    first = _CHOOSE_ATTACH_RE.match(sentences[index].strip())
    if first is None or index + 1 >= len(sentences):
        return None
    if not _ATTACH_ANY_NUMBER_RE.match(sentences[index + 1].strip()):
        return None
    subtype = canonical_subtype(first.group("subtype"))
    if subtype is None:
        return None

    def attach_any_number_to_chosen(game: Game, spell: CardState) -> None:
        from .keywords import _protection_refusal_for_attachment

        controller = game.controller_of(spell)
        board = game.computed_board()
        owned = game.permanents_controlled_by(controller.username)
        hosts = [
            c
            for c in owned
            if board.of(c).is_creature and subtype in {w.lower() for w in board.of(c).subtypes}
        ]
        if not hosts:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose {first.group('subtype')} you control",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=1,
                exact=True,
                cards=tuple(c.id for c in hosts),
                card_labels=tuple(c.name for c in hosts),
                default_cards=(hosts[0].id,),
            )
        )
        assert isinstance(chosen, tuple)
        host = next((c for c in hosts if c.id in chosen), None)
        if host is None:
            return
        equipment = [
            c
            for c in owned
            if "equipment" in {w.lower() for w in board.of(c).subtypes} and c.id != host.id
        ]
        if not equipment:
            return
        picked = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="attach any number of Equipment you control to it",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=len(equipment),
                exact=False,
                cards=tuple(c.id for c in equipment),
                card_labels=tuple(c.name for c in equipment),
            )
        )
        assert isinstance(picked, tuple)
        for piece in equipment:
            if piece.id not in picked:
                continue
            if _protection_refusal_for_attachment(game, piece, host) is not None:
                continue  # CR 301.5b: the Equipment doesn't move.
            piece.attach_to(host)

    return attach_any_number_to_chosen, 2


_VEHICLES_BECOME_RE = re.compile(
    r"^vehicles you control become artifact creatures until end of turn\.?$", re.IGNORECASE
)


def _vehicles_become_creatures_reader(sentences: list[str], index: int) -> tuple[_Step, int] | None:
    """Armed and Armored: "Vehicles you control become artifact creatures until
    end of turn." The group is the Vehicles on the battlefield as the sentence
    begins (CR 611.2c); `machines/layers.py` reads the rewritten group sentence
    (CR 205.1b: a Vehicle that becomes an artifact creature keeps its types)."""
    if not _VEHICLES_BECOME_RE.match(sentences[index].strip()):
        return None

    def vehicles_become_artifact_creatures(game: Game, spell: CardState) -> None:
        from .effects import continuous_effects, layer_context_for
        from .layers import parsed_layer_effects

        controller = game.controller_of(spell)
        board = game.computed_board()
        vehicles = [
            c
            for c in game.permanents_controlled_by(controller.username)
            if "vehicle" in {w.lower() for w in board.of(c).subtypes}
        ]
        builder = parsed_layer_effects(
            "creatures you control become artifact creatures until end of turn."
        )
        if not vehicles or builder is None:
            return
        store = continuous_effects(game)
        context = layer_context_for(game, controller)
        for built in builder(spell, store.tick(), vehicles, context):
            if built.holds(game):
                store.add(built)

    return vehicles_become_artifact_creatures, 1


def _threaten_triple_reader(sentences: list[str], index: int) -> tuple[_Step, int] | None:
    """Kari Zev's Expertise: "Gain control of target creature or Vehicle until end
    of turn. Untap it. It gains haste until end of turn." - Act of Treason's
    three instructions as separate sentences ahead of a sentence this module
    reads, so the splitter never hands them over as one clause."""
    if index + 3 > len(sentences) or not sentences[index].strip().lower().startswith(
        "gain control of "
    ):
        return None

    from .effects import _parse_untap_and_gain_control_clause

    effect = _parse_untap_and_gain_control_clause(
        " ".join(s.strip() for s in sentences[index : index + 3])
    )
    return (effect, 3) if effect is not None else None


_FAMILY_READERS: tuple[_Reader, ...] = (
    _threaten_triple_reader,
    _vehicles_become_creatures_reader,
    _free_cast_reader,
    _named_search_reader,
    _choose_and_attach_reader,
)


def _claims_a_sentence(sentences: list[str], slot_sentences: int) -> bool:
    """Whether `spell_sentence_sequence_effect`'s walk reaches a sentence one of
    this module's families claims, every unclaimed sentence before it taken as
    read (the walk's only other outcome there is `None`)."""
    for index, sentence in enumerate(sentences):
        if slot_sentences >= 2 and _SLOT_SENTENCE_RE.match(sentence.strip()):
            return True
        if any(reader(sentences, index) is not None for reader in _FAMILY_READERS):
            return True
    return False


def spell_sentence_sequence_effect(whole: str) -> Effect | None:
    """A spell's resolution text, when it carries one of this module's sentence
    families and every other sentence is readable on its own - each performed
    in printed order. `None` otherwise (the other readers get their turn)."""
    from .effects import (
        _is_notice_only,
        _plain_resolution_sentences,
        _spell_effect_or_notice,
    )

    sentences = _plain_resolution_sentences(whole)
    if len(sentences) < 2:
        return None
    slot_sentences = sum(1 for s in sentences if _SLOT_SENTENCE_RE.match(s.strip()))
    if not _claims_a_sentence(sentences, slot_sentences):
        # Nothing below would claim a sentence, so the walk ends unclaimed (or
        # earlier, on an unreadable sentence) - `None` either way, without
        # dispatching every other sentence through the whole spell ladder.
        return None
    claimed = False
    steps: list[_Step] = []
    slot = 0
    index = 0
    while index < len(sentences):
        sentence = sentences[index].strip()
        if slot_sentences >= 2 and _SLOT_SENTENCE_RE.match(sentence):
            steps.append(_slot_step(sentence, slot))
            slot += 1
            claimed = True
            index += 1
            continue
        for reader in _FAMILY_READERS:
            read = reader(sentences, index)
            if read is not None:
                step, used = read
                steps.append(step)
                claimed = True
                index += used
                break
        else:
            other = _spell_effect_or_notice(_THEN_PREFIX_RE.sub("", sentence))
            if (
                other is None
                or _is_notice_only(other)
                or getattr(other, "unparsed_remainder", None) is not None
            ):
                return None
            steps.append(other)
            index += 1
    if not claimed:
        return None

    def sentence_sequence_effect(game: Game, spell: CardState) -> None:
        for step in steps:
            step(game, spell)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return sentence_sequence_effect


__all__ = ["spell_sentence_sequence_effect"]
