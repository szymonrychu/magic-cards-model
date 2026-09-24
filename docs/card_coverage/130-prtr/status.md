# Return to Ravnica Promos (prtr)

- Expansion: 130
- Set code: `prtr`
- Release date: 2012-10-05
- Cards in scope (Modern/Pioneer/Standard-legal): 9

## Legality

| Format | Legal cards |
|---|---|
| Modern | 9 |
| Pioneer | 9 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 11.1% |
| Partial (unaudited) | 2 | 22.2% |
| Not tested (handled, untested) | 3 | 33.3% |
| Not working (silent / notice / error) | 3 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Archon of the Triumvirate | silent | Whenever this creature attacks, detain up to two target nonland permanents your opponents control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Carnival Hellsteed | silent | Unleash | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Deadbridge Goliath | silent | Scavenge | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Dryad Militant | unaudited | If an instant or sorcery card would be put into a graveyard from anywhere, exile it instead. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Hypersonic Dragon | unaudited | You may cast sorcery spells as though they had flash. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Corpsejack Menace | handled | If one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters are put on it instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cryptborn Horror | handled | This creature enters with X +1/+1 counters on it, where X is the total life lost by your opponents this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grove of the Guardian | handled | {3}{G}{W}, {T}, Tap two untapped creatures you control, Sacrifice this land: Create an 8/8 green and white Elemental creature token with vigilance. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Supreme Verdict

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| If an instant or sorcery card would be put into a graveyard from anywhere, exile it instead. | Dryad Militant | 1 |
| Scavenge | Deadbridge Goliath | 1 |
| Unleash | Carnival Hellsteed | 1 |
| Whenever this creature attacks, detain up to two target nonland permanents your opponents control. | Archon of the Triumvirate | 1 |
| You may cast sorcery spells as though they had flash. | Hypersonic Dragon | 1 |

## Notes


