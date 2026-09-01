#!/bin/sh
# Print a Comprehensive Rules rule and its subrules, in full.
#
#     scripts/cr.sh 305.7        one rule and every subrule under it
#     scripts/cr.sh 613.8        613.8, 613.8a, 613.8b, 613.8c
#
# This exists because `knowledge_search(type="rules")` TRUNCATES long rules.
# CR 305.7 came back cut at "and any" on every phrasing tried, and the missing
# tail - "Note that this doesn't remove any abilities that were granted to the
# land by other effects" - was the sentence that settled the question it was
# asked about. knowledge_search stays the fast first stop; this is the primary
# source for when it cuts off or misses.
#
# A leading `^` anchor is deliberate: rule numbers appear inside the prose of
# other rules constantly ("see rule 613"), and only a line-start match is the
# rule itself. The file ships with CRLF line endings, which `tr` strips so the
# output is readable in a terminal.
set -eu

RULES="$(dirname "$0")/../.rules/MagicCompRules.txt"

if [ $# -eq 0 ]; then
    echo "usage: scripts/cr.sh <rule number>   e.g. scripts/cr.sh 305.7" >&2
    exit 1
fi

if [ ! -f "$RULES" ]; then
    echo "no local rules file - run 'mise run rules:pull' first" >&2
    exit 1
fi

found=0
for rule in "$@"; do
    if grep -a "^${rule}" "$RULES" | tr -d '\r'; then
        found=1
    else
        echo "no rule matching '${rule}' - check the number, the CR renumbers" >&2
    fi
done

[ "$found" -eq 1 ]
