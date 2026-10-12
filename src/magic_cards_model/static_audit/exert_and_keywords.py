"""Audit of the EP-01 round 3 exert and keyword statics (T2): the legend rule
switched off for exactly two permanents sharing a name (Brothers Yamazaki). A
line is credited only when the production reader performs it."""

from ..machines.game_rule_statics import legend_rule_pair_name_of_line


def reads_exert_and_keywords_line(printing, text, *, card_name, legendary) -> bool:
    return legend_rule_pair_name_of_line(text) is not None
