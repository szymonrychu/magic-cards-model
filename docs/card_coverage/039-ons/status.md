# Onslaught (ons)

- Expansion: 039
- Set code: `ons`
- Release date: 2002-10-07
- Cards in scope (Modern/Pioneer/Standard-legal): 58

## Legality

| Format | Legal cards |
|---|---|
| Modern | 58 |
| Pioneer | 17 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 13 | 22.4% |
| Works (untested) | 32 | 55.2% |
| Partial (unaudited) | 3 | 5.2% |
| Not working | 10 | 17.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Biorhythm | silent | Each player's life total becomes the number of creatures they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blackmail | silent | Target player reveals three cards from their hand and you choose one of them. That player discards that card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gluttonous Zombie | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Goblin Piledriver | silent | Whenever this creature attacks, it gets +2/+0 until end of turn for each other attacking Goblin. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Head Games | silent | Target opponent puts the cards from their hand on top of their library. Search that player's library for that many cards. The player puts those cards into their | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mobilization | silent | Soldier creatures have vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Patriarch's Bidding | silent | Each player chooses a creature type. Each player returns all creature cards of a type chosen this way from their graveyard to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reminisce | silent | Target player shuffles their graveyard into their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sea's Claim | silent | Enchanted land is an Island. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Severed Legion | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Cover of Darkness | unaudited | Creatures of the chosen type have fear. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Future Sight | unaudited | Play with the top card of your library revealed. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Gratuitous Violence | unaudited | If a creature you control would deal damage to a permanent or player, it deals double that damage instead. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Arcanis the Omnipotent | handled | {T}: Draw three cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Barren Moor | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crafty Pathmage | handled | {T}: Target creature with power 2 or less can't be blocked this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cruel Revival | handled | Destroy target non-Zombie creature. It can't be regenerated. Return up to one target Zombie card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Discombobulate | handled | Counter target spell. Look at the top four cards of your library, then put them back in any order. | the engine reads this text and performs it | Y/-/- | not_tested |
| Doomed Necromancer | handled | {B}, {T}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dragon Roost | handled | {5}{R}{R}: Create a 5/5 red Dragon creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elvish Pioneer | handled | When this creature enters, you may put a basic land card from your hand onto the battlefield tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elvish Scrapper | handled | {G}, {T}, Sacrifice this creature: Destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elvish Warrior | handled |  |  | Y/-/- | not_tested |
| Enchantress's Presence | handled | Whenever you cast an enchantment spell, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Explosive Vegetation | handled | Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Festering Goblin | handled | When this creature dies, target creature gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Forgotten Cave | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glory Seeker | handled |  |  | Y/Y/- | not_tested |
| Goblin Sky Raider | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Infest | handled | All creatures get -2/-2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inspirit | handled | Untap target creature. It gets +2/+4 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lonely Sandbar | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Husk | handled | Sacrifice a creature: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Naturalize | handled | Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Renewed Faith | handled | You gain 6 life. Cycling {1}{W} ({1}{W}, Discard this card: Draw a card.) When you cycle this card, you may gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Riptide Laboratory | handled | {1}{U}, {T}: Return target Wizard you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sage Aven | handled | When this creature enters, look at the top four cards of your library, then put them back in any order. | the engine reads this text and performs it | Y/-/- | not_tested |
| Secluded Steppe | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Silklash Spider | handled | {X}{G}{G}: This creature deals X damage to each creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Slate of Ancestry | handled | {4}, {T}, Discard your hand: Draw a card for each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Smother | handled | Destroy target creature with mana value 3 or less. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tranquil Thicket | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Voidmage Prodigy | handled | {U}{U}, Sacrifice a Wizard: Counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Mulch | handled | {G}, Sacrifice a Wall: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Weathered Wayfarer | handled | {W}, {T}: Search your library for a land card, reveal it, put it into your hand, then shuffle. Activate only if an opponent controls more lands than you. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>13 cards</summary>

- Annex
- Bloodstained Mire
- Choking Tethers
- Demystify
- Flooded Strand
- Krosan Tusker
- Polluted Delta
- Skirk Prospector
- Threaten
- True Believer
- Weird Harvest
- Windswept Heath
- Wooded Foothills

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| fear | 2 | Gluttonous Zombie, Severed Legion | ons |
| creatures of the chosen type have fear. | 1 | Cover of Darkness | ons |
| each player chooses a creature type. each player returns all creature cards of a type chosen ~ from their graveyard to the battlefield. | 1 | Patriarch's Bidding | ons |
| each player's life total becomes the number of creatures they control. | 1 | Biorhythm | ons |
| enchanted land is an island. | 1 | Sea's Claim | ons |
| if a creature you control would deal damage to a permanent or player, it deals double that damage instead. | 1 | Gratuitous Violence | ons |
| play with the top card of your library revealed. | 1 | Future Sight | ons |
| soldier creatures have vigilance. | 1 | Mobilization | ons |
| target opponent puts the cards from their hand on top of their library. search that player's library for that many cards. the player puts those cards into their | 1 | Head Games | ons |
| target player reveals three cards from their hand and you choose one of them. that player discards that card. | 1 | Blackmail | ons |
| target player shuffles their graveyard into their library. | 1 | Reminisce | ons |
| whenever ~ attacks, it gets +N/+N until end of turn for each other attacking goblin. | 1 | Goblin Piledriver | ons |

## Notes


