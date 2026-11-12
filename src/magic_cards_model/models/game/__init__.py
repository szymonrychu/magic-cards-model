"""A single game: the players, the shared zones, and where the turn is."""

import re
from collections.abc import Mapping
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import Field, PrivateAttr, model_validator

from ...machines.casting import (
    PlayPermission,
)
from ...machines.casting_restrictions import (
    CastingRuleEffect,
)
from ...machines.combat import (
    CombatMachine,
    EvasionNotice,
    KeywordLineNotice,
    UndefinedPowerNotice,
)
from ...machines.cost import (
    CostModifierNotice,
    CostPayment,
)
from ...machines.decisions import (
    DecisionScript,
    ask_mulligan,
)
from ...machines.delayed import (
    DelayedTriggers,
)
from ...machines.effects import (
    AnaphoricClauseNotice,
    CastFromHandExileNotice,
    ConditionalClauseNotice,
    ControlReplacementNotice,
    DelayedClauseNotice,
    ImprintNotice,
    LayerRemainderNotice,
    ModeNotice,
    PlayerSubjectSplitNotice,
    ReflexiveClauseNotice,
    SearchDescriptionNotice,
    SuspendRedirectNotice,
    UnmodeledTriggerEffectNotice,
    UnreadableCounterAmountNotice,
)
from ...machines.layers import (
    Characteristics,
    ContinuousEffects,
)
from ...machines.next_spell import (
    NextSpellFreeCastGrant,
    NextSpellKeywordGrant,
    SpellCostReductionGrant,
)
from ...machines.opening_hand import (
    OpeningHandNotice,
)
from ...machines.priority import PriorityMachine
from ...machines.replacement import (
    CreatedReplacement,
    NextTimeDrawReplacement,
    UnreadableCopyExceptionNotice,
    UnwiredChoiceNotice,
)
from ...machines.triggers import (
    AbilityOnStack,
    CastConditionNotice,
    GameEvent,
    InterveningIfNotice,
    TargetingNotice,
)
from ...machines.turn import (
    DayNight,
    Step,
    TurnMachine,
)
from ...serialization import SortedSet
from ...snapshot import EngineModel
from ..card import (
    Color,
)
from ..card_state import (
    CardState,
    TargetRef,
)
from ..mana import ManaPool
from ..player import Player
from ..zone import Zone

# isort: off
from ...machines.abilities import AbilityKind as AbilityKind
from contextlib import AbstractContextManager as AbstractContextManager
from ..action import Action as Action
from ...machines.abilities import ActivatedAbility as ActivatedAbility
from ...machines.casting import AlternativeCostOption as AlternativeCostOption
from ...machines.casting import AlternativeCostSource as AlternativeCostSource
from typing import Annotated as Annotated
from ...machines.combat import Attack as Attack
from ...machines.layers import BASIC_LAND_TYPES as BASIC_LAND_TYPES
from ...machines.layers import CANT_ACTIVATE_ABILITIES_TEXT as CANT_ACTIVATE_ABILITIES_TEXT
from collections.abc import Callable as Callable
from ..card import Card as Card
from ...machines.cost import CardRequirement as CardRequirement
from ...machines.decisions import CardSplit as CardSplit
from ...machines.casting import Casting as Casting
from ...machines.casting_restrictions import CastingRuleKind as CastingRuleKind
from ..card_state import ChoiceKind as ChoiceKind
from ...machines.cost import ComponentKind as ComponentKind
from ...machines.layers import ComputedBoard as ComputedBoard
from ...machines.layers import Condition as Condition
from pydantic import ConfigDict as ConfigDict
from ...machines.layers import ContinuousEffect as ContinuousEffect
from ...machines.cost import CostComponent as CostComponent
from ...machines.abilities import CostKind as CostKind
from ...machines.cost import CostModifierEffect as CostModifierEffect
from ...machines.cost import CostModifierKind as CostModifierKind
from ...machines.cost import CostStep as CostStep
from ...machines.abilities import CouldProduce as CouldProduce
from ..card_state import Counter as Counter
from ...machines.layers import DOESNT_UNTAP_TEXT as DOESNT_UNTAP_TEXT
from ...machines.decisions import Decision as Decision
from ...machines.decisions import DecisionKind as DecisionKind
from ...machines.decisions import DecisionPending as DecisionPending
from ...machines.delayed import DelayedEffectSpec as DelayedEffectSpec
from ...machines.delayed import DelayedEffectSpecBase as DelayedEffectSpecBase
from ...machines.delayed import DelayedTrigger as DelayedTrigger
from ...machines.layers import Duration as Duration
from ...machines.replacement import EventKind as EventKind
from ..card_state import ExileAnnotation as ExileAnnotation
from ..card_state import ExileMarker as ExileMarker
from ...machines.delayed import ExileWarped as ExileWarped
from ...machines.triggers import ExtraTriggerEvent as ExtraTriggerEvent
from collections.abc import Iterable as Iterable
from collections.abc import Iterator as Iterator
from ...machines.combat import Keyword as Keyword
from ...machines.casting import KeywordCastOption as KeywordCastOption
from ...machines.layers import LEGEND_RULE_EXEMPT_TEXT as LEGEND_RULE_EXEMPT_TEXT
from ...machines.layers import LOST_LIFE_TURN_FACT as LOST_LIFE_TURN_FACT
from ...machines.layers import Layer as Layer
from ...machines.layers import LayerContext as LayerContext
from ...machines.layers import LayerNotice as LayerNotice
from ..card import Layout as Layout
from typing import Literal as Literal
from ...machines.turn import MAIN_PHASES as MAIN_PHASES
from ...numbers import MULTIPLIER as MULTIPLIER
from ...machines.abilities import ManaAbilityRider as ManaAbilityRider
from ..mana import ManaCost as ManaCost
from ..mana import ManaRetentionScope as ManaRetentionScope
from ..mana import ManaSpend as ManaSpend
from ..mana import ManaSpendEffect as ManaSpendEffect
from ...machines.modes import ModalProfile as ModalProfile
from ...machines.modes import Mode as Mode
from uuid import NAMESPACE_OID as NAMESPACE_OID
from ...machines.effects import NO_FURTHER_MODES as NO_FURTHER_MODES
from ...machines.decisions import NamedManaAbility as NamedManaAbility
from typing import NamedTuple as NamedTuple
from ...machines.opening_hand import OpeningHandAction as OpeningHandAction
from ...machines.opening_hand import OpeningHandActionKind as OpeningHandActionKind
from ...machines.delayed import ParadigmCopyAndCast as ParadigmCopyAndCast
from ...machines.decisions import PendingAbility as PendingAbility
from ...machines.decisions import PendingDecision as PendingDecision
from ...machines.turn import Phase as Phase
from ...machines.casting import PlayAction as PlayAction
from ..player import PlayerTargetingGrant as PlayerTargetingGrant
from ...machines.priority import PriorityOutcome as PriorityOutcome
from random import Random as Random
from ...machines.replacement import ReplaceableEvent as ReplaceableEvent
from ...machines.targeting import RetargetScope as RetargetScope
from ...machines.layers import SPELLS_HAVE_SPLIT_SECOND_TEXT as SPELLS_HAVE_SPLIT_SECOND_TEXT
from ...machines.turn import STEP_SEQUENCE as STEP_SEQUENCE
from collections.abc import Sequence as Sequence
from ...serialization import SortedFrozenSet as SortedFrozenSet
from enum import StrEnum as StrEnum
from ..card import Supertype as Supertype
from ..mana import SymbolKind as SymbolKind
from ...machines.targeting import TargetRequirement as TargetRequirement
from ...machines.triggers import TargetingNoticeKind as TargetingNoticeKind
from ...machines.targeting import TargetingProfile as TargetingProfile
from ..token import TokenDefinition as TokenDefinition
from ..token import TokenState as TokenState
from ...machines.cost import TotalCost as TotalCost
from ...machines.abilities import TriggerEvent as TriggerEvent
from ...machines.abilities import TriggeredAbility as TriggeredAbility
from ..card import Type as Type
from ...machines.casting import _BLIGHT_PHRASE as _BLIGHT_PHRASE
from ...machines.casting import _OPTIONAL_ADDITIONAL_COST as _OPTIONAL_ADDITIONAL_COST
from ...machines.casting import _printed_alternative_total_cost as _printed_alternative_total_cost
from ...machines.triggers import activated_abilities_from_lines as activated_abilities_from_lines
from ...machines.triggers import activated_abilities_of as activated_abilities_of
from ...machines.cost import (
    activated_ability_group_discount_effect as activated_ability_group_discount_effect,
)
from ...machines.effects import activated_effect_for as activated_effect_for
from ...machines.triggers import added_ability_lines as added_ability_lines
from ...machines.cost import additional_cost_phrases as additional_cost_phrases
from ...machines.layers import additional_land_plays_of_line as additional_land_plays_of_line
from ...machines.layers import all_activated_abilities_grant as all_activated_abilities_grant
from ...machines.cost import alternative_cost_offers as alternative_cost_offers
from ...machines.cost import among_colors as among_colors
from ..card_state import annihilate_counters_on as annihilate_counters_on
from ...machines.casting import annotate_exile as annotate_exile
from ...machines.cost import announce_count as announce_count
from ...machines.cost import announce_reveal as announce_reveal
from ...machines.triggers import apnap_order as apnap_order
from ...machines.keywords import apply_as_enters_day_night as apply_as_enters_day_night
from ...machines.keywords import apply_daybound_nightbound as apply_daybound_nightbound
from ...machines.effects import apply_gift_if_promised as apply_gift_if_promised
from ...machines.replacement import apply_replacements as apply_replacements
from ...machines.keywords import ascend_as_a_spell_resolves as ascend_as_a_spell_resolves
from ...machines.decisions import ask_attackers as ask_attackers
from ...machines.decisions import ask_blockers as ask_blockers
from ...machines.decisions import ask_trigger_order as ask_trigger_order
from ...machines.keywords import attachment_state_based_actions as attachment_state_based_actions
from ...machines.keywords import aura_state_based_actions as aura_state_based_actions
from ...snapshot import board_snapshot as board_snapshot
from functools import cache as cache
from ...snapshot import cached_board as cached_board
from ...machines.casting_restrictions import cannot_be_copied as cannot_be_copied
from ...machines.casting_restrictions import cannot_be_countered as cannot_be_countered
from ...data.subtypes import canonical_subtype as canonical_subtype
from ...machines.casting import castable_faces as castable_faces
from ...machines.speed import check_speed_increase_on_life_loss as check_speed_increase_on_life_loss
from ...machines.casting_restrictions import (
    combat_lockdown_restriction_source as combat_lockdown_restriction_source,
)
from ...machines import combat as combat_rules  # noqa: F401
from ...snapshot import command as command
from ...machines.keyword_counters import (
    conditional_group_keyword_grant_of_line as conditional_group_keyword_grant_of_line,
)
from ...machines.casting_restrictions import (
    conditionally_cannot_be_countered as conditionally_cannot_be_countered,
)
from ...machines.keyword_counters import consume_shield_counter as consume_shield_counter
from contextlib import contextmanager as contextmanager
from ..token import copiable_card_of as copiable_card_of
from ...machines.cost import cost_announces_x as cost_announces_x
from ...machines.cost import cost_component_for_phrase as cost_component_for_phrase
from ...machines.cost import cost_modifier_effect as cost_modifier_effect
from ...numbers import count_pattern as count_pattern
from ...data.creature_types import creature_types as creature_types
from ...machines.decisions import damage_assignment_answer as damage_assignment_answer
from dataclasses import dataclass as dataclass
from ...machines.turn import day_night_after_untap_check as day_night_after_untap_check
from ...machines.decisions import default_answer as default_answer
from ...machines.effects import devotion_to as devotion_to
from ...machines.cost import discard_cost as discard_cost
from ...machines.layers import dont_cause_triggers_text as dont_cause_triggers_text
from ...machines.casting_restrictions import draw_cap_restriction as draw_cap_restriction
from ...machines.keywords import dredge as dredge
from ...machines.keywords import dredge_count as dredge_count
from ...machines.effects import effect_for as effect_for
from ...machines.effects import (
    effect_text_with_named_token_reminder as effect_text_with_named_token_reminder,
)
from ...machines import enlist as enlist
from ...machines.keywords import enters_transformed_at_night as enters_transformed_at_night
from ...machines.keyword_counters import (
    enters_with_counters_pronoun_fallback as enters_with_counters_pronoun_fallback,
)
from ...machines.keywords import equipment_state_based_actions as equipment_state_based_actions
from ...machines.counter_effects import event_count_target_text as event_count_target_text
from ...machines.cost import exile_cost as exile_cost
from ...machines.casting import face_being_cast as face_being_cast
from ...machines.targeting import face_spell_profile as face_spell_profile
from ...machines.layers import grant_ability as grant_ability
from ...machines.keywords import grant_enduring_stories as grant_enduring_stories
from ...machines.casting import grant_suspend_haste as grant_suspend_haste
from ...machines.keywords import grant_the_citys_blessing as grant_the_citys_blessing
from ...machines.triggers import granted_activated_abilities_of as granted_activated_abilities_of
from ...machines.casting import granted_cast_options as granted_cast_options
from ...machines.spell_grants import granted_hand_keyword_lines as granted_hand_keyword_lines
from ...machines.keywords import (
    granted_keyword_triggered_abilities as granted_keyword_triggered_abilities,
)
from ...machines.abilities import granted_mana_abilities as granted_mana_abilities
from ..card import has_changeling as has_changeling
from ...machines.combat import has_keyword as has_keyword
from ...machines.keywords import has_paradigm as has_paradigm
from ...machines.casting import has_quality as has_quality
from ...machines.keywords import has_rebound_now as has_rebound_now
from ...machines.keyword_counters import has_shield_counter as has_shield_counter
from ...machines.casting import hexproof_abilities_in as hexproof_abilities_in
from ...machines.cost import increase as increase
from ...ids import install_id_allocator as install_id_allocator
from ...machines.triggers import intervening_if_holds as intervening_if_holds
from ...data.card_names import is_card_name as is_card_name
from ...machines.cost import is_cave_source as is_cave_source
from ...machines.cost import is_creature_source as is_creature_source
from ...machines.keywords import is_indestructible as is_indestructible
from ..token import is_token as is_token
from ...machines.cost import is_treasure_source as is_treasure_source
import itertools as itertools
from ...machines.casting import keyword_cast_options as keyword_cast_options
from ...machines.keywords import keyword_effect_for as keyword_effect_for
from ...machines.keywords import keyword_triggered_abilities as keyword_triggered_abilities
from ...machines.combat import keywords_as_it_exists as keywords_as_it_exists
from ...machines.targeting import kicked_instead_target_text as kicked_instead_target_text
from ...machines.decisions import legal_options as legal_options
from ...machines.casting import life_or_mana_additional_costs as life_or_mana_additional_costs
from ...machines.effects import link_cards_exiled_as_cost as link_cards_exiled_as_cost
from ...machines.effects import link_cards_exiled_during as link_cards_exiled_during
from ...machines.casting import linked_exile_play_source as linked_exile_play_source
from ...machines.cost import looks_like_unparsed_cost_modifier as looks_like_unparsed_cost_modifier
from ...machines.casting_restrictions import (
    loyalty_activation_restriction as loyalty_activation_restriction,
)
from ...machines.cost import loyalty_cost as loyalty_cost
from ...machines.triggers import mana_ability_activated_event as mana_ability_activated_event
from ...machines.triggers import mana_added_event as mana_added_event
from ...machines.cost import mana_candidate_scan as mana_candidate_scan
from ...machines.casting import marker_cast_options as marker_cast_options
from ...machines.modes import modal_profile as modal_profile
from ...machines.effects import modal_trigger_profile as modal_trigger_profile
from ...machines.effects import mode_effect_body as mode_effect_body
from ...machines.monarch import monarch_effect_for as monarch_effect_for
from ...machines.monarch import inherent_triggers_for as monarch_inherent_triggers_for  # noqa: F401
from ...machines.keywords import morph_ability as morph_ability
from ..token import move_refused as move_refused
from ...ids import new_id as new_id
from ...machines.next_spell import next_spell_keyword_grants_for as next_spell_keyword_grants_for
from ...machines.layers import (
    off_battlefield_characteristics_of as off_battlefield_characteristics_of,
)
from ...machines.abilities import one_named_color as one_named_color
from ...machines.layers import only_this_incarnation as only_this_incarnation
from ...machines.casting import optional_additional_costs as optional_additional_costs
from ...machines.casting import or_additional_cost_alternatives as or_additional_cost_alternatives
from ...machines.delayed import paradigm_copy_and_cast as paradigm_copy_and_cast
from ...machines.abilities import parse_abilities as parse_abilities
from ...numbers import parse_count as parse_count
from ...machines.abilities import parse_mana_abilities as parse_mana_abilities
from ...numbers import parse_multiplier as parse_multiplier
from ...machines.abilities import parse_triggered_mana as parse_triggered_mana
from ...machines.objects_as_costs import convoke as pay_convoke  # noqa: F401
from ...machines.objects_as_costs import delve as pay_delve  # noqa: F401
from ...machines.objects_as_costs import improvise as pay_improvise  # noqa: F401
from ...machines.opening_hand import perform_rider as perform_rider
from ...machines.cost import plan_mana_payment as plan_mana_payment
from ..card_state import planeswalkers_with_zero_loyalty as planeswalkers_with_zero_loyalty
from ...machines.casting import play_permissions_on as play_permissions_on
from ...machines.casting import player_keyword_grant_of_line as player_keyword_grant_of_line
from ...machines.speed import players_starting_their_engines as players_starting_their_engines
from ...machines.layers import plays_lands_from_graveyard_line as plays_lands_from_graveyard_line
from ...machines.targeting import profile_for_modes as profile_for_modes
from ...machines.targeting import profile_for_modes_with_owners as profile_for_modes_with_owners
from ...machines.targeting import profile_for_text as profile_for_text
from ...machines.opening_hand import read_opening_hand_actions as read_opening_hand_actions
from ...machines.delayed import rebound_recast as rebound_recast
from ...machines.targeting import reflexive_consequence_text as reflexive_consequence_text
from dataclasses import replace as replace
from ...machines.replacement import replace_mana_production as replace_mana_production
from ...ids import reset_id_allocator as reset_id_allocator
from ...machines.triggers import resolution_key as resolution_key
from ...machines.abilities import resolve_mana_count_expression as resolve_mana_count_expression
from ...data.printing_pool import resolve_printing as resolve_printing
from ...machines.delayed import return_subject_to_hand as return_subject_to_hand
from ...machines.triggers import rewritten_ability_lines as rewritten_ability_lines
from ...machines.decisions import rule_for_kind as rule_for_kind
from ...machines.cost import sacrifice_cost as sacrifice_cost
from ...snapshot import scan_pin as scan_pin
from ...machines.casting_restrictions import search_prohibition_source as search_prohibition_source
from ...machines.abilities import self_normalized_effect_text as self_normalized_effect_text
from ...machines.abilities import self_reference_names as self_reference_names
from ...machines.unspent_mana import settle_mana_loss as settle_mana_loss
from ...machines.combat import source_had_keyword as source_had_keyword
from ...machines.decisions import source_id_of as source_id_of
from ...machines.next_spell import spell_has_quality as spell_has_quality
from ...machines.targeting import spell_profile_for_text as spell_profile_for_text
from ...machines.casting_restrictions import (
    spell_protected_from_countering as spell_protected_from_countering,
)
from ...machines.layers import spend_effect_effects as spend_effect_effects
from ...machines.cost import spend_restriction as spend_restriction
from ...machines.casting import split_second_restriction_source as split_second_restriction_source
from ...machines.speed import start_engines as start_engines
from ...machines.triggers import state_triggers_for as state_triggers_for
from ...machines.casting import static_free_cast_grants as static_free_cast_grants
from ...machines.casting import static_free_cast_refusal as static_free_cast_refusal
from ...machines.casting import static_zone_cast_permission as static_zone_cast_permission
from ...machines.modes import substitute_x as substitute_x
from ...machines.cost import tap_cost as tap_cost
from ...machines.triggers import tapped_for_mana_event as tapped_for_mana_event
from ...machines.targeting import targeting_profile as targeting_profile
from ...machines.teamwork import teamwork_instead_target_text as teamwork_instead_target_text
from ..token import tokens_that_cease_to_exist as tokens_that_cease_to_exist
from ...machines.cost import total_cost_for_phrase as total_cost_for_phrase
from ...machines.keywords import transform_for_day_night as transform_for_day_night
from ...machines.effects import trigger_effect_for as trigger_effect_for
from ...machines.triggers import triggers_for as triggers_for
from ...machines.keywords import turn_face_up_ban as turn_face_up_ban
from ...machines.keywords import turn_face_up_cost as turn_face_up_cost
from ...machines.casting import types_being_cast as types_being_cast
from ...machines.special_actions import unlock_cost as unlock_cost
from ...machines.cost import untap_cost as untap_cost
from ...machines.casting import usable_play_permission as usable_play_permission
from uuid import uuid5 as uuid5
from ...machines.casting import why_cannot_cast_restriction as why_cannot_cast_restriction
from ...machines.keywords import why_cannot_dredge as why_cannot_dredge
from ...machines.keywords import why_cannot_turn_face_up as why_cannot_turn_face_up
from ...machines.special_actions import why_cannot_turn_face_up_as as why_cannot_turn_face_up_as
from ...machines.special_actions import why_cannot_unlock_door as why_cannot_unlock_door
from ...machines.special_actions import why_cannot_unlock_door_as as why_cannot_unlock_door_as
from ...machines.cost import why_payer_cannot_use as why_payer_cannot_use
from ..card import with_every_creature_type as with_every_creature_type
from ...machines.modes import x_restriction_refusal as x_restriction_refusal
from ._costs_mana import (
    CostsManaMixin,
    _AFFINITY_CARD_TYPES,
    _AFFINITY_RE,
    _AFFINITY_SUBTYPES,
    _COSTS_LESS_IF_CONDITION_RE,
    _COSTS_LESS_IF_LIFE_TOTAL_VS_STARTING_X_IS_DIFFERENCE_RE,
    _COSTS_LESS_IF_TARGETS_DESCRIPTION_RE,
    _COSTS_LESS_IF_TARGETS_SPELL_RE,
    _COSTS_LESS_PER_BASIC_LAND_TYPE_RE,
    _COSTS_LESS_PER_CARD_DISCARDED_RE,
    _COSTS_LESS_PER_CARD_TYPE,
    _COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE,
    _COSTS_LESS_PER_QUALITY_CARD_IN_GRAVEYARD_RE,
    _COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE,
    _COSTS_LESS_X_WHERE_X_IS_RE,
    _COSTS_LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE,
    _LOOKS_LIKE_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE,
    _SELF_COST_REDUCTION_SHAPES,
    _SELF_REFERENCE,
    _activate_named_mana_abilities,
    _cost_moved,
    _cost_refers_to_self,
    _named_mana_abilities,
    reads_self_cost_reduction_line,
)
from ._common import (
    ENERGY_PAID_OR_LOST,
    StackObject,
    Targetable,
    _ABILITY_WORD_PREFIX_RE,
    _CAST_THIS_TURN_QUALITY_RE,
    _COLOR_COUNT_QUALITIES,
    _COLOR_WORDS,
    _DAMAGE_CANT_BE_PREVENTED_RE,
    _DRAW_OR_LIFE_GAIN_PROHIBITION_RE,
    _DRAW_PROHIBITION_RE,
    _EACH_OPPONENT_PROTECTION_QUALITY,
    _LEGENDARY_TYPE_COUNT_POWER_RE,
    _LIFE_GAIN_PROHIBITION_RE,
    _SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE,
)
from .records import (
    ActivationInstructions,
    ActivationProhibition,
    CastRecord,
    CombatDamageToPlayer,
    CountersPutRecord,
    DamageDealt,
    ExileArrival,
    GraveyardArrival,
    KnownCard,
    KnownCarry,
    LibraryOrderKept,
    LoyaltyInstantSpeedPermission,
    ObjectCostOffer,
    PreventionShield,
    ReflectedDamage,
    ShieldSourceFilter,
    Reveal,
    SchemaVersionMismatch,
    ShieldKind,
    TurnHistoryEntry,
    UntapStepRule,
)
from ._zones import (
    ZonesMixin,
    _ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE,
    _EXILE_THIS_PERMANENT,
    _LIBRARY_MOVEMENT,
    _LOOKS_LIKE_DRAW_PROHIBITION_RE,
    _exiles_itself_by_name,
    entered_type_facts,
    moves_a_library_card,
)
from ._casting import (
    CastingMixin,
    _CONDITIONAL_ADDITIONAL_LAND_PLAYS_RE,
    _SPELLS_THAT_ARE_QUALITY_RE,
    _is_cast_this_turn_quality,
    _is_spell_quality,
    _spell_colour_quality,
    conditional_additional_land_plays_of_line,
)
from ._continuous import (
    ContinuousMixin,
    RING_EMBLEM_ABILITIES,
    RING_EMBLEM_NAME,
    _COMBAT_KEYWORDS,
    _MANA_VALUE_QUALITY_RE,
    _PLAYER_COUNTERS_PROHIBITION_RE,
    _card_characteristics,
    _characteristic_quality,
    _characteristic_word,
    _emblem_card,
    is_player_rules_static_line,
    ring_emblem_text,
)
from ._conditions import (
    ConditionsMixin,
    _ACTIVATE_ONLY_IF,
    _AND_AN,
    _AND_ONLY_TAIL,
    _A_QUALITY,
    _CONDITION_ADDITIONAL_COST_PAID,
    _CONDITION_ATTACKED_WITH_N,
    _CONDITION_CAST_A_SPELL_THIS_TURN,
    _CONDITION_CAST_FROM_GRAVEYARD,
    _CONDITION_CAST_USING_TEAMWORK,
    _CONDITION_CONTROLS_A,
    _CONDITION_CONTROLS_ANOTHER,
    _CONDITION_CONTROLS_N,
    _CONDITION_CONTROLS_NAMED_PAIR,
    _CONDITION_CREATURES_DIED_THIS_TURN,
    _CONDITION_CREATURE_DIED_THIS_TURN,
    _CONDITION_DESCENDED,
    _CONDITION_ENTERED_THIS_TURN,
    _CONDITION_GIFT_PROMISED,
    _CONDITION_GRAVEYARD_CARDS,
    _CONDITION_HAND_CARDS,
    _CONDITION_KICKED,
    _CONDITION_LAND_ENTERED_THIS_TURN,
    _CONDITION_LIBRARY_EMPTY_RE,
    _CONDITION_LOYALTY_AMONG_NAMED,
    _CONDITION_NOT_CAST_FROM_HAND,
    _CONDITION_OPPONENT_CAST_COLOR,
    _CONDITION_OPPONENT_COMPARISON,
    _CONDITION_OPPONENT_GRAVEYARD_CARDS,
    _CONDITION_OPPONENT_NONCOMBAT_DAMAGE_THIS_TURN,
    _CONDITION_OPPONENT_POISON,
    _CONDITION_OR_IF,
    _CONDITION_PATTERNS,
    _CONDITION_POWER,
    _CONDITION_SACRIFICED_THIS_TURN,
    _CONDITION_SCRIED_OR_SURVEILLED_THIS_TURN,
    _CONDITION_SELF_COUNTERS,
    _CONDITION_SELF_ENTERED_THIS_TURN,
    _CONDITION_SELF_IS_A_CREATURE,
    _CONDITION_SELF_NO_COUNTERS,
    _CONDITION_SPELLS_CAST_THIS_TURN,
    _CONDITION_SUSPENDED,
    _CONDITION_TYPES_AMONG_GRAVEYARD,
    _CONDITION_YOU_ATTACKED_THIS_TURN,
    _PERMANENT_TYPES,
    _PROTECTION,
    _REMINDER_TEXT,
    _SYMBOL_THRESHOLD_EXILE_COST,
    _UNRESOLVED_PROTECTION_QUALITY,
    _card_quality,
    _card_type_named,
    _condition_alternatives,
    _has_color_quality,
    _is_minus_symbol,
    _names_match,
    _names_the_source,
    _negated_card_type_named,
    _permanent_quality,
    _qualities_from_text,
    _symbol_threshold_exile_component,
    builtin_condition_readable,
    colored_symbol_count,
    condition_is_readable,
    symbol_threshold_exile_cost,
)
from ._activation import (
    ActivationMixin,
    _ACTIVATE_LEAD,
    _ACTIVATION_PROHIBITION_RE,
    _ACTIVATION_WINDOW,
    _CHOSEN_NAME_PROHIBITION_RE,
    _CHOSEN_NAME_SUBJECT_RE,
    _HASTE_ACTIVATION_PERMISSION_RE,
    _LOOKS_LIKE_ACTIVATION_PROHIBITION_RE,
    _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE,
    _LOYALTY_INSTANT_SPEED_STATIC_RE,
    _RESTRICTION_DURING,
    _RESTRICTION_IF,
    _RESTRICTION_INSTANT,
    _RESTRICTION_JOIN,
    _RESTRICTION_ONCE,
    _RESTRICTION_PER_TURN,
    _RESTRICTION_SORCERY,
    _SACRIFICE_A_AND_A,
    _SACRIFICE_OR_DISCARD,
    _SELF_LOYALTY_INSTANT_SPEED_RE,
    _STEP_NAMES,
    _WHO_MAY_ACTIVATE,
    _activation_condition,
    _parse_activation_prohibition,
    read_activation_instructions,
    reads_activation_rule_line,
)
from ._stack_priority import (
    StackPriorityMixin,
    _PLAYER_PROTECTION_FROM_CHOSEN_NAME,
    _TARGET_PLAYER_BEFORE_THAT_PLAYER_RE,
    _THAT_PLAYER_BINDING_RE,
    _illegal_option_refusal,
    _that_player_of,
    protection_qualities,
    protection_quality_readable,
)
from ._turn_sba import TurnSbaMixin, _ZERO_LOYALTY_EXEMPTION_RE
from ._damage_life import DamageLifeMixin, _LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE
from ._combat import CombatMixin, attacked_with_type_facts
from ._triggers_decisions import TriggersDecisionsMixin
# isort: on


