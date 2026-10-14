"""Casting a spell, as a state machine (CR 601.2).

The rules cast a spell in a fixed order, and the whole thing is one action: if
any part of it cannot be completed legally, the game rewinds to before it began
(CR 601.6, 733.1).

    PROPOSED -> MODES -> TARGETS -> COST_DETERMINED -> PAYING -> CAST
         \\____________________________________________________/
                            cancel, rewinding everything

MODES is where the choices that change what the spell costs are made: the mode,
whether an alternative cost is being paid, and whether any optional additional
cost is being paid (CR 601.2b). TARGETS is CR 601.2c, and legality is checked
there rather than left to resolution.

Paying is delegated to `CostPayment`, so the mana side of casting is one
machine and the announcement side is another.
"""

# isort: off
from ..abilities import AbilityKind as AbilityKind
from typing import Any as Any
from collections.abc import Callable as Callable
from ...models.card import Card as Card
from ..cost import CardRequirement as CardRequirement
from ...models.card_state import CardState as CardState
from ..casting_restrictions import CastingRuleKind as CastingRuleKind
from ...models.card import Color as Color
from ..cost import ComponentKind as ComponentKind
from pydantic import ConfigDict as ConfigDict
from ..layers import ContinuousEffect as ContinuousEffect
from ..cost import CostComponent as CostComponent
from ..cost import CostPayment as CostPayment
from ..cost import CostStep as CostStep
from ...models.card_state import Counter as Counter
from ...snapshot import EngineModel as EngineModel
from ...models.card_state import ExileAnnotation as ExileAnnotation
from ...models.card_state import ExileMarker as ExileMarker
from ..triggers import ExtraTriggerEvent as ExtraTriggerEvent
from ..keywords import FACE_DOWN_CAST_COST as FACE_DOWN_CAST_COST
from pydantic import Field as Field
from ..triggers import GameEvent as GameEvent
from collections.abc import Iterable as Iterable
from collections.abc import Iterator as Iterator
from ..abilities import KeywordAbility as KeywordAbility
from ..layers import Layer as Layer
from ...models.card import Layout as Layout
from ...models.mana import ManaCost as ManaCost
from ...models.mana import ManaSpend as ManaSpend
from collections.abc import Mapping as Mapping
from ..modes import ModalProfile as ModalProfile
from ..modes import Mode as Mode
from collections.abc import Sequence as Sequence
from ..cost import StaticFreeCastGrant as StaticFreeCastGrant
from ..turn import Step as Step
from enum import StrEnum as StrEnum
from ...models.card_state import TargetRef as TargetRef
from ..targeting import TargetingProfile as TargetingProfile
from ..cost import TotalCost as TotalCost
from ..abilities import TriggerEvent as TriggerEvent
from ...models.card import Type as Type
from uuid import UUID as UUID
from ...numbers import VariableX as VariableX
from ...models.zone import Zone as Zone
from ..cost import additional_cost_phrases as additional_cost_phrases
from ..cost import alternative_cost_offers as alternative_cost_offers
from ..cost import alternative_cost_phrase_of_line as alternative_cost_phrase_of_line
from ..cost import announce_reveal as announce_reveal
from ..cost import apply_modifications as apply_modifications
from ..cost import behold_cost as behold_cost
from ..spell_grants import casualty_numbers as casualty_numbers
from ..casting_restrictions import (
    combat_lockdown_restriction_source as combat_lockdown_restriction_source,
)
from ..spell_grants import conspire_count as conspire_count
from contextlib import contextmanager as contextmanager
from ..cost import cost_component_for_phrase as cost_component_for_phrase
from ...numbers import count_pattern as count_pattern
from ..keywords import enchant_restrictions as enchant_restrictions
from ..keywords import face_down_characteristics as face_down_characteristics
from ..targeting import face_spell_profile as face_spell_profile
from ..layers import grant_ability as grant_ability
from ..spell_grants import granted_affinity_reductions as granted_affinity_reductions
from ..casting_restrictions import has_sorcery_speed_flash_grant as has_sorcery_speed_flash_grant
from ..abilities import keyword_abilities as keyword_abilities
from ..targeting import kicked_instead_target_text as kicked_instead_target_text
from functools import lru_cache as lru_cache
from ..cost import mana_value_cap_for as mana_value_cap_for
from ..modes import modal_profile as modal_profile
from ..layers import only_this_incarnation as only_this_incarnation
from ..abilities import parse_abilities as parse_abilities
from ...numbers import parse_amount as parse_amount
from ...numbers import parse_count as parse_count
from ..abilities import parse_granted_ability_lines as parse_granted_ability_lines
from ..cost import pay_life_cost as pay_life_cost
from ..cost import per_object_exile_cost_reduction as per_object_exile_cost_reduction
from ..cost import per_object_exile_reduction_of_sentence as per_object_exile_reduction_of_sentence
from ..cost import per_object_sacrifice_cost_reduction as per_object_sacrifice_cost_reduction
from ..cost import (
    per_object_sacrifice_reduction_of_sentence as per_object_sacrifice_reduction_of_sentence,
)
from ..cost import place_counters_cost as place_counters_cost
from ..objects_as_costs import power_of as power_of
from ..keywords import printed_casualty_numbers as printed_casualty_numbers
from ..keywords import printed_conspire_count as printed_conspire_count
from ..targeting import profile_for_modes as profile_for_modes
from ..targeting import profile_for_modes_with_owners as profile_for_modes_with_owners
from ..targeting import profile_for_text as profile_for_text
import re as re
from ..casting_restrictions import (
    restricted_from_noncreature_casting as restricted_from_noncreature_casting,
)
from ..cost import return_to_hand_cost as return_to_hand_cost
from ..casting_restrictions import (
    sorcery_speed_restriction_source as sorcery_speed_restriction_source,
)
from ..decisions import source_id_of as source_id_of
from ..targeting import spell_profile_for_text as spell_profile_for_text
from ..cost import static_free_cast_grant as static_free_cast_grant
from ..modes import substitute_x as substitute_x
from ..cost import tap_cost as tap_cost
from ..casting_restrictions import targeted_cant_cast_restriction as targeted_cant_cast_restriction
from ..targeting import targeting_profile as targeting_profile
from ..targeting import targeting_trigger_text as targeting_trigger_text
from ..teamwork import teamwork_ability as teamwork_ability
from ..teamwork import teamwork_instead_target_text as teamwork_instead_target_text
from ..teamwork import teamwork_payment_refusal as teamwork_payment_refusal
from ..cost import total_cost_for_phrase as total_cost_for_phrase
from ...models.card import types_of as types_of
from ..keywords import why_cannot_enchant as why_cannot_enchant
from ..cost import why_not_unblocked as why_not_unblocked
from ...phrases import with_indefinite_article as with_indefinite_article
from ..modes import x_restriction_refusal as x_restriction_refusal
from ..casting_restrictions import (
    own_play_prohibition_source as own_play_prohibition_source,
)
from ..casting_restrictions import zone_cast_prohibition_source as zone_cast_prohibition_source
from .granted_life_costs import GrantedLifeCost as GrantedLifeCost
from .granted_life_costs import granted_life_costs as granted_life_costs
from .granted_life_costs import reads_granted_life_cost_line as reads_granted_life_cost_line
from .options import (
    AlternativeCostOption,
    AlternativeCostSource,
    CastTiming,
    ConditionalAlternativeCostOffer,
    KeywordCastOption,
    OptionalAdditionalCost,
    PAY_LIFE_KEYWORD,
    SpliceCandidate,
    _ADDITIONAL_COST_LINE,
    _CONDITIONAL_ALTERNATIVE,
    _EMERGE_FROM,
    _KICKER_AND_OR,
    _OPTIONAL_ADDITIONAL_COST,
    _OPTIONAL_COST_KEYWORDS,
    _OPTIONAL_SACRIFICE_REDUCTION_LINE,
    _OR_PAY_LIFE_TAIL,
    _OR_PAY_TAIL,
    _PAY_FIRST_OR,
    _PAY_ONLY_MANA,
    _SPLICE_PARAMETER_RE,
    _SPLICE_REMINDER_RE,
    _describe_keyword_cost,
    _keyword,
    _matches_splice_quality,
    _option_from_keyword,
    _primary_alternatives_of,
    _printed_alternative_total_cost,
    _splice_parameter,
    _spliced_rules_text,
    _turn_number,
    _warp_from_exile,
    casualty_cost_option,
    casualty_cost_phrase,
    conditional_alternative_cost_offers,
    printed_condition_refusal,
    with_keyword_spell_ability_target,
    conspire_cost_option,
    keyword_cast_options,
    kicker_costs,
    life_or_mana_additional_costs,
    mandatory_additional_costs,
    marker_cast_options,
    optional_additional_costs,
    or_additional_cost_alternatives,
    or_additional_cost_halves,
    reads_mandatory_additional_cost_line,
    reads_optional_exile_reduction_line,
    reads_optional_sacrifice_reduction_line,
    reads_or_pay_additional_cost_line,
    reads_printed_alternative_cost_line,
    splice_candidates,
)
from ._common import (
    BARGAIN_COST,
    CONSPIRE_COST,
    _BLIGHT_PHRASE,
    _OPTIONAL_BEHOLD,
    _OPTIONAL_BEHOLD_CHOSEN_TYPE,
    _OPTIONAL_COLLECT_EVIDENCE,
    _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND,
    _OPTIONAL_REVEAL,
    _OPTIONAL_SACRIFICE_ANY_NUMBER,
    _OPTIONAL_WATERBEND,
)
from .permissions import (
    CAST_PERMISSION,
    GrantedCastOption,
    LinkedExileStaticCast,
    PlayAction,
    PlayPermission,
    StaticZoneCastPermission,
    UsingKeywordPermission,
    _CAST_SPELLS_FROM_A_ZONE,
    _CAST_USING_THEIR_KEYWORD_RE,
    _COLOR_COUNT_WORDS,
    _COLOR_WORDS,
    _CONDITIONAL_FLASH_RE,
    _CONDITIONAL_FLASH_RES,
    _COST_IS_THE_CARDS_MANA_COST,
    _EACH_COLOR_QUALITIES,
    _ENTERS_WITH_A_COUNTER_RIDER_RE,
    _EXILE_SPELLS_CAST_THIS_WAY,
    _EXILE_SPELLS_CAST_THIS_WAY_ANY,
    _GRANTED_KEYWORD_AS_YOU_CAST,
    _GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE,
    _GRANTED_KEYWORD_SPELL_YOU_CAST_HAS,
    _HEXPROOF_ABILITY,
    _LINKED_EXILE_STATIC_CAST_RE,
    _NUMBER_OF_SUBTYPES_YOU_CONTROL_RE,
    _ONCE_EACH_TURN_CAST_FROM_GRAVEYARD,
    _ONLY_MANA_SYMBOLS,
    _PERMANENT_TYPES,
    _PLAYER_KEYWORD_GRANT_LINE,
    _PRINTED_CAST_FROM_ZONE_USING_KEYWORD,
    _PRINTED_PERMISSION_ZONES,
    _PILE_PERMISSION_BODY_RE,
    _PLAY_CARDS_EXILED_WITH_STATIC_RE,
    _PRINTED_SELF_ZONE_CAST_RE,
    _PRINTED_SELF_ZONE_CAST_WITH_ADDITIONAL_COST_RE,
    _STATIC_ZONE_CAST_PERMISSION_RE,
    _printed_self_zone_cast_additional_cost,
    _QUALITY_PREFIX,
    _QUALITY_SEPARATOR,
    _REMINDER_TEXT,
    _REMINDER_TEXT_RE,
    _STATIC_ZONE_CAST_BODY_RE,
    _ZONE_WORDS_FOR_GRANTS,
    _cast_spells_from_a_zone,
    _controls_that_object,
    _count_listed_subtypes,
    _grant_as_you_cast,
    _grant_on_a_card_in_a_zone,
    _grant_spell_you_cast_has_keyword,
    _granted_option,
    _graveyard_cast_grant_option,
    _linked_exile_play_option,
    _linked_exile_static_cast_option,
    _opponents_exile_counter_cast_option,
    _normalized_spell_quality,
    _once_each_turn_cast_from_graveyard,
    printed_self_zone_cast,
    _printed_self_zone_cast_with_additional_cost,
    _printed_self_zone_cast_with_counters,
    _printed_zone_permissions,
    _rezoned_by_using,
    _spell_matches_grant_filter,
    _static_zone_cast_option,
    _using_keyword_permissions,
    _within_bound,
    adventure_face,
    castable_faces,
    castable_from,
    conditional_free_cast_condition,
    conditional_free_cast_unavailable,
    has_quality_flash_grant,
    quality_flash_grant,
    reads_quality_flash_grant_line,
    printed_cast_only_zones,
    class_gated_lines,
    conditional_flash_condition,
    flash_surcharge,
    exiles_spells_cast_this_way,
    grant_suspend_haste,
    granted_cast_options,
    granted_optional_additional_costs,
    has_flash,
    has_quality,
    has_split_second,
    hexproof_abilities_in,
    hexproof_qualities_in,
    is_top_of_library,
    linked_exile_play_grant,
    may_look_at_linked_exile,
    linked_exile_play_source,
    opponents_exile_counter_cast,
    reads_opponents_exile_counter_cast_line,
    linked_exile_static_cast,
    modal_dfc_spell_back_faces,
    once_per_turn_key,
    play_cards_exiled_with_line,
    play_permissions_on,
    player_keyword_grant_of_line,
    reads_as_graveyard_cast_permission_line,
    reads_granted_cast_spell_keyword_line,
    reads_granted_zone_keyword_line,
    reads_linked_exile_static_cast_line,
    reads_play_cards_exiled_with_line,
    reads_printed_self_zone_cast_line,
    reads_printed_zone_permission_line,
    reads_search_cast_permission_line,
    reads_static_zone_cast_permission_line,
    search_cast_candidates,
    reads_using_keyword_permission_line,
    split_second_restriction_source,
    static_permission_applies_now,
    static_zone_cast_permission,
    land_quality_allows,
    record_graveyard_land_use,
    static_graveyard_land_source,
    strip_ability_word,
    cast_condition_holds,
    cast_condition_readable,
    usable_play_permission,
    using_keyword_permission,
)
from .casting import (
    ADDITIONAL_COST_KEYWORDS,
    CASTING_ORDER,
    Casting,
    CastingStep,
    MarkedExile,
    TARGET_LEGALITY_KEYWORDS,
    TIMING_KEYWORDS,
    _CANNOT_CAST_UNLESS_RE,
    _COST_INCREASE_PER_TARGET_RE,
    _GREATEST_AMONG_CREATURES,
    _OPPONENT_SPELL_COUNT_CONDITION,
    _X_CAP,
    _as_mana,
    _why_not_in_own_declare_blockers_step,
    annotate_exile,
    exile_adventured,
    exile_warped,
    face_being_cast,
    finish_suspend,
    remove_suspend_time_counter,
    spell_has_type_word,
    static_free_cast_grants,
    static_grant_option,
    static_free_cast_refusal,
    types_being_cast,
    why_cannot_cast_a_land,
    why_cannot_cast_from,
    why_cannot_cast_now,
    why_cannot_cast_restriction,
    why_cannot_cast_self_restriction,
    why_mana_cost_unpayable,
)
# isort: on


