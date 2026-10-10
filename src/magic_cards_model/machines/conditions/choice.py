"""Conditions on the source's own as-enters choice (CR 614.12a).

"this permanent's chosen mode is Khans" gates a Siege's mode bullet (see
`machines/abilities._parse_line_mode_gated`): true only while the source's
recorded `Choice` is that `ChoiceKind.MODE` word.
"""

import re

from ...models.card_state import ChoiceKind
from . import ConditionContext, ConditionReader


def _chosen_mode_is(context: ConditionContext, match: re.Match[str]) -> bool:
    source = context.source
    choice = None if source is None else source.choice
    return (
        choice is not None
        and choice.kind is ChoiceKind.MODE
        and choice.value.lower() == match.group("mode")
    )


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(r"this permanent's chosen mode is (?P<mode>[a-z][\w'-]*)"), _chosen_mode_is
    ),
)
