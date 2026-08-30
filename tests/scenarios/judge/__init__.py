"""Scenario tests mined from real judge rulings.

Each file here is sourced from the DDR judge-discussion transcripts served by
the `spellslinger` knowledge base (`knowledge_search(type="youtube")`), filtered
down to pure rules interactions - the tournament-policy episodes (missed
triggers, deck checks, angle shooting) are judge procedure and are not
modellable by a rules engine.

Every test docstring names its episode (`DDR#nnn`), states the interaction in
one line, and cites the CR rule the conclusion rests on. Every CR number in this
package was looked up with `knowledge_search(type="rules")`, never written from
memory - the transcripts are people talking and can be imprecise or outdated,
so the rules text is the authority and the tests follow it.

Most of these are `xfail`: the cases judges argue about are precisely the ones
that need triggered abilities, replacement effects, and the layer system, and
those are the parts of the engine still being built. The xfail reasons name what
is missing, so the backlog is the deliverable as much as the passing tests are.
"""
