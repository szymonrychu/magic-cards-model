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
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 33.3% |
| Not working (silent / notice / error) | 4 | 66.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Dreg Mangler | silent | Scavenge | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Korozda Guildmage | silent | {1}{B}{G}: Target creature gets +1/+1 and gains intimidate until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Street Spasm | silent | Overload | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Jarad, Golgari Lich Lord | notice | {1}{B}{G}, Sacrifice another creature: Each opponent loses life equal to the sacrificed creature's power. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Goblin Electromancer | handled | Instant and sorcery spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Izzet Charm | handled | Choose one — • Counter target noncreature spell unless its controller pays {2}. • Izzet Charm deals 2 damage to target creature. • Draw two cards, then discard  | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Overload | Street Spasm | 1 |
| {1}{B}{G}, Sacrifice another creature: Each opponent loses life equal to the sacrificed creature's power. | Jarad, Golgari Lich Lord | 1 |
| Scavenge | Dreg Mangler | 1 |
| {1}{B}{G}: Target creature gets +1/+1 and gains intimidate until end of turn. | Korozda Guildmage | 1 |

## Notes