class _FlatMixins(type(EngineModel)):
    """Folds the plain-class bases into one generated base, keeping the MRO short."""

    _CLASS_ONLY = frozenset(
        ("__module__", "__qualname__", "__doc__", "__dict__", "__weakref__")
        + ("__firstlineno__", "__static_attributes__")
    )

    def __new__(mcs, name, bases, namespace, **kwargs):
        mixins = [b for b in bases if type(b) is type]
        if mixins:
            members = {}
            for mixin in reversed(mixins):
                members.update((k, v) for k, v in vars(mixin).items() if k not in mcs._CLASS_ONLY)
            folded = type(f"_{name}Mixins", (), members)
            bases = (folded, *(b for b in bases if type(b) is not type))
        return super().__new__(mcs, name, bases, namespace, **kwargs)


class Game(
    ZonesMixin,
    ActivationMixin,
    StackPriorityMixin,
    CostsManaMixin,
    CastingMixin,
    TurnSbaMixin,
    ContinuousMixin,
    ConditionsMixin,
    DamageLifeMixin,
    CombatMixin,
    TriggersDecisionsMixin,
    EngineModel,
    metaclass=_FlatMixins,
):
    """One game of Magic, from the first untap step to somebody winning.

    Holds the four shared zones. The per-player zones - library, hand,
    graveyard, sideboard - belong to each `Player`.
    """

    players: list[Player] = Field(min_length=1)
    turn: TurnMachine | None = None
    shared_zones: dict[Zone, list[StackObject]] = Field(
        default_factory=lambda: {
            Zone.BATTLEFIELD: [],
            Zone.STACK: [],
            Zone.EXILE: [],
            Zone.COMMAND: [],
            # CR 400.1's optional eighth zone, shared like the rest of these.
            # Empty in every game that is not being played for ante (CR 407.2).
            Zone.ANTE: [],
        }
    )
    priority: PriorityMachine | None = None
    combat: CombatMachine = Field(default_factory=CombatMachine)
    lands_played: dict[str, int] = Field(default_factory=dict)
    extra_land_plays: dict[str, int] = Field(default_factory=dict)
    """CR 305.2's allowance increase, granted for one turn by a *resolving*
    effect rather than a permanent's own static ability - Way of the
    Paradox's own "You may play an additional land this turn.", read fresh
    each turn alongside `lands_played` (`Game.begin_turn`'s own reset).
    `land_allowance` adds this to `additional_land_plays`'s static-ability
    count rather than replacing it, so a player with both a static grant and
    a resolved one gets the sum, the same way CR 305.2's "however, continuous
    effects may increase this number" stacks any number of independent
    grants."""
    casting_rule_effects: list[CastingRuleEffect] = Field(default_factory=list)
    """CR 611.1's third kind of continuous effect - one that "affects players
    or the rules of the game" rather than any object's characteristics, so
    the layer system (CR 613) has nothing to compute for it. Ranger-Captain of
    Eos's "Your opponents can't cast noncreature spells this turn" is
    recorded here when its sacrifice-cost ability resolves, and Teferi, Time
    Raveler's "+1: Until your next turn, you may cast sorcery spells as
    though they had flash" is recorded here too - both outlive the instant
    they were created, unlike Teferi's *other* half (his static restricting
    opponents to sorcery-speed timing), which is read straight off the
    battlefield by `machines.casting_restrictions.sorcery_speed_restriction_
    source` and needs no record at all. `cleanup_step` drops the
    "until end of turn" entries and `begin_turn_for` drops the "until your
    next turn" ones, exactly as `play_permissions` already does for its own
    two durations."""
    loyalty_instant_speed_permissions: list[LoyaltyInstantSpeedPermission] = Field(
        default_factory=list
    )
    """CR 606.3's timing loosened for particular planeswalkers - see
    `LoyaltyInstantSpeedPermission`. Checked by `why_cannot_activate`,
    dropped in the cleanup step for the "until end of turn" entries
    (`until_end_of_turn=True`), the same way `play_permissions`' own
    "until end of turn" grants are."""
    play_permissions: list[PlayPermission] = Field(default_factory=list)
    """CR 601.3's dynamic half: permissions a resolving effect handed out to
    specific cards - Ugin, Eye of the Storms' −11, Ragavan, Nimble Pilferer's
    combat-damage trigger. Granted through `grant_play_permission`, read
    through `machines/casting.usable_play_permission`, and dropped in the
    cleanup step (CR 514.2). Deliberately a list of per-object records rather
    than a flag on the cards: see `PlayPermission`'s own docstring."""
    winner: str | None = None
    drawn: bool = False
    """Whether the game ended in a draw (CR 104.4a).

    "If all the players remaining in a game lose simultaneously, the game is a
    draw." `check_state_based_actions` sets this when every player still in the
    game would lose at the same state-based-action check: nobody wins (CR 104.2a
    needs a player still in the game) and `winner` stays None, but the game ends
    immediately all the same (CR 104.1), which is why `is_over` reads this too.
    CR 104.5 sends a player the game is a draw for out of the game, so the
    losers still leave and their objects go with them (CR 800.4a).

    Not the whole of CR 104.4. **CR 104.4b's mandatory-action loop is detected
    in exactly one shape and no other**: a chain of CR 605.1b triggered mana
    abilities resolving inline off a single activation, bounded by
    `resolve_triggered_mana_abilities`. That is DDR#990's Caged Sun under Toph,
    the First Metalbender, where CR 605.4a keeps every link off the stack so no
    player ever receives priority to break it. This is *not* general loop
    detection: a loop built out of anything that does reach the stack, or out of
    replacement effects, or out of two permanents triggering each other, is
    still undetected and will hang or recurse rather than draw.

    CR 104.4c's "an effect may state that the
    game is a draw" needs a registry effect to reach, which none has -
    `end_in_draw` is the staging entry for both. The teams variant (CR 104.4d)
    is outside the free-for-all defaults this model plays.
    """

    conceded: list[str] = Field(default_factory=list)
    losers: list[str] = Field(default_factory=list)
    fizzled: list[UUID] = Field(default_factory=list)
    """Spells that were removed from the stack without resolving (CR 608.2b)."""

    pending_triggers: list[AbilityOnStack] = Field(default_factory=list)
    """Abilities that have triggered but are not on the stack yet (CR 603.2, 603.3).

    "The ability doesn't do anything at this point" - it waits here until the
    next time a player would receive priority, which is what
    `put_triggers_on_stack` represents.
    """

    trigger_targets: dict[str, list[TargetRef]] = Field(default_factory=dict)
    """What a triggered ability will target, keyed by its source's card name.

    CR 603.3d: choosing a trigger's targets is part of putting it on the stack,
    and follows the same rules as CR 601.2c-d. There is no player here to ask,
    so a scenario says in advance what a given card's trigger aims at.
    """

    creatures_cant_attack_until_turns_taken: int | None = None
    """CR 508.1c: "restrictions (effects that say a creature can't attack...)"
    - Orim's Chant's kicked "creatures can't attack this turn" is a blanket
    one, over every creature any player controls, not read off any single
    permanent's own static text the way `combat.has_keyword`'s `Keyword.
    DEFENDER` check is. Recorded as the `TurnMachine.turns_taken` value the
    turn it was granted on, the same "this turn" comparison `PlayPermission.
    expired` already makes for its own `granted_turns_taken` - simpler than a
    `casting_rule_effects`-style list, since nothing in the pool prints this
    restriction more than once at a time or needs to say who granted it.
    `combat.attack_refusal` reads it directly; nothing needs to clear it
    early, since the comparison itself goes stale the moment the turn ends."""

    phased_out: list[CardState] = Field(default_factory=list)
    """Permanents that are phased out (CR 702.26b), in the order they
    phased out.

    CR 702.26b: "a phased-out permanent is treated as though it does not
    exist. It can't affect or be affected by anything else in the game." So
    it is held here rather than in `battlefield`, which is what every reader
    of the battlefield - combat, targeting, the layer system's selectors,
    state-based actions, counts, `find_by_id` - walks: none of them has to
    learn to skip it. CR 702.26d keeps its `zone` at `Zone.BATTLEFIELD`
    (phasing is no zone change), its counters, and a token's existence.
    `Game.phase_out` and `Game.phase_in` are the only writers.
    """

    players_skipping_next_untap: dict[str, int] = Field(default_factory=dict)
    """How many of a username's upcoming untap steps are replaced with
    nothing (CR 614.10: "skip [something]" is a replacement effect). Brine
    Elemental's "each opponent skips their next untap step" is the only card
    in the pool that grants this; `untap_step` decrements one entry per
    skipped step and drops the key once it reaches zero. A count rather than
    a flag on purpose, so two stacked grants (two Brine Elementals turned
    face up against the same opponent) cost that opponent two untap steps,
    matching CR 614.10a's "waits for the first occurrence that isn't
    skipped" read once per grant.
    """

    targeting_notices: list[TargetingNotice] = Field(default_factory=list)
    """One entry per triggered ability whose targets could not be worked out
    normally (`Game._ask_trigger_targets`) - either the restriction itself was
    unreadable, or it was read fine but nothing on the battlefield satisfies
    it right now. Both leave the ability on the stack with no targets
    (CR 603.3d's outcome is unchanged either way); this is only the record of
    which of the two happened, so a gap in the parser stays visible instead of
    looking identical to a legal "nothing to target"."""

    intervening_if_notices: list[InterveningIfNotice] = Field(default_factory=list)
    """One entry per triggered ability whose intervening *if* clause
    (CR 603.4) could not be evaluated. `intervening_if_holds` fails such a
    clause closed - the ability does not trigger - and records it here rather
    than leaving that indistinguishable from a clause that was read and found
    false."""

    cast_condition_notices: list[CastConditionNotice] = Field(default_factory=list)
    """One entry per "Whenever you cast a ... spell" condition (CR 601.2,
    603.2) that named a mana-value restriction `condition_matches` recognised
    but could not parse into a number and a direction. The condition fails
    closed - the ability does not trigger - rather than being treated as
    unrestricted, the same "recognised but unreadable is not the same as
    absent" reasoning `intervening_if_notices` already applies."""

    mode_notices: list[ModeNotice] = Field(default_factory=list)
    """One entry per chosen mode of a resolving modal spell (CR 700.2a) whose
    text `resolve_modal_spell` could not read into an effect - the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps, so a mode that silently does nothing is not indistinguishable
    from one that legitimately has nothing left to do."""

    cost_modifier_notices: list[CostModifierNotice] = Field(default_factory=list)
    """One entry per permanent whose static cost-modifying text
    (`static_cost_modifiers_for`) could not be read into one of
    `cost_modifier_effect`'s recognised shapes - a card whose text
    `looks_like_unparsed_cost_modifier` flags as a cost sentence this cannot
    yet classify. A cost increase that silently fails to apply looks
    identical to ordinary play, which is the DDR#978 defect this is written
    against; recording it here keeps the gap visible instead."""

    anaphoric_clause_notices: list[AnaphoricClauseNotice] = Field(default_factory=list)
    """One entry per "<verb> target X. Its/that X's controller ..." effect
    whose anaphoric second sentence (CR 400.7) could not be read - Solitude's
    own defect: it used to exile a legally-targeted creature and gain no life
    at all, with nothing anywhere recording that the second sentence had gone
    unread. The same unreadable-is-not-the-same-as-no-effect record every
    other notice list here keeps."""

    layer_remainder_notices: list[LayerRemainderNotice] = Field(default_factory=list)
    """One entry per multi-sentence resolution whose CR 611.2 layer sentence
    (a pump, a keyword grant, a base P/T set) ran, but a sibling sentence in
    the same paragraph is not a layer shape and could not be read either -
    Academic Ascent's own "Empower Jace 2." used to be silently dropped the
    moment the pump sentence routed the *whole* text to `create_continuous_
    effect`. See `LayerRemainderNotice`."""

    player_subject_split_notices: list[PlayerSubjectSplitNotice] = Field(default_factory=list)
    """One entry per "You and `<group>` gain `<keyword(s)>` until end of
    turn" compound subject (Veil of Summer's own third sentence) whose
    player half is read but not yet granted - see
    `PlayerSubjectSplitNotice`."""

    search_description_notices: list[SearchDescriptionNotice] = Field(default_factory=list)
    """Library searches whose card description could not be read, so the
    search was not run at all (CR 701.23a) - see `SearchDescriptionNotice`."""

    imprint_notices: list[ImprintNotice] = Field(default_factory=list)
    """One entry per "you may exile a `<quality>` card ... from your hand"
    effect (CR 207.2c's "Imprint" ability word among them) whose stated
    quality could not be read - Ugin's Labyrinth's own defect: its imprint
    trigger used to resolve offering no decision at all, with nothing anywhere
    recording that a choice had gone unoffered. The same unreadable-is-not-
    the-same-as-no-effect record every other notice list here keeps."""

    cast_from_hand_exile_notices: list[CastFromHandExileNotice] = Field(default_factory=list)
    """One entry per "Whenever a player casts a spell from their hand, that
    player exiles it[, ...]" effect (Knowledge Pool's, Possibility Storm's)
    whose tail - what happens after the exile - this wave could not read.
    Knowledge Pool's own reported defect: ability 2 used to resolve, put
    nothing in exile, grant no free cast, and leave the cast spell sitting on
    the stack, with nothing anywhere recording that a clause had gone
    unread. The same unreadable-is-not-the-same-as-no-effect record every
    other notice list here keeps."""

    conditional_clause_notices: list[ConditionalClauseNotice] = Field(default_factory=list)
    """One entry per "you may sacrifice `<restriction>`. If you do,
    `<consequence>`." effect (CR 118.12) whose restriction or consequence
    could not be read - Disciple of Freyalise's and Sanctum of Ugin's own
    defect before this list existed: both used to resolve offering no choice
    at all, with nothing anywhere recording that a choice had gone unoffered.
    The same unreadable-is-not-the-same-as-no-effect record every other
    notice list here keeps."""

    reflexive_clause_notices: list[ReflexiveClauseNotice] = Field(default_factory=list)
    """One entry per "`<action>`. When you do, `<consequence>`." effect
    (CR 603.12) whose action or consequence could not be read - Guide of
    Souls' own defect before this list existed: its attack trigger's "you may
    pay {E}{E}{E}" resolved offering no choice at all (paying energy is a
    missing primitive, `docs/engine-coverage.md`), with nothing anywhere
    recording that a choice had gone unoffered. The same unreadable-is-not-
    the-same-as-no-effect record every other notice list here keeps."""

    unwired_choice_notices: list[UnwiredChoiceNotice] = Field(default_factory=list)
    """One entry per sentence of a card that reads back its own CR 614.12a
    "as [this] enters, choose ..." answer in a shape this wave does not
    perform - Runed Halo's player-granted protection, Pithing Needle's and
    Disruptor Flute's activation/casting restrictions by name, Cavern of
    Souls' restricted-mana grant. See `UnwiredChoiceNotice` for why each of
    the four is out of scope and what would be needed to wire it. The one
    payoff this wave performs end to end - "adds an additional ..." mana - is
    excluded from this list entirely, and Voice of All's permanent-targeted
    protection grant already gets a `LayerNotice` for free from the existing
    static-ability sweep, so it is not duplicated here either."""

    unreadable_copy_exception_notices: list[UnreadableCopyExceptionNotice] = Field(
        default_factory=list
    )
    """One entry per "enter as a copy of X, except ..." replacement whose
    exception tail this session's parser could not read - see
    `UnreadableCopyExceptionNotice`. Recorded instead of silently applying the
    copy with no exception, which is the fix for a real defect: Echoing Deeps
    copying a graveyard land without ever becoming a Cave, because a `None`
    meaning "unreadable" and a `None` meaning "nothing printed" collapsed into
    the same `effect.copy_exception or CopyException()` default."""

    unreadable_counter_amount_notices: list[UnreadableCounterAmountNotice] = Field(
        default_factory=list
    )
    """One entry per "counters ... equal to `<expr>`" whose expression
    `machines/effects.amount_expression` could not evaluate - see
    `UnreadableCounterAmountNotice`. The counters are not placed: a guessed
    number is worse than none, and Slumbering Trudge's "three minus X" used to
    be skipped here with nothing recorded at all."""

    suspend_redirect_notices: list[SuspendRedirectNotice] = Field(default_factory=list)
    """Retired: nothing writes here any more. Delay's "... exile it with N
    time counters ... If it doesn't have suspend, it gains suspend." used to
    fail closed into this list; it is now executed by `machines/effects.
    _parse_exile_into_suspend_clauses`. The field stays only so the persisted
    shape of a `Game` - and so `schema_version` - is unchanged; drop it with
    the next schema bump."""

    delayed_clause_notices: list[DelayedClauseNotice] = Field(default_factory=list)
    """One entry per delayed-trigger clause (CR 603.7) whose timing this wave
    recognised but whose antecedent or verb it still could not read - Phelia,
    Exuberant Shepherd's own defect before this list existed: its attack
    trigger exiled a legal target and never returned it, with nothing
    recording that the second and third sentences had gone unread. Postmortem
    Lunge and Nahiri, the Harbinger's -8 land here too: both name a delayed
    return, but off an antecedent (a variable-mana-value reanimation target, a
    search result) this wave does not yet capture."""

    evasion_notices: list[EvasionNotice] = Field(default_factory=list)
    """One entry per attacker whose own "can't be blocked" restriction text
    (CR 509.1b) `combat.block_refusal` could read as an attempt at the shape
    but not fully parse - see `combat.evasion_restriction_refusal`'s own
    docstring for the shapes read; anything outside them fails closed here
    instead of a block silently going through unrestricted, the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps."""

    keyword_line_notices: list[KeywordLineNotice] = Field(default_factory=list)
    """One entry per computed ability line (CR 613.5) that is part CR 702
    keyword and part something `machines/combat.py`'s reading vocabulary cannot
    name - Nevinyrral, Urborg
    Tyrant's "Hexproof from artifacts, creatures, and enchantments", which
    CR 702.11f makes shorthand for several separate abilities. The line is
    dropped whole rather than half-read, because half-reading it would grant an
    ability unconditionally that the card grants conditionally; this is the
    record that it was dropped, the same unreadable-is-not-the-same-as-no-effect
    entry `EvasionNotice` and `UndefinedPowerNotice` keep. Before this list
    existed the drop was silent, which is how Emrakul, the Promised End lost
    flying and trample on the computed board with nothing saying so."""

    undefined_power_notices: list[UndefinedPowerNotice] = Field(default_factory=list)
    """One entry per creature `combat._power_of` was asked to assign combat
    damage for but could not compute a power for - a printed `*` with no
    characteristic-defining ability the engine reads. `power or 0` used to
    fold that into a real 0 rather than record the gap; now the creature
    assigns no combat damage for the step and this is why, the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps."""

    unmodeled_trigger_effect_notices: list[UnmodeledTriggerEffectNotice] = Field(
        default_factory=list
    )
    """One entry per triggered ability whose condition fired for real but whose
    resolution clause names a mechanism this engine has no primitive for at
    all - a per-instance cast permission, an unbounded card-count choice, a
    target restricted by the trigger event rather than the ability's own
    printed text. See `UnmodeledTriggerEffectNotice`'s own docstring for the
    three cases this wave found (Ragavan, Nashi, Questing Beast). The same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps.

    Also one entry per resolving instant or sorcery face `effect_for` has no
    reader for at all (`Game.resolve`), carrying the spell's id and name and
    the face's whole printed text - a spell that leaves a replacement effect
    (Plagiarize) is not one.

    And one entry per resolving triggered ability with printed effect text
    that `_effect_of` has no reader for (`Game._note_unread_trigger`),
    carrying the source's id and name and the ability's whole effect text."""

    control_replacement_notices: list[ControlReplacementNotice] = Field(default_factory=list)
    """One entry per resolving spell whose text reads as a CR 614.1a
    "if [a permanent] would enter the battlefield under [a player]'s
    control, it enters under [another player]'s control instead" in a
    wording `machines/replacement.created_replacement_spec` does not read -
    the fail-closed net behind Gather Specimens' own, which is built
    (`created_replacements`). See `ControlReplacementNotice`."""

    opening_hand_notices: list[OpeningHandNotice] = Field(default_factory=list)
    """One entry per card paragraph that claims a CR 103.6 opening-hand action
    the engine did not carry out - a paragraph that mentions an opening hand but
    matches neither CR 103.6a's nor CR 103.6b's template, or one that matches but
    carries a rider `machines/opening_hand.read_rider` cannot read. The
    action is then not offered at all, so nothing reads as permission while doing
    less than the card says. The same unreadable-is-not-the-same-as-no-effect
    record every other notice list here keeps."""

    opening_hand_actions_taken: bool = False
    """Whether CR 103.6's sequence has already run for this game.

    CR 103.6b: "Each card may be revealed this way only on[ce]" - the excerpt
    truncates, but running the sequence twice would break it, and CR 103.6 puts
    the sequence between one completed mulligan process and one first turn.
    `take_opening_hand_actions` is idempotent because of this flag."""

    pregame_seed: str = ""
    """Seed prefix for every reshuffle CR 103.5's mulligans cause in this game.

    A mulligan shuffles (CR 103.5), so the pregame is the one part of starting a
    game that consumes randomness, and it has to stay reproducible now that the
    process is driven declaration by declaration rather than by one call. The
    `Match` that dealt the hands sets this to the same prefix its own
    `_game_seed` builds, so the per-mulligan seed string is byte for byte the one
    the blocking loop derived and a replay with the same declarations is
    identical. Empty for a game nobody dealt a deck to, which never mulligans.
    """

    mulligan_declarations: dict[str, bool] = Field(default_factory=dict)
    """This round's CR 103.5 declarations, by username. True is "take a mulligan".

    CR 103.5: "First, the starting player declares whether they will take a
    mulligan. Then each other player in turn order does the same. Once each
    player has made a declaration, all players who decided to take mulligans do
    so at the same time." The declarations have to be *collected* before any of
    them is acted on, and this is where they wait. Cleared as each round
    resolves, so it always holds the round in progress and nothing else.
    """

    opening_hand_seat: int = 0
    """Which seat is taking its CR 103.6 opening-hand actions, as an index into `players`.

    CR 103.6: "the starting player may take any such actions in any order. Then
    ea[ch ...]" - the excerpt truncates, but the starting player going first and
    the other players following is stated outright, and `players` is seated with
    the starting player first. So this walks that list, one seat at a time, and
    a seat is done when it says so.
    """

    opening_hand_reveals: list[UUID] = Field(default_factory=list)
    """Cards revealed from an opening hand under CR 103.6b, in the order shown.

    "The card remains revealed until the first turn begins." A `Reveal` in
    `reveals` is CR 701.20a's momentary showing and says nothing about how long
    it lasts; this is the separate, longer-lived fact CR 103.6b creates, kept as
    ids because the cards themselves stay in hand (CR 701.20b)."""

    reveals: list[Reveal] = Field(default_factory=list)
    """Every card that has been revealed this game (CR 701.20a), in order.

    Public information, and *only* what was actually shown: a reveal out of a
    hidden group of cards - a hand, a library, a sideboard outside the game -
    puts one entry here per card the effect named, never the group it came
    from. Anything reading this to decide what an opponent may see gets the
    reveal and nothing around it. See `Reveal`.

    A look (CR 701.20e) is recorded here as well, with `Reveal.viewers`
    naming who looked; `Game.known_to` is the reader that tells them apart."""

    known_carries: list[KnownCarry] = Field(default_factory=list)
    """Records carried into a hand by a library-to-hand move or a move from a
    public zone, in order. See `KnownCarry` - a knowledge policy, not a CR
    rule."""

    announced_reveal_counts: dict[str, int] = Field(default_factory=dict)
    """How many cards an activation's "Reveal X ... cards from your hand" cost
    revealed, keyed like `activations` (`_activation_key`). Written by
    `begin_activating` and taken back by `activate_ability`: CR 107.3a's X is
    announced as the cost is chosen, and the ability on the stack is built by
    a second call, so this is the value that crosses from one to the other."""

    _announced_targets: dict[str, tuple[list[TargetRef], CostPayment]] = PrivateAttr(default={})
    _announced_modes: dict[str, tuple[list[int], list[list[TargetRef]]]] = PrivateAttr(default={})
    """The modes (and each one's targets) `begin_activating` announced for a
    modal activated ability (CR 700.2a), taken back by `activate_ability`
    together with `_announced_targets`. Not persisted, for the same reason."""
    _opened_payments: dict[str, CostPayment] = PrivateAttr(default={})
    _activation_source_stamps: dict[str, UUID] = PrivateAttr(default={})
    """The source's `zone_change_stamp` as `begin_activating` opened each
    payment - before a cost that moves the source (Pyxis of Pandemonium's own
    "Sacrifice this artifact") made it a new object (CR 400.7). Read once by
    `activate_ability` into `AbilityOnStack.source_stamp`, so the ability
    remembers the object it was activated from (CR 113.7a), the object whose
    linked pile it reads (CR 607.2a)."""
    """The payment `begin_activating` opened, keyed like `activations`, for
    `activate_ability` to read back which objects the cost actually moved
    once it is paid (CR 602.2b) - "`<verb>` this way" on the resolving
    ability counts them. Not persisted, for the same reason as
    `_announced_targets`: both calls run inside one command."""
    """The targets `begin_activating` announced (CR 601.2c), keyed like
    `activations`, with the payment it opened for them. `activate_ability`
    takes them back only once that payment is paid (CR 601.2h): a payment
    rewound, cancelled or never paid ended that activation, so its
    announcement is discarded and the next activation announces its own.
    Not persisted: both calls run inside one command, and a command that
    pauses is replayed from its start, `begin_activating` included."""
    _departure_epoch: int = PrivateAttr(default=0)
    """Which batch of simultaneous events the game is in, for CR 603.10a's
    look-back: bumped as each resolution (CR 608.2) and each round of
    state-based actions (CR 704.3) begins, so the permanents one of them
    moves off the battlefield share it. A leaves-the-battlefield ability of
    an object that left in the current batch still triggers on the others
    (CR 603.10a's own example); one that left in an earlier batch is just a
    card in a graveyard (CR 113.6). Not persisted: it only compares objects
    within one command."""
    _left_battlefield_characteristics: dict[UUID, Characteristics] = PrivateAttr(default={})
    """What each permanent was as it last left the battlefield (CR 603.10a's
    look-back), taken by `_note_left_battlefield` while it was still there,
    so a departure event its move did not stamp with types still carries
    them - `emit` fills `subject_types`/`subject_subtypes` from here. Not
    persisted: it is read within the same move that wrote it."""
    _paying_cost: tuple[str, str | None, str | None] | None = PrivateAttr(default=None)
    """`(what, keyword, payer)` while a spell's or ability's total cost is
    being paid (`paying_cost_of`), stamped onto every event raised meanwhile.
    Not persisted: it opens and closes within one `CostPayment.pay`."""
    _returning_together: list[tuple[GameEvent, GameEvent]] | None = PrivateAttr(default=None)
    """The departure events of permanents returned to hand inside
    `returning_together`, raised together once the last of them has moved
    (CR 603.10a). `None` outside one. Not persisted: the block opens and
    closes within one resolving effect or one cost payment."""
    _damage_recorders: dict[UUID, list[UUID]] = PrivateAttr(default={})
    """Per damage source currently being watched by `recording_damage_from`,
    the permanents it has actually dealt damage to (CR 120.3), in order. Not
    persisted: the block opens and closes within one resolving effect."""
    _tapped_batch: tuple[CardState, ...] = PrivateAttr(default=())
    """The permanents `ExtraTriggerEvent.PERMANENTS_TAPPED` is being matched
    for right now (`tapped_batch`). Empty outside `announce_batched_events`.
    Not persisted: read only while that event is being raised."""
    _exile_arrivals_pending: tuple["ExileArrival", ...] = PrivateAttr(default=())
    """Cards and permanents put into exile from the battlefield or a graveyard
    since `announce_batched_events` last ran, one entry per arrival. Drained
    into one `ExtraTriggerEvent.PUT_INTO_EXILE` per player (CR 603.2c). Not
    persisted: every instruction ends with an announce, so it is empty at any
    point a snapshot is taken."""
    _exile_batch: tuple["ExileArrival", ...] = PrivateAttr(default=())
    """The arrivals `ExtraTriggerEvent.PUT_INTO_EXILE` is being matched for
    right now. Empty outside `announce_batched_events`; not persisted."""
    _graveyard_batch: tuple["GraveyardArrival", ...] = PrivateAttr(default=())
    """The arrivals `ExtraTriggerEvent.PUT_INTO_GRAVEYARD` is being matched for
    right now (`graveyard_batch`). Empty outside `announce_batched_events`.
    Not persisted: read only while that event is being raised."""
    _returned_to_hand_batch: tuple[GameEvent, ...] = PrivateAttr(default=())
    """The `LEAVES_BATTLEFIELD_TO_HAND` events being raised right now as one
    event (`returned_to_hand_batch`). Empty outside `_announce_returns`. Not
    persisted: read only while those events are being raised."""
    _entry_batch: tuple[tuple[UUID, Zone | None], ...] = PrivateAttr(default=())
    """While `entering_together` announces its permanents, every one of them
    with the zone it came from - written onto each enters event as
    `GameEvent.entered_together` (CR 603.6a). Not persisted: it opens and
    closes within one announcement loop."""
    _dying_together: list[GameEvent] | None = PrivateAttr(default=None)
    """Dies events held back inside `dying_together` until its last creature has
    left (CR 704.3, CR 608.2f). `None` outside one. Not persisted: it opens and
    closes within one state-based-action pass or one destroy-all."""
    _entering_together: list[CardState] | None = PrivateAttr(default=None)
    #: The zone each permanent entered from, held only between
    #: `enter_the_battlefield` and the enters event it raises (`_enters_event`
    #: reads it into `GameEvent.origin_zone`) - never across a call, so not
    #: game state and not persisted.
    _entry_origins: dict[UUID, Zone] = PrivateAttr(default={})
    """Permanents put onto the battlefield inside `entering_together`, whose
    enters events wait for the last of them (CR 603.6a). `None` outside one.
    Not persisted: the block opens and closes within one resolving effect."""

    library_orders_kept: list[LibraryOrderKept] = Field(default_factory=list)
    """Library cards that kept their order through a put onto the bottom or a
    scry/surveil put-back, one row per card per put, in order. See
    `LibraryOrderKept`."""

    mana_spent_on_spells_this_turn: dict[str, int] = Field(default_factory=dict)
    """The total mana each player has spent this turn to cast spells, keyed by
    username (CR 700.14's "the amount of mana that player spent this turn to
    cast spells"). `put_on_stack` adds each cast's `CastRecord.mana_spent` here
    and emits `ExtraTriggerEvent.EXPEND` for every threshold the cast crossed;
    reset where `spells_cast_this_turn` is."""

    spells_cast_this_turn: dict[str, list[CardState]] = Field(default_factory=dict)
    """Every spell each player has cast this turn, keyed by controller
    (CR 601.2a marks the casting event; `put_on_stack` records it here).
    Feeds Damping Sphere's per-spell cost increase and
    `_first_spell_this_turn_holds`'s "first [type] spell you've cast this
    turn" intervening *if* clauses. Cleared when a new turn begins."""

    cards_drawn_in_own_draw_step: dict[str, int] = Field(default_factory=dict)
    """How many cards each player has drawn during the draw step in progress,
    their own (CR 504.1's turn-based draw and anything drawn after it in that
    step), counted in `draw_cards` alongside `cards_drawn_this_turn`. Answers
    Orcish Bowmasters' "except the first one they draw in each of their draw
    steps" (`machines/triggers.condition_matches`). Cleared as every draw
    step begins (`_note_step_began`), not per turn: CR 500.8 can add a whole
    beginning phase (CR 501.1: untap, upkeep, draw), and so a second draw
    step, to one turn. Also cleared when a new turn begins."""

    cards_drawn_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many cards each player has actually drawn this turn, keyed by the
    player who drew them.

    CR 121.2: "Cards may only be drawn one at a time. If a player is instructed
    to draw multiple cards, that player performs that many individual card
    draws." So this counts individual draws, not instructions - which is what
    makes an ordinal condition ("you draw your third card in a turn", Tamiyo,
    Inquisitive Student) answerable at all.

    Counted in `draw_cards`, inside the loop over the cards that were *really*
    drawn, immediately before the `TriggerEvent.DRAWS_A_CARD` emit for that
    same card. Before, because the matcher
    (`machines/triggers._unread_condition_matches`) reads this counter while
    the event is being dispatched and compares it for equality with the
    ordinal - counting afterwards would leave the third draw reading two and
    the ability would silently never fire. A draw that a replacement effect
    reduced to nothing produced no card and is not counted (CR 603.2g: "An
    ability triggers only if its trigger event actually occurs").

    Cleared when a new turn begins, the same reset `spells_cast_this_turn`
    already gets."""

    permanents_sacrificed_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many permanents each player has sacrificed this turn, keyed by the
    controller who sacrificed them.

    CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    battlefield directly to its owner's graveyard." That is a distinct action
    from the destruction or the bounce that also move a permanent off the
    battlefield, which is why `permanents_left_battlefield_this_turn` cannot
    answer "you sacrificed a permanent this turn" (Phoenix Fleet Airship's
    intervening *if*, CR 603.4): a destroyed permanent left the battlefield
    and was never sacrificed.

    Recorded in `sacrifice`, next to the `TriggerEvent.IS_SACRIFICED` emit, by
    the controller the permanent had while it was still on the battlefield -
    the player CR 701.21a names as the one doing the sacrificing. A count
    rather than a flag, so a future card asking "two or more" has the number;
    today only "at least one" is ever asked. Cleared when a new turn begins."""

    ability_resolutions_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many times each triggered or activated ability has resolved this
    turn, keyed by `_resolution_key` (the source object, as that object, and
    the ability's own text). "If this is the fourth time this ability has
    resolved this turn" (Sephiroth, Fabled SOLDIER) reads it; the count
    includes the resolution in progress. Counted in `_resolve_ability` and
    cleared when a new turn begins."""

    noncombat_damage_to_players_this_turn: dict[str, int] = Field(default_factory=dict)
    """How much noncombat damage (CR 120.2a) each player has been dealt this
    turn, keyed by the damaged player - Chandra's Incinerator's "the total
    amount of noncombat damage dealt to your opponents this turn" sums it over
    the caster's opponents when the cost is determined (CR 601.2f). Recorded
    next to the `dealt_noncombat_damage` turn fact; cleared when a new turn
    begins."""

    creatures_died_this_turn: int = 0
    """How many creatures have died this turn, whoever controlled them.

    Morbid's condition (an ability word, CR 207.2c): "if a creature died this
    turn". CR 700.4: "The term dies means 'is put into a graveyard from the
    battlefield.'" Counted in `put_into_graveyard` next to the
    `TriggerEvent.DIES` emit, so a creature exiled instead (a finality
    counter, Rest in Peace) never counts. A count rather than a flag, the
    same choice `permanents_sacrificed_this_turn` makes. Cleared when a new
    turn begins."""

    upkeeps_begun: dict[str, int] = Field(default_factory=dict)
    """How many upkeep steps each player has begun this game (CR 503.1), the
    clock echo's "came under your control since the beginning of your last
    upkeep" (CR 702.30a) is read against: `CardState.controlled_since_upkeep`
    stamps a permanent with its controller's count as it comes under their
    control. Counted in `Game._advance_past_checks` as the upkeep begins, before its
    "at the beginning of your upkeep" abilities trigger."""

    nontoken_creatures_died_under_control_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many nontoken creatures have died under each player's control this
    turn, keyed by that controller.

    Vile Redeemer's own cast trigger: "create a 1/1 colorless Eldrazi Scion
    creature token for each nontoken creature that died under your control
    this turn." CR 700.4's "dies" (put into a graveyard from the battlefield)
    is the same event `creatures_died_this_turn` already counts, but that
    field is global and counts every creature whoever controlled it; this is
    the per-controller, nontoken-only twin (CR 111.1's "token" - a permanent
    represented by something other than a card - excluded the same way
    `count_expression`'s own "nontoken `<qualifier>` you control" branch
    already excludes one). Counted in `put_into_graveyard` next to
    `creatures_died_this_turn`, by the controller the creature had while
    still on the battlefield (CR 603.10a's look-back). Cleared when a new
    turn begins."""

    open_payment_pools: dict[str, ManaPool] = Field(default_factory=dict)
    """The working mana pool of each player's currently open `CostPayment`.

    CR 106.4: mana a player has produced and not yet spent is in their mana
    pool. `machines/cost.CostPayment` works on a *copy* of that pool so a
    cancelled payment (CR 733.1) throws away only what it produced, which
    means that between CR 601.2g's mana abilities and CR 601.2h's payment the
    player's own `ManaPool` underreports: the mana the payment just made is
    real, unspent, and invisible there.

    Nothing cared until a continuous effect had to count it. Omnath, Locus of
    Mana's "Omnath gets +1/+1 for each unspent green mana you have" is read by
    `computed_board`, and DDR#955 is exactly the case where the mana is
    sitting in an open payment - four green produced for Momentous Fall, with
    the sacrifice paid before it (CR 601.2h's "in any order"). Registered by
    `CostPayment._seed_payer_pool` and dropped when the payment is paid,
    cancelled or rewound, so it is never a second pool a player owns - it
    *replaces* the player's own for as long as it is open, since it opened as
    a copy of it.

    """

    lands_entered_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many lands have entered the battlefield under each player's control
    this turn, counting ones that have since left (CR 603.6a's "entered" is a
    fact of the turn). Bioengineered Future's "for each land that entered the
    battlefield under your control this turn" reads it
    (`machines/keyword_counters`); reset with the other per-turn ledgers."""

    permanents_left_battlefield_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many permanents each player controlled at the moment those
    permanents left the battlefield this turn, keyed by that controller.

    Feeds Revolt (an ability word, CR 207.2c - `knowledge_search` found no
    numbered rule for Revolt itself beyond that) and any other card whose text
    reads "a permanent you controlled left the battlefield this turn": Fatal
    Push's own "if a permanent left the battlefield under your control this
    turn." Recorded at the moment of the move (`destroy`, `sacrifice`,
    `exile_permanent`, `return_to_hand` all route through `_note_left_
    battlefield`), by the controller the permanent had *while it was still on
    the battlefield* - not the owner, since revolt asks who controlled it, and
    not whoever controls the object now that it has moved to an uncontrolled
    zone. A count, not a bare flag, so nothing here has to guess whether two
    departures in the same turn matter to some future card; today only
    "at least one" is ever asked. Cleared when a new turn begins, the same
    reset `spells_cast_this_turn` already gets."""

    spells_cast_last_turn: dict[str, list[CardState]] = Field(default_factory=dict)
    """What `spells_cast_this_turn` held during the turn before this one.

    The werewolves' question (CR 603.4's intervening *if*): Duskwatch Recruiter
    transforms "if no spells were cast last turn" and Krallenhorde Howler
    transforms back "if a player cast two or more spells last turn". Neither is
    answerable from `spells_cast_this_turn`, which is emptied as a new turn
    begins - so it is snapshotted here at that same moment instead of being
    thrown away. A spell is counted when it is cast (CR 601.2a, CR 601.2i),
    which is exactly what `put_on_stack` already records.
    """

    day_night: DayNight | None = None
    """The game's day/night designation (CR 731.1). `None` is "neither", the
    designation every game starts with; once set it is only ever replaced by
    the other one. Changed only through `set_day_night`."""

    previous_turn_active_player: str | None = None
    """Who was the active player during the turn before this one - the player
    CR 502.2's untap-step day/night check asks about ("the previous turn's
    active player", CR 731.2a, CR 731.2b), read against
    `spells_cast_last_turn`. Snapshotted at the same moment that ledger is,
    because an extra turn (CR 500.7) makes it unanswerable from the seat
    order. `None` before any turn has ended."""

    cards_discarded_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many cards each player has cycled or discarded this turn, keyed by
    the player who discarded them.

    CR 701.9a is the discard itself ("To discard a card, move it from its
    owner's hand to that player's graveyard"), and CR 702.29a makes cycling a
    discard too: "'Cycling [cost]' means '[Cost], Discard this card: Draw a
    card.'" - the card is discarded to pay an activation cost, so one cycled
    card is one discarded card and is counted once, never twice, which is the
    same "only once when a card is cycled" CR 702.29d spells out for the
    triggered-ability version of the question.

    Recorded in `discard_cards`, the single place a discard is instructed
    (`machines/cost.py`'s discard cost component - which is what a cycling
    activation pays - and `machines/effects.py`'s discard effects both route
    there). `Player.discard_to_maximum_hand_size`, the cleanup step's CR 514.1
    discard, is the one path that still does not, so a cleanup discard is not
    counted here; nothing can be cast between it and the turn ending, so no
    cost this feeds could read it.

    Feeds Hollow One's own "This spell costs {2} less to cast for each card
    you've cycled or discarded this turn" (CR 601.2f). Cleared when a new turn
    begins, the same reset `spells_cast_this_turn` already gets."""

    life_gained_this_turn: SortedSet[str] = Field(default_factory=set)
    """Which players have gained life this turn (CR 119.9 treats any source
    of the gain the same way). `Player.gain_life` is the single place a life
    total actually goes up, so it is recorded there rather than only at
    `Game.gain_life`'s call site - a direct gain (an effect, a cost paid with
    life the other way) used to leave this unrecorded. Feeds Ocelot Pride's
    "you gained life this turn" intervening *if*. Cleared when a new turn
    begins."""

    life_gained_amount_this_turn: dict[str, int] = Field(default_factory=dict)
    """How much life each player has gained this turn, the amount twin of
    `life_gained_this_turn`'s plain boolean - recorded at the same call site
    (`Player.gain_life`) for the same CR 119.9 reason, the same shape
    `cards_drawn_this_turn` already counts a per-player total in. Feeds
    Germinate Recruits' own "where X is the amount of life you gained this
    turn" (CR 107.3f) and Enlightened Confidant's own "a card with mana
    value less than or equal to the amount of life you gained this turn" -
    the printed amount itself, not merely whether any was gained. Cleared
    when a new turn begins.

    The FRA "trigger events and per-turn history" stream (S5) independently
    built the identical fact as `Player.life_gained_tally`/`life_gained_
    tally_turn` before this field landed; reconciled at merge in favour of
    this one, since Germinate Recruits' own effect (`machines/effects.py`)
    already reads it - `Player.gain_life` keeps only one recorder, not two,
    per `CLAUDE.md`'s "keep one mechanism" rule."""

    became_tapped_count_this_turn: dict[UUID, int] = Field(default_factory=dict)
    """How many times each permanent (by id) has become tapped (CR 701.26a)
    this turn, for Captain America, Living Legend's own "Whenever a creature
    you control becomes tapped during your turn, if it's the first time that
    creature has become tapped this turn, untap it." - `machines/triggers.
    intervening_if_holds`'s own "it's the first time `<subject>` has become
    tapped this turn" clause reads `== 1` off this. Incremented wherever a
    `BECOMES_TAPPED` `GameEvent` is emitted (`Game.note_became_tapped`), so
    it always agrees with what the trigger itself watches - not a second,
    independently-kept count that could drift from the event stream. Cleared
    when a new turn begins, the same reset `attacked_this_turn` already
    gets."""

    attack_count_this_turn: dict[UUID, int] = Field(default_factory=dict)
    """How many times each creature (by id) has been declared as an attacker this
    turn (CR 508.1) - a creature can attack once per combat phase, and an
    additional combat phase (CR 500.8) gives it another, so this is a count where
    `attacked_this_turn` is a set. Moraug, Fury of Akoum's "+1/+0 for each time it
    has attacked this turn" reads it. Written where `attacked_this_turn` is,
    cleared with it when a new turn begins."""

    attacked_this_turn: SortedSet[UUID] = Field(default_factory=set)
    """Which creatures (by id) have attacked this turn (CR 508.1), for
    Hexhaven Dueling Arena's own "target creature that attacked this turn" -
    a historical fact CR 511.3/514's end of combat/cleanup does not answer,
    unlike `machines/combat.Combat`'s live attacking status. Recorded by
    `Game.declare_attackers`. Cleared when a new turn begins, the same reset
    `spells_cast_this_turn` already gets.

    Deliberately per-object (`UUID`, not `turn_facts`' per-player `str`):
    `turn_facts` answers "did this *player's* creatures do X this turn",
    which is not enough to judge *which* creature a target names - FRA
    stream S2's own field, not folded into `turn_facts` for that reason."""

    exerted_this_turn: SortedSet[UUID] = Field(default_factory=set)
    """Which permanents (by id) have been exerted this turn (CR 701.43a), for
    Combat Celebrant's "If this creature hasn't been exerted this turn, you may
    exert it as it attacks." - `CardState.exerted` is the untap-step flag and
    stays set across the turn boundary, so it cannot answer "this turn".
    Recorded where a permanent is actually exerted (`machines/exert_on_attack`
    and the exert cost component) and cleared when a new turn begins, the
    same reset `attacked_this_turn` gets."""

    attacked_players_this_turn: dict[UUID, SortedSet[str]] = Field(default_factory=dict)
    """Which players (by username) each attacking creature (by id) attacked
    this turn (CR 508.1a), for Angel of Destiny's own "each player this
    creature attacked this turn loses the game." `attacked_this_turn` above
    already answers "did this creature attack this turn"; this answers
    "whom" - not folded into it, the same `attacked_this_turn`-vs-`turn_facts`
    split above: a creature can attack a different defending player in an
    extra combat phase (CR 500.7/508.1a), and every one of them must be swept
    up, not just the latest. Recorded by `Game.declare_attackers` off
    `machines.combat.defending_player`. Cleared when a new turn begins, the
    same reset `attacked_this_turn` already gets."""

    turn_facts: dict[str, SortedSet[str]] = Field(default_factory=dict)
    """A general per-turn, per-player fact ledger: `turn_facts[fact]` is the
    set of usernames for whom `fact` has happened this turn.

    `life_gained_this_turn`, `cards_discarded_this_turn`, and the other
    single-purpose per-turn fields above each grew a new `Game` field the
    first time a card needed one; this is the FRA "trigger events and
    per-turn history" stream's alternative for the batch of this-turn
    predicates it adds (CR 701.22d's scry, CR 701.25c's surveil, CR 606.3's
    loyalty ability, CR 120.2a's noncombat damage) - one field, many keys,
    rather than one field per fact. `record_turn_fact`/`turn_fact_holds` are
    the read/write pair; nothing reads or writes this dict directly.
    Cleared when a new turn begins, `turn_facts_last_turn` keeping the
    previous turn's copy the same way `spells_cast_last_turn` already does
    for `spells_cast_this_turn`."""

    turn_facts_last_turn: dict[str, SortedSet[str]] = Field(default_factory=dict)
    """What `turn_facts` held during the turn before this one - Command the
    Stage's own "if an opponent was dealt noncombat damage **last turn**"
    (CR 603.4), the same snapshot `spells_cast_last_turn` already takes."""

    turn_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    """A per-turn, per-player *count* ledger: `turn_counts[fact][player]` is
    how many times `fact` has happened for `player` this turn - the counting
    twin of `turn_facts`, for the conditions that ask "how many" or "the
    first" rather than "did you" (CR 506.1's "the first combat phase of the
    turn", counted per active player as each combat phase begins).
    `note_turn_count`/`turn_count` are the write/read pair; nothing reads or
    writes this dict directly. Cleared when a new turn begins, with
    `turn_counts_last_turn` keeping the previous turn's counts."""

    turn_counts_last_turn: dict[str, dict[str, int]] = Field(default_factory=dict)
    """What `turn_counts` held during the turn before this one."""

    combat_damage_dealt_this_turn_by: SortedSet[UUID] = Field(default_factory=set)
    """The ids of every creature that has dealt combat damage this turn
    (CR 510.2) - a per-object "this turn" fact rather than a per-player one,
    which is why it is its own field instead of a `turn_facts` key.
    `machines/combat.py`'s `_deal_combat_damage` is the single writer, the
    same way `Player.gain_life` is `life_gained_this_turn`'s. Ruric Thar's
    "hexproof as long as they haven't dealt combat damage yet" is the reader,
    through `LayerContext.combat_damage_dealt_this_turn`. Cleared when a new
    turn begins."""

    combat_damage_to_players_this_turn: list[CombatDamageToPlayer] = Field(default_factory=list)
    """Every source's combat damage actually dealt to a player this turn, with
    its controller and creature types at that moment - CR 702.76a's prowl
    condition (see `CombatDamageToPlayer`). `machines/combat.py`'s
    `_deal_combat_damage` is the single writer through
    `record_combat_damage_to_player`; `prowl_condition_holds` is the reader.
    Cleared when a new turn begins."""

    counters_put_this_turn: list[CountersPutRecord] = Field(default_factory=list)
    """Every counter placement on a permanent this turn, one entry per
    instruction and permanent, in order - see `CountersPutRecord`.
    `_emit_counters_put` is the single writer; `LayerContext.
    counters_put_this_turn` carries it to the statics that read it
    (`machines/counter_effects.py`). Cleared when a new turn begins."""

    next_spell_free_cast_grants: list[NextSpellFreeCastGrant] = Field(default_factory=list)
    """"The next `<quality>` spell you cast this turn can be cast without paying
    its mana cost." (CR 118.9) - live until that spell becomes cast (CR
    601.2i) or the turn ends. See `machines/next_spell.py`."""

    next_spell_keyword_grants: list[NextSpellKeywordGrant] = Field(default_factory=list)
    """"The next `<quality>` spell you cast this turn has `<keyword>`." (Don &
    Raph, Hard Science's affinity for artifacts, CR 702.41a; Archway of
    Innovation's improvise, CR 702.126a) - live until that spell becomes cast
    (CR 601.2i) or the turn ends. See `machines/next_spell.py`."""

    spell_cost_reduction_grants: list[SpellCostReductionGrant] = Field(default_factory=list)
    """"`<Quality>` spells you cast this turn cost {N} less to cast." (CR
    601.2f) - live for the rest of the turn it was created in. See
    `machines/next_spell.py`."""

    tapped_since_last_batch: list[UUID] = Field(default_factory=list)
    """Permanents tapped (CR 701.26a) since `announce_batched_events` last
    raised `ExtraTriggerEvent.PERMANENTS_TAPPED`, in the order tapped - one
    instruction's, cost's or declaration's worth, which CR 603.2c makes one
    event for a "one or more ... become tapped" condition. Filled by
    `note_permanent_tapped`. Persisted: a resolution paused on a decision
    (CR 608.2d) may already have tapped some."""

    graveyard_arrivals_announced: int = 0
    """How many of `graveyard_arrivals_this_turn`'s entries `announce_batched_
    events` has already raised as `ExtraTriggerEvent.PUT_INTO_GRAVEYARD` -
    everything after it is the next batch (CR 603.2c). Reset with the ledger
    when a new turn begins."""

    damage_dealt_this_turn: list[DamageDealt] = Field(default_factory=list)
    """Every damage event this turn, with its source's controller and types
    as it dealt the damage (`DamageDealt`). Written by `machines/conditions/
    history.record`; cleared when a new turn begins."""

    turn_history: list[TurnHistoryEntry] = Field(default_factory=list)
    """This turn's entries, attacks, departures, sacrifices and crews, each
    with the object's characteristics at that moment (`TurnHistoryEntry`).
    Written by `machines/conditions/history.record`; rolled into
    `turn_history_last_turn` when a new turn begins."""

    turn_history_last_turn: list[TurnHistoryEntry] = Field(default_factory=list)
    """What `turn_history` held during the turn before this one - Ephara, God
    of the Polis's "if you had another creature enter the battlefield under
    your control last turn"."""

    exile_residents_seen: SortedSet[str] = Field(default_factory=set)
    """Every object ("<id>/<zone change stamp>", CR 400.7) this turn has seen
    in exile, seeded with the exile zone's residents when the turn began - a
    card in exile that is not in it was put there this turn, and is counted
    once in `turn_counts["cards_put_into_exile"]` (`machines/conditions/
    history.note_exile_arrivals`)."""

    dealt_combat_damage_since_their_turn: SortedSet[str] = Field(default_factory=set)
    """The players dealt combat damage (CR 120.2a) since their own most
    recent turn ended - Marchesa, Resolute Monarch's "if you haven't been
    dealt combat damage since your last turn". A player joins on the damage
    and leaves as their own turn ends."""

    _pending_damage_excess: int = PrivateAttr(default=0)
    """CR 120.10's excess for the damage event now being raised, worked out by
    `deal_damage` before the damage changed the recipient and read by
    `machines/conditions/history.record` inside that event's `emit`. Not
    persisted: it lives only between the two."""

    graveyard_arrivals_this_turn: list[GraveyardArrival] = Field(default_factory=list)
    """Every card that arrived at a graveyard this turn (CR 400.6), one entry
    per arrival - see `GraveyardArrival`'s own docstring for why this is one
    general ledger rather than a narrower counter. Cleared when a new turn
    begins.

    The fu-events stream independently built the identical fact for CR
    700.11's Descend as `Game.permanent_cards_to_graveyard_this_turn` (a
    `dict[str, int]` running count) before this field landed; reconciled at
    merge in favour of this one - `Game.descended`/`Game.descend_count` now
    read `cards_put_into_graveyard_this_turn(player, permanent_only=True)`
    instead, per `CLAUDE.md`'s "keep one mechanism" rule. That method's own
    `permanent_only` filter was widened at the same merge to also recognise
    a permanent card that reached the graveyard without ever touching the
    battlefield (a discard, a mill, a countered permanent spell) - see
    `GraveyardArrival.is_permanent_card`'s own docstring for why CR 700.11's
    "from anywhere" needs that in addition to `permanent_types`."""

    activations: dict[str, int] = Field(default_factory=dict)
    """How often each ability has been activated this turn, keyed
    `"<permanent id>:<ability index>"`, for CR 602.5b restrictions such as
    "Activate only once each turn". Cleared when a new turn begins."""

    exhausted: SortedSet[str] = Field(default_factory=set)
    """Which abilities have been activated at all, ever, keyed the same way
    as `activations` (`Game._activation_key`) - CR 702.177a's Exhaust:
    "'[Cost]: [Effect]' means '[Cost]: [Effect]. Activate only once.'" -
    and CR 702.193a's Power-up, the same "Activate this ability only once"
    in different words. Never cleared on a new turn, unlike `activations` -
    the whole point of either keyword is that it is not a per-turn limit. A
    key is naturally never reused by a different object: `_activation_key`
    folds in `permanent.zone_change_stamp`, which a fresh CR 400.7 object
    always gets (unlike `permanent.id`, which is stable across an ordinary
    zone change - see `CardState`'s own "same id, new object" note), so a
    card that leaves and returns is not exhausted by what its earlier self
    did. A `SortedSet` so it dumps in one canonical order: as a bare set of
    strings its JSON order followed per-process hash randomisation, and a
    decode and re-dump could list the same keys differently."""

    harnessed: SortedSet[str] = Field(default_factory=set)
    """Which permanents are harnessed right now (CR 701.64a-b), keyed
    `"<permanent id>:<zone_change_stamp>"` - `Game._harness_key`, the same
    id-plus-incarnation scoping `exhausted` already uses, which is what
    gives CR 701.64b's own "stays harnessed until it leaves the battlefield"
    for free: a permanent that leaves and returns is a fresh CR 400.7 object
    with a fresh stamp, so it is never harnessed by what its earlier self
    was. Read by `Game.is_harnessed`, written by `Game.harness`; see
    `machines/keyword_counters.py` for CR 702.186's own ∞ keyword this
    designation gates. A `SortedSet` for the identical canonical-dump reason
    `exhausted` is one."""

    power_up_restricted_turns: SortedSet[int] = Field(default_factory=set)
    """`TurnMachine.turns_taken` ordinals during which no power-up ability
    (CR 702.193a) may be activated - Kang the Conqueror's own power-up rider,
    "Take an extra turn after this one. During that turn, power-up abilities
    can't be activated.": the extra turn CR 500.7 inserts directly after the
    current one is the very next turn taken, so `turns_taken` (which "goes up
    exactly once per turn that actually begins, extra ones included" - its
    own docstring) is the ordinal the rider's own resolution records here,
    ahead of time, and `why_cannot_activate` checks against once that turn
    is actually the one under way. A `SortedSet` of ordinals rather than a
    single one, so two Kangs in the same game each get their own restricted
    turn recorded rather than the second overwriting the first; entries
    older than the current turn are simply never matched again, and are left
    rather than pruned - each is a handful of bytes for the life of the
    game."""

    loyalty_activations: dict[str, int] = Field(default_factory=dict)
    """How often a loyalty ability of each permanent has been activated this
    turn, keyed by permanent id, for CR 606.3's once-per-turn rule - which is
    per permanent, not per ability: "but only if no player has previously
    activated a loyalty ability of that permanent that turn". Any of a
    planeswalker's loyalty abilities having been activated refuses the next
    one. Cleared when a new turn begins."""

    loyalty_activation_allowance: dict[str, int] = Field(default_factory=dict)
    """How often loyalty abilities of each permanent may be activated *this turn*, keyed by
    permanent id, when an effect raised it above CR 606.3's one - Kaito, Dancing Shadow's "you
    may activate loyalty abilities of Kaito twice this turn rather than only once". A permanent
    with no entry has its printed allowance (`Game._loyalty_activations_allowed`). Cleared when
    a new turn begins, alongside `loyalty_activations`."""

    text_change_originals: dict[str, Card] = Field(default_factory=dict)
    """CR 612.1 / CR 613.1c: the printed `Card` of each object (keyed by its id)
    whose rules text a color-word change (Swirl the Mists) is rewriting right
    now - put back by `machines/text_changes.sync_text_changes` the moment the
    effect no longer reaches it. Empty unless such a permanent is in play."""

    forecast_activations: SortedSet[str] = Field(default_factory=set)
    """Which forecast abilities (CR 702.57a) have been activated this turn,
    keyed `"<card id>:<zone_change_stamp>"` - `Game._activation_key`'s own
    id-plus-incarnation scoping, without an ability index, since a hand card
    only ever prints one forecast line. CR 702.57b: "A forecast ability may
    be activated only ... once each turn" - read and written by
    `machines/keywords.KeywordActivation.why_not`/`_activate_impl`, which
    (unlike `Game.activate_ability`'s battlefield path, the one that fills
    `activations` below) is the only entry point a hand-zone activation ever
    reaches. Cleared when a new turn begins, alongside `activations`/
    `loyalty_activations` - a `SortedSet` for the same canonical-dump reason
    `exhausted` is one."""

    once_per_turn_triggers: dict[str, int] = Field(default_factory=dict)
    """How often a "this ability triggers only once each turn" ability has
    already triggered this turn, keyed `"<source id>:<printed condition>"` -
    CR 603.2h: "A triggered ability may have an instruction ... This ability
    triggers only if its source's controller has not yet taken the indicated
    action that turn." Caretaker's Talent's own "Whenever one or more tokens
    you control enter, draw a card. This ability triggers only once each
    turn." is the only printing in the pool; `machines/triggers.triggers_for`
    reads and increments this instead of putting a second copy of the same
    trigger on the stack later in the same turn. Cleared when a new turn
    begins, alongside `activations`/`loyalty_activations`."""

    once_per_turn_cast_permissions_used: dict[str, int] = Field(default_factory=dict)
    """Which "Once during each of your turns, you may cast ... from your
    graveyard" grants have been used this turn (Rivaz of the Claw, Gisa and
    Geralf, Kess, Dissident Mage), keyed by the granting permanent as that
    object (`machines/casting.once_per_turn_key`, CR 400.7) - a permanent
    that leaves and returns is a new object with a use of its own. Written
    by `Casting.cast()` when a spell is cast under the grant, and cleared
    when a new turn begins."""

    resolving: StackObject | None = Field(default=None, exclude=True, repr=False)
    """The object currently resolving, or None (CR 608.2).

    `resolve_top` pops the object off the stack before running its effect, so
    while a spell resolves it is on no zone at all. CR 724.1b's "including the
    object that's resolving" needs to be able to name it, and this is the only
    place that can. Excluded from serialisation: it is live only for the length
    of one resolution and means nothing in a stored board."""

    _linked_count: int | None = PrivateAttr(default=None)
    """How many objects the latest counted instruction of the resolving
    object actually moved - discarded, sacrificed, exiled, milled, life paid
    - for a later "that many" of the same object to read (CR 608.2c: its
    instructions are followed in the order written, and later text refers
    back to earlier text). Written by `record_count`, read by
    `recorded_count`, cleared by `resolve_top` around every resolution so it
    never outlives the object that wrote it. Not persisted: a command that
    pauses is replayed from its start, and the same clauses write it again."""

    _linked_counts_by_player: dict[str, int] = PrivateAttr(default={})
    """The same count, one per player, for an "each player ..." instruction
    whose later "that many" is each player's own (Awaken the Erstwhile's
    "Each player discards all the cards in their hand, then creates that many
    ... tokens"). Written while `counting_for` names a player."""

    _counting_player: str | None = PrivateAttr(default=None)

    turn_ended_exiled_ids: SortedSet[UUID] = Field(default_factory=set, exclude=True, repr=False)
    """Spells CR 724.1b exiled while they were resolving.

    `end_the_turn` gives the resolving spell a zone (exile) that `resolve_top`
    would otherwise overwrite with the graveyard or the battlefield a few lines
    later. This is how the two halves agree; each id is consumed once."""

    state_trigger_latches: dict[str, UUID] = Field(default_factory=dict)
    """Which CR 603.8 state trigger is currently held shut, and by what.

    CR 603.8: an ability that triggers on a game state rather than an event
    "doesn't trigger again until it has left the stack". Keyed
    `"<source id>:<printed condition>"`, the value is the id of the
    `AbilityOnStack` that triggered - `machines/triggers.state_triggers_for`
    drops the entry the moment that object is neither on the stack nor waiting
    in `pending_triggers`, so the latch opens for a resolved ability and a
    *countered* one alike (CR 701.6a: countering removes it from the stack).
    Not cleared per turn: the latch is about the stack, not the turn."""

    blocks_triggered: list[str] = Field(default_factory=list)
    """The blocker/attacker pairs that have already fired their block triggers
    this combat, so re-declaring the same block does not trigger twice."""

    attacks_unblocked_triggered: list[UUID] = Field(default_factory=list)
    """Attacker ids that have already fired their CR 508.3f/509.3g "attacks
    and isn't blocked" event this combat - the identical dedup `blocks_
    triggered` gives block pairs, so a `Game.declare_blockers` call that adds
    more blocks to an already-legal declaration (a scenario building one up
    over several calls) never re-emits the same still-unblocked attacker's
    event a second time."""

    continuous_effects: ContinuousEffects = Field(default_factory=ContinuousEffects)
    """Every continuous effect a resolving spell or ability has created (CR 611.2).

    A static ability's effect (CR 611.3b) is rebuilt from the battlefield every
    time and needs no storage. This kind outlives the object that made it, so
    the game has to write it down. `machines/layers.py` owns the store and the
    timestamps (CR 613.7a, 613.7b); this is where it lives.

    Two calls keep it honest, and both are in this file: `note` stamps each
    permanent as it enters (CR 613.7a), and `end_the_turn` ends the "until end
    of turn" effects in the cleanup step (CR 514.2).
    """

    delayed_triggers: DelayedTriggers = Field(default_factory=DelayedTriggers)
    """Delayed triggered abilities waiting for their event (CR 603.7).

    Not printed on any card, so `machines/triggers.py` cannot find them; they
    are created by a resolution and watch `Game.emit` for the event they were
    told to wait for. See `machines/delayed.py`.
    """

    melded_pairs: dict[UUID, CardState] = Field(default_factory=dict)
    """The "held" other half of each melded permanent (CR 712.4a, 712.8g),
    keyed by the *primary* `CardState.id` (the one still sitting in
    `Game.battlefield`, carrying `CardState.meld_result`).

    CR 712.4a: "the resulting permanent is a single object represented by two
    cards." Rather than teach every battlefield-enumerating site in this
    engine (combat, `legal_actions`, every state-based action) that a melded
    pair is one permanent, the partner card is lifted out of `Game.
    battlefield` entirely while melded and held here instead - so every
    existing reader of `Game.battlefield` already sees exactly one permanent,
    with no changes of its own needed. `Game.meld` puts a pair in; whichever
    zone-leaving method the primary goes through next (`put_into_graveyard`,
    `exile_permanent`, `return_to_hand`, ...) pops it back out through
    `Game._accompany_meld_partner` and moves it to the same destination
    (CR 712.21: "one permanent leaves the battlefield and two cards are put
    into the appropriate zone").

    A real `CardState`, not an id: unlike `Player.companion_id`, this is the
    partner's *one* true home while melded - it is in no player's zones and
    no shared zone, so embedding it here does not create the second,
    independently-mutable copy `models/action.py`'s "ids only" convention
    guards against.
    """

    merged_components: dict[UUID, list[CardState]] = Field(default_factory=dict)
    """The components of each merged permanent other than the battlefield
    object itself (CR 730.2), keyed by that object's `CardState.id` - the one
    still in `Game.battlefield`, carrying `CardState.merged_order`. The same
    held-off-the-battlefield shape as `melded_pairs`, for the same reason:
    a merged permanent is one object (CR 702.140c), so every reader of
    `Game.battlefield` sees exactly one. `Game.merge` puts a component in;
    `Game._accompany_meld_partner` sends every one of them to the zone the
    permanent left for (CR 730.3)."""

    cast_records: dict[UUID, "CastRecord"] = Field(default_factory=dict)
    """How each spell now on the stack was cast (CR 601.2b), keyed by the
    `CardState.zone_change_stamp` of the object the record describes - never
    by the card's id. CR 400.7 makes a card that changes zones a new object,
    and this engine keeps its `id`, so an id key let a permanent that left and
    came back read the cast of the object it used to be (battle 8, B8-02).
    Read through `Game.cast_record_of`; the key follows the object only across
    the moves a cast crosses (`Game._carry_cast_record`).

    Several rules ask a question about *how* a spell was cast rather than about
    what it is: CR 702.34a exiles a card whose flashback cost was paid,
    CR 715.3d exiles a spell that was cast as an Adventure, CR 702.185a's warp
    creates its delayed trigger only "if this spell's warp cost was paid", and
    CR 700.2c makes a modal spell's targets depend on the modes announced.

    `Casting` knows all four and the `CardState` it puts on the stack carries
    none of them, so the answer is recorded here by `note_cast`.
    """

    decisions: DecisionScript = Field(default_factory=DecisionScript)
    """The answers a caller has queued for questions asked during resolution.

    CR 608.2d: "If an effect of a spell or ability offers any choices other than
    choices already made as part of casting the spell ... the player announces
    these while applying the effect." There is no player agent here and there is
    deliberately not going to be one, so a caller says in advance what it wants -
    which scry keeps what on top, whether the shockland's 2 life is paid - and
    `Game.ask` matches each answer to the question when it is asked.

    Unanswered questions fall through to `machines/decisions.default_answer`,
    whose table is written down in that module rather than improvised per card.
    """

    shuffle_seed: int = 0
    """The seed every shuffle in this game derives from (CR 701.24a).

    "To shuffle a library or a face-down pile of cards, randomize the cards
    within it so that no player knows their order." Randomize, not "make
    unpredictable to the program": a seeded shuffle satisfies the rule and keeps
    a scenario reproducible, which an unseeded one would not. The seed is mixed
    with `shuffles_performed` so the second shuffle of a game differs from the
    first, and a game replayed from the same seed shuffles identically.
    """

    shuffles_performed: int = 0
    """How many shuffles this game has done, counting up (CR 701.24e, 701.24f).

    Both rules turn on a shuffle having *happened* rather than on it having
    changed anything: a library of zero or one cards still shuffles, and two
    simultaneous shuffles are two shuffles. Nothing triggers on a shuffle yet,
    so this is the only record that one occurred.
    """

    coin_flips_performed: int = 0
    """How many coin flips this game has done, counting up - `shuffles_performed`'s
    own convention (see its docstring), applied to CR 705.1's own randomness
    instead: `flip_coin` seeds each flip from `f"{shuffle_seed}:
    {coin_flips_performed}:coin"`, so a scenario asserting on the result
    stays reproducible and the second flip of a game differs from the first."""

    monarch: str | None = None
    """CR 725.1: "The monarch is a designation a player can have. There is no
    monarch in a game until an effect instructs a player to become the
    monarch." - `None` for exactly that state.

    A single nullable username, not a per-`Player` flag like `has_citys_
    blessing`: CR 725.3 - "Only one player can be the monarch at a time. As a
    player becomes the monarch, the current monarch ceases to be the
    monarch." - so the designation is a fact about the game, not about each
    player, and a plain reassignment is the whole of CR 725.3 with no
    invariant a setter has to maintain by hand. `Game.become_monarch` is the
    one way this is ever set to a real username; `machines/monarch.py`'s two
    inherent triggered abilities (CR 725.2) and `Game._player_left` (CR 725.4)
    are its only other writers, and every condition reader ("you're the
    monarch") and clause parser ("you become the monarch", "target player
    becomes the monarch") reads or writes it through those, never this field
    directly."""

    schema_version: int
    """The engine schema version this `Game` was built or decoded at - T9 of
    the stateless-library plan.

    **What this tracks, and why it is not `__version__`.** `magic_cards_model
    .__version__` (`src/magic_cards_model/__init__.py`) names a package
    release; it changes for reasons that have nothing to do with whether a
    decoded snapshot still means what it meant when it was written - a new
    public helper, a packaging fix, a docstring pass. Gating replay safety on
    it would force a bump on every irrelevant release and, worse, would not
    force one on the change that actually matters: correcting an entry in
    `machines/effects.py`'s `EFFECTS` (card-name-keyed), a mana-ability parse
    in `machines/abilities.py`, a `DelayedEffectSpec` in `machines/delayed.py`,
    a continuous-effect spec in `machines/layers.py`, or `machines/triggers.
    py`'s condition matching - none of which need to move the package version
    at all. This field is a separate, purpose-built counter, starting at
    `CURRENT_SCHEMA_VERSION` (see that `ClassVar`'s own docstring for exactly
    when to bump it), that exists for exactly one question: "does a `Game`
    dumped by the build that wrote it still mean the same thing decoded here?"

    **Why a bare `int` field with no default, not a defaulted one.** A
    defaulted field would let a decoded dict that is simply missing this key -
    every snapshot written before this field existed, and any future decode
    input nobody stamped - fill in `CURRENT_SCHEMA_VERSION` silently and pass
    as though it were current. That is exactly the shape `memory/silent-
    default-dispatch-tables.md` names as this codebase's dominant defect: "a
    lookup that defaults instead of refusing." `_check_schema_version` below
    (a `mode="before"` validator, so it sees the raw input before pydantic
    would apply any default) refuses both a present-but-different version and
    an absent one, with two distinct messages - **fail closed** is the
    documented policy for both, deliberately, per this task's own directive.
    That refusal fires on every construction path alike (`Game(...)`,
    `Game.model_validate(...)`, and `Game` nested inside `Match.games`, since
    a `mode="before"` validator is compiled into the type's own core schema
    rather than being a classmethod override some entry points could route
    around) - which is exactly why every fresh-construction call site in this
    repo (`Match.start_game`, the scenario harness, and the handful of bare
    `Game(players=...)` sites in `tests/`) now passes
    `schema_version=Game.CURRENT_SCHEMA_VERSION` explicitly rather than
    relying on a default: nothing builds a `Game` without saying, out loud,
    what engine version it is built at.

    **The migration answer for pre-versioning data**, stated plainly since the
    task asked for a deliberate choice rather than an accident: there is no
    real pre-versioning data anywhere this engine persists to yet (`GameStore`
    in `magic-cards-model-api` is in-memory only; PostgreSQL persistence is
    the very next phase this task exists to prepare for), so "migrate it
    forward" has no data to act on and would be inventing a guarantee nobody
    can honour - a decoded snapshot's *behaviour*, not just its shape, is what
    is unknown, and no mechanical upgrade can restore behaviour that was never
    recorded. A versionless snapshot is therefore refused exactly like a
    mismatched one, with a message that says so, rather than assumed current.
    """

    #: The schema version a fresh `Game` is stamped with and the only one
    #: `_check_schema_version` accepts on decode. Bump this whenever a change
    #: would make a `Game.model_dump()` produced by the *previous* value mean
    #: something different decoded under the *new* one - which is a wider set
    #: of changes than "the dump's shape changed":
    #:
    #: - A field added to, removed from, renamed on, or retyped on `Game` or
    #:   anything reachable from its dump (`Player`, `CardState`,
    #:   `AbilityOnStack`, a `DelayedEffectSpec` variant's `kind`, a
    #:   `machines/layers.py` continuous-effect spec, ...), or a changed
    #:   default for one of those fields.
    #: - A behavioural change to anything a decoded `Game`'s *own recorded
    #:   state* could already be pointing at by name or kind: an `EFFECTS`
    #:   entry in `machines/effects.py` gaining, losing, or changing its
    #:   resolution (this is the case `docs/engine-coverage.md` calls out by
    #:   name - a card that resolved as a no-op under the old build and does
    #:   something under the new one is exactly a state resolving differently
    #:   with no signal, the failure mode this whole field exists to catch),
    #:   a `machines/abilities.py` mana-ability parse, a `DelayedEffectSpec`'s
    #:   resolution, a `machines/triggers.py` condition match, a layer
    #:   application in `machines/layers.py`, or any other name-/kind-keyed
    #:   dispatch a `CardState` already on a decoded battlefield, stack, or
    #:   pending-trigger list could reach.
    #:
    #: Not bumped for a change that cannot affect any state that could
    #: already exist - a docstring, a test, a refactor with no behavioural
    #: delta, or a wholly new mechanic/keyword no printing in the pool used
    #: before this change existed to write it. When genuinely unsure whether a
    #: change qualifies, bump it: a spurious bump costs a discarded stale
    #: snapshot on the next decode; a missed one costs a wrong game nobody
    #: detects, which is the entire problem this field exists to solve.
    CURRENT_SCHEMA_VERSION: ClassVar[int] = 178
    #: 67: `machines/cost.CostComponent` gained `link_to_permanent_id` (CR
    #: 607.2q), reachable from `Game` through a pending `AbilityOnStack.
    #: keyword_activation`/`.unless_payment`'s own `CostPayment.components`.
    #: 68: `Player` gained `has_enduring_story` (C01-T1).
    #: 69: `machines/casting.PlayPermission` gained `pays_life_for_mana_value`
    #: (CR 118.9b's required life alternative cost) and `choice_group` ("one of
    #: those cards"), both reachable from `Game.play_permissions`;
    #: `machines/triggers.GameEvent` gained `mana_ability` (a pending
    #: trigger's event); `machines/delayed` gained the
    #: `return_each_exiled_to_battlefield_under_owner` effect kind (C01-T3).
    #: 70: `CardState` gained `chosen_modal_options` (Gollum, Riddle Master's
    #: own "choose one that hasn't been chosen -" trigger), reachable from
    #: `Game` through the battlefield (C01-T6).
    #: 71: `PreventionShield` gained `source_stamp`/`lasts_while` and
    #: `GraveyardArrival` gained `card_id` (C01-T7).
    #: 72: `machines/combat.CombatMachine` gained `declared_attacking_power`
    #: (pack tactics, C01 integration).
    #: 73: `ManaPool` gained `treasure` and `CastRecord` gained
    #: `treasure_mana_spent` (mana from a Treasure, C01 integration).
    #: 74: `CastRecord` gained `cast_using_teamwork` and `Game` gained
    #: `became_tapped_count_this_turn` (C02-T2, teamwork).
    #: 75: `Game` gained `harnessed` (CR 701.64b's own designation) and
    #: `power_up_restricted_turns` (Kang the Conqueror's own power-up
    #: rider, CR 702.193a) - a snapshot written before either field decodes
    #: with both missing, which would silently read as "nothing is
    #: harnessed" and "no turn is power-up-restricted" for a game that
    #: actually has one of either recorded.
    #: 76: `Game` gained `counters_put_this_turn` (per-turn counter placement
    #: history, CR 122.6/122.6a), and a `COUNTERS_PUT` event's `player` is
    #: now who put the counters (C02-T4).
    #: 77: `Game` gained `tapped_since_last_batch` and
    #: `graveyard_arrivals_announced` (C02-T5, "one or more" batch triggers).
    #: 78: `CardState` gained `chosen_modal_options_this_turn` (The Vision's
    #: own per-turn "choose one that hasn't been chosen this turn -", a
    #: sibling of `chosen_modal_options` reset every cleanup step rather than
    #: never) and `machines.delayed.StaticPrisonReturn` gained `return_zone`
    #: (Cloak and Dagger, Entwined's own CR 610.2 exile-until-departure can
    #: take a card from a hand, not only a permanent from the battlefield,
    #: so its CR 610.3 return needs to remember which) (C02-T7).
    #: 79: `machines/layers.CountPermanentsControlledBy` and
    #: `CountPermanentsWithSubtypeControlledBy` gained `excludes_self` ("for
    #: each other artifact you control", C02-T8).
    #: 80: `SpendClause` gained `min_mana_value`/`requires_x_in_cost` and
    #: `ManaSpend` gained `mana_value`/`x_in_cost` (Helga, Skittish Seer's
    #: spend restriction, C02 integration).
    #: 81: `Game` gained `turn_counts`/`turn_counts_last_turn` (the per-turn
    #: count ledger) and `damage_dealt_this_turn`, `CastRecord` gained
    #: `cast_step`/`cast_during_turn_of`, and `machines/triggers.GameEvent`
    #: gained `declared_attacker` (EC2's condition reader;
    #: renumbered from 74 at the EC round 1 merge).
    #: 82: `CastRecord` gained `kicker_costs_paid`, `bargained`,
    #: `evidence_collected`, `revealed_for_cost`,
    #: `controlled_subtypes_as_cast`, `creature_mana_spent` and
    #: `snow_mana_spent`, and `ManaPool`/`ManaPayment` gained `creature`/
    #: `creature_spent` (EC3's cast-record condition readers).
    #: 83: `Game` gained `turn_history`/`turn_history_last_turn`
    #: (`TurnHistoryEntry`), `exile_residents_seen` and
    #: `dealt_combat_damage_since_their_turn`, and `DamageDealt` gained
    #: `source_supertypes`/`source_colors`/`recipient_types`/
    #: `recipient_controller`/`excess` (EC4's turn-history readers;
    #: renumbered from 82 at the EC round 2 merge).
    #: 84: `Player` gained `starting_life` (CR 103.4; EC5's player-state
    #: readers - bumped at the EC round 2 merge, game.py being EC4's).
    #: 85: `CardState` gained `saddled`, `saddled_by`, `suspected`,
    #: `renowned`, `venture_room`, `dungeon_completions` and
    #: `last_known_attachments` (EC6's object-state readers - bumped at the
    #: EC round 2 merge).
    #: 86: `Game` gained `forecast_activations` (CR 702.57b's own once-each-
    #: turn restriction on a forecast ability, tracked per card incarnation
    #: - `KeywordActivation.why_not`/`_activate_impl` in `machines/
    #: keywords.py` are the reader and writer, reachable from a decoded
    #: `Game` the moment a Forecast card sits in a hand).
    #: 87: `machines/delayed.DelayedTrigger` gained `any_main_phase` and
    #: `machines/delayed` gained the `add_mana_amount_for_controller` effect
    #: kind (Mana Sculpt's own "at the beginning of your next main phase",
    #: 273-sos T1).
    #: 88: `machines/turn.TurnMachine` gained `skipped_turns` (CR 614.10's
    #: "skip your next turn" counter, Ral Zarek, Guest Lecturer's own "−7").
    #: 89: `CastRecord` gained `casualty_paid` (CR 702.153a/b, sos T5), and
    #: `CardState` gained `last_known_spell` (CR 608.2h, sos T5), carrying
    #: its `CastRecord` as JSON.
    #: 90: `CardState` gained `manifested` (CR 701.40a), which distinguishes a
    #: manifested permanent from a face-down morph/disguise spell so
    #: CR 701.40b's own turn-up procedure (pay the card's mana cost) is
    #: offered only where it actually applies (FD1's special-action wiring;
    #: renumbered from 86, then 87, at the main merges).
    #: 91: `CastRecord` gained `enters_with_counters` (a cast permission's
    #: CR 614.1c rider, tmt T6) and `Game` gained `next_spell_keyword_grants`
    #: ("the next noncreature spell you cast this turn has affinity for
    #: artifacts", CR 702.41a, tmt T6; renumbered from 90 at integration).
    #: 92: `machines/cost.CostComponent` gained `exile_after` (CR 118.8/
    #: 601.2f's "behold a <quality> and exile it", ecl T4); `CastRecord` and
    #: `machines/casting.Casting` both gained `behold_chosen_type_paid` and
    #: `chosen_creature_type` (Celestial Reunion's own optional "choose a
    #: creature type and behold two creatures of that type" cost, CR 607.2d);
    #: `machines/cost.CostModifierEffect` gained `creature_only` and
    #: `scoped_to_caster` (Urza's Incubator's own `CHOSEN_TYPE_DECREASE`
    #: wording, proven alongside Gathering Stone); `machines/layers.Selector`
    #: gained the `PermanentsControlledByWithSubtype` variant (Selfless
    #: Safewright's own chosen-type grant, ecl T4).
    #: 93: `ContinuousEffects` gained `keyword_counter_stamps` (CR 613.7c's
    #: timestamp for a keyword counter, ordered against layer 6 removals, CR
    #: 613.1f) and `GameEvent` gained `entered_together` (CR 603.6a's one
    #: enters event for several permanents, a pending or stacked trigger's
    #: event); token creation raises its enters events together and counts
    #: each creation event per turn ("token creation", Mirrormind Crown's
    #: "the first time", ecl T5; renumbered from 92 at integration).
    #: 94: `CastRecord` gained `conspire_paid` (CR 702.78a), `CostComponent`
    #: gained `from_among` ("remove N counters from among creatures you
    #: control"), `PlayPermission` gained `while_controlling` (CR 611.2b's
    #: "for as long as you control this creature") and `machines/delayed`
    #: gained the `that_creature_dies_consequence` effect kind ("When that
    #: creature dies this turn, ...") - ecl T7 (renumbered from 92 at
    #: integration).
    #: 95: `machines/delayed.ReturnSubjectToBattlefieldUnderOwner` and
    #: `ReturnEachExiledToBattlefieldUnderOwner` both gained `tapped`
    #: (Morningtide's Light's own "... tapped under their owners' control",
    #: ecl T8), and `PreventionShield` gained `until_next_turn_of`
    #: (Morningtide's Light's own "Until your next turn, prevent all damage
    #: that would be dealt to you.", CR 611.2a, ecl T8; renumbered from 92 at
    #: integration).
    #: 96: `CardState` gained `protector` (CR 310.9); a creature attacking a
    #: battle is now defended by its protector, not its controller (CR
    #: 310.9d, 508.5), and CR 704.5x/704.5y run as state-based actions. Also
    #: battles' defense counters (CR 310.4b), CR 704.5v/w, the Siege defeat
    #: trigger (CR 310.12b) and `Casting.transformed` (CR 712.11a).
    #: 97 (fix-enters-with-counters): a permanent's intrinsic entering
    #: loyalty/defense/lore counters go through `Game.add_counters` (CR 122.6),
    #: so counter replacements and Solemnity now apply to them;
    #: `CounterAmountReplacement` gained `opponent_puts`/`players`/`divisor`/
    #: `round_up`; `CastingRuleEffect` gained `while_source_id`/
    #: `while_source_stamp`; `machines/layers.Selector` gained
    #: `permanents_of_types` and `other_transformed_permanents_controlled_by`;
    #: `machines/casting.PlayPermission` gained `cost_increase`; and every
    #: battle card's previously unread clauses now resolve.
    #: 98: new selector kind `layers.CreaturesControlledByQuality` for a
    #: group-subject "can't be blocked" grant (CR 509.1b; Deepchannel Mentor,
    #: Graaz, Tanglewalker) - fix-cant-be-blocked-by, renumbered from 96 then 97 at
    #: merge.
    #: 99: `CardState` gained `solved` (CR 719.3b's Case designation, R0a-T5;
    #: renumbered from 96 at the R0a integration).
    #: 100: `CardState` gained `unlocked_doors` (CR 709.5c's Room designations,
    #: R0a-T6; renumbered from 96 at the R0a integration).
    #: 101: `Player` gained `speed` and `speed_increased_on_turn` (CR 702.179's
    #: Start your engines! speed, R0a-T8; renumbered from 96 at the R0a
    #: integration).
    #: 102: `AbilityOnStack` gained `mana_spent` and `treasure_mana_spent`
    #: (CR 601.2h via CR 602.2b: what paid an activation's own cost, the
    #: ability-side twin of `CastRecord`'s identical two fields) - Paragon of
    #: Modernity's and Jetmir's Fixer's own "If `<mana condition>`, put a
    #: +1/+1 counter on it instead" (ec7-instead).
    #: 103: `Game` gained `monarch` (CR 725, the monarch designation), and
    #: `machines/abilities.TriggeredAbility` gained `monarch_inherent`, the
    #: tag `machines/monarch.py`'s two synthetic, sourceless CR 725.2
    #: abilities carry so `Game._effect_of` can find their effect without a
    #: card name to key off of (ec7-monarch; renumbered from 96 at
    #: integration and again above main's 97-101).
    #: 104: `GraveyardArrival` gained `card_types` (Raphael, Fiendish Savior's
    #: and Macabre Reconstruction's "a creature card was put into your
    #: graveyard from anywhere this turn", EC7; renumbered from 96 at
    #: integration and again above main's 97-101).
    #: 105: `Game` gained `nontoken_creatures_died_under_control_this_turn`
    #: (ec7-cast-optional: Vile Redeemer's own cast-trigger "for each
    #: nontoken creature that died under your control this turn").
    #: The 101 -> 105 window also changed, under the bumps above rather than
    #: a version of its own: `machines/layers`
    #: `QualifiedCreatures`/`CreatureQualifiers` gained `colorless`; the
    #: `turn_history` event kinds gained "blocked" and "fought"; generic P/T
    #: counters joined `_counter_effects`; and protection gained CR 112.1's
    #: "spell" quality.
    #: 106: `machines/triggers.GameEvent` gained `subject_stamp` (ec7-rv-rules:
    #: a cast-trigger's own X, Hydroid Krasis/Genesis Hydra/Old Stickfingers/
    #: Geometer's Arthropod, read off `Game.cast_record_as_last_known` once
    #: the cast spell has left the stack - CR 608.2h - rather than lost the
    #: moment a countered spell's zone change stamps it fresh).
    #: 107: `Game` gained `attacked_players_this_turn` and
    #: `attacks_unblocked_triggered` (CR 508.3f's attacks-and-isn't-blocked
    #: trigger, `TriggerEvent.ATTACKS_UNBLOCKED`), `CardState` gained
    #: `assigns_no_combat_damage_this_combat`, the replacement layer gained
    #: `DamageLifeFloorReplacement` and the `EventKind.LOSE_THE_GAME`/
    #: `LOSE_LIFE` event kinds, and CR 119.5 "your life total becomes" got one
    #: reader (fix-archangel-beckett).
    #: 108 (stream s7c, one bump): `machines/triggers.AbilityOnStack` gained
    #: `cost_sacrificed_powers`/`cost_sacrificed_toughnesses` (CR 608.2h last
    #: known information for "the sacrificed creature's power/toughness");
    #: `machines/delayed` gained the `create_token_copy_of_last_known`
    #: effect kind (Ochre Jelly's Split) and `CardState` gained
    #: `last_known_copiable` (CR 707.2 as it last existed); a counter-count
    #: intervening "if" now reads the past tense ("it had") off the last
    #: known counters, and a returning Aura chooses its host (CR 303.4f/g);
    #: `machines/replacement.CreatedReplacementSpec` gained
    #: `LeaveBattlefieldExile` (Whip of Erebos' "If it would leave the
    #: battlefield, exile it instead of putting it anywhere else", one
    #: permanent for as long as it stays the same object - CR 614.1a,
    #: CR 400.7), reachable from `Game.created_replacements`; `Duration`
    #: gained `UNTIL_END_OF_COMBAT` ("can't block this combat", CR 500.5a/511.2).
    #: 109 (stream E5, one bump): the turn-history record gained
    #: `cast_mana_spent` and the "left_battlefield"/"spell_warped" kinds
    #: (intervening ifs, CR 603.4); `CreatedReplacementSpec` gained
    #: `DieToExileReplacement` ("if a creature would die this turn, exile it
    #: instead", CR 614.1a); `CardState` gained `flipped` (CR 710);
    #: `TargetRequirement` gained `object_dealt_damage_clause` and
    #: `ThatCreatureDiesConsequence` gained `source_stamp` (CR 400.7);
    #: combat's `Attack` gained `blocked_by` (CR 509.1h); the layer selector
    #: union gained `SelfIfAttachedCount`, `SelfIfControlsCounted` gained
    #: `of_its_controller` and `ControlledQuality` gained `color`.
    #: 110 (round 293-fra): `GameEvent` gained `loyalty_removed` (CR 606.4),
    #: read by "if you removed two or more loyalty counters to activate it".
    #: 111 (fix-station): `BaseAbility` gained `station_threshold` (CR 721.2a)
    #: and `ManaAbility` gained `for_each_expression`, both reachable from
    #: `Game` through a pending `AbilityOnStack.ability`.
    #: 112 (fix-mana-any-combination): "Add N mana in any combination of
    #: {A} and/or {B}" parses as a mixed palette mana ability (it read as one
    #: mana of one colour), an X announced by the cost counts, and the new
    #: `AddManaInAnyCombinationForController` delayed effect kind.
    #: 113 (fix-mana-leftovers): `Answer` gained `mana_abilities` (a
    #: `PAY_MANA` answer naming mana abilities of any cost, CR 605.3a),
    #: reachable from `Game` through the decision tape; and existing boards
    #: resolve differently - a step ending under "If you would lose unspent
    #: mana, that mana becomes <colour> instead" / "You don't lose unspent
    #: <colour> mana" keeps the mana (CR 106.4, 614.1a), Ozai's "as long as you
    #: have six or more unspent mana" grants apply, and Xenagos's `-6`,
    #: Tezzeret, Master of the Bridge's `-8`, Omnath, Locus of All's first-main
    #: trigger and Sorin the Mirthless's `+1` resolve where they did nothing.
    #: 114 (NW01-T2): `CastRecord` gained `additional_cost_kinds` and
    #: `additional_cost_powers` (which verb paid each additional-cost card, and
    #: its power as the cost was paid, CR 608.2h), and `CostComponent` gained
    #: `every_matching` ("sacrifice all creatures you control"); existing
    #: boards resolve differently - Burn at the Stake, Soulblast, Nahiri's
    #: Wrath and Corpse Cobble read back what their additional cost paid.
    #: 115 (nw01-t3-damage): `TargetRef` gained `slot` (CR 601.2c: which target
    #: requirement it filled), and `TargetRequirement` gained `must_be_enchanted`
    #: ("target enchanted creature", CR 303.4b).
    #: 116 (nw02-t2-prevention): `PreventionShield` gained `source_filter`
    #: (`ShieldSourceFilter`, CR 609.7b), `players_only`, `and_permanents_of`
    #: and `reflects` (`ReflectedDamage`, CR 615.5); `created_replacements`
    #: can hold a `GainNoLifeReplacement` (CR 614.1a, CR 119.10).
    #: 117 (NW02-T3): `CastRecord` gained `controlled_modified_creature_as_cast`
    #: (CR 700.9, CR 601.2i: Flame Discharge's "If you controlled a modified
    #: creature as you cast this spell" is fixed at casting); an existing
    #: stack of that spell reads the base branch only. 116 is held by another
    #: NW-02 task.
    #: 118 (NW03-T1): `PreventionShield` gained `recipient_types` and
    #: `recipient_controller` ("to creatures", "to you and creatures you
    #: control"); `ShieldSourceFilter` gained `creatures`, `colors_any`,
    #: `colorless` and `not_controlled_by` (CR 609.7b, CR 105.2c);
    #: `ReflectedDamage` gained `optional` (CR 608.2d, CR 615.5); `CardState`
    #: gained `last_known_attacking` (CR 608.2h, "by attacking creatures").
    #: 125 (NW04-T5): `ReflectedDamage` gained `to_source_controller`,
    #: `source_quality`, `reflexive` and `draws` (CR 615.5, CR 603.12:
    #: Deflecting Palm, Honorable Passage, New Way Forward);
    #: `DamageRedirectReplacement` gained `amount_is_x`, `protects_yours`,
    #: `protected_types` and `redirect_player` (CR 614.9, CR 115.4: Harm's
    #: Way, Shining Shoal); `DelayedEffectSpec` gained the
    #: `reflexive_prevented_damage_payoff` kind.
    #: 126 (nw-04-waterbend): `CastRecord` gained `waterbend_paid` (CR 701.67a,
    #: CR 118.8b: a spell's optional "you may waterbend {N}"), folded into
    #: `optional_additional_cost_paid`; an existing stack of Ruinous
    #: Waterbending would otherwise read its paid branch as unpaid.
    #: 127 (nw-05-t6-keywords): `BaseAbility` gained `level_band` (CR 711.2a/b),
    #: reachable from `Game` through a pending `AbilityOnStack.ability`; a
    #: leveler's striated ability decoded without it would read as one the
    #: permanent has at every level.
    #: 128 (nw-05-t4): `TurnHistoryEntry` gained `damage_baseline` (CR 120.1,
    #: CR 400.7: the damage already marked when a permanent entered, so "the
    #: amount of damage dealt to it this turn" counts only this incarnation).
    #: 129 (NW05-T5): `DamageModifierReplacement` gained `any_controller`
    #: (CR 614.1a: Rankle and Torbran's "If a source would deal damage to a
    #: player or battle this turn" applies to every source, not only yours);
    #: decoded as current, an older turn-long modifier would keep reading
    #: "you control" and a new one would lose its reach.
    #: 130 (NW05-T2): `DamageRedirectReplacement` gained
    #: `redirect_to_enchanted` (CR 614.9, CR 303.4b: Saving Grace's "is dealt
    #: to enchanted creature instead"); an older created redirect decoded
    #: without it would read its target index instead.
    #: 131 (NW06-T4): `machines/abilities.TriggeredAbility` gained
    #: `triggers_only_if` (Quakebringer's "This ability triggers only if ..."),
    #: reachable from `Game` through every `AbilityOnStack.ability`; an older
    #: dump's ability would decode without its restriction.
    #: 132 (NW06-T1): `PreventionShield` gained `recipient_subtypes` (Pack
    #: Leader's "to Dogs you control", CR 611.2c) and `TargetRequirement`
    #: gained `battles_protected_by_event_player` (Rampaging Raptor's "battle
    #: that player protects", CR 310.9e); decoded as current, an older shield
    #: or announced target would cover every permanent of its controller.
    #: 139 (EP01-R1-T6, reserved: 133 + task 6): the layer selector
    #: `QualifiedCreatures` gained `enchanted` (Necromancer's Magemark), and the
    #: delayed-effect union gained `SpellEntersWithAdditionalCounter` (Kumano
    #: Faces Kakkazan II) and `ReturnThatCardToBattlefieldUnderOwner` (Melira);
    #: a card in exile with an exile-conditioned trigger is now offered events
    #: (Darigaaz Reincarnated). The integrator renumbers to contiguous order.
    #: 133 (NW06-T5): `CardState` gained `chosen_player` (CR 614.12a's "choose
    #: a player/an opponent"), `devoured` (CR 702.82b) and
    #: `controlled_since_upkeep`, and `Game` gained `upkeeps_begun` (echo, CR
    #: 702.30a); an older dump would decode with no chosen player, nothing
    #: devoured and every permanent's echo due again. The same (unreleased)
    #: version also covers `SpendClause.class_level` on floating mana's CR
    #: 106.6 restriction (NW-06 integration, Sorcerer Class's "to gain a Class
    #: level", CR 716.2a).
    #: 134 (EP01-R1-T1): `CastRecord` gained `convoked` (CR 702.51c, "for each
    #: creature that convoked it") and `returned_mana_value` (CR 702.188a,
    #: web-slinging's "mana value of the returned creature"); an older dump
    #: would read every convoked spell as convoked by none. `Game` also gained
    #: `lands_entered_this_turn` (Bioengineered Future's "for each land that
    #: entered the battlefield under your control this turn").
    #: 137 (EP01-R1-T4): `CardState` gained `paired_with` (CR 702.95a's soulbond
    #: pair); an older dump would decode every creature unpaired, so a
    #: Flowering Lumberknot that was paired could no longer attack or block.
    #: The same version: `machines/cost.CostComponent` gained
    #: `shared_creature_type` (Weight of Conscience's "that share a creature
    #: type"), reachable through a pending activation's cost.
    #: 140 (EP01-R1-T7): `Game` gained `noncombat_damage_to_players_this_turn`
    #: (Chandra's Incinerator's "the total amount of noncombat damage dealt to
    #: your opponents this turn", CR 601.2f); an older dump would read none.
    #: 140 also: `CardRequirement.keywords` (Sephara, Sky's Blade's "tap four
    #: untapped creatures you control with flying") and
    #: `CreaturesControlledByQuality.excluding_card_id` (its "other creatures
    #: you control with flying"), both defaulting to nothing in an older dump.
    #: 142 (EP01-R2-T1): `Game` gained `text_change_originals` (CR 612.1, CR
    #: 613.1c, Swirl the Mists): the printed `Card` of every object whose rules
    #: text a color-word change is rewriting, so it can be put back when the
    #: effect stops. An older dump decodes with none, which is right: no text
    #: change was recorded.
    #: 147 (EP01-R2-T6, reserved main + 6): `Game` gained `exerted_this_turn`
    #: (CR 701.43a, Combat Celebrant's "hasn't been exerted this turn"); an
    #: older dump would let a creature exerted earlier this turn exert again.
    #: 141 (EP01-R1-T8): `CardState` gained `crafted_with` (CR 702.167c, the
    #: exiled cards used to craft a permanent), `KeywordActivation` gained
    #: `craft_materials` and `ManaSpend` gained `no_mana` (Hogaak); an older
    #: dump would decode a crafted Mastercraft Raptor with no materials, so its
    #: power would read 0.
    #: 145 (EP01-R2-T4, reserved: 141 + task 4): `CardState` gained
    #: `has_dealt_damage` (Karakyk Guardian's and Ratonhnhake's "hasn't dealt
    #: damage yet"); an older dump would read every creature that has dealt
    #: damage as one that has not, handing it hexproof back.
    #: 148 (EP01-R2-T7, reserved: 141 + task 7): `ManaPool` gained `basic_land`
    #: (CR 106.3, the part of the pool a basic land made - Imperiosaur's "Spend
    #: only mana produced by basic lands"), `ManaPayment` gained
    #: `basic_land_spent` and `ManaSpend` gained `only_from` / `any_type`; an
    #: older dump would let floating nonbasic mana pay for Imperiosaur.
    #: 149 (EP01-R2-T8): `Modification` gained `RemoveSupertype` (Aeve) and
    #: `LoseAllAbilitiesExceptManaAbilities` (Blood Sun), both stored in a
    #: continuous effect; an older dump would refuse to decode an effect of
    #: either kind. T8's reserved number (main at the cut + 8).
    #: 153 (EP01-R3-T4, reserved: 149 + task 4): `CardState` gained
    #: `merged_order`, and `Game` gained `merged_components`
    #: (mutate, CR 702.140, 730.2); an older dump would decode a mutated
    #: permanent as its bottom card alone, with its other components lost.
    #: 157 (EP01-R3-T8, reserved: 149 + task 8): behavioural changes to
    #: name-keyed dispatch a decoded game could already be pointing at - a
    #: trigger's "that much" / "its mana value" / "that creature's power" now
    #: read the resolving event, a damage-event trigger names the planeswalker
    #: it hit, "Enchanted player can't gain life." and "Players have no maximum
    #: hand size." are read off the battlefield, and a Crew N ability is
    #: once-per-turn; an older dump would resolve each of these as a no-op.
    #: EP-02-R2: T2, T4, T5 and T7 each reserved 164; the round lands as one version, 169.
    #: 170 (EP02-R3-T1): the layer model gained `Count` kinds (and
    #: `PermanentIds`) that a decoded older effect never carried, so the
    #: static "gets +N/+N for each ..." readers resolve differently; the
    #: `GAIN_CONTROL` cost component and the `untap_all_creatures_for_controller`
    #: delayed effect joined their unions.
    #: 171 (EP02-R3-T1): `GameEvent` gained `subject_power` and `died_together`
    #: (the simultaneous-death batch of "whenever one or more creatures die",
    #: CR 603.2c / CR 704.3), reachable from `Game` through a pending
    #: `AbilityOnStack.event`.
    #: 173 (EP02-R3-T3): `PlayPermission` gained
    #: `any_color_mana` (Daxos of Meletis's "you may spend mana as though it were
    #: mana of any color to cast that spell" on a CR 601.3 grant); a decoded older
    #: permission would price the cast against the printed colors, and a pending
    #: Daxos grant would refuse a payment it should accept. Also the persisted
    #: selector variant `CreaturesControlledButNotOwnedBy` (Laughing Jasper
    #: Flint's "creatures you control but don't own are Mercenaries"), reachable
    #: from `Game.continuous_effects`.
    #: 174 (EP-02-R3-T4): `GameEvent` gained `batch_ids` (a pending
    #: `AbilityOnStack.event`'s "from among them", for CR 603.2c's batched "put
    #: into exile" event); an older dump has none, so a "put into exile" trigger
    #: would never have seen the exiled cards. Also dispatch a decoded game could
    #: already point at: "draw X cards, then you may put a permanent card with
    #: mana value X or less from your hand onto the battlefield" off a
    #: sacrifice, the per-colour graveyard return, the two-target graveyard
    #: return, "return ... and all Auras attached to it", and the any-type-mana
    #: rider on "If you cast a spell this way"; an older dump would resolve
    #: each of these as a no-op.
    #: 175 (EP02-R3-T5): `Game` gained
    #: `loyalty_activation_allowance` (Kaito, Dancing Shadow's "activate loyalty abilities of
    #: Kaito twice this turn", CR 606.3); `ExileMarker` gained `HAUNTING` (CR 702.55b) and
    #: `TriggerEvent` gained `RESOLVED_INTO_GRAVEYARD` (CR 702.55a), both reachable through a
    #: haunting card in exile and a pending trigger's event; the layer modification union gained
    #: `SetToughness` (CR 613.4b, an exchanged life total); `delayed.SacrificeSubject` gained
    #: `max_mana_value` (Angrath, the Flame-Chained's "if it has mana value 3 or less") and
    #: `TargetRequirement.comparison_count` gained `CONTROLLER_LIFE` (Blazing Hope). An older
    #: dump would decode a haunting card as an ordinary exiled one, and a second loyalty
    #: activation, a toughness exchange or a conditional sacrifice as the plain one.
    #: 169 (EP02-R2-T2): `Player` gained `cannot_cast_spells_for_rest_of_game`
    #: and `CardState` gained `epic_suppressed` (epic, CR 702.50a/b), and
    #: `DelayedEffectSpec` gained the variant `epic_copy_spell`; a pending
    #: `AbilityOnStack` can carry it. Also behavioural changes to dispatch a
    #: decoded game could already point at: an animation sentence with no
    #: printed stats whose quoted ability defines them (Svogthos), a pawprint
    #: mode profile (CR 700.2i), "equipped creature gets +X/+X until end of turn"
    #: off a trigger, an equip cost scaled by the hand, and the free cast of an
    #: instant or sorcery bounded by "that damage"; an older dump would resolve
    #: each of these as a no-op.
    #: 169 (EP02-R2-T4): `CardState` gained `prototyped` (CR 718.3b, the
    #: alternative mana cost, power and toughness of a prototyped spell and its
    #: permanent; a decoded older object is never prototyped); `AbilityOnStack`
    #: gained `cost_discarded_card_ids` and
    #: `cost_discarded_mana_values` (the card an activation's "Discard a card"
    #: cost moved, for "damage equal to the discarded card's mana value" and
    #: "X/X, where X is the discarded card's mana value"); a decoded older
    #: ability would resolve those texts with no discarded card to read, and
    #: referenced-permanent amounts ("its controller gains life equal to its
    #: toughness", "scry X, where X is its power", "look at the top X cards ...
    #: where X is that creature's power", the sacrificed permanent's mana value
    #: as X damage and life) now resolve where an older dump would have done
    #: nothing.
    #: 169 (EP02-R2-T6, reserved: 163 + task 6): `AbilityOnStack` gained
    #: `cost_tapped_card_ids`, `cost_tapped_powers` and `cost_sacrificed_types`
    #: (the permanents a cost tapped or sacrificed, for "the power of the
    #: creature tapped this way" and "if you sacrificed an Angel this way"), the
    #: `DelayedEffectSpec` union gained `phase_in_each` (Out of Time's "phase out
    #: until this enchantment leaves the battlefield") and
    #: `reflexive_damage_equal_to_subject_mana_value` (Hidetsugu's "when you
    #: exile a nonland card this way"), a permanent held phased out for a
    #: duration carries `phased_out_under = "until:<source id>"`, and an
    #: overloaded spell (CR 702.96a) resolves its changed text; an older dump
    #: would resolve each of these as a no-op or as the unchanged spell.
    #: 163 (EP02-R1-T6, reserved: 157 + task 6): a `DelayedEffectSpec` variant
    #: `return_subject_then_discard_its_stat` (Vanish into Memory's return with
    #: its "if you do, discard cards equal to that creature's toughness"), and
    #: behavioural changes to dispatch a decoded game could already point at -
    #: "you gain life / draw cards / mill cards equal to its power", "deals
    #: damage equal to the sacrificed creature's power" off an activation cost,
    #: "equal to that creature's toughness" after a destroy, exile or edict, an
    #: "enters" condition qualified by a subtype-and-creature or "with flying"
    #: subject, and a "colorless" word in a cost's card requirement; an older
    #: dump would resolve each of these as a no-op or fire the trigger on every
    #: creature.
    #: 169 (EP02-R2-T7): `Game.mana_spent_on_spells_this_turn` (CR 700.14's
    #: expend), `SpellCostReductionGrant.once` (Kaza's "the next instant or
    #: sorcery spell you cast this turn costs {1} less ..."), and a
    #: `DelayedEffectSpec` variant `damage_each_opponent_per_card_still_exiled`;
    #: an older dump has no running total, so it would expend from zero.
    #: 162 (EP02-R1-T5, reserved: 157 + task 5): `ActivationCostReduction`
    #: gained `graveyard_quality` (an activated ability's "costs {1} less ...
    #: for each creature card in your graveyard"), reachable from `Game`
    #: through a pending `AbilityOnStack.ability.cost_reduction`; graveyard
    #: counts ("for each <type> card in your graveyard", "card types among
    #: cards in your graveyard", "that player's graveyard") now resolve where
    #: an older dump would have resolved the same text as a no-op.
    #: 178 (T-110 B6): `Player` gained `spells_cast_this_game` ("the first spell you've
    #: cast this game"); an older dump could not say how many spells a player had cast.
    #: 177 (T-110 B4): `TurnMachine` gained `extra_turns_begun_by` (CR 500.7,
    #: "haven't begun an extra turn this game"), `ReplaceableEvent` gained
    #: `attacking` (CR 508.4), and a decoded game's permanents now read honorific
    #: short names (CR 201.5c), "a card leaves your graveyard", the phasing lock,
    #: a group destroy replacement, abilities granted to exiled cards and The
    #: Holodeck's outside-the-game permission; an older dump could not say so.
    #: 176 (EP02-R3-T8): `PlayPermission` gained `harmonize` (CR 702.180a), so a graveyard
    #: card that "gains harmonize" (Songcrafter Mage) is cast with the tap-a-creature discount
    #: and exiled instead of going to the graveyard; and `DelayedEffectSpec` gained the
    #: `CipherCopyAndCast` variant (CR 702.99a, Whispering Madness), which an older decode
    #: cannot name; an older dump could not say so.
    #: 169 (EP-02-R2-T5): `machines/layers` gained the persisted selector variants
    #: `CreaturesControlledByOpponentsOfWithPowerAtMost` and
    #: `PermanentsOfTypesWithCounter` and the modification variant
    #: `SetPowerToughnessToCounters`, all reachable from `Game.continuous_effects`;
    #: and dispatch a decoded game could already point at now reads "for each kind of
    #: counter", "double the number of ... counters", "remove ... counters. ... removed
    #: this way", a loyalty-counter-sized creature, a base power and toughness set on a
    #: group, and a CR 603.8 "has N or fewer counters" state; an older dump would
    #: resolve each of these as a no-op.
    #: 172 (EP-02-R3-T2): `ManaPool` gained `cave` and `ManaPayment` `cave_spent`
    #: (CR 106.3's Cave provenance), `CastRecord` gained `cave_mana_spent` (Bat Colony),
    #: and `CreatedReplacementSpec` gained `TokenAmountReplacement` (Kaya's turn-long
    #: token doubler); `ManaSpend`/`SpendClause` gained `has_foretell`/
    #: `requires_foretell` and `SpendPurpose` `FORETELL` (Niko Defies Destiny's
    #: restricted mana); and an `AbilityOnStack.x_value` now holds a count locked "as
    #: you activate this ability" (Lukka). An older dump would resolve each of these
    #: as a no-op or refuse the restricted mana.
    """Bumped 1 -> 2: `CardState` gained `state_class` (defect 2, the
    `engine-stateless-library` review) - a field added to `CardState`, per the
    bump rule above, and one whose absence would change what a decode of a
    copy-of-a-permanent-spell mid-stack means (a plain `CardState` loses CR
    111.8's protection the moment it becomes a token, silently).

    Bumped 2 -> 3: `AbilityOnStack` gained `state_class` (T3, the
    `StackObject`-discriminated-union task) - a field added to a persisted
    model, per the bump rule above, needed to turn `StackObject` from an
    untagged `CardState | AbilityOnStack` union into a discriminated one so a
    `TokenState` in `Game.shared_zones` dumps without a
    `PydanticSerializationUnexpectedValue` warning. A snapshot written at
    version 2 has no `state_class` on any `AbilityOnStack` it holds, so
    decoding it at version 3 would fail the union's own discriminator lookup
    with no signal beyond a raw pydantic error - refusing it at the schema
    check instead names the real reason.

    Bumped 3 -> 4: `TargetRef` gained `zone_change_stamp` (CR 400.7/608.2b -
    the blink-versus-removal-spell defect: a target that changed zones and
    came back is a new object even though `CardState.id` did not change, and
    nothing previously recorded which incarnation a target reference named).
    A snapshot written at version 3 has every `TargetRef` on the stack with
    no stamp at all, which `Game.legal_target` reads as "cannot judge the
    zone-change half of CR 608.2b" rather than as evidence of anything - a
    silent fail-open on the exact rule this field exists to enforce, so a
    version-3 snapshot is refused rather than decoded as if it were current.

    Bumped 4 -> 5: `Game` gained `keyword_line_notices`, and - the half that
    actually matters - `machines/combat.py::has_keyword` reads a computed
    ability line with a wider vocabulary than it used to. A version-4 snapshot
    is a board on which Emrakul, the Promised End has no flying and no trample,
    because `protection from instants` sharing their line took them down with
    it; decoded under version 5 the same board has both. That is a
    name-keyed dispatch resolving differently on state that already exists -
    the bump rule's second bullet exactly - and it changes who may block whom
    and how much damage a defending player takes, so a version-4 snapshot is
    refused rather than replayed into a different game.

    Bumped 5 -> 6: the CR 106.6 spend-restriction grammar (`machines/cost.py`)
    learned two forms, and both bullets of the bump rule are tripped at once.

    *The field.* `SpendClause` gained `zone` - the origin the spell's
    CR 601.2a move started from, one of CR 400.1's seven zones (all three
    looked up this session) - and a `SpendClause` is reachable from
    `Game.model_dump()` through `Player.mana_pool.restricted[].restriction.
    clauses[]`, so a floating restricted mana carries one. A version-5 dump
    has no `zone` key on any clause it holds, and decoded at version 6 that
    absence reads as "this clause asks nothing about the origin zone": the
    Web Watch's "Spend this mana only to cast spells from exile" quietly
    paying for a spell cast from the hand. `ManaSpend` gained the same field
    for the other side of the check.

    *The behaviour.* `machines/abilities.py` now reads "Add two mana in any
    combination of colors" as a per-mana colour choice, on Interdimensional
    Web Watch and Smokebraider - printings that were already in the pool, so a
    version-5 board can already have one on the battlefield with that ability
    parsed the old way. A `machines/abilities.py` mana-ability parse is the
    bump rule's second bullet by name. And-joined type lists ("instant and
    sorcery spells") are a parse that used to fail closed and now permits,
    which changes what an already-recorded restricted mana in a pool may pay
    for.

    Bumped 6 -> 7: the same grammar again, and the same two bullets.

    *The field.* `SpendClause` gained `joined` - whether the qualities it
    holds were printed as a list (alternatives) or juxtaposed (all required),
    which is what tells "instant and sorcery spells" from "Dragon creature
    spells". A version-6 dump has no `joined` key, and every clause it holds
    was written by a parse that asked for one card type from its list *and*
    one subtype from it; decoded at version 7 the missing key reads as
    `False`, "all of them required", which is the right answer for the
    juxtaposed clauses and the wrong one for every joined list - Séance
    Board's "instant, sorcery, Demon, and Spirit spells" would go on paying
    for nothing.

    *The behaviour.* `machines/cost.py` reads three things it used to read
    differently, all of them on printings already in the pool: a printed
    plural is read back to the subtype it names ("activate abilities of
    Elementals", Smokebraider - a clause that permitted nothing now permits
    what the card says), "and" and "and/or" split two clauses the way "or"
    already did, and `machines/abilities.py` reads a printed count of mana up
    to ten rather than three. Each changes what an already-recorded restricted
    mana in a pool may pay for, or what an already-recorded permanent's mana
    ability produces.

    Bumped 7 -> 8: known information. `Reveal` gained `viewers`,
    `zone_change_stamp`, `turn` and `library_epoch`, `Player` gained
    `library_epoch`, and `Game` gained `known_carries` - fields added to
    models reachable from the dump, the bump rule's first bullet. A version-7
    snapshot's reveals carry no stamp and no epoch, and decoded here every one
    of them would be a record of a shape `Game.known_to` refuses: a game in
    which everything already shown had silently stopped being known. Refused
    instead.

    Bumped 8 -> 9: `Decision` gained `source_id` - the id of the object asking
    each question - and a `Decision` is reachable from `Game.model_dump()`
    through `decisions.asked`. A dump written before it has no `source_id` on
    any question it recorded, and decoded at version 9 that absence would read as
    "no object asked this" - the claim this field makes only for a turn-based
    action, a state-based action or the pregame - on every shockland's,
    fetchland's and scry spell's question alike. Refused rather than decoded
    into a record that says the wrong thing about who asked.
    This change and the known-information one above were each stamped 7 -> 8
    on separate lines of development, so a version-8 dump is either one
    without the other: known information with no `source_id`, or `source_id`
    with no stamp or epoch on any reveal. 9 is the first version that means
    both, and every 8 is refused.

    Bumped 9 -> 10: `CardState` gained `cast_with_keyword` (CR 702.176a's
    impending asks "if this permanent's impending cost was paid" of the
    permanent on every later end step), and `machines/layers.py`'s
    `Modification` union gained `RemoveType`. A version-9 dump of a permanent
    cast for its impending cost records no paid cost on the permanent, so
    decoded here it would read as a hardcast creature that happens to carry
    time counters - refused instead.

    Bumped 10 -> 11: `Game` gained `library_orders_kept`, the rows that keep a
    library record true through a put onto the bottom or a scry/surveil
    put-back that did not reorder its card (CR 701.20d, CR 401.2). A
    version-10 dump has none, and decoded here every record such a put had
    kept would silently end. Refused instead.
    The two were built in parallel, each as 9 -> 10, so a 10 from either line
    lacks the other's field; merged, the number moved on once more.

    Bumped 11 -> 12: `Decision` gained `quality` (which CR 614.12a quality a
    `CHOOSE_A_QUALITY` question asks), tokens are created with `owner` set to
    their creator (CR 111.2) instead of `None`, and Malevolent Rumble lost its
    `EFFECTS` row to a reveal-to-hand parser that records each reveal. A
    version-11 dump holds decisions with no quality, ownerless tokens, and
    possibly a Rumble on the stack that would now resolve differently.
    Refused instead.

    Bumped 12 -> 13: battle 5. `AbilityOnStack` gained `modes` and
    `mode_targets` (a modal triggered ability's modes are chosen as it goes on
    the stack, CR 603.3c), `Game` gained `announced_reveal_counts` and
    `search_description_notices`, `CostComponent` gained `variable_count` and
    `source`, `ExileMarker` gained `LINKED`, and a card moved from a public
    zone into its owner's hand now carries a `KnownCarry`. A version-12 dump
    holds modal triggers with no chosen mode, which decoded here would be
    asked again at resolution, and hand cards whose public origin left no
    record. Refused instead.
    This change and battle 3's above were each stamped 11 -> 12 on separate
    lines of development, so a 12 from either line lacks the other's fields;
    merged, the number moved on once more.

    Bumped 13 -> 14: battle 6. `CastRecord` gained `keyword_cost_paid` (warp's
    delayed exile applies only "If this spell's warp cost was paid", CR
    702.185a) and `Decision` gained `mana_sources` (an "unless ... pays"
    payment may activate mana abilities, CR 608.2g). A version-13 dump holds
    cast records that read every warp cast as cast for its mana cost. Refused
    instead. Battle 6 was stamped 12 -> 13 on a line of development beside
    battle 5's, so a 13 from either line lacks the other's fields; merged, the
    number moved on once more.
    Bumped 14 -> 15: battle 4. `Answer` gained `damage` (the
    `ASSIGN_COMBAT_DAMAGE` tape field, CR 510.1c, CR 702.19b), `Decision`
    gained `lethal_damage`, `default_damage` and `trample`, and `Game` gained
    `unreadable_counter_amount_notices`. A version-14 dump has no notices list
    and a tape that cannot hold a combat damage assignment, so a paused combat
    decoded here would replay against a question that build never asked.
    Refused instead. Battle 4 was stamped 11 -> 12 on its own line of
    development; landed after battles 3, 5 and 6, it moved on to 15.

    Bumped 15 -> 16: battle 7, U1 (PR #21) and battle 8, one bump for all
    three because none of them was deployed at 16 on its own.
    Battle 7: no field was added, but existing state now resolves
    differently, the bump rule's second bullet: a triggered mana ability (CR
    605.1b) resolves at once instead of from the stack (CR 605.4a), so a
    version-15 dump can hold Leyline of Abundance's trigger on the stack that
    no version-16 game could have put there; a scry that bottoms two or more
    cards asks CR 401.4's order, so a version-15 tape replays one question
    short; "Put one of them into your hand and the other/the rest ..." looks
    and the attacks-each-combat requirement (CR 508.1d) are read now, so a
    recorded declaration or spell on the stack can decode into a different
    game.
    U1: `AbilityOnStack` gained `source_last_known` (CR 113.7a, 608.2h), and
    the resolution of "Gain control of target ... Untap that creature. It
    gains haste until end of turn." changed on spells and abilities alike: a
    version-15 stack holding Act of Treason resolved without the untap or the
    haste.
    Battle 8: `Game.cast_records` is keyed by the described object's
    `zone_change_stamp` instead of its card id, `CastRecord` gained `card_id`
    (CR 400.7, B8-02), and `AbilityOnStack` gained `source_stamp` so a
    resolution recheck reads the record of the object the ability came from
    (CR 113.7a). A version-15 dump holds id-keyed records that would read as
    no record at all.
    Refused instead.

    Bumped 16 -> 17: `TurnMachine` gained `turns_taken_by`, each player's
    count of their own turns begun (CR 102.1, CR 500.7 extra turns included),
    read through `TurnMachine.own_turns_taken`. A version-16 dump has no such
    field, and it cannot be rebuilt from what that dump holds once an extra
    turn has been taken, so a default would silently misstate it. Refused
    instead.

    Bumped 17 -> 18: `machines/delayed.py` gained the
    `reflexive_counter_count_consequence` `DelayedEffectSpec` kind (Earthbender
    Ascension's "When you do, if it has four or more quest counters on it"),
    and `machines/triggers.py` condition matches changed for state already on a
    battlefield: counter-count intervening ifs read "N or more"/"N or fewer",
    CR 603.8 state triggers read a spelled count, "draw your Nth card each turn"
    triggers, and "you've cast N or more spells this turn" reads without a type
    list. A version-17 dump could hold a pending trigger or a landfall ability
    that now resolves differently.

    Bumped 18 -> 19: a finality counter now exiles its permanent instead of
    letting it reach a graveyard (CR 122.1h). A version-18 battlefield holding
    one resolves that permanent's death differently under this build. "You may
    sacrifice <N> ... If/When you do" now reads a count other than one
    (Leviathan, Scavenger's Talent), so a version-18 stack holding such a
    trigger resolved as a notice and now sacrifices. Refused instead. Stamped
    17 -> 18 on its own line of development, beside the delayed-trigger/
    intervening-if change above which claimed 18 first; merged, the number
    moved on once more.

    Bumped 19 -> 20: `Game` gained `creatures_died_this_turn` (morbid, CR
    207.2c, CR 700.4). A version-19 dump has no count of the deaths it already
    saw this turn, and a default of zero would switch morbid off mid-turn.
    Refused instead.

    Bumped 20 -> 21: `machines/delayed.py`'s `DrawACardForController` gained
    `count` (a delayed "draw `<n>` cards", not just one - Nth-draw and
    for-each-qualifier draw triggers whose delayed half now reads a count
    other than 1). `count` defaults to 1, which is every version-20 use's
    only possible value, but a `DelayedEffectSpec` is reachable from
    `Game.model_dump()` and the bump rule's first bullet does not carve out
    an exception for a field whose default happens to match every existing
    use - refused rather than trusted on that observation holding forever.

    Bumped 21 -> 22: number sweep G0b, the "that many" count channel.
    `AbilityOnStack` gained `cost_exiled_card_ids`, and a batched "one or
    more ... attack" trigger's `event` now carries its own `amount`. A
    version-21 stack holding a "that many"/"this way" ability (Fable of the
    Mirror-Breaker II, The Earth King, Corpseweft) resolved as a notice or
    nothing and now moves cards. Refused instead. `ManaPool` also gained
    `retained` (CR 500.5a/500.5b mana that survives a step or phase ending -
    firebending, Photon, Mighty Marvel); a version-21 pool has none, so a
    decoded one never silently loses mana it never had a way to keep.

    Also bumped 21 -> 22, independently, on the fu-costs line: `Player`
    gained `emblems` (CR 114.2 - Wrenn and Seven's -8, Tamiyo, Inquisitive
    Student's -7), and `has_no_maximum_hand_size` read it, changing what
    `cards_over_maximum_hand_size` (and so the cleanup step's own discard)
    computes for a player any such emblem reaches.

    Bumped 22 -> 23: the number sweep G0b and fu-costs lines of development
    each claimed 21 -> 22 on their own; merged, the number moves on once
    more. Both halves carry over: G0b's (above) and fu-costs', which added
    CR 114 emblems - now one subsystem, emblem objects in the shared command
    zone (`Game.create_emblem`, `Game.emblems_of`; `Player.emblems` reads
    them), which also changes what `cards_over_maximum_hand_size` computes
    for a player an emblem reaches. `Game.ability_resolutions_this_turn` is
    new too. Refused instead.

    Bumped 23 -> 24: the fra-s3 line of development claimed 21 -> 22
    independently too, for `life_gained_amount_this_turn` (Germinate
    Recruits' own "where X is the amount of life you gained this turn" -
    CR 107.3f) - the running-total twin of `life_gained_this_turn`'s plain
    boolean, recorded in `Player.gain_life` for the same CR 119.9 reason. A
    version-23 dump has no record of how much life was already gained this
    turn, and a default of zero would silently answer "none" for a turn
    where life was in fact already gained before the snapshot. Merged onto
    the G0b/fu-costs line above; the number moves on once more. Refused
    instead.

    Bumped 24 -> 25: the FRA S5 line of development (trigger events and
    per-turn history), reconciled at the same merge as this note. `Game`
    gained `turn_facts`/`turn_facts_last_turn` - a general per-turn,
    per-player fact ledger (`record_turn_fact`/`turn_fact_holds`) for the
    batch of this-turn predicates the stream adds (CR 701.22d's scry, CR
    701.25c's surveil, CR 606.3's loyalty ability, CR 120.2a's noncombat
    damage) - and `graveyard_arrivals_this_turn` (`GraveyardArrival`, one
    entry per card that reached a graveyard this turn, with its origin zone
    and whether it was a permanent card as it left the battlefield):
    deliberately shaped so a Descend-style "permanent cards put into
    graveyards this turn" count and this stream's own "from a library" one
    both read the same ledger, for whichever of this branch and fu-events'
    (not yet merged) lands its own record second. `GameEvent` (reachable
    from a decoded `AbilityOnStack.event`) gained `target_id`/
    `target_controller`/`target_types` (a damage event's recipient, not just
    its source), `discarded_ids` (which cards a batched discard actually
    moved), and `attacking_alone`/`attacking_player_alone` (CR 506.5/506.6,
    settled once the whole attacking party is known). `machines/delayed.
    DelayedTrigger` (reachable from `Game.delayed_triggers`) gained
    `combat_only`/`to_player_only`, both defaulting `False` - Lyra, Tolarian
    Archangel's own granted "Until end of turn, whenever Lyra deals combat
    damage to a player, draw two cards." None of these fields existed for a
    version-24 dump to have populated, so a default would silently read
    every attacks-alone/is-dealt-damage/discard-this-card condition as
    false, or a delayed trigger of Lyra's shape as also matching noncombat
    damage and damage to a creature, rather than admit the state was never
    recorded. Refused instead. (The stream's own independent `Player.
    life_gained_tally`/`life_gained_tally_turn` field, for the identical
    fact fra-s3's `life_gained_amount_this_turn` above already covers, was
    dropped at this same merge rather than carried forward - one mechanism,
    not two; no schema bump needed for a field that never reached a build
    anyone decoded.)

    Bumped 25 -> 26: the fra-s3b line of development claimed 24 -> 25
    independently too, for `machines/delayed.py`'s `DelayedTrigger` gaining
    `forbidden_types` (CR 205.2a's type negation - "a noncreature spell" -
    checked against a watched event's own subject) alongside FRA S5's
    `combat_only`/`to_player_only` on that same model, and for a new
    `DelayedEffectSpec` member, `CreateTokenCopyOfControlledToken` (Summon:
    Good King Mog XII's Saga chapters II and III: "Whenever you cast a
    noncreature spell this turn, create a token that's a copy of a non-Saga
    token you control."). A version-25 dump's own delayed triggers have no
    `forbidden_types` at all, so a default empty tuple is exactly right for
    every one of them (none could have used a field that did not exist yet)
    - refused anyway, per the bump rule's own "a field added to ... anything
    reachable from [`Game.model_dump()`]" bullet, not because this one's
    default could ever disagree with an old dump. Merged onto the FRA S5
    line above; the number moves on once more.

    Bumped 26 -> 27: the fu-events line of development claimed 21 -> 26
    independently too, in its own five steps, reconciled at the same merge
    as this note. Four of its five fields are real additions, carried
    forward under this one combined bump:

    - `CardState` gained `granted_rebound` (CR 702.88, Ojer Pakpatiq,
      Deepest Epoch's own "it gains rebound") - one whose absence would
      silently drop a granted rebound for a spell mid-resolution on the
      stack.
    - `machines/layers.py`'s `Selector` discriminated union gained
      `PermanentsOfTypesControlledBy` (Sorin, Vengeful Bloodlord's own
      "creatures and planeswalkers you control have lifelink" - a compound
      subject `PermanentsControlledBy` cannot name).
    - `machines/layers.py`'s `Count` discriminated union gained
      `CountCreaturesWithSubtypesControlledBy` (The Mycotyrant's own
      characteristic-defining "the number of creatures you control that are
      Fungi and/or Saprolings").
    - `Game` gained `next_time_draw_replacements` (Urabrask, Heretic
      Praetor's own "the next time they would draw a card this turn,
      instead they exile the top card of their library" - CR 614.1a's
      one-shot "next time ... instead ..." shape, distinct from
      Plagiarize's every-draw-until-end-of-turn shape).

    The fifth, `permanent_cards_to_graveyard_this_turn` (CR 700.11, Descend's
    own running count), was dropped rather than carried forward: FRA S5's
    `graveyard_arrivals_this_turn` above already ledgers the identical fact
    more generally, so `Game.descended`/`Game.descend_count` now read
    `cards_put_into_graveyard_this_turn(player, permanent_only=True)`
    instead - one mechanism, not two, per `CLAUDE.md`'s own rule. A
    version-26 dump from either line is refused either way, since every one
    of the four surviving fields is a field added to something reachable
    from `Game.model_dump()`, per the bump rule's first bullet.

    Bumped 27 -> 28: the FRA S2 line of development (Prepare / preparation
    cards, CR 722), reconciled at the same merge as this note. `CardState`
    gained `prepared`/`prepared_copy_id`/`prepare_spell_face` and `Game`
    gained `attacked_this_turn` (Hexhaven Dueling Arena's own "target
    creature that attacked this turn" - deliberately not folded into
    `turn_facts` above, since that ledger answers "did this player's
    creatures do X" and this needs *which* creature). A version-27 dump has
    no record of which permanents were prepared, what their exile copies
    were, or which creatures attacked this turn - a default of "none of the
    above" would silently un-prepare every prepared permanent (dropping its
    castable exile copy from the decode entirely) and refuse every "attacked
    this turn" target that should be legal. Refused instead. (The stream's
    own independent `Player._record_life_gained`/`life_gained_tally` field,
    for the identical fact `life_gained_amount_this_turn` above already
    covers - inherited from an earlier merge with fra-s3 on the FRA S2
    branch itself - was dropped at this same merge rather than carried
    forward, the same "one mechanism, not two" call this file already made
    once for the same pair of fields.)

    Bumped 28 -> 29: the FRA S10 line of development (costs, casting rules,
    mana - CR 601.3/604.5/605.1b/605.4a work), reconciled at the same merge
    as this note. `CastRecord` gained `exile_instead_of_graveyard` and
    `PlayPermission` gained `any_type_mana`/`condition`/`exile_instead_of_
    graveyard` (Dire Fleet Daredevil's "mana of any type can be spent to
    cast that spell" and "exile it instead of graveyard" riders on a CR
    601.3 grant; Null Summoner's Threshold-conditioned grant). `DelayedEffectSpec`
    gained two variants: `RevokeGrantedAbility` (Emrakul, the Exigent Doom's
    own land-mana-grant, revoked when the exiled card is cast) and
    `AddManaWhenLandTapped` (Molten Tide's/High Tide's "until end of turn,
    whenever you tap a Mountain for mana, add an additional {R}" delayed
    trigger). The last also changed how `Game._resolve_triggered_mana_
    abilities` runs: a delayed triggered mana ability now resolves inline,
    with no stack, per CR 605.4a - `DelayedEffectSpecBase.is_mana_ability`
    is a new `ClassVar` read there, not a persisted field, but the
    resolution behaviour itself is exactly the "a `DelayedEffectSpec`'s
    resolution" case the bump rule's second bullet already names. A
    version-28 dump has none of the new fields (all default `False`/`None`,
    silently dropping which spell an exile-instead redirect or an
    any-type-mana grant belonged to) and no way to decode a pending
    `RevokeGrantedAbility`/`AddManaWhenLandTapped` delayed trigger's own
    `kind` at all. Refused instead.

    Bumped 29 -> 30: the FRA S9 line of development (static abilities,
    layers, replacement statics - reconciled at the same merge as this
    note), branched from FRA S5's tip before the S2/S3b/fu-events/S10
    reconciliations above landed, so its own independent history (which
    re-numbered the same ground those cover, from Lyra's `combat_only`/
    `to_player_only` at its local 22 -> 23 onward) carries no field this
    line does not already have except the two below. `Game` gained
    `combat_damage_dealt_this_turn_by` (Ruric Thar, Magecrusher's "hexproof
    as long as they haven't dealt combat damage yet"), and
    `machines/layers.py`'s `LayerContext` gained `turn_facts`/
    `combat_damage_dealt_this_turn` (`active_player` above already covers
    the same "whose turn it is" reader Skilled Battlecarver's own
    during-your-turn grant needed) plus `has_turn_fact`/
    `has_turn_fact_for_opponent`, read by newly-parsed static shapes
    (scried-or-surveilled-this-turn, opponent-noncombat-damage-this-turn,
    and Ruric Thar's own combat-damage-yet condition). A version-29
    snapshot mid-combat has no record of which creatures already dealt
    combat damage this turn, and a default of "none" would wrongly grant
    Ruric Thar hexproof back after it has already fought - refused rather
    than silently mis-answering. The same merge also builds the shroud
    subsystem (CR 702.18a): `machines/combat.py`'s `KEYWORDS_OUTSIDE_COMBAT`
    gains "shroud" and `Game.shroud_refusal`/`TargetingProfile._check_shroud`
    now enforce it. No field changed, but this is the bump rule's second
    bullet by name: a permanent printing "Shroud" that a version-29 decode
    could legally target (the ability was inert - recognised by no
    vocabulary, enforced nowhere) becomes untargetable the instant this
    build reads the same snapshot, for a spell or ability already recorded
    against it. Refused instead.

    Bumped 30 -> 31: FRA S4's own planeswalker/loyalty subsystem work,
    merged onto this line at the same point as this note (its own branch
    read "Bumped 29 -> 30" for the identical FRA S9 ground the paragraph
    above already covers, superseded by it here).
    `Game` gained `loyalty_instant_speed_permissions` (a new
    `LoyaltyInstantSpeedPermission` model, CR 606.3's timing loosened for
    Jace's Machinations' own resolved grant) and `extra_land_plays` (Way of
    the Paradox's own resolved land-drop grant, CR 305.2). `machines/
    delayed.DelayedTrigger` gained `expires_end_of_next_turn`,
    `defending_controller_only`, and `required_any_types`; `machines/
    triggers.GameEvent` gained `defender_controller`; `machines/delayed`'s
    `DelayedEffectSpec` union gained a new variant, `PumpEventSubject`
    (Jace, Reality Sculptor's own `-3`'s delayed attack pump). A version-30
    snapshot mid-watch (an active "until your next turn" attack-pump
    trigger, an unspent instant-speed loyalty grant, or an unspent extra
    land drop) has no record of any of these and a default of "none" would
    silently drop the still-active grant; refused rather than
    mis-answering.

    Still version 31 - two narrow gaps closed on the same branch before it
    merged, combined into this one note rather than bumped again, since
    neither changed anything a version-30 snapshot could already be resolved
    against mid-decode: `machines/decisions.DecisionKind` gained
    `CHOOSE_PLAYERS` (CR 701.34a's own "and/or players" half of Proliferate),
    with `Decision.players` and `Answer.usernames` alongside it - a wholly
    new decision kind no older snapshot's pending decision or answer tape
    could ever have recorded, so an old dump decodes exactly as before. And
    `AbilityOnStack`/`CardState` both gained `target_amounts` (an unequal
    two-target damage split, "`<n>` damage to `<phrase1>` and `<m>` damage to
    `<phrase2>`" - Hungry Flames), `None` by default and populated only as
    resolution of that specific shape begins, so a version-30 stack object
    mid-resolution simply has none yet, same as it always would have.

    Still version 31 at the FRA S8 merge (zone-movement templates: hand/
    library/graveyard/exile/outside-the-game) - reconciled with no bump at
    all. Its own independent history (branched before the fra-s3/FRA S5/FRA
    S9 reconciliations above landed) claimed 21 -> 24 for `life_gained_
    amount_this_turn` (fra-s3, "Bumped 23 -> 24" above) and
    `noncombat_damage_recipients_this_turn`/`scried_or_surveilled_this_turn`
    (FRA S9, "Bumped 29 -> 30" above), which this line already has. It also
    built `machines/triggers.GameEvent.recipient_id`, a *permanent* damage
    recipient for the passive "is dealt damage" condition (Hexhaven
    Invigorator) - the identical fact FRA S5's own `target_id`/`target_
    controller`/`target_types` above already carries, just for a narrower
    case (a permanent only, not a player too). Dropped in favour of the
    existing fields rather than carried forward - `condition_matches`'s own
    passive-voice branch already reads `target_id` before a self-referential
    check on `recipient_id` could ever be reached, so the second field and
    its own dead branch were both a redundant "two mechanisms" the way
    `CLAUDE.md`'s own rule already forbids elsewhere in this history, not
    reachable at all rather than merely unreachable *the way* a bumped-and-
    then-superseded field is. No schema change either way.

    Bumped 31 -> 32: FRA S7's own two fields, merged onto this line together
    as one combined bump rather than the two separate ones ("21 -> 22" and
    "22 -> 23") its own branch history recorded before it caught up to this
    merge - `Game` gained `die_to_exile_this_turn` (Essence Burn's own "if
    it would die this turn, exile it instead", a new required-shape field
    with no default an older snapshot could supply) and `TurnMachine`
    (reachable from `Game.turn`) gained `extra_phase_queue`/`resume_index`
    (CR 500.8's queued extra-phase steps, Aggravated Assault's "After this
    main phase, there is an additional combat phase followed by an
    additional main phase.") - both new fields per the bump rule above.

    Bumped 32 -> 33: FRA S8b's own merge, folded into one combined bump
    rather than left at its own branch's stale 31 - `machines/delayed.
    DelayedTrigger` gained `attacking_alone_only` (The Last Ronin's own Saga
    chapter III, CR 506.5's "attacks alone" read as a structured field the
    same way `combat_only`/`to_player_only` already are, since `DelayedTrigger
    .matches` has no string condition to parse it off) and `machines/delayed.
    DelayedEffectSpec` gained a new discriminated-union member,
    `CountersAndKeywordsEventSubject` (the same chapter's own permanent-
    counter-plus-temporary-keyword-grant resolution) - both reachable from
    `Game.delayed_triggers.triggers`, so both are new-field/new-kind bumps
    per the rule above even though no pre-existing decoded snapshot could
    ever have exercised either (CR 603.7's delayed trigger did not exist to
    create one before this change). `machines/decisions.DecisionKind` also
    gained `CHOOSE_PILE` (CR 700.3's pile-choice primitive, Liliana of the
    Veil's own `-6`/Do or Die) - not itself reachable from a `Game` dump (a
    pending `Decision` is raised, never persisted, per `schema_version`'s
    own docstring on why this field exists at all), so that addition alone
    would not have forced this bump on its own; bumped together with the
    two `DelayedTrigger`/`DelayedEffectSpec` additions above as one merge-
    wide note rather than two.

    Bumped 33 -> 34: FRA batch E's own merge, renumbered from its own
    branch's stale "32 -> 33" (already spent by FRA S8b's merge just above,
    landed first) - `machines/delayed.DelayedTrigger` gained `defending_
    opponent_only` (Garruk, Curse Breaker's own `-4`, "whenever one or more
    creatures attack one of your opponents" - the opposite half of the
    existing `defending_controller_only`'s compound-defender check), and
    `machines/delayed.PumpEventSubject` (a `DelayedEffectSpec` variant a
    live `DelayedTrigger.effect` can already be pointing at, Jace, Reality
    Sculptor's own `-3` among them) gained `keywords`, so the same delayed
    pump can also grant an ability (trample) alongside the power/toughness
    change - two new fields per the bump rule above, both with a default an
    older snapshot's decode fills in unchanged (`False`/`()`), which is
    exactly the "same shape, different meaning if left undetected" case
    this field exists to catch rather than trust to a silent default.

    Bumped 34 -> 35: CR 603.1b compound trigger conditions ("When you cast
    this spell and whenever this creature attacks") now parse into one
    `TriggeredAbility` per condition, so a card already on a decoded
    battlefield or stack (Cityscape Leveler, Orcish Bowmasters, Voice of
    Resurgence) triggers on events it silently ignored before; `Game` gained
    `cards_drawn_in_own_draw_step`; and the anaphoric "Its controller ..."
    sentence now runs for a legal target the destroy failed to move. Same
    bump: `once_per_turn_triggers` is keyed on the ability's printed text
    rather than its condition, and `cards_drawn_in_own_draw_step` is reset
    per draw step.

    Bumped 35 -> 36: `machines/decisions.Decision` gained `abilities`, a
    `PendingAbility` per `ORDER_TRIGGERS` question - id, source id, source
    name, printed text and controller for each ability CR 603.3b is ordering,
    reachable from a decoded game via `Game.decisions.asked` (a pending
    `ORDER_TRIGGERS` question a caller paused on and dumped). The batch is in
    no zone at all at the moment the question is asked (CR 603.3b comes one
    step before CR 603.3 puts anything on the stack), so a client reading a
    paused game previously had no way to name it or point at its source.

    Bumped 36 -> 37: `Player` gained `targeting_grants` (CR 702.11c/702.11d/
    702.18a's player hexproof and shroud from a resolved effect, with its CR
    611.2a duration) and `CardState` gained `last_known_colors`/`types`/
    `subtypes` (CR 608.2b's last known information for an ability's source).
    Behaviour changed on state that can already exist too: hexproof now
    refuses abilities as well as spells and is rechecked at CR 608.2b, a
    "You have hexproof."/"You have shroud." permanent now protects its
    controller, "You gain hexproof ..." clauses now resolve, and Knight of
    Grace's "+1/+0 as long as any player controls a black permanent" now
    applies - so a version-36 snapshot is refused rather than replayed into a
    different game.

    Bumped 37 -> 38: infect, wither and toxic (CR 702.90, 702.80, 702.164)
    now change what damage does - `Game.deal_damage` gives poison and -1/-1
    counters instead of life loss and marked damage (CR 120.3b, 120.3d), and
    `combat._deal_combat_damage` adds toxic's poison (CR 120.3g). Glistener
    Elf, Blightsteel Colossus and Myr Convert were already printings a decoded
    battlefield could hold, so the same board resolves combat differently
    (the bump rule's second bullet). `CardState` also gained
    `last_known_keywords`, CR 702.90d's last known information (first
    bullet), and "gets N poison counters" and "a creature you control becomes
    the target of a spell" are newly read clauses on Venerated Rotpriest.

    Bumped 38 -> 39: `CombatMachine` gained `first_strike_damage_step` and
    `first_strike_step_ids` (CR 510.4's first-strike combat damage step as a
    step of its own, with its own priority round, and the creatures that had
    first strike or double strike as it began). A version-38 snapshot paused
    in a combat damage step would resume into a different game, so it is
    refused.

    Bumped 39 -> 40: `CastRecord` gained `is_copy`, and `Game.copy_spell` now
    writes a `CastRecord` for every copy it makes (CR 707.10: a copy carries
    the choices made for the original, but "a copy of a spell isn't cast").
    A version-39 snapshot holding a copied spell on the stack has no record
    for it and would resolve that copy differently, so it is refused.

    Bumped 40 -> 41: `Decision` gained `default_may` (the unscripted answer
    to "you may shuffle" after a look-and-put-back is to decline), and "look
    at the top N cards of your library, then put them back in any order"
    plus its optional shuffle are newly read, so a paused game asking that
    question, or holding such an ability, would resume differently.

    Bumped 41 -> 42: `CardState` gained `monstrous`/`monstrous_x` (CR
    701.37a-c's Monstrosity keyword action and its own designation), and the
    Monstrosity action, the `TriggerEvent.BECOMES_MONSTROUS` trigger, and the
    "as long as ... is monstrous" static condition are all newly read. A
    version-41 snapshot holding a permanent that had already become
    monstrous has no record of it - the designation would silently vanish,
    any "as long as monstrous" static would stop applying, and a repeat
    Monstrosity activation would put counters on it a second time.

    Bumped 42 -> 43: `CardState` gained `goaded_by` (CR 701.15, Goad). A
    version-42 dump has no record of which creatures are goaded or by whom,
    and a default of "nobody" would silently drop every standing attack
    requirement a goad created.

    Bumped 43 -> 44: `CastRecord` gained `sneak_defender` (CR 702.190b), and
    sneak is newly a way to cast Michelangelo's Technique and every other
    pool printing with it, so a spell of theirs on the stack would resolve
    differently.

    Bumped 44 -> 45: miracle (CR 702.94). No field was added, but existing
    state now plays differently, the bump rule's second bullet: the turn's
    first draw of a card with miracle asks its drawer a new reveal question
    (`Game._offer_miracle_reveal`), so a version-44 tape replaying such a
    draw would read one answer short; `machines/triggers.ExtraTriggerEvent`
    gained `REVEALED_FOR_MIRACLE`, a value a version-44 build cannot decode on
    a pending or stacked trigger; and "Put all creatures on the bottom of
    their owners' libraries" is newly read (Terminus). Refused instead.

    Bumped 45 -> 46: `CastRecord` gained `phyrexian_life_symbols_paid`
    (CR 107.4f), and compleated (CR 702.150a) is newly read: a planeswalker
    with the keyword now enters with two fewer loyalty counters for each
    Phyrexian symbol of its cost paid with life
    (`machines/replacement._compleated_modifier`). Nahiri, the Unforgiving,
    Ajani, Sleeper Agent and Tamiyo, Compleated Sage were already printings a
    decoded stack could hold mid-cast, so the same resolving spell enters the
    battlefield with a different loyalty total - a version-45 snapshot paused
    partway through casting one is refused rather than resolved differently.

    Bumped 46 -> 47: `GameEvent` gained `zone_change_stamp` (CR 400.7e), the
    dying object's graveyard incarnation, which a dies trigger's "exile it" /
    "return it" / "put it into its owner's library" now checks before moving
    the card. `AbilityOnStack.event` persists that event on the stack and in
    `pending_triggers`, so a version-46 snapshot holding such a trigger would
    decode with the stamp `None` and resolve as "nothing found" where it used
    to move the card - it is refused rather than resolved differently.

    Bumped 47 -> 48 (G7): a "`<SUBJ>` `<verb1>`, `<verb2>`, and `<verb3>`"
    shared-subject verb list is newly carried across every item instead of
    only its first. `_parse_optional_player_clause`'s own "you " retry is
    unchanged - it is still every other caller's correct way to read a
    genuinely subject-less fragment - but `_parse_shared_subject_clauses`
    now claims a shared-subject sentence whole, before `_CLAUSE_SEPARATOR`
    ever splits its later items into the orphaned fragments that retry used
    to see. (Round 2 widened this to claim a shared-subject sentence even
    when it sits beside an *ordinary* sentence with no subject word of its
    own - "Draw a card.", "Scry 1." - closing a gap the first cut left open;
    see `_parse_shared_subject_clauses`'s own docstring. The dispatch
    fingerprint's one changed entry from that widening, "You draw a card
    and lose 1 life. Then if your library has no cards in it, you win the
    game." (Doctor Doom, Unrivaled's activated ability), moves from
    `<none>` to `_parse_shared_subject_clauses` in `_parse_mixed_clauses`'s
    own chain - the per-clause split path that used to read it still exists
    and is unchanged, this sentence is just claimed one step earlier now;
    `tests/scenarios/test_self_owner_shuffles_and_win_the_game.py::test_doctor_doom_wins_the_game_when_his_activated_draw_empties_the_library_off_pool`
    reruns the same draw/life-loss/win-check/shuffle against a real board
    and still passes, so this is a dispatch-path change with no behaviour
    change - no further bump for it. No other entry in either whole-text or
    single-clause chain moved, across the full pool - in particular, no
    entry moved off `_parse_optional_player_clause` as `_parse_mixed_
    clause`'s own winner, because that function was never the thing to
    change: the fix is which sentences reach the per-clause split at all.)
    Archon of Cruelty's own trigger went from a no-op to a real
    edict/discard/life-loss; Arbiter of Woe's "each opponent discards a
    card and loses 2 life" now costs the opponent the life instead of the
    controller. A paused game with either trigger already on
    the stack, or one holding either permanent, would resolve that trigger
    differently, so a version-47 snapshot is refused rather than replayed
    into a different game.

    Bumped 48 -> 49: `Game` gained `cleanup_owed` (CR 724.1's "end the turn"
    now performs CR 724.1c's state-based check and defers the cleanup step's
    own CR 514.1/514.2 turn-based actions rather than skipping them, and
    `_before_priority` pays that debt off, CR 514.3a/724.1f included). A
    version-48 snapshot paused mid-resolution after an effect ended the turn
    would resume with that debt silently forgotten - the cleanup that
    "until end of turn" effects and the discard step depend on would simply
    never happen - so it is refused.

    Bumped 49 -> 50: `Game` gained `combat_damage_to_players_this_turn` (CR
    702.76a's prowl: each combat hit on a player with its source's controller
    and creature types at that moment), and Prowl became a cast option with a
    resolution-time "if this spell's prowl cost was paid" reader. A version-49
    snapshot paused after combat damage this turn has no record of it, so
    Morsel Theft's prowl cost would be refused on a board where it is legal -
    refused rather than decoded into that different game.

    Bumped 50 -> 51 (flow 3's integration wave): no field was added, but three
    already-reachable dispatch paths resolve differently now, the bump rule's
    second bullet exactly, like "Bumped 44 -> 45" above. **Blocks**:
    `machines.combat.block_refusal` gained a blocker-side reader for the
    blocker's own "can't block" text (CR 509.1b) - Bloodghast, a real pool
    printing, could declare an illegal block before this; and
    `declare_blockers_step` now calls `Combat.declare_blockers` even when
    nobody blocks (CR 509.1's turn-based action runs regardless), so
    `Combat.blockers_declared` no longer sits falsely `False` after a fully
    unblocked attack reached through `turn_based_actions`/`advance` - which
    CR 509.1h's "unblocked creature" checks (sneak, ninjutsu's return cost)
    read directly. **Annihilation**: `Game._state_based_actions_once` now
    calls `annihilate_counters_on` itself (CR 704.5q's pairwise +1/+1/-1/-1
    removal), which previously lived only in `models/card_state.py` with no
    `Game` caller at all - a decoded permanent already carrying both counter
    kinds was never swept by the engine's own state-based-action loop.
    **Tapping**: `machines/effects.py`'s tap-target effects call
    `CardState.tap_if_untapped` rather than the strict `tap` (CR 701.26a:
    "Only untapped permanents can be tapped" is silent on an already-tapped
    one, not a refusal), so a version-50 snapshot paused mid-resolution of an
    effect targeting an already-tapped permanent would have raised where the
    current build does nothing and continues. **Copies** and **cleanup** are
    not part of this bump: CR 707.10e's illegal-specified-copy-target refusal
    was already covered at "Bumped 39 -> 40" above (the same commit that
    added `CastRecord.is_copy`), and the owed-cleanup machinery at "Bumped 48
    -> 49"; this wave's own copy work (Ivy, Gleeful Spellthief's "targets
    only a single creature other than itself" trigger condition) is a wholly
    new mechanic no pool printing used before it existed to write it - the
    bump rule's own carve-out - so it needs no bump of its own.

    Bumped 51 -> 52 (F1T11 integration): `Game` gained `player_subject_split_
    notices` and `CastingRuleEffect` gained `excluded_source_id` (T5/G2b's
    "You and `<group>` gain `<keyword(s)>` until end of turn" subject split and
    Determined's "Other spells you control can't be countered this turn." -
    fields added to `Game` and to something reachable from its dump per the
    bump rule's first bullet, landed on this branch without their own bump on
    the wave's stated convention of one bump at integration). A version-51
    snapshot holding either - a pending player-half split notice, or a
    `SPELLS_CANT_BE_COUNTERED_GRANT` naming an excluded source - would decode
    with the new field silently absent: the split notice would lose its own
    identity and the exclusion would read as "no exclusion", letting a
    counterspell that should still work against Determined's own casting fail
    instead. (T9/G6's own `GameEvent.zone_change_stamp` - the dead-object-to-
    library dies readers' CR 603.10a/400.7e look-back stamp - already moved
    this version once, 46 -> 47, at its own merge; nothing further to bump for
    it here.)

    This bump also covers the wave's own bump-rule second bullet: f1-t8/G5's
    "you may `<action>`. If you do, `<consequence>`." merger closed Smuggler's
    Copter - a printing already in the pool, not one this task added - from a
    silent no-op (`<none>` in the dispatch fingerprint) to a real reader
    (`parse_mixed_effect`), so a crewed, attacking or blocking Copter's draw-
    then-discard trigger now actually draws and discards instead of doing
    nothing. A version-51 snapshot holding that trigger on the stack, or
    holding the Copter itself, would resolve it differently decoded here, so
    it is refused rather than replayed into a different game. (f3-t8's own
    CR 707.10e generalisation, read against this same rule, changes no
    already-pooled card's resolution - only Ivy, a new fixture this session
    added - so it needs no bump of its own; Frontline Heroism's copy-
    targeting fix was already bumped at its own, earlier merge.)

    Bumped 52 -> 53 (F2T18 integration): no field changed, but
    `machines/triggers.py`'s
    `_ATTACKS_OR_BLOCKS_RE`/`_ENTERS_OR_LEAVES_RE`-style self-reference
    widened from a fixed ten-phrase list (`_SELF_PHRASES`) to every CR 205.2a
    card type and CR 205.3 subtype the pool's own vocabulary knows
    (`_self_reference_type_words`), and `_ATTACKS_OR_BLOCKS_RE`/`_ENTERS_OR_
    ATTACKS_RE` took an open "this `<kind>`" the way `_ENTERS_OR_LEAVES_RE`
    already did rather than a literal "creature" - both a `machines/
    triggers.py` condition match, the bump rule's second bullet by name.
    Smuggler's Copter, already in the pool, is exactly the state this
    changes: a version-52 board reads its "this Vehicle attacks or blocks"
    condition as naming no self-reference at all (a bare, unrecognised
    subtype word `_types_match` used to fall through as "no restriction" on),
    so the same recorded stack could fire the trigger off an opponent's
    unrelated attacker; decoded at 53 it correctly fires only for Copter's
    own attack or block. A version-52 snapshot with that trigger already
    pending is refused rather than resolved into that different outcome.

    Bumped 53 -> 54 (S03): `Player` gained `no_maximum_hand_size_for_rest_of_
    game` (Sea Gate Restoration's "You have no maximum hand size for the rest
    of the game.", CR 613.11/611.2a) - a field added to a persisted model,
    the bump rule's first bullet. `has_no_maximum_hand_size` also now reads a
    permanent's own static "You have no maximum hand size." (Reliquary Tower,
    CR 604.2), which changes what a version-53 board's cleanup discard
    (CR 514.1) does for a player controlling one; and annihilator (CR
    702.86a) now triggers where it did nothing. Refused instead.

    Bumped 54 -> 55 (S05, putting creature cards onto the battlefield): new
    persisted fields - `CardState.last_known_mana_value` (CR 608.2h) and
    `times_transformed` (CR 701.27f), `CastRecord.additional_cost_mana_values`
    and `AbilityOnStack.cost_sacrificed_mana_values` (a sacrificed cost's
    mana value, taken as it was paid), and `DelayedEffectSpec`'s new
    `transform_subject` kind. Activated abilities now also record their
    `source_stamp` (CR 400.7), which moves `resolution_key`.

    Bumped 55 -> 56 (S09, linked "exiled with this" piles): `ExileAnnotation`
    gained `linked_permanent_stamp` (CR 400.7: which incarnation of the
    permanent a CR 607.2a link names) and `GameEvent` gained
    `origin_exile_annotation` (the pile a played card came out of, for "When
    you play a card exiled with this creature") - fields added to models
    reachable from `Game`'s dump, the bump rule's first bullet. An activated
    `AbilityOnStack` now carries `source_stamp` too, and every ability that
    exiles for a source with a linked reader now links what it exiled
    (`machines/effects.link_cards_exiled_during`) - Keen-Eyed Curator, Voltaic
    Visionary, Pyxis of Pandemonium and Boiling Rock Rioter, all already in
    the pool, resolve differently from a version-55 board, the second bullet.

    Bumped 56 -> 57 (S12, impulse exile and exile-until casts):
    `PlayPermission` gained `until_next_end_step_of` ("until your next end
    step", Riveteers Charm) - a field added to a model reachable from
    `Game.play_permissions`, the bump rule's first bullet. Cori Mountain
    Monastery, Burning Curiosity, Riveteers Charm, Territorial Bruntar,
    Improvisation Capstone and Germination Practicum, all already in the
    pool, now resolve where a version-56 board resolved them to nothing,
    the second bullet.
    Bumped 57 -> 58 (S15, resolution-created "this turn" triggers and
    replacements): `Game.draw_redirections` (Plagiarize's one-shape record)
    became `Game.created_replacements`, a `kind`-tagged union covering draw
    redirection, counter-amount and enter-under-your-control replacements;
    `DelayedEffectSpec` gained `CreatedTriggeredAbility`; and a draw replaced
    by "you draw a card" is now the same modified event (CR 614.6) rather than
    a second draw - a version-57 board holding a pending Plagiarize has
    nowhere to decode it to.

    Bumped 58 -> 59 (S18, tap-all and counter manipulation): `CardState`
    gained `last_known_attached_to`, the attachment an Aura or Equipment had
    as it left the battlefield (CR 608.2h), so an Aura's pending enters
    trigger can still find what it enchanted - a field added to `CardState`.

    Bumped 59 -> 60 (S23, static anthems): the `QualifiedCreatures` selector
    gained `nontoken`, `legendary`, `of_chosen_color` and `chosen_color`, and
    the `Count` union gained `CountOtherCreaturesLikeThatOne` - fields and a
    kind added to a `machines/layers.py` continuous-effect spec, the bump
    rule's first bullet. Caged Sun, Voice of All, Mirror Box and Nightpack
    Ambusher, all already in the pool, now apply where a version-59 board
    applied nothing, and protection now also refuses blocks (CR 702.16f) and
    attachments (CR 702.16c, CR 702.16d), the second bullet.

    Bumped 60 -> 61 (S29, day and night): `Game` gained `day_night` (CR
    731.1) and `previous_turn_active_player` (CR 502.2's "previous turn's
    active player") - fields added to `Game`, the bump rule's first bullet.
    Daybound/nightbound permanents already in the pool now transform, and
    "whenever day becomes night or night becomes day" and "enters or
    transforms into" triggers now fire, the second bullet.

    Bumped 61 -> 62 (S30, the Ring tempts you): `Player` gained
    `ring_tempted_count`, `ring_bearer_id` and `ring_bearer_stamp` (CR
    701.54), the `Modification` union gained `AddSupertype`, the
    `DelayedEffectSpec` union gained `SacrificedByItsController` and
    `ExtraTriggerEvent` gained `RING_TEMPTS_YOU` - the bump rule's first
    bullet. Gollum, Patient Plotter's leaves-the-battlefield trigger, already
    in the pool, now tempts where a version-61 game did nothing, the second.

    Bumped 62 -> 63 (S31, phasing): `CardState` gained `phased_out_under`
    and `phased_out_indirectly`, and `Game` gained `phased_out` (CR 702.26) -
    fields added, the first bullet. Savor the Moment's `EFFECTS` row became
    `parse_clause_effect`'s extra-turn and skip-untap clauses, and Teferi,
    Master of Time's -3/-10, Teferi, Timebender's -9 and Haystack's ability,
    all in the pool, now resolve where a version-62 board resolved nothing -
    the second bullet.

    Bumped 63 -> 64 (S33, optional transform and airbend): `AbilityOnStack`
    gained `source_times_transformed` (CR 701.27f), the bump rule's first
    bullet. Aang, Master of Elements' upkeep trigger, Appa, Steadfast
    Guardian's airbend, a board-wide "Spells you cast cost {W}{U}{B}{R}{G}
    less" and "that player controls" targets now resolve where a version-63
    board did nothing, the second.

    Bumped 64 -> 65 (S26, graveyard cast permissions): `Game` gained
    `once_per_turn_cast_permissions_used` and `CastingRuleEffect` gained
    `spell_quality`/`any_graveyard`/`exile_instead`, the first bullet. Saga
    chapters printed with a name, The Great Work's and Liliana, Untouched by
    Death's turn-long graveyard permissions and Jace, Telepath Unbound's -3 now
    resolve where a version-64 board did nothing, the second.

    Bumped 65 -> 66 (C00-T1, activation prohibitions and permissions;
    renumbered from 65 at the C00 integration):
    `ManaSpend` gained `any_color` (CR 609.4b), carried on an open
    `CostPayment.spend` - the first bullet. Pithing Needle's chosen-name
    prohibition, The Wandering Emperor's timing, Agatha's Soul Cauldron's
    grant and any-color spend now apply where a version-65 board did nothing,
    the second.

    Bumped 66 -> 67 (C00-T5, enters-state; renumbered from 65 at the C00
    integration): `CostComponent` gained `link_to_permanent_id` (CR 607.2q),
    carried on a pending ability's own `CostPayment.components` - the first
    bullet.

    Bumped 67 -> 68 (C01-T1, storied): `Player` gained `has_enduring_story`
    (CR 702.195b's designation) - the first bullet. A version-67 board with
    three storied qualifiers has no story where a version-68 one does, and
    every "as long as you have an enduring story" static reads it - the
    second.

    Bumped 70 -> 71 (C01-T7, layers, copy and control): `PreventionShield`
    gained `source_stamp` (CR 400.7) and `lasts_while` (CR 611.2b), and
    `GraveyardArrival` gained `card_id` - the first bullet. Old Fat Spider
    Can't See Me's source-keyed prevention and Supper for Spiders' / Faith's
    Reward's "put there from the battlefield this turn" now resolve where a
    version-70 board did nothing, the second.

    Bumped 71 -> 72 (C01 integration, pack tactics): `CombatMachine` gained
    `declared_attacking_power` - the first bullet. A version-71 board in
    combat would decode with no declared power, and a pack tactics trigger
    already on the stack would do nothing - the second.

    Bumped 72 -> 73 (C01 integration, mana from a Treasure): `ManaPool`
    gained `treasure` and `CastRecord` gained `treasure_mana_spent` - the
    first bullet. A version-72 pool would decode its Treasure mana as plain
    mana, and Smaug, Wicked Worm's trigger on a spell already cast with it
    would not resolve - the second.

    Bumped 73 -> 74 (C02-T2, teamwork): `CastRecord` gained `cast_using_
    teamwork` (`machines/teamwork.py`'s own optional additional cost) and
    `Game` gained `became_tapped_count_this_turn` (Captain America, Living
    Legend's own "if it's the first time that creature has become tapped
    this turn" intervening if) - the first bullet. A version-73 record would
    decode a Teamwork spell's cast as never having used teamwork, so every
    "if this spell was cast using teamwork" rider in the pool would read
    false even for a spell that paid it, and a version-73 board has no
    per-turn tap count for Captain America's trigger to read at all - the
    second.

    Bumped 76 -> 77 (C02-T5, "one or more" batch triggers): `Game` gained
    `tapped_since_last_batch` and `graveyard_arrivals_announced` - the first
    bullet. A version-76 game would decode with every graveyard arrival this
    turn not yet announced and raise them all again as one batch - the
    second.

    Bumped 98 -> 99 (R0a-T5, renumbered from 95 -> 96 at the R0a
    integration): `CardState` gained `solved` (CR 719.3b's Case
    designation) - a field added to a persisted model, the bump rule's first
    bullet. A version-98 Case would decode unsolved forever and its "Solved"
    abilities would never be available. Refused instead.
    """

    @model_validator(mode="before")
    @classmethod
    def _check_schema_version(cls, data: Any) -> Any:
        """Refuse to decode a `Game` snapshot at any schema version other
        than `CURRENT_SCHEMA_VERSION`, and refuse one with no version at all -
        see `schema_version`'s own docstring for why both are refusals rather
        than a silent default. `mode="before"` so this runs on the raw input,
        before pydantic could fill in a default and make "missing" look like
        "current", and so it fires uniformly on `Game(...)`, `Game.
        model_validate(...)`, and `Game` decoded as an element of
        `Match.games` alike.
        """
        if not isinstance(data, Mapping):
            # Not a mapping decode input - a `Game` instance being re-wrapped,
            # or another shape pydantic's own validation will reject on its
            # own terms. Nothing here to check against a raw dict.
            return data
        if "schema_version" not in data:
            raise SchemaVersionMismatch(
                "Game snapshot carries no schema_version field, so it predates "
                "engine schema versioning (current: "
                f"{cls.CURRENT_SCHEMA_VERSION}). Refusing to decode it: engine "
                "behaviour is a function of (state, engine version), not of "
                "state alone, and an unversioned snapshot gives no way to know "
                "which engine version's behaviour it was recorded under."
            )
        found = data["schema_version"]
        if found != cls.CURRENT_SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"Game snapshot was written at schema_version={found!r}, but "
                f"this build decodes schema_version={cls.CURRENT_SCHEMA_VERSION}. "
                "Refusing to decode a mismatched snapshot: a name-keyed "
                "registry or text parser change between those versions may "
                "make this state resolve differently than it did when it was "
                "written, silently. Replay it on the engine version that wrote "
                "it, or migrate it explicitly - decoding it here unmigrated is "
                "not safe."
            )
        return data

    game_uid: UUID = Field(default_factory=uuid4)
    """This `Game`'s own identity, mixed into every id `_allocate_id` mints.

    `shuffle_seed` is what makes two games *shuffle* identically when they
    share a seed (CR 701.24a) - by design, since a replay must reshuffle the
    same way. An object id has the opposite requirement: it must be unique,
    never shared with any other object anywhere, including another game built
    at the default `shuffle_seed=0`. Deriving ids from `shuffle_seed` alone
    made every such game mint the identical sequence
    `uuid5(NAMESPACE_OID, "0:0")`, `"0:1"`, ... - two unrelated games colliding
    on every id in lockstep. `game_uid` is a plain serialised field precisely
    so it survives a decode: a snapshot replayed twice carries the same
    `game_uid` both times (byte-identical replay, `objects_created`'s own
    guarantee below), while a freshly built `Game` gets a fresh one via
    `uuid4`'s own randomness (unique identity, this field's guarantee) -
    `default_factory` runs once per construction, never on `model_validate`
    decoding an already-serialised value.
    """

    objects_created: int = 0
    """How many object ids this game has minted, counting up -
    `shuffles_performed`'s own convention (see its docstring), applied to
    `ids.new_id` instead of `Random`. Every mutating public method installs
    `_allocate_id` as this context's id allocator for the span of its own
    call, through `_id_allocator_scope` (see its docstring), so a game
    replayed from the same decoded snapshot - the same sequence of calls -
    mints the same ids, in the same order, both times.

    Scoped to the one call that installs it, and reset again once it returns,
    rather than installed once for the object's whole life: two unrelated
    `Game`s built moments apart in the same process would otherwise both start
    minting from whatever `_allocate_id` produces first and leave that
    allocator sitting active for whichever next call anywhere in the process
    happens to create an object - a card built for a *different* game's
    opening hand, say - which is a real collision, not merely a cosmetic one:
    two distinct objects would compare equal by id."""

    created_replacements: list[CreatedReplacement] = Field(default_factory=list)
    """CR 614.1a replacement effects a resolved spell or ability left behind
    for a stated duration (CR 611.2a) - Plagiarize's draw redirection, Prairie
    Dog's "that many plus one", Gather Specimens' "enters under your control
    instead" (`machines/replacement.CreatedReplacement`).

    Kept beside `prevention_shields` and for the same reason: the source may
    be a graveyard card, or gone, by the time the effect ever applies, and the
    effect has a duration of its own (CR 514.2 ends it in the cleanup step)."""

    next_time_draw_replacements: list[NextTimeDrawReplacement] = Field(default_factory=list)
    """CR 614.1a's "the next time [player] would draw a card this turn,
    instead ..." - a one-shot replacement, unlike `created_replacements`'
    every-draw-until-end-of-turn shape. Urabrask, Heretic Praetor's own
    triggered ability installs one of these here when it resolves; a future
    draw event for the named player consumes it at most once (CR 614.5) and
    the cleanup step drops whatever is left unused (CR 514.2)."""

    die_to_exile_this_turn: list[UUID] = Field(default_factory=list)
    """CR 614.1a replacement effects a resolved spell left behind, each
    naming one permanent: "If [it] would die this turn, exile it instead" -
    Essence Burn's own rider (Combustion Technique's identical shape is the
    real, off-set printing). Stored the same way `created_replacements` is,
    for the identical reason: the creating spell is long gone in a graveyard
    by the time the replacement ever fires, and CR 514.2's cleanup step ends
    every "this turn" effect, so the whole list is simply cleared there
    rather than tracked per-entry the way a shield's own `until_end_of_turn`
    flag is (nothing here ever outlives its own turn)."""

    prevention_shields: list["PreventionShield"] = Field(default_factory=list)
    """Prevention effects created by a resolving spell or ability (CR 615.1).

    Distinct from `machines/replacement.py`'s registry, which holds the
    prevention effects that are *static abilities* of permanents on the
    battlefield (CR 609.7c) and are rebuilt from the board every time. These
    outlive their source and have a duration, so the game writes them down -
    the same reason `continuous_effects` is a field.
    """

    _holding_mana_triggers: bool = False
    """True while `CostPayment.activate_mana_ability` activates a mana
    ability in the middle of a payment (CR 605.3a): the triggers the
    activation sets off wait in `pending_triggers` for the next player to
    receive priority (CR 603.3), the same as a `{T}` source tapped by
    `tap_for_mana`, rather than going onto the stack under the spell still
    being cast."""

    _mana_hints_planned: bool = False
    """True while a payment's solver planned the tap now resolving its
    triggered mana abilities: a "may add" the plan did not count is declined
    rather than asked (`CostPayment.auto_tap`)."""

    _mana_color_hints: tuple[Color, ...] = ()
    """Colours a payment's solver already chose for the triggered mana
    abilities (CR 605.1b) the tap it is making sets off, consumed by
    `take_mana_color_hint` - the way `CostPayment.auto_tap` picks a dual land's
    colour instead of asking. Empty everywhere else, so an unpicked colour is
    asked (CR 608.2d)."""

    _dealing_combat_damage: bool = False
    """True only while a combat damage step is running (CR 510.2).

    Damage reaches `deal_damage` as a target and a number, with nothing to say
    where it came from, so this is how a prevention effect limited to *combat*
    damage tells the two apart."""

    _combat_damage_this_step: dict[UUID, int] | None = None
    """Damage marked on each permanent during the combat damage step now being
    dealt (CR 510.2: one simultaneous event) - what "all other damage already
    dealt to him" (Wolverine, Fierce Fighter) must not count as already
    dealt. A fresh ledger as each combat damage step begins, `None` outside
    one."""

    automatic_turn_based_actions: bool = True
    """Whether `advance` performs the step's turn-based actions itself (CR 703.3).

    On by default, because the rules say these happen automatically and a game
    that does not draw is not a game. Turning it off is for scenario tests that
    want to drive a single mechanic by hand without the engine acting around
    them - notably a board built with an empty library, whose owner would
    otherwise lose to CR 704.5b the moment `advance` reached the draw step.

    `Game.turn_based_actions` is always callable directly, and
    `Scenario.manual_turn_based_actions()` turns this off for one scenario.
    Note that `Scenario.start_at` walks the turn machine directly and never
    fires turn-based actions, whatever this is set to.
    """

    cleanup_owed: bool = False
    """Whether a cleanup step's own CR 514.1/514.2 turn-based actions are
    owed but have not run yet (CR 724.1d/724.1f).

    Set by `end_the_turn`, which drops the turn pointer straight into the
    cleanup step without performing its discard or its damage/"until end of
    turn" wipe - CR 608.2m lets the spell or ability whose text called it
    keep resolving, and those effects must still be in force for it. Cleared
    by `_before_priority`, which is where the owed cleanup actually happens
    once that resolution finishes: see both docstrings.

    A plain persisted field rather than transient state: CR 608.2d's
    decision-pending pause can leave a game sitting with this true (the
    resolution that set it has not yet reached its own end), and a paused
    game that forgot the debt would resume having silently skipped it.
    """

    def model_post_init(self, _context: object) -> None:
        usernames = [player.username for player in self.players]
        # A stored layer 2 control effect asks the game who may now look at a
        # hideaway card (CR 702.75a), from callers that do not pass `game`.
        self.continuous_effects.bind_to_game(self)
        for player in self.players:
            # CR 701.9a's discard has to be able to consult the game, because
            # CR 702.35a's madness replaces where the discarded card lands. A
            # `Player` on its own has nothing to ask; this is the back-reference
            # that lets `Player.discard` find the rules. Excluded from the
            # serialised model, so it cannot make the game state cyclic.
            player.game = self
        for zone_cards in self.shared_zones.values():
            # `CardState.bind_to_game` (CR 613.5) is what makes `power`/
            # `toughness` ask the layer engine instead of falling back to the
            # printed value plus counters. `Game.put_onto_battlefield` is its
            # only production call site, so a permanent already on the
            # battlefield the moment a `Game` is built straight from a dict -
            # every cold `model_validate` - never got bound at all, and
            # answered with the printed value even under an anthem, silently
            # different from the same game played continuously. This binds
            # every `CardState` the game holds, shared zones and each player's
            # own, the same walk `card_state.bind_all_to_game` does by hand.
            for state in zone_cards:
                if isinstance(state, CardState):
                    state.bind_to_game(self)
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    state.bind_to_game(self)
        for state in self.phased_out:
            state.bind_to_game(self)
        for stack_item in (*self.stack, *self.pending_triggers):
            # `AbilityOnStack.keyword_activation.game` (`machines/keywords.
            # KeywordActivation.game`) is the same shape as `Player.game`
            # above - excluded from serialisation because it is a live `Game`,
            # relinked here rather than kept as a cycle. Both `self.stack` and
            # `self.pending_triggers` can hold an `AbilityOnStack` (`CostPayment.
            # _discard_triggers_caused` checks the same two places for the
            # identical reason), so both are walked even though only an
            # *activated* ability ever actually carries a `keyword_activation` -
            # a triggered one has none to relink.
            #
            # Only `self.stack` is walked among `shared_zones` - not every zone
            # the dict's declared type (`dict[Zone, list[StackObject]]`) would
            # in principle allow an `AbilityOnStack` into. That is correct
            # today: every place this engine puts an `AbilityOnStack` anywhere
            # puts it on the stack (`battlefield`'s own docstring already says
            # as much - "Only cards ever live here, never abilities" - and the
            # same is true of exile, command, and ante, none of which any
            # activation or trigger path ever touches). It is still brittle
            # against the type as written, which says nothing that would stop
            # a future zone from holding one; if that ever changes, this walk
            # has to widen with it rather than silently leaving a relink gap
            # the type system would not catch.
            if not isinstance(stack_item, AbilityOnStack):
                continue
            if stack_item.keyword_activation is not None:
                activation = stack_item.keyword_activation
                activation.game = self
                if activation.payment is not None:
                    # `KeywordActivation.payment` (`machines/cost.CostPayment`)
                    # has the identical `game: Any = Field(exclude=True)` shape,
                    # and without this a resumed crew/equip/cycling payment
                    # that is still `PENDING` - an open ward-shaped cost mid
                    # activation - comes back unable to seed its payer's pool
                    # or find anything it tapped (CR 733.1's rewind needs
                    # `game` to find the payer and the tapped sources by id).
                    activation.payment.game = self
            if stack_item.unless_payment is not None:
                # `AbilityOnStack.unless_payment` (CR 702.21a's ward) is the
                # other `CostPayment` this object can hold, sitting beside
                # `keyword_activation` rather than inside it - relinked the
                # same way and for the same reason: `_seed_payer_pool` needs
                # `game` to have run at all, and a payment paused mid-payment
                # (`begin_paying`, still `PENDING`) needs it seeded to resume.
                stack_item.unless_payment.game = self
        if self.turn is None:
            self.turn = TurnMachine(players=usernames)
        if self.priority is None:
            self.priority = PriorityMachine(players=usernames)
            # A fresh `TurnMachine` rests at `Step.UNTAP`, where CR 502.4 gives
            # nobody priority. Saying so from the first moment is the point:
            # a client polling a just-built game must not be told the active
            # player is on the clock when the only legal next thing is the
            # step ending.
            self.sync_priority_with_step()

    #: The highest X `_announce_alternative_cost_x` ever offers - far past any
    #: board's mana, and a stop for a cost the search could otherwise chase.
    ALTERNATIVE_COST_X_BOUND: ClassVar[int] = 99

    #: Enough for any real multikicker or replicate payment, and a stop for a
    #: cost of nothing, which an unscripted player would otherwise pay forever.
    REPEATED_ADDITIONAL_COST_BOUND: ClassVar[int] = 20

    #: How many triggered mana abilities may resolve inline, back to back, off
    #: one activation before the engine calls it a CR 104.4b loop. There is no
    #: printing in the pool that legitimately chains more than a handful, and a
    #: real loop is unbounded, so any bound well clear of the honest cases
    #: separates the two. See `resolve_triggered_mana_abilities`.
    TRIGGERED_MANA_ABILITY_LOOP_BOUND: ClassVar[int] = 64

    # -- settling a pregame with nobody there to answer -----------------------

    def settle_pregame(self) -> Step:
        """Run the whole pregame through the ordinary decision machinery.

        The headless path, and the one every scenario that just wants a game to
        play uses. Each declaration goes through `ask_mulligan` and each CR 103.6
        action through `Game.ask`, so a scripted answer wins, then the replay
        tape, and only when neither speaks does `default_answer` stand - keep
        the dealt hand, decline every opening-hand action. That is immediate
        and deterministic, which is exactly what it was before this became a
        rested-in step.

        Returns the step the game ends in: `Step.UNTAP` of CR 103.8's first turn,
        unless the game was never in the pregame at all.
        """
        assert self.turn is not None
        with self._id_allocator_scope():
            while self.turn.step is Step.MULLIGAN:
                pending = self.awaiting_mulligan_declarations
                for username in pending:
                    # CR 103.5b: "any time you could mulligan" is a time a seat
                    # owing a declaration may act, before it declares.
                    while True:
                        for option in self.mulligan_time_options(username):
                            if self.ask(option):
                                self.take_mulligan_time_action(username, option.card)
                                break
                        else:
                            break
                    self.declare_mulligan(username, ask_mulligan(self.decisions, username))
                if not pending:
                    # Every seat left is at CR 103.5's ceiling, so the round has
                    # no questions in it at all and nothing triggered its
                    # resolution. Resolving it keeps every remaining hand, which
                    # ends the process.
                    self._resolve_mulligan_round_if_ready()
                # Anything else means a round resolved and a fresh one opened
                # for whoever mulliganed, which is the loop going round again.
                # It always terminates: a player who keeps mulliganing runs out
                # of hand.

            if self.turn.step is Step.PREGAME_ACTIONS:
                self.take_opening_hand_actions()
            return self.turn.step

    #: "You may look at the top card of your library any time." (Courser of
    #: Kruphix, Radha, Heart of Keld, Augur of Autumn; Daredevil's own "Radar
    #: Sense", Ka-Zar's and Iron Lad's own bare printing) - a CR 611.3d
    #: rules-modifying grant to a player, the same family
    #: `plays_lands_from_graveyard_line` above already reads, except this one
    #: grants information rather than a play: not owned by any single
    #: subsystem (`machines/layers.py`, not touched by this task), so it is
    #: read locally here rather than added to that file's own static-grant
    #: readers.
    #: Booby Trap's "The chosen player reveals each card they draw." - CR
    #: 701.20a's reveal, made as each card is drawn by the player the
    #: permanent's CR 614.12a choice named (`Game._reveal_drawn_card`).
    _REVEALS_EACH_CARD_DRAWN_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^the chosen player reveals each card they draw\.?$", re.IGNORECASE
    )
    #: "Play with your hand revealed." (Enduring Renewal) - the controller's
    #: hand is revealed to every player for as long as the permanent grants it
    #: (CR 701.20a), read fresh by `known_to` (`Game.hand_is_revealed`).
    _PLAY_WITH_HAND_REVEALED_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^play with your hand revealed\.?$", re.IGNORECASE
    )
    #: "Play with the top card of your library revealed." (Courser of
    #: Kruphix, Melek, Garruk's Horde) - CR 400.2: the top card is public.
    _TOP_CARD_REVEALED_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^play with the top card of your library revealed\.?$", re.IGNORECASE
    )
    _LOOK_AT_TOP_CARD_ANY_TIME_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^you may look at the top card of your library any time\.?$", re.IGNORECASE
    )
    #: Lens of Clarity's "You may look at the top card of your library and at
    #: face-down creatures you don't control any time." - the top-card grant
    #: above plus CR 708.3's controller-only look, widened to the opposing
    #: face-down creatures on the battlefield (`Game.known_to`).
    _LOOK_AT_TOP_AND_FACE_DOWN_ANY_TIME_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^you may look at the top card of your library and at face-down creatures you "
        r"don't control any time\.?$",
        re.IGNORECASE,
    )
    #: "You may play lands from the top of your library." (Courser of
    #: Kruphix, Radha, Ka-Zar's own second static) - CR 305.1's land drop
    #: opened to a zone other than the hand, the identical shape
    #: `plays_lands_from_graveyard_line` already reads for the graveyard.
    _PLAYS_LANDS_FROM_TOP_OF_LIBRARY_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^you may play lands from the top of your library\.?$", re.IGNORECASE
    )

    #: CR 207.2c's ability word and its em dash, at the very start of a
    #: computed ability line ("Radar Sense — ...") - `computed_board().of(
    #: ...).abilities` hands lines over exactly as printed, with any leading
    #: ability word still attached (`machines/layers.py`'s own `_strip_
    #: ability_word` reads the identical shape for the static-grant readers
    #: it owns; that file is another C02 task's this round, so this is its
    #: own small, local copy rather than an import of a private name).
    _ABILITY_WORD_PREFIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^[A-Z][a-z']*(?: (?:[A-Za-z][a-z']*|\d+))? — (?P<rest>.+)$"
    )

    #: CR 207.2's reminder text, italicized parenthetical rules restatement
    #: that carries no rules meaning of its own - stripped the same way a
    #: trailing "(...)" is elsewhere in this codebase, needed here because
    #: `computed_board().of(...).abilities` hands a static line over with its
    #: own trailing reminder still attached ("Nonartifact spells you cast
    #: have improvise. (Your artifacts can help cast those spells. ...)").
    _TRAILING_REMINDER_TEXT_RE: ClassVar[re.Pattern[str]] = re.compile(r"\s*\([^()]*\)\s*$")

    #: "Noncreature spells you cast have improvise." (Ironheart, Clever
    #: Champion) - CR 113.6's static ability grant, over a whole family of
    #: spells rather than one printed card (CR 702.126a's keyword itself).
    #: The qualifier is the same closed vocabulary `_TYPE_NOUNS`/`Type`
    #: already enumerate; an unqualified "Spells you cast have improvise."
    #: is read too (`quality` group empty).
    _SPELLS_YOU_CAST_HAVE_IMPROVISE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:(?P<negated>non)?(?P<type>creature|artifact|land|enchantment|"
        r"planeswalker|battle|instant|sorcery) )?spells you cast have improvise\.?$",
        re.IGNORECASE,
    )

    #: "Instant and sorcery spells you cast with mana value `<N>` or greater
    #: cost `{X}` less to cast, where X is `<this>`'s power." (The Scarlet
    #: Witch) - matched only after `self_normalized_effect_text` has turned
    #: the card's own printed name back into "this creature" (CR 201.5).
    _TYPE_MV_THRESHOLD_COST_LESS_SELF_POWER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<types>instant and sorcery|instant|sorcery) spells you cast with mana value "
        r"(?P<mv>\d+) or greater cost \{x\} less to cast, where x is this "
        r"(?:creature|permanent|artifact)'s power\.?$",
        re.IGNORECASE,
    )

    #: "You may cast spells as though they had flash." (High Fae Trickster,
    #: unconditional), optionally preceded by "As long as `<condition>`, "
    #: (Captain Mar-Vell's own "Cosmic Awareness — As long as an opponent
    #: has cast a spell this turn, you may cast spells as though they had
    #: flash.") - a CR 611.3d rules-modifying grant to a player, read the
    #: same way the "look at the top card"/"play lands from the top" grants
    #: above are, additively alongside `has_first_spell_flash_grant`'s own
    #: pre-existing Radagast-shaped check rather than in place of it.
    _CAST_SPELLS_AS_THOUGH_FLASH_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:as long as (?P<condition>[^,]+), )?"
        r"you may cast spells as though they had flash\.?$",
        re.IGNORECASE,
    )

    #: Wonder Man, Hollywood Hero's own static: "Each power-up ability of
    #: permanents you control can be activated an additional time." Read
    #: generally off the printed line (any number of card-name variants
    #: could print the identical sentence), not gated to Wonder Man's own
    #: name - `_power_up_activation_limit` is the reader.
    _POWER_UP_EXTRA_ACTIVATION_TEXT: ClassVar[str] = (
        "Each power-up ability of permanents you control can be activated an additional time."
    )

    #: "Power-up abilities of other creatures you control cost `<N>` less to
    #: activate." - Hulk, Gamma Goliath's own static, read generally off the
    #: printed number (CR 601.2f: any amount, not hardcoded to Hulk's own
    #: {3}) so a future printing of the identical template discounts by its
    #: own number rather than Hulk's.
    _POWER_UP_GROUP_DISCOUNT_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^power-up abilities of other creatures you control cost \{(?P<amount>\d+)\} "
        r"less to activate\.?$",
        re.IGNORECASE,
    )

    #: "This ability costs `<N>` less to activate if it targets a `<quality>`
    #: with power `<M>` or less/greater." (Raft Security Officer) - a
    #: reduction gated on the ability's own *chosen target*, CR 602.2b's own
    #: CR 601.2c-then-601.2f ordering (the target is announced before the
    #: cost is priced), unlike `activation_cost_reduction_for`'s own "for
    #: each `<quality>` you control" shape above, which never looks at a
    #: target at all.
    _ABILITY_COSTS_LESS_IF_TARGETS_POWER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"this ability costs \{(?P<n>\d+)\} less to activate if it targets an? "
        r"(?P<quality>[a-z]+) with power (?P<power>\d+) or "
        r"(?P<cmp>less|greater)\.",
        re.IGNORECASE,
    )

    # -- priority ----------------------------------------------------------

    #: CR 502.4, quoted, and the refusal anybody trying to act in untap gets.
    UNTAP_HAS_NO_PRIORITY: ClassVar[str] = (
        "no player receives priority during the untap step, so no spells can be "
        "cast or resolve and no abilities can be activated or resolve (CR 502.4)"
    )

    #: CR 514.3, quoted. Only used for a cleanup step CR 514.3a did not except.
    CLEANUP_HAS_NO_PRIORITY: ClassVar[str] = (
        "normally, no player receives priority during the cleanup step, so no "
        "spells can be cast and no abilities can be activated (CR 514.3)"
    )


