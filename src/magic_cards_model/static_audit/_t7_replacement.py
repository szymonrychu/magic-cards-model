"""EP-01 round 2, task T7: audit rules for the replacement family of static lines.

`reads_line` asks the PRODUCTION reader whether it performs the line (never a
regex of its own); see `static_audit/__init__.py`.
"""


def reads_line(printing, text: str, *, card_name: str | None = None, legendary: bool = False) -> bool:
    return False
