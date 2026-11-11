"""Modal spells and abilities, read off oracle text (CR 700.2).

CR 700.2: "A spell or ability is modal if it has two or more options in a
bulleted list preceded by instructions for a player to choose a number of those
options, such as 'Choose one -.'" Each option is a mode. That is exactly the
shape this module looks for: an instruction line beginning `Choose`, followed by
lines beginning with a bullet.

The sub-rules this module implements, all looked up rather than remembered:

- **CR 700.2a** - the controller of a modal spell or activated ability chooses
  the mode(s) as part of casting it. `machines/casting.py` does that at
  `CastingStep.MODES`, which CR 601.2b puts before targets are chosen.
- **CR 700.2c** - a spell that targets only if a particular mode is chosen needs
  those targets chosen only if that mode was chosen. This is why the targeting
  profile of a modal card is derived *for a set of modes*, not for the card.
- **CR 700.2d** - a player choosing more than one mode normally can't choose the
  same mode more than once. Some cards say they may; Mystic Confluence prints
  "You may choose the same mode more than once." `repeatable` records it.
- **CR 700.2f / CR 115.8** - modal spells may have different targeting
  requirements for each mode.
- **CR 702.42a Entwine** - "You may choose all modes of this spell instead of
  just the number specified" for its cost. `entwine_cost` records the cost; a
  casting that pays it says so with `entwined=True`.
- **CR 702.120a Escalate** - an additional cost "for each mode you choose beyond
  the first". `escalate_cost` records it. Cards with escalate print
  "Choose one or more -", so the mode *count* needs nothing special; what
  escalate changes is what the caster pays, which is the caller's job.
- **CR 700.2h** - a mode with its own cost printed before its effect: Tiered
  (CR 702.183a, `•` bullets, a tier label before the cost) is read this way.
  Its keyword introduces the modal list with a reminder-text parenthetical
  rather than a bare "Choose ..." line (`Tiered (Choose one additional
  cost.)`), so the instruction line is read out of that parenthetical when
  the line itself does not start with "Choose" - a shape rule, not a
  keyword-name check, so any future keyword using the same reminder-text
  convention is covered for free. Each mode's own cost is read into
  `Mode.cost`; `machines/casting.py`'s `choose_modes` charges it
  automatically, the same way `_charge_entwine` already does for CR 702.42a.
  Spree (CR 702.172a) shares this same "cost before effect" shape, the
  parenthetical-instruction reading, and now its own `+`-symbol bullets
  (CR 702.172b) too - `_BULLET_RE` matches `+` followed by whitespace as well
  as `•`, told apart from a loyalty ability's "+1:"/"+2:" line (CR 606.4) by
  that same whitespace, which a loyalty symbol's immediate digit never has.
  Proved against Smuggler's Surprise, a real printing in this pool.

CR 700.2i pawprint modes (`{P}{P} — effect` lines under "Choose up to five {P}
worth of modes") are read too: each `Mode.pawprints` is its symbol count, the
profile's `pawprint_budget` is the "up to N {P}" total, and `resolve` checks the
chosen modes' pawprints sum to at most the budget, not a mode count.

Deliberately not handled, each of them leaving `understood=False` rather than a
confident wrong answer:

- **CR 700.2e / CR 601.7** - a mode chosen by a player other than the
  controller.

This module is parsing and validation only. It never touches game state.
"""

import functools
import re
from collections.abc import Iterable, Sequence

from pydantic import ConfigDict

from ..models.card import Card
from ..numbers import parse_count
from ..snapshot import EngineModel

#: The bullet WOTC prints in front of each mode.
BULLET = "•"
#: CR 702.172b: "Cards with the spree ability ... use a plus sign (+) rather
#: than traditional bullet points." Spree's own bullet is always followed by
#: whitespace before its cost ("+ {2} — Mill four cards...", Smuggler's
#: Surprise) - never immediately by a digit and a colon the way a loyalty
#: ability's own "+1:"/"+2:" line is (CR 606.4, Wrenn and Seven's "+1: Reveal
#: the top four cards..."). The two shapes never collide on that whitespace,
#: so this reads generally off any card printing either bullet rather than
#: needing a Spree-specific keyword gate - the same "shape rule, not a
#: keyword-name check" `_PARENTHETICAL_INSTRUCTION` already is for Tiered
#: and Spree's shared reminder-text instruction line.
_BULLET_RE = re.compile(rf"^(?:{re.escape(BULLET)}|\+\s+)")

