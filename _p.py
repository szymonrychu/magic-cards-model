from magic_cards_model.machines import effects as E

for text in (
    "Search your library for a creature card with mana value equal to 1 plus the sacrificed "
    "creature's mana value, put that card onto the battlefield with an additional +1/+1 "
    "counter on it, then shuffle.",
    "Search your library for a creature card with mana value X or less, where X is 2 plus the "
    "sacrificed creature's mana value. Put that card onto the battlefield, then shuffle. "
    "Exile Eldritch Evolution.",
    "You draw cards equal to the sacrificed creature's power, then you gain life equal to its "
    "toughness.",
):
    print(E._prepare_effect_clauses(text))
    print()
