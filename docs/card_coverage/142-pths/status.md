# Theros Promos (pths)

- Expansion: 142
- Set code: `pths`
- Release date: 2013-09-21
- Cards in scope (Modern/Pioneer/Standard-legal): 10

## Legality

| Format | Legal cards |
|---|---|
| Modern | 10 |
| Pioneer | 10 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 10.0% |
| Not tested (handled, untested) | 5 | 50.0% |
| Not working (silent / notice / error) | 4 | 40.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Abhorrent Overlord | silent | When this creature enters, create a number of 1/1 black Harpy creature tokens with flying equal to your devotion to black. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Anthousa, Setessan Hero | silent | Heroic — Whenever you cast a spell that targets Anthousa, up to three target lands you control each become 2/2 Warrior creatures until end of turn. They're stil | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bident of Thassa | silent | {1}{U}, {T}: Creatures your opponents control attack this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Shipbreaker Kraken | silent | When this creature becomes monstrous, tap up to four target creatures. Those creatures don't untap during their controllers' untap steps for as long as you cont | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nighthowler | unaudited | This creature and enchanted creature each get +X/+X, where X is the number of creature cards in all graveyards. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Celestial Archon | handled | Enchanted creature gets +4/+4 and has flying and first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ember Swallower | handled | {5}{R}{R}: Monstrosity 3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Karametra's Acolyte | handled |  |  | Y/Y/- | not_tested |
| Phalanx Leader | handled | Heroic — Whenever you cast a spell that targets this creature, put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sylvan Caryatid | handled | Hexproof | machines/casting.py (target legality) | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| {1}{U}, {T}: Creatures your opponents control attack this turn if able. | Bident of Thassa | 1 |
| Heroic — Whenever you cast a spell that targets Anthousa, up to three target lands you control each become 2/2 Warrior creatures until end of turn. They're stil | Anthousa, Setessan Hero | 1 |
| This creature and enchanted creature each get +X/+X, where X is the number of creature cards in all graveyards. | Nighthowler | 1 |
| When this creature becomes monstrous, tap up to four target creatures. Those creatures don't untap during their controllers' untap steps for as long as you cont | Shipbreaker Kraken | 1 |
| When this creature enters, create a number of 1/1 black Harpy creature tokens with flying equal to your devotion to black. | Abhorrent Overlord | 1 |

## Notes