__all__ = [
    "ActivationInstructions",
    "ActivationProhibition",
    "CastRecord",
    "CombatDamageToPlayer",
    "CountersPutRecord",
    "DamageDealt",
    "ENERGY_PAID_OR_LOST",
    "ExileArrival",
    "Game",
    "GraveyardArrival",
    "KnownCard",
    "KnownCarry",
    "LibraryOrderKept",
    "LoyaltyInstantSpeedPermission",
    "ObjectCostOffer",
    "PreventionShield",
    "ReflectedDamage",
    "ShieldSourceFilter",
    "RING_EMBLEM_ABILITIES",
    "RING_EMBLEM_NAME",
    "Reveal",
    "SchemaVersionMismatch",
    "ShieldKind",
    "StackObject",
    "Targetable",
    "TurnHistoryEntry",
    "UntapStepRule",
    "_ABILITY_WORD_PREFIX_RE",
    "_ACTIVATE_LEAD",
    "_ACTIVATE_ONLY_IF",
    "_ACTIVATION_PROHIBITION_RE",
    "_ACTIVATION_WINDOW",
    "_ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE",
    "_AFFINITY_CARD_TYPES",
    "_AFFINITY_RE",
    "_AFFINITY_SUBTYPES",
    "_AND_AN",
    "_AND_ONLY_TAIL",
    "_A_QUALITY",
    "_CAST_THIS_TURN_QUALITY_RE",
    "_CHOSEN_NAME_PROHIBITION_RE",
    "_CHOSEN_NAME_SUBJECT_RE",
    "_COLOR_COUNT_QUALITIES",
    "_COLOR_WORDS",
    "_COMBAT_KEYWORDS",
    "_CONDITIONAL_ADDITIONAL_LAND_PLAYS_RE",
    "_CONDITION_ADDITIONAL_COST_PAID",
    "_CONDITION_ATTACKED_WITH_N",
    "_CONDITION_CAST_A_SPELL_THIS_TURN",
    "_CONDITION_CAST_FROM_GRAVEYARD",
    "_CONDITION_CAST_USING_TEAMWORK",
    "_CONDITION_CONTROLS_A",
    "_CONDITION_CONTROLS_ANOTHER",
    "_CONDITION_CONTROLS_N",
    "_CONDITION_CONTROLS_NAMED_PAIR",
    "_CONDITION_CREATURES_DIED_THIS_TURN",
    "_CONDITION_CREATURE_DIED_THIS_TURN",
    "_CONDITION_DESCENDED",
    "_CONDITION_ENTERED_THIS_TURN",
    "_CONDITION_GIFT_PROMISED",
    "_CONDITION_GRAVEYARD_CARDS",
    "_CONDITION_HAND_CARDS",
    "_CONDITION_KICKED",
    "_CONDITION_LAND_ENTERED_THIS_TURN",
    "_CONDITION_LIBRARY_EMPTY_RE",
    "_CONDITION_LOYALTY_AMONG_NAMED",
    "_CONDITION_NOT_CAST_FROM_HAND",
    "_CONDITION_OPPONENT_CAST_COLOR",
    "_CONDITION_OPPONENT_COMPARISON",
    "_CONDITION_OPPONENT_GRAVEYARD_CARDS",
    "_CONDITION_OPPONENT_NONCOMBAT_DAMAGE_THIS_TURN",
    "_CONDITION_OPPONENT_POISON",
    "_CONDITION_OR_IF",
    "_CONDITION_PATTERNS",
    "_CONDITION_POWER",
    "_CONDITION_SACRIFICED_THIS_TURN",
    "_CONDITION_SCRIED_OR_SURVEILLED_THIS_TURN",
    "_CONDITION_SELF_COUNTERS",
    "_CONDITION_SELF_ENTERED_THIS_TURN",
    "_CONDITION_SELF_IS_A_CREATURE",
    "_CONDITION_SELF_NO_COUNTERS",
    "_CONDITION_SPELLS_CAST_THIS_TURN",
    "_CONDITION_SUSPENDED",
    "_CONDITION_TYPES_AMONG_GRAVEYARD",
    "_CONDITION_YOU_ATTACKED_THIS_TURN",
    "_COSTS_LESS_IF_CONDITION_RE",
    "_COSTS_LESS_IF_LIFE_TOTAL_VS_STARTING_X_IS_DIFFERENCE_RE",
    "_COSTS_LESS_IF_TARGETS_DESCRIPTION_RE",
    "_COSTS_LESS_IF_TARGETS_SPELL_RE",
    "_COSTS_LESS_PER_BASIC_LAND_TYPE_RE",
    "_COSTS_LESS_PER_CARD_DISCARDED_RE",
    "_COSTS_LESS_PER_CARD_TYPE",
    "_COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE",
    "_COSTS_LESS_PER_QUALITY_CARD_IN_GRAVEYARD_RE",
    "_COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE",
    "_COSTS_LESS_X_WHERE_X_IS_RE",
    "_COSTS_LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE",
    "_DAMAGE_CANT_BE_PREVENTED_RE",
    "_DRAW_OR_LIFE_GAIN_PROHIBITION_RE",
    "_DRAW_PROHIBITION_RE",
    "_EACH_OPPONENT_PROTECTION_QUALITY",
    "_EXILE_THIS_PERMANENT",
    "_HASTE_ACTIVATION_PERMISSION_RE",
    "_LEGENDARY_TYPE_COUNT_POWER_RE",
    "_LIBRARY_MOVEMENT",
    "_LIFE_GAIN_PROHIBITION_RE",
    "_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE",
    "_LOOKS_LIKE_DRAW_PROHIBITION_RE",
    "_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE",
    "_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE",
    "_LOOKS_LIKE_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE",
    "_LOYALTY_INSTANT_SPEED_STATIC_RE",
    "_MANA_VALUE_QUALITY_RE",
    "_PERMANENT_TYPES",
    "_PLAYER_COUNTERS_PROHIBITION_RE",
    "_PLAYER_PROTECTION_FROM_CHOSEN_NAME",
    "_PROTECTION",
    "_REMINDER_TEXT",
    "_RESTRICTION_DURING",
    "_RESTRICTION_IF",
    "_RESTRICTION_INSTANT",
    "_RESTRICTION_JOIN",
    "_RESTRICTION_ONCE",
    "_RESTRICTION_PER_TURN",
    "_RESTRICTION_SORCERY",
    "_SACRIFICE_A_AND_A",
    "_SACRIFICE_OR_DISCARD",
    "_SELF_COST_REDUCTION_SHAPES",
    "_SELF_LOYALTY_INSTANT_SPEED_RE",
    "_SELF_REFERENCE",
    "_SPELLS_THAT_ARE_QUALITY_RE",
    "_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE",
    "_STEP_NAMES",
    "_SYMBOL_THRESHOLD_EXILE_COST",
    "_TARGET_PLAYER_BEFORE_THAT_PLAYER_RE",
    "_THAT_PLAYER_BINDING_RE",
    "_UNRESOLVED_PROTECTION_QUALITY",
    "_WHO_MAY_ACTIVATE",
    "_ZERO_LOYALTY_EXEMPTION_RE",
    "_activate_named_mana_abilities",
    "_activation_condition",
    "_card_characteristics",
    "_card_quality",
    "_card_type_named",
    "_characteristic_quality",
    "_characteristic_word",
    "_condition_alternatives",
    "_cost_moved",
    "_cost_refers_to_self",
    "_emblem_card",
    "_exiles_itself_by_name",
    "_has_color_quality",
    "_illegal_option_refusal",
    "_is_cast_this_turn_quality",
    "_is_minus_symbol",
    "_is_spell_quality",
    "_named_mana_abilities",
    "_names_match",
    "_names_the_source",
    "_negated_card_type_named",
    "_parse_activation_prohibition",
    "_permanent_quality",
    "_qualities_from_text",
    "_spell_colour_quality",
    "_symbol_threshold_exile_component",
    "_that_player_of",
    "attacked_with_type_facts",
    "builtin_condition_readable",
    "colored_symbol_count",
    "condition_is_readable",
    "conditional_additional_land_plays_of_line",
    "entered_type_facts",
    "is_player_rules_static_line",
    "moves_a_library_card",
    "protection_qualities",
    "protection_quality_readable",
    "read_activation_instructions",
    "reads_activation_rule_line",
    "reads_self_cost_reduction_line",
    "ring_emblem_text",
    "symbol_threshold_exile_cost",
]
