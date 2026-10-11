"""Audit of the EP-01 R2 T2 families: static "can't be the target" lines and an
Aura spell's own "you can't choose an untapped ... as this spell's target"
(CR 115.2, CR 601.2c, CR 702.11, CR 702.18, CR 702.16).

A line is credited only when the PRODUCTION reader performs it:

- "<this creature | enchanted creature | cards in graveyards ...> can't be the
  target of [<quality>] spells ... or abilities ..." must be a line
  `machines/protection_statics.parse_target_restriction` reads - the same
  parser `static_target_refusal` runs every targeting path through
  (`Game.hexproof_refusal`);
- "You can't choose an untapped creature as this spell's target as you cast
  it." must be one `machines/targeting._with_aura_target` turns into a
  tapped-only enchant target on the spell's real targeting profile.

Group hexproof/shroud/protection grants are read by the layer parser
(`protection_statics.parse_protection_grant`) and are credited by the
support oracle's own `parsed_layer_effects` step; they need no rule here.
"""

from ..machines.abilities import self_normalized_effect_text
from ..machines.protection_statics import parse_target_restriction
from ..machines.targeting import targeting_profile, untapped_target_forbidden


def reads_targeting_protection_line(printing, text, *, card_name=None, legendary=False) -> bool:
    lowered = text.lower()
    if "can't be the target" in lowered:
        normalized = self_normalized_effect_text(
            card_name or printing.name, text, legendary=legendary
        )
        return parse_target_restriction(normalized) is not None
    if "as this spell's target as you cast it" in lowered:
        if not untapped_target_forbidden(text) or "Aura" not in printing.subtypes:
            return False
        profile = targeting_profile(printing)
        return profile.understood and any(
            requirement.must_be_tapped for requirement in profile.requirements
        )
    return False
