# Duel Decks: Izzet vs. Golgari (ddj)

- Expansion: 129
- Set code: `ddj`
- Release date: 2012-09-07
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 6 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 33.3% |
| Works (untested) | 3 | 50.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Street Spasm | silent | Overload | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Dreg Mangler | handled | Scavenge | machines/keywords.py (off_zone_abilities: scavenge) | Y/Y/- | not_tested |
| Goblin Electromancer | handled | Instant and sorcery spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Izzet Charm | handled | Choose one — • Counter target noncreature spell unless its controller pays {2}. • Izzet Charm deals 2 damage to target creature. • Draw two cards, then discard  | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Jarad, Golgari Lich Lord
- Korozda Guildmage

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| overload | 1 | Street Spasm | ddj |

## Notes