__all__ = [
    "ADDITIONAL_COST_KEYWORDS",
    "AlternativeCostOption",
    "AlternativeCostSource",
    "BARGAIN_COST",
    "CASTING_ORDER",
    "CAST_PERMISSION",
    "CONSPIRE_COST",
    "CastTiming",
    "Casting",
    "CastingStep",
    "ConditionalAlternativeCostOffer",
    "GrantedCastOption",
    "KeywordCastOption",
    "LinkedExileStaticCast",
    "MarkedExile",
    "OptionalAdditionalCost",
    "PAY_LIFE_KEYWORD",
    "PlayAction",
    "PlayPermission",
    "SpliceCandidate",
    "StaticZoneCastPermission",
    "TARGET_LEGALITY_KEYWORDS",
    "TIMING_KEYWORDS",
    "UsingKeywordPermission",
    "_ADDITIONAL_COST_LINE",
    "_BLIGHT_PHRASE",
    "_CANNOT_CAST_UNLESS_RE",
    "_CAST_SPELLS_FROM_A_ZONE",
    "_CAST_USING_THEIR_KEYWORD_RE",
    "_COLOR_COUNT_WORDS",
    "_COLOR_WORDS",
    "_CONDITIONAL_ALTERNATIVE",
    "_CONDITIONAL_FLASH_RE",
    "_CONDITIONAL_FLASH_RES",
    "_COST_INCREASE_PER_TARGET_RE",
    "_COST_IS_THE_CARDS_MANA_COST",
    "_EACH_COLOR_QUALITIES",
    "_EMERGE_FROM",
    "_ENTERS_WITH_A_COUNTER_RIDER_RE",
    "_EXILE_SPELLS_CAST_THIS_WAY",
    "_EXILE_SPELLS_CAST_THIS_WAY_ANY",
    "_GRANTED_KEYWORD_AS_YOU_CAST",
    "_GRANTED_KEYWORD_ON_A_CARD_IN_A_ZONE",
    "_GRANTED_KEYWORD_SPELL_YOU_CAST_HAS",
    "_GREATEST_AMONG_CREATURES",
    "_HEXPROOF_ABILITY",
    "_KICKER_AND_OR",
    "_LINKED_EXILE_STATIC_CAST_RE",
    "_NUMBER_OF_SUBTYPES_YOU_CONTROL_RE",
    "_ONCE_EACH_TURN_CAST_FROM_GRAVEYARD",
    "_ONLY_MANA_SYMBOLS",
    "_OPPONENT_SPELL_COUNT_CONDITION",
    "_OPTIONAL_ADDITIONAL_COST",
    "_OPTIONAL_BEHOLD",
    "_OPTIONAL_BEHOLD_CHOSEN_TYPE",
    "_OPTIONAL_COLLECT_EVIDENCE",
    "_OPTIONAL_COST_KEYWORDS",
    "_OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND",
    "_OPTIONAL_REVEAL",
    "_OPTIONAL_SACRIFICE_ANY_NUMBER",
    "_OPTIONAL_WATERBEND",
    "_OPTIONAL_SACRIFICE_REDUCTION_LINE",
    "_OR_PAY_LIFE_TAIL",
    "_OR_PAY_TAIL",
    "_PAY_FIRST_OR",
    "_PAY_ONLY_MANA",
    "_PERMANENT_TYPES",
    "_PLAYER_KEYWORD_GRANT_LINE",
    "_PLAY_CARDS_EXILED_WITH_STATIC_RE",
    "_PRINTED_CAST_FROM_ZONE_USING_KEYWORD",
    "_PRINTED_PERMISSION_ZONES",
    "_PILE_PERMISSION_BODY_RE",
    "_PLAY_CARDS_EXILED_WITH_STATIC_RE",
    "_PRINTED_SELF_ZONE_CAST_RE",
    "_PRINTED_SELF_ZONE_CAST_WITH_ADDITIONAL_COST_RE",
    "_STATIC_ZONE_CAST_PERMISSION_RE",
    "_printed_self_zone_cast_additional_cost",
    "_QUALITY_PREFIX",
    "_QUALITY_SEPARATOR",
    "_REMINDER_TEXT",
    "_REMINDER_TEXT_RE",
    "_SPLICE_PARAMETER_RE",
    "_SPLICE_REMINDER_RE",
    "_STATIC_ZONE_CAST_BODY_RE",
    "_X_CAP",
    "_ZONE_WORDS_FOR_GRANTS",
    "_as_mana",
    "_cast_spells_from_a_zone",
    "_controls_that_object",
    "_count_listed_subtypes",
    "_describe_keyword_cost",
    "_grant_as_you_cast",
    "_grant_on_a_card_in_a_zone",
    "_grant_spell_you_cast_has_keyword",
    "_granted_option",
    "_graveyard_cast_grant_option",
    "_keyword",
    "_linked_exile_play_option",
    "_linked_exile_static_cast_option",
    "_opponents_exile_counter_cast_option",
    "_matches_splice_quality",
    "_normalized_spell_quality",
    "_once_each_turn_cast_from_graveyard",
    "_option_from_keyword",
    "_primary_alternatives_of",
    "_printed_alternative_total_cost",
    "printed_self_zone_cast",
    "_printed_self_zone_cast_with_additional_cost",
    "_printed_self_zone_cast_with_counters",
    "_printed_zone_permissions",
    "_rezoned_by_using",
    "_spell_matches_grant_filter",
    "_splice_parameter",
    "_spliced_rules_text",
    "_static_zone_cast_option",
    "_turn_number",
    "_using_keyword_permissions",
    "_warp_from_exile",
    "_why_not_in_own_declare_blockers_step",
    "_within_bound",
    "adventure_face",
    "annotate_exile",
    "castable_faces",
    "castable_from",
    "conditional_free_cast_condition",
    "conditional_free_cast_unavailable",
    "has_quality_flash_grant",
    "quality_flash_grant",
    "reads_quality_flash_grant_line",
    "printed_cast_only_zones",
    "casualty_cost_option",
    "casualty_cost_phrase",
    "class_gated_lines",
    "conditional_alternative_cost_offers",
    "printed_condition_refusal",
    "with_keyword_spell_ability_target",
    "conditional_flash_condition",
    "flash_surcharge",
    "conspire_cost_option",
    "exile_adventured",
    "exile_warped",
    "exiles_spells_cast_this_way",
    "face_being_cast",
    "finish_suspend",
    "grant_suspend_haste",
    "granted_cast_options",
    "granted_optional_additional_costs",
    "has_flash",
    "has_quality",
    "has_split_second",
    "hexproof_abilities_in",
    "hexproof_qualities_in",
    "is_top_of_library",
    "keyword_cast_options",
    "kicker_costs",
    "life_or_mana_additional_costs",
    "linked_exile_play_grant",
    "may_look_at_linked_exile",
    "linked_exile_play_source",
    "opponents_exile_counter_cast",
    "reads_opponents_exile_counter_cast_line",
    "linked_exile_static_cast",
    "mandatory_additional_costs",
    "marker_cast_options",
    "modal_dfc_spell_back_faces",
    "once_per_turn_key",
    "optional_additional_costs",
    "or_additional_cost_alternatives",
    "or_additional_cost_halves",
    "play_cards_exiled_with_line",
    "play_permissions_on",
    "player_keyword_grant_of_line",
    "reads_as_graveyard_cast_permission_line",
    "reads_granted_cast_spell_keyword_line",
    "reads_granted_zone_keyword_line",
    "reads_linked_exile_static_cast_line",
    "reads_mandatory_additional_cost_line",
    "reads_optional_exile_reduction_line",
    "reads_optional_sacrifice_reduction_line",
    "reads_or_pay_additional_cost_line",
    "reads_play_cards_exiled_with_line",
    "reads_granted_life_cost_line",
    "reads_printed_alternative_cost_line",
    "reads_printed_self_zone_cast_line",
    "reads_printed_zone_permission_line",
    "reads_search_cast_permission_line",
    "reads_static_zone_cast_permission_line",
    "search_cast_candidates",
    "reads_using_keyword_permission_line",
    "remove_suspend_time_counter",
    "spell_has_type_word",
    "splice_candidates",
    "split_second_restriction_source",
    "static_free_cast_grants",
    "static_grant_option",
    "static_free_cast_refusal",
    "static_zone_cast_permission",
    "static_permission_applies_now",
    "land_quality_allows",
    "record_graveyard_land_use",
    "static_graveyard_land_source",
    "strip_ability_word",
    "cast_condition_holds",
    "cast_condition_readable",
    "types_being_cast",
    "usable_play_permission",
    "using_keyword_permission",
    "why_cannot_cast_a_land",
    "why_cannot_cast_from",
    "why_cannot_cast_now",
    "why_cannot_cast_restriction",
    "why_cannot_cast_self_restriction",
    "why_mana_cost_unpayable",
]
