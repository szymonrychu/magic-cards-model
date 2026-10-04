"""Fixture: every placement precedence step."""

import re


def early(text):
    return text


PATTERN = re.compile("a")
SHARED_LIMIT = 4


def alpha_parse(text):
    return PATTERN.match(text), SHARED_LIMIT


def alpha_other(text):
    return helper_one(text)


def helper_one(text):
    return text


def beta_parse(text):
    return SHARED_LIMIT, helper_two(text)


def alpha_special(text):
    return text


class BetaRecord:
    pass


def helper_two(text):
    return text


NOTE = "unreferenced"


def trailing(text):
    return text
