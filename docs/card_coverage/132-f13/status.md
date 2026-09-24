# Friday Night Magic 2013 (f13)

- Expansion: 132
- Set code: `f13`
- Release date: 2013-01-01
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 50.0% |
| Not working (silent / notice / error) | 2 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Experiment One | silent | Remove two +1/+1 counters from this creature: Regenerate it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dimir Charm | notice | Choose one — • Counter target sorcery spell. • Destroy target creature with power 2 or less. • Look at the top three cards of target player's library. Put one b | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Ghor-Clan Rampager | handled | Bloodrush — {R}{G}, Discard this card: Target attacking creature gets +4/+4 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sin Collector | handled | When this creature enters, target opponent reveals their hand. You choose an instant or sorcery card from it and exile that card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Choose one — • Counter target sorcery spell. • Destroy target creature with power 2 or less. • Look at the top three cards of target player's library. Put one b | Dimir Charm | 1 |
| Remove two +1/+1 counters from this creature: Regenerate it. | Experiment One | 1 |

## Notes


