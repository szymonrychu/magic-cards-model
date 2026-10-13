# Portal (por)

- Expansion: 016
- Set code: `por`
- Release date: 1997-05-01
- Cards in scope (Modern/Pioneer/Standard-legal): 39

## Legality

| Format | Legal cards |
|---|---|
| Modern | 39 |
| Pioneer | 9 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 7 | 17.9% |
| Works (untested) | 25 | 64.1% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 7 | 17.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Baleful Stare | silent | Target opponent reveals their hand. You draw a card for each Mountain and red card in it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blessed Reversal | silent | You gain 3 life for each creature attacking you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Boiling Seas | silent | Destroy all Islands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Exhaustion | silent | Creatures and lands target opponent controls don't untap during their next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Primeval Force | silent | When this creature enters, sacrifice it unless you sacrifice three Forests. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thundermare | silent | When this creature enters, tap all other creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Withering Gaze | silent | Target opponent reveals their hand. You draw a card for each Forest and green card in it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Anaconda | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Ardent Militia | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Blaze | handled | Blaze deals X damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bog Raiders | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Coral Eel | handled |  |  | Y/-/- | not_tested |
| Foot Soldiers | handled |  |  | Y/-/- | not_tested |
| Giant Octopus | handled |  |  | Y/-/- | not_tested |
| Gift of Estates | handled | If an opponent controls more lands than you, search your library for up to three Plains cards, reveal them, put them into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gravedigger | handled | When this creature enters, you may return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Horned Turtle | handled |  |  | Y/-/- | not_tested |
| Lava Axe | handled | Lava Axe deals 5 damage to target player or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Monstrous Growth | handled | Target creature gets +4/+4 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Natural Spring | handled | Target player gains 8 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Needle Storm | handled | Needle Storm deals 4 damage to each creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phantom Warrior | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rain of Tears | handled | Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sacred Nectar | handled | You gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seasoned Marshal | handled | Whenever this creature attacks, you may tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serpent Warrior | handled | When this creature enters, you lose 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Snapping Drake | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Spined Wurm | handled |  |  | Y/-/- | not_tested |
| Time Ebb | handled | Put target creature on top of its owner's library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Venerable Monk | handled | When this creature enters, you gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vengeance | handled | Destroy target tapped creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Volcanic Hammer | handled | Volcanic Hammer deals 3 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>7 cards</summary>

- Angelic Blessing
- Balance of Power
- Charging Rhino
- Mind Rot
- Raging Goblin
- Wind Drake
- Wood Elves

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| creatures and lands target opponent controls don't untap during their next untap step. | 1 | Exhaustion | por |
| destroy all islands. | 1 | Boiling Seas | por |
| target opponent reveals their hand. you draw a card for each forest and green card in it. | 1 | Withering Gaze | por |
| target opponent reveals their hand. you draw a card for each mountain and red card in it. | 1 | Baleful Stare | por |
| when ~ enters, sacrifice it unless you sacrifice three forests. | 1 | Primeval Force | por |
| when ~ enters, tap all other creatures. | 1 | Thundermare | por |
| you gain N life for each creature attacking you. | 1 | Blessed Reversal | por |

## Notes