_INSTRUCTION = re.compile(r"^(?P<optional>you may )?choose\b(?P<rest>.*)$", re.IGNORECASE)
#: "Each mode must target a different player." (Shadrix Silverquill): the
#: chosen modes' targets must be pairwise different players.
_DISTINCT_PLAYERS = re.compile(r"\beach mode must target a different player\b", re.IGNORECASE)
_REPEATABLE = re.compile(r"you may choose the same mode more than once", re.IGNORECASE)
_UP_TO = re.compile(r"^\s*up to (?P<count>[\w]+)\b")
#: "Choose any number -" (Rankle, Master of Pranks): zero to every mode, CR
#: 700.2b's "If no mode is chosen, the ability is removed from the stack"
#: being what happens when none is.
_ANY_NUMBER = re.compile(r"^\s*any number\b", re.IGNORECASE)
_OR_MORE = re.compile(r"^\s*(?P<count>[\w]+)\s+or\s+(?:more|both)\b", re.IGNORECASE)
_PLAIN = re.compile(r"^\s*(?P<count>[\w]+)\b")
#: The instruction's second sentence: "Choose one. If you control a Wizard as
#: you cast this spell, you may choose two instead." (Flame of Anor), "If there
#: are four or more card types among cards in your graveyard, choose both
#: instead." (Prophetic Titan). The condition is read by `Game.condition_holds`
#: when the modes are chosen; "as you cast this spell" is only when (CR 601.2b).
_ALTERNATIVE = re.compile(
    r"\.\s*if (?P<condition>[^,]+?)(?: as you cast this spell)?,\s*"
    r"(?P<optional>you may )?choose (?P<count>[^.]+?) instead\b",
    re.IGNORECASE,
)

#: CR 700.2h: a mode whose effect is preceded by a cost. An optional short
#: label (Tiered's tier name: "Fire", "Fira", "Firaga") followed by a dash,
#: then a mandatory brace-delimited cost, then the dash that introduces the
#: effect. Spree's own shape ("+ {1} — effect") is the same pattern with no
#: label at all - the leading "+" is CR 702.172b's bullet, already stripped
#: before this runs. The label is capped at 20 characters and may not itself
#: contain a brace or a dash, so this cannot swallow an ordinary mode whose
#: effect text happens to mention a mana symbol partway through the line.
_MODE_WITH_COST = re.compile(
    r"^\s*(?:(?P<label>[^{}\-—]{1,20}?)\s*[-—]\s*)?"
    r"(?P<cost>(?:\{[^{}]+\})+)\s*[-—]\s*(?P<effect>.+)$"
)
#: CR 207.2d: a flavor word (or CR 207.2c ability word) naming a mode -
#: "Bring Down", "Two-Weapon Fighting", "Learn Their Secrets", each followed
#: by an em dash. A
#: capitalised run of at most 40 characters with no sentence punctuation, no
#: mana symbol and no dash of its own, then the em dash. The cap and the
#: punctuation ban are what keep an ordinary instruction that merely has an
#: em dash further along from being read as a label.
_MODE_LABEL = re.compile(r"^[A-Z][^{}.:;\u2014\n]{0,39}?\s+\u2014\s+")
#: CR 700.2i: pawprint modes are not counted in bullets at all.
_PAWPRINT = re.compile(r"\{P\}")
#: A pawprint mode line: "{P}{P} — Draw a card for each creature ...".
_PAWPRINT_MODE = re.compile(r"^(?P<marks>(?:\{P\})+)\s*[-\u2014]\s*(?P<effect>.+)$")
#: "Choose up to five {P} worth of modes."
_PAWPRINT_BUDGET = re.compile(r"\bup to (?P<count>\w+) \{P\} worth of modes", re.IGNORECASE)
#: CR 700.2h keywords (Spree, Tiered) print their modal instruction inside a
#: reminder-text parenthetical after the keyword name, not as a bare "Choose
#: ..." line: `Tiered (Choose one additional cost.)`. This reads the shape
#: of that parenthetical, not the keyword name in front of it, so any future
#: keyword using the same reminder-text convention is covered for free.
_PARENTHETICAL_INSTRUCTION = re.compile(r"\((?P<inner>Choose\b[^()]*)\)", re.IGNORECASE)

