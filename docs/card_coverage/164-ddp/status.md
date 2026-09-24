# Duel Decks: Zendikar vs. Eldrazi (ddp)

- Expansion: 164
- Set code: `ddp`
- Release date: 2015-08-28
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
| Full (handled + tested) | 1 | 16.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 33.3% |
| Not working (silent / notice / error) | 3 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Dominator Drone | silent | Ingest | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Oblivion Sower | silent | When you cast this spell, target opponent exiles the top four cards of their library, then you may put any number of land cards that player owns from exile onto | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sheer Drop | silent | Awaken | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Retreat to Kazandu | handled | Landfall — Whenever a land you control enters, choose one — • Put a +1/+1 counter on target creature. • You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Veteran Warleader | handled | Veteran Warleader's power and toughness are each equal to the number of creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Forerunner of Slaughter

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| awaken | 1 | Sheer Drop | ddp |
| ingest | 1 | Dominator Drone | ddp |
| when you cast ~, target opponent exiles the top four cards of their library, then you may put any number of land cards that player owns from exile onto the batt | 1 | Oblivion Sower | ddp |

## Notes


