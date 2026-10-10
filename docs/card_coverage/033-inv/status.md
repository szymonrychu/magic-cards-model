# Invasion (inv)

- Expansion: 033
- Set code: `inv`
- Release date: 2000-10-02
- Cards in scope (Modern/Pioneer/Standard-legal): 44

## Legality

| Format | Legal cards |
|---|---|
| Modern | 44 |
| Pioneer | 11 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 6 | 13.6% |
| Works (untested) | 32 | 72.7% |
| Partial (unaudited) | 1 | 2.3% |
| Not working | 5 | 11.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Elvish Champion | silent | Other Elf creatures get +1/+1 and have forestwalk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fact or Fiction | silent | Reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the other into your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Obliterate | silent | This spell can't be countered. Destroy all artifacts, creatures, and lands. They can't be regenerated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Verdeloth the Ancient | silent | Saproling creatures and other Treefolk creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Void | silent | Choose a number. Destroy all artifacts and creatures with mana value equal to that number. Then target player reveals their hand and discards all nonland cards  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sterling Grove | unaudited | Other enchantments you control have shroud. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Absorb | handled | Counter target spell. You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aggressive Urge | handled | Target creature gets +1/+1 until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Assault // Battery | handled | Assault deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Coastal Tower | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cremate | handled | Exile target card from a graveyard. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dismantling Blow | handled | Kicker {2}{U} (You may pay an additional {2}{U} as you cast this spell.) Destroy target artifact or enchantment. If this spell was kicked, draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elfhame Palace | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Exclude | handled | Counter target creature spell. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frenzied Tilling | handled | Destroy target land. Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hate Weaver | handled | {2}: Target blue or red creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heroes' Reunion | handled | Target player gains 7 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kavu Climber | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Might Weaver | handled | {2}: Target red or white creature gains trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Molimo, Maro-Sorcerer | handled | Molimo's power and toughness are each equal to the number of lands you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Planar Portal | handled | {6}, {T}: Search your library for a card, put that card into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Prohibit | handled | Kicker {2} (You may pay an additional {2} as you cast this spell.) Counter target spell if its mana value is 2 or less. If this spell was kicked, counter that s | the engine reads this text and performs it | Y/-/- | not_tested |
| Rage Weaver | handled | {2}: Target black or green creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Razorfoot Griffin | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Recover | handled | Return target creature card from your graveyard to your hand. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Restock | handled | Return two target cards from your graveyard to your hand. Exile Restock. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reviving Dose | handled | You gain 3 life. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reya Dawnbringer | handled | At the beginning of your upkeep, you may return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rogue Kavu | handled | Whenever this creature attacks alone, it gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Salt Marsh | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shivan Oasis | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sky Weaver | handled | {2}: Target white or black creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spirit Weaver | handled | {2}: Target green or blue creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tower Drake | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Urborg Volcano | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Urza's Rage | handled | Kicker {8}{R} (You may pay an additional {8}{R} as you cast this spell.) This spell can't be countered. Urza's Rage deals 3 damage to any target. If this spell  | the engine reads this text and performs it | Y/-/- | not_tested |
| Utopia Tree | handled |  |  | Y/-/- | not_tested |
| Worldly Counsel | handled | Domain — Look at the top X cards of your library, where X is the number of basic land types among lands you control. Put one of those cards into your hand and t | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Chromatic Sphere
- Coalition Victory
- Opt
- Skizzik
- Teferi's Moat
- Tribal Flames

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| choose a number. destroy all artifacts and creatures with mana value equal to that number. then target player reveals their hand and discards all nonland cards  | 1 | Void | inv |
| other elf creatures get +N/+N and have forestwalk. | 1 | Elvish Champion | inv |
| other enchantments you control have shroud. | 1 | Sterling Grove | inv |
| reveal the top five cards of your library. an opponent separates those cards into two piles. put one pile into your hand and the other into your graveyard. | 1 | Fact or Fiction | inv |
| saproling creatures and other treefolk creatures get +N/+N. | 1 | Verdeloth the Ancient | inv |
| ~ can"..."t be regenerated. | 1 | Obliterate | inv |

## Notes