_ENTWINE = re.compile(r"^Entwine\s*[-—]?\s*(?P<cost>[^(]+)", re.IGNORECASE)
_ESCALATE = re.compile(r"^Escalate\s*[-—]?\s*(?P<cost>[^(]+)", re.IGNORECASE)

_REMINDER = re.compile(r"\([^()]*\)")
_X = re.compile(r"(?<![\w])X(?![\w])")


class Mode(EngineModel):
    """One option from the bulleted list (CR 700.2)."""

    model_config = ConfigDict(frozen=True)

    #: 1-based position on the card, the way a player would point at it.
    number: int
    #: The bullet's text exactly as printed, bullet character removed.
    text: str
    #: CR 700.2h: this mode's own additional cost, printed before its effect
    #: (Spree, Tiered), or None for an ordinary mode. Mandatory once the mode
    #: is chosen (CR 700.2h, CR 601.2f-h) - not an optional cost like kicker.
    cost: str | None = None
    #: CR 700.2i: the number of pawprint symbols ({P}) printed in front of this
    #: mode; 0 for a bulleted mode.
    pawprints: int = 0

    def __str__(self) -> str:
        return f"{self.number}. {self.text}"


class ModalProfile(EngineModel):
    """The modal structure of one card: its instruction and its modes."""

    model_config = ConfigDict(frozen=True)

    #: The instruction line as printed, e.g. `Choose one -`.
    instruction: str
    modes: tuple[Mode, ...]
    #: How many modes must be chosen, and how many may be (CR 700.2).
    minimum: int
    maximum: int
    #: CR 700.2d: whether the card allows the same mode more than once.
    repeatable: bool = False
    #: "You may choose two" (Shadrix Silverquill): the whole instruction is
    #: optional - choosing no mode at all is legal (and removes the ability,
    #: CR 700.2b), but choosing some of the modes is not.
    optional: bool = False
    #: "Each mode must target a different player": no two chosen modes may
    #: aim at the same player.
    distinct_targets: bool = False
    #: CR 700.2i: "Choose up to five {P} worth of modes" - the most pawprint
    #: symbols the chosen modes may add up to; None for a bulleted card.
    pawprint_budget: int | None = None
    #: CR 702.42a: the entwine cost, if the card has entwine.
    entwine_cost: str | None = None
    #: CR 702.120a: the escalate cost, if the card has escalate.
    escalate_cost: str | None = None
    #: False when the card is modal but this parser could not read its
    #: structure. Callers must not enforce anything from an unread profile.
    understood: bool = True
    #: The condition of the instruction's "If <condition>, [you may] choose N
    #: instead" sentence, or None when it prints none. `Game.
    #: modal_alternative_applies` answers it as the modes are chosen.
    alternative_condition: str | None = None
    #: The printed alternative count ("two", "both", "one or more").
    alternative_text: str | None = None
    #: How many modes may be chosen while the condition holds - the printed
    #: range widened to the alternative for "you may choose N instead", replaced
    #: by it for a mandatory "choose N instead". None when the alternative count
    #: was not read, which keeps the printed range and records a notice.
    alternative_minimum: int | None = None
    alternative_maximum: int | None = None

    @property
    def has_entwine(self) -> bool:
        return self.entwine_cost is not None

    def mode(self, spec: "int | str | Mode") -> Mode:
        """The mode a caster meant, by number, by text, or already resolved.

        A string matches a mode's printed text case-insensitively, either whole
        or as a unique substring, so a test can say `"Destroy target
        enchantment"` without pasting the bullet exactly.
        """
        if isinstance(spec, Mode):
            if spec not in self.modes:
                raise ValueError(f"{spec.text!r} is not a mode of this spell")
            return spec
        if isinstance(spec, int):
            for mode in self.modes:
                if mode.number == spec:
                    return mode
            raise ValueError(
                f"there is no mode {spec}: this spell has {len(self.modes)} modes, "
                f"numbered 1 to {len(self.modes)}"
            )

        wanted = spec.strip().lower()
        exact = [mode for mode in self.modes if mode.text.lower() == wanted]
        if len(exact) == 1:
            return exact[0]
        partial = [mode for mode in self.modes if wanted and wanted in mode.text.lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise ValueError(f"{spec!r} matches more than one mode of this spell")
        raise ValueError(f"{spec!r} is not a mode of this spell")

    def resolve(
        self,
        chosen: Sequence["int | str | Mode"],
        *,
        entwined: bool = False,
        alternative: bool = False,
    ) -> tuple[Mode, ...]:
        """The modes a caster announced, checked against what the card allows.

        CR 700.2a has the modes chosen as part of casting, so everything wrong
        with the choice is wrong *now*: an unknown mode, a repeat the card does
        not allow (CR 700.2d), or the wrong number of them.

        `entwined` is CR 702.42a: paying the entwine cost lets the caster choose
        all of the modes instead of the number the instruction specifies.

        `alternative` is whether the instruction's "If ..., choose N instead"
        condition holds for this choice (`Game.modal_alternative_applies`).
        """
        modes = tuple(self.mode(spec) for spec in chosen)

        if self.pawprint_budget is not None:
            # CR 700.2i: any number of modes whose pawprints total at most the
            # budget; the same mode again is CR 700.2d's repeat, which the
            # instruction allows or not like any other modal card.
            total = sum(mode.pawprints for mode in modes)
            if total > self.pawprint_budget:
                raise ValueError(
                    f"{total} pawprint symbols chosen where the spell allows at most "
                    f"{self.pawprint_budget} {{P}} worth of modes (CR 700.2i)"
                )
        if not self.repeatable:
            seen: set[int] = set()
            for mode in modes:
                if mode.number in seen:
                    raise ValueError(
                        f"mode {mode.number} was chosen twice, and this spell does not "
                        f"say the same mode may be chosen more than once (CR 700.2d)"
                    )
                seen.add(mode.number)

        minimum, maximum = self.allowed_range(entwined=entwined, alternative=alternative)
        if self.pawprint_budget is not None:
            minimum, maximum = 0, len(modes)
        if len(modes) < minimum:
            raise ValueError(
                f"too few modes: {len(modes)} chosen where the spell requires {minimum}"
            )
        if len(modes) > maximum:
            raise ValueError(
                f"too many modes: {len(modes)} chosen where the spell allows at most {maximum}"
            )
        # CR 608.2a: "the controller of the spell or ability follows its
        # instructions in the order written" - a modal spell's own
        # instructions *are* the bulleted modes in printed order (CR 700.2),
        # so the chosen subset resolves in that order however the caster
        # announced them (CR 601.2b's choice is which modes, not what order
        # they run in). `sorted` is stable, so CR 700.2d's repeated mode -
        # "the spell is treated as if that mode appeared that many times in
        # sequence" - keeps its own repeats adjacent and in the order they
        # were announced.
        return tuple(sorted(modes, key=lambda mode: mode.number))

    @property
    def chosen_at_random(self) -> bool:
        """ "Choose one at random" (Outlaws' Merriment): the game picks the
        mode, not the controller - so CR 700.17's "a player faces a dilemma
        whenever they choose one or more modes" does not happen."""
        return "at random" in self.instruction.lower()

    def allowed_range(
        self, *, entwined: bool = False, alternative: bool = False
    ) -> tuple[int, int]:
        """How many modes may be chosen, entwine (CR 702.42a) and a held
        "choose N instead" condition (`alternative`) included."""
        if entwined:
            if not self.has_entwine:
                raise ValueError("this spell has no entwine cost to pay")
            return len(self.modes), len(self.modes)
        if (
            alternative
            and self.alternative_minimum is not None
            and self.alternative_maximum is not None
        ):
            return self.alternative_minimum, self.alternative_maximum
        return self.minimum, self.maximum


_CACHE: dict[tuple[str, str], ModalProfile | None] = {}


def modal_profile(card: Card) -> ModalProfile | None:
    """The card's modal structure, or None if it is not a modal card.

    Cached, since a printing's oracle text never changes.
    """
    # `front_oracle_text`, not `oracle_text`: same DFC-null-field family as
    # `targeting.targeting_profile`'s fix - without it, a modal-DFC/transform
    # spell's front face never gets a modal reading either.
    text = card.front_oracle_text
    key = (card.name, text)
    if key not in _CACHE:
        _CACHE[key] = _parse(text, card.keywords)
    return _CACHE[key]


def is_modal(card: Card) -> bool:
    """CR 700.2: does this card offer a bulleted list of modes at all?"""
    return modal_profile(card) is not None


def is_modal_text(oracle_text: str | None) -> bool:
    """CR 700.2, from raw oracle text alone, no `Card` required.

    A card's modality follows entirely from its bulleted list and the
    instruction line in front of it - unlike `entwine_cost`/`escalate_cost`,
    nothing here is gated on `Card.keywords`. That makes this safe for a
    caller holding only text, such as `effects.py`'s clause parser, which
    needs to tell a genuinely modal card ("Choose two -" with a bulleted
    list) apart from a card that merely contains the word "Choose" in an
    ordinary instruction ("Choose target creature ...", "Choose a creature
    type"), without constructing a full `Card`.
    """
    return _parse(oracle_text or "", ()) is not None


def modal_profile_from_text(oracle_text: str | None) -> ModalProfile | None:
    """`modal_profile`'s own reading, from raw text alone - no `Card` and no
    cache, for a caller that only has text to hand.

    Elder Gargaroth's own "attacks or blocks, choose one -" is not a modal
    *spell* at all (CR 700.2's own kind of object is "a spell or ability");
    it is a modal *triggered* ability, so there is no `Card` whose front
    face is the modal text - the modal text is only the tail of one printed
    line, everything after the trigger condition (`TriggeredAbility.effect`).
    `machines/effects.py`'s `_resolve_modal_triggered_ability` is the one
    caller.
    """
    return _parse(oracle_text or "", ())


def substitute_x(text: str, x_value: int | None) -> str:
    """CR 107.3a/CR 107.3c: X has no value until the caster announces one for
    this spell or ability; given one, it applies "while that spell or ability
    is on the stack" - throughout its whole text, not just the mana cost. This
    is that substitution on its own, for callers (`machines/effects.py`'s
    per-mode dispatch) that need X applied to a mode's *effect* text, where
    `mode_rules_text`'s quote-blanking would destroy a quoted ability the
    effect still needs to read.
    """
    if x_value is None:
        return text
    return _X.sub(str(x_value), strip_x_restrictions(text))


#: "X can't be 0." - a restriction on the value announced for X (CR 107.3a),
#: not an instruction to carry out. Left in the text it would be substituted
#: into nonsense ("3 can't be 0.") and read as an unparsed remainder.
_X_CANT_BE_ZERO = re.compile(r"(?<![\w])X can[\u2019']t be 0\.?[ \t]*", re.IGNORECASE)


#: "Spend only black mana on X." (Consume Spirit; Crypt Rats on an activated
#: ability) - a restriction on how the X share of the cost is paid (CR 107.3a
#: announces X, CR 601.2h pays the total cost), not an instruction to carry out.
#: Only a colour list is matched; any other quality is left in the text so the
#: clause stays unread rather than being silently widened.
_X_SPEND_COLOUR = r"(?:white|blue|black|red|green)"
SPEND_ONLY_ON_X_RE = re.compile(
    rf"(?<![\w])Spend only (?P<colours>{_X_SPEND_COLOUR}(?: or {_X_SPEND_COLOUR})*)"
    r" mana on X\.?[ \t]*",
    re.IGNORECASE,
)


@functools.lru_cache(maxsize=16384)
def strip_x_restrictions(text: str) -> str:
    """`text` without its "X can't be 0." and "Spend only <colour> mana on X."
    sentences - read at the announcement of X (`x_restriction_refusal`) and at
    the payment of the cost (`machines/cost/text.x_spend_colours`), never part
    of what resolves."""
    return SPEND_ONLY_ON_X_RE.sub("", _X_CANT_BE_ZERO.sub("", text))


def x_restriction_refusal(text: str, x_value: int) -> str | None:
    """Why the announced `x_value` breaks a restriction the text itself states
    on X (CR 107.3a: X is chosen as the spell is cast or the ability is
    activated, and "X can't be 0" bounds that choice), or `None`."""
    if x_value == 0 and _X_CANT_BE_ZERO.search(text):
        return "X can't be 0 (CR 107.3a)"
    return None


def mode_rules_text(mode: Mode, x_value: int | None = None) -> str:
    """One mode's text, prepared for a parser that reads rules templates.

    Three things get in the way of reading a mode the way a whole card is
    read:

    - CR 700.2h's own cost prefix (Tiered's tier label and cost, Spree's
      cost) is not part of the instruction at all - it is what was already
      paid to choose this mode (CR 601.2f) - so it is stripped the same way
      `mode_effect_text` strips it for a resolution-time reader. Left in,
      its own brace-delimited digit reads as if it were a printed target
      count: Metamorphic Blast's second mode, "{3} — Target player draws
      two cards.", used to hand the word-scan below the literal text
      "{3} — Target player draws two cards." and it read the cost's "3" as
      "target player" needing three targets, not one - a Spree/Tiered mode
      whose printed cost happens to differ from its own target count (every
      one of them but a lucky coincidence) could never be cast with a legal
      target list at all.
    - Text in quotes is an ability being granted to something else, not
      instructions to follow now. Kozilek's Command's first mode makes tokens
      with `"Sacrifice this token: Add {C}."` - the colon inside those quotes
      would otherwise make the line look like an activated ability. Quoted
      spans are blanked, keeping every other index where it was.
    - X has no value until the caster announces one (CR 107.3a). Given one,
      it is substituted in, so "up to X target cards" becomes countable.

    This blanks quotes *before* substituting X, which is right for a
    *targeting* profile (the only current caller, `profile_for_modes`) - it
    never needs to read inside a quoted granted ability at all. A caller that
    needs the mode's actual effect, quoted ability included, wants
    `substitute_x` on the mode's own unblanked text instead.
    """
    text = _blank_quotes(mode_effect_text(mode))
    return substitute_x(text, x_value)


def mode_effect_text(mode: Mode) -> str:
    """One mode's own effect text, with everything in front of the
    instruction that is not rules text taken off - what a resolution-time
    parser (`machines/effects.py::parse_mode_effect`) and a targeting
    profile (`mode_rules_text`) should both read:

    - CR 700.2h's cost-before-effect prefix (Tiered's tier label and cost,
      Spree's cost): paying it already happened during casting (CR 601.2f).
    - A named mode's label - Scout the City's "Bring Down" in front of
      "Destroy target creature with flying.", School Daze's "Do Homework"
      in front of "Draw three cards." CR 207.2d: flavor words "have no special rules meaning", so
      the instruction is only the text after the dash. Stripped here, once,
      rather than by each reader stepping over it on its own.

    A mode with neither prefix is returned unchanged.
    """
    text = mode.text
    if mode.cost is not None:
        match = _MODE_WITH_COST.match(text)
        if match is not None:
            text = match.group("effect")
    return _MODE_LABEL.sub("", text, count=1)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _parse(oracle_text: str, keywords: Iterable[str]) -> ModalProfile | None:
    lines = [line.strip() for line in oracle_text.splitlines()]
    bullets = [
        index
        for index, line in enumerate(lines)
        if _BULLET_RE.match(line) or (line.startswith("{P}") and _PAWPRINT_MODE.match(line))
    ]
    if not bullets:
        return None

    first = bullets[0]
    raw_instruction_line = next(
        (lines[index] for index in range(first - 1, -1, -1) if lines[index]),
        None,
    )
    # CR 700.2h keywords (Tiered, Spree) print their "Choose ..." instruction
    # inside a reminder-text parenthetical after the keyword's own name,
    # rather than as a bare instruction line - read the parenthetical's own
    # words as the instruction when the line itself does not already start
    # with "Choose".
    instruction_line = raw_instruction_line
    if instruction_line is not None and _INSTRUCTION.match(instruction_line) is None:
        parenthetical = _PARENTHETICAL_INSTRUCTION.search(instruction_line)
        if parenthetical is not None:
            instruction_line = parenthetical.group("inner").strip()

    if instruction_line is None or _INSTRUCTION.match(instruction_line) is None:
        # A bulleted list with no "Choose ..." in front of it is not the
        # templating CR 700.2 describes. Say so rather than guess at it.
        return ModalProfile(
            instruction=raw_instruction_line or "",
            modes=(),
            minimum=0,
            maximum=0,
            understood=False,
        )

    pawprint_lines = [_PAWPRINT_MODE.match(lines[index]) for index in bullets]
    if any(pawprint_lines):
        return _parse_pawprint(
            lines, bullets, pawprint_lines, instruction_line, raw_instruction_line
        )
    mode_texts = [_BULLET_RE.sub("", lines[index], count=1).strip() for index in bullets]
    mode_costs: list[str | None] = []
    for text in mode_texts:
        match = _MODE_WITH_COST.match(text)
        mode_costs.append(match.group("cost") if match is not None else None)
    modes = tuple(
        Mode(number=number, text=text, cost=cost)
        for number, (text, cost) in enumerate(zip(mode_texts, mode_costs, strict=True), start=1)
    )

    keyword_set = {keyword.lower() for keyword in keywords}
    profile_kwargs = {
        "instruction": raw_instruction_line or "",
        "modes": modes,
        "repeatable": bool(_REPEATABLE.search(instruction_line)),
        "optional": _INSTRUCTION.match(instruction_line).group("optional") is not None,  # type: ignore[union-attr]
        "distinct_targets": _DISTINCT_PLAYERS.search(instruction_line) is not None,
        "entwine_cost": _keyword_cost(lines, _ENTWINE, "entwine", keyword_set),
        "escalate_cost": _keyword_cost(lines, _ESCALATE, "escalate", keyword_set),
    }

    counted = _read_counts(instruction_line, len(modes))
    profile_kwargs.update(_read_alternative(instruction_line, len(modes), counted))
    unreadable = counted is None or _PAWPRINT.search(instruction_line) is not None
    if unreadable:
        minimum, maximum = counted or (0, 0)
        return ModalProfile(**profile_kwargs, minimum=minimum, maximum=maximum, understood=False)

    minimum, maximum = counted
    return ModalProfile(**profile_kwargs, minimum=minimum, maximum=maximum)


def _parse_pawprint(
    lines: Sequence[str],
    bullets: Sequence[int],
    pawprint_lines: Sequence["re.Match[str] | None"],
    instruction_line: str,
    raw_instruction_line: str | None,
) -> ModalProfile:
    """CR 700.2i's profile: every mode line is `{P}...` and the instruction
    names the {P} total. Anything else leaves `understood=False`."""
    budget = _PAWPRINT_BUDGET.search(instruction_line)
    count = parse_count(budget.group("count"), article=False) if budget is not None else None
    if count is None or not all(pawprint_lines):
        return ModalProfile(
            instruction=raw_instruction_line or "", modes=(), minimum=0, maximum=0, understood=False
        )
    modes = tuple(
        Mode(
            number=number,
            text=found.group("effect").strip(),
            pawprints=found.group("marks").count("{P}"),
        )
        for number, found in enumerate(pawprint_lines, start=1)
        if found is not None
    )
    return ModalProfile(
        instruction=raw_instruction_line or "",
        modes=modes,
        minimum=0,
        maximum=count,
        repeatable=bool(_REPEATABLE.search(instruction_line)),
        optional=True,
        pawprint_budget=count,
    )


def _read_counts(instruction: str, mode_count: int) -> tuple[int, int] | None:
    """How many modes the instruction line asks for, as (minimum, maximum).

    The templates, all of them real:

        Choose one -            exactly one
        Choose two -            exactly two
        Choose one or both -    at least one, up to every mode
        Choose one or more -    at least one, up to every mode
        Choose up to two -      as few as none
        Choose any number -     as few as none, up to every mode
        Choose three. You may choose the same mode more than once.
    """
    match = _INSTRUCTION.match(instruction)
    if match is None:
        return None
    rest = match.group("rest")

    if _ANY_NUMBER.match(rest) is not None:
        return 0, mode_count

    up_to = _UP_TO.match(rest)
    if up_to is not None:
        count = parse_count(up_to.group("count"), article=False)
        return None if count is None else (0, min(count, mode_count))

    or_more = _OR_MORE.match(rest)
    if or_more is not None:
        count = parse_count(or_more.group("count"), article=False)
        return None if count is None else (count, mode_count)

    plain = _PLAIN.match(rest)
    if plain is None:
        return None
    count = parse_count(plain.group("count"), article=False)
    if count is None or count > mode_count:
        return None
    return count, count


def _read_alternative(
    instruction: str, mode_count: int, counted: tuple[int, int] | None
) -> dict[str, str | int]:
    """The `alternative_*` fields for an instruction's "If <condition>, [you
    may] choose N instead" sentence, or nothing when it prints none.

    The alternative count is read the way the printed one is (`_read_counts`),
    so "two", "one or more" and "up to three" all work; "both" and "all" are
    every mode. "Any number" (CR 601.4's own Inscription of Abundance
    example: "its controller may choose any number of modes") is zero to
    every mode, the same "choose any number of ..." idiom CR 701.34a
    (proliferate) and its siblings use elsewhere - zero is a legal choice,
    unlike "both"/"all", which is why it is not folded into that branch.
    "You may choose two instead" of "Choose one" leaves one legal too, so the
    range is widened rather than replaced; a mandatory "choose both instead"
    (or "choose any number instead") replaces it. An unread count keeps only
    the condition, which `Game.modal_alternative_applies` turns into a
    notice.
    """
    match = _ALTERNATIVE.search(instruction)
    if match is None:
        return {}
    text = match.group("count").strip()
    fields: dict[str, str | int] = {
        "alternative_condition": match.group("condition").strip(),
        "alternative_text": text,
    }
    if text.lower() in ("both", "all"):
        alternative: tuple[int, int] | None = (mode_count, mode_count)
    elif text.lower() == "any number":
        alternative = (0, mode_count)
    else:
        alternative = _read_counts(f"Choose {text}", mode_count)
    if alternative is None or counted is None:
        return fields
    minimum, maximum = alternative
    if match.group("optional"):
        minimum, maximum = min(minimum, counted[0]), max(maximum, counted[1])
    fields["alternative_minimum"] = minimum
    fields["alternative_maximum"] = maximum
    return fields


def _keyword_cost(
    lines: Sequence[str],
    pattern: re.Pattern[str],
    keyword: str,
    keywords: set[str],
) -> str | None:
    """The cost printed on an `Entwine {2}` or `Escalate-Discard a card.` line.

    Gated on the printing's own Scryfall `keywords` list, so a card that merely
    mentions the word in its text does not grow the ability.
    """
    if keyword not in keywords:
        return None
    for line in lines:
        match = pattern.match(line)
        if match is not None:
            return _REMINDER.sub("", match.group("cost")).strip().rstrip(".").strip()
    return None


def _blank_quotes(text: str) -> str:
    """Replace quoted spans with spaces, keeping every other index the same."""
    out = list(text)
    inside = False
    for index, char in enumerate(out):
        if char == '"':
            inside = not inside
            out[index] = " "
        elif inside:
            out[index] = " "
    return "".join(out)


#: A rider on the instruction line itself - Glorfindel, Dauntless Rescuer's
#: "Whenever you scry, choose one and Glorfindel gets +1/+1 until end of
#: turn." (CR 700.2: the bullets are the modes; the rest of the instruction
#: is an instruction like any other and happens whichever mode is chosen).
_INSTRUCTION_RIDER = re.compile(
    r"^choose (?:one|two|three) and (?P<rider>[^.]+\.)\s*$", re.IGNORECASE
)


def instruction_rider(instruction: str) -> str | None:
    """The sentence a modal instruction line carries after "choose N and",
    capitalised as a sentence of its own, or `None` when it carries none."""
    match = _INSTRUCTION_RIDER.match(instruction.strip())
    if match is None:
        return None
    rider = match.group("rider")
    return rider[:1].upper() + rider[1:]
