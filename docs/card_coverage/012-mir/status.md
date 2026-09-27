# Mirage (mir)

- Expansion: 012
- Set code: `mir`
- Release date: 1996-10-08
- Cards in scope (Modern/Pioneer/Standard-legal): 31

## Legality

| Format | Legal cards |
|---|---|
| Modern | 31 |
| Pioneer | 6 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 6.5% |
| Works (untested) | 20 | 64.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 9 | 29.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Celestial Dawn | silent | Lands you control are Plains. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Early Harvest | silent | Target player untaps all basic lands they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Maro | silent | Maro's power and toughness are each equal to the number of cards in your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mind Bend | silent | Change the text of target permanent by replacing all instances of one color word with another or one basic land type with another. (For example, you may change  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sacred Mesa | silent | At the beginning of your upkeep, sacrifice this enchantment unless you sacrifice a Pegasus. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shadow Guildmage | silent | {U}, {T}: Put target creature you control on top of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stupor | silent | Target opponent discards a card at random, then discards a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grinning Totem | notice | {2}, {T}, Sacrifice this artifact: Search target opponent's library for a card and exile it. Then that player shuffles. Until the beginning of your next upkeep, | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Polymorph | notice | Destroy target creature. It can't be regenerated. Its controller reveals cards from the top of their library until they reveal a creature card. The player puts  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Daring Apprentice | handled | {T}, Sacrifice this creature: Counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dissipate | handled | Counter target spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Enfeeblement | handled | Enchanted creature gets -2/-2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Femeref Archers | handled | {T}: This creature deals 4 damage to target attacking creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Foratog | handled | {G}, Sacrifice a Forest: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Giant Mantis | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Goblin Elite Infantry | handled | Whenever this creature blocks or becomes blocked, it gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hammer of Bogardan | handled | Hammer of Bogardan deals 3 damage to any target. {2}{R}{R}{R}: Return this card from your graveyard to your hand. Activate only during your upkeep. | the engine reads this text and performs it | Y/-/- | not_tested |
| Patagia Golem | handled | {3}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Vault | handled | {2}, {T}, Sacrifice a creature: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rampant Growth | handled | Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Savage Twister | handled | Savage Twister deals X damage to each creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spitting Earth | handled | Spitting Earth deals damage to target creature equal to the number of Mountains you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stalking Tiger | handled | This creature can't be blocked by more than one creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sunweb | handled | This creature can't block creatures with power 2 or less. | the engine reads this text and performs it | Y/-/- | not_tested |
| Volcanic Dragon | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Volcanic Geyser | handled | Volcanic Geyser deals X damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wall of Roots | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Wildfire Emissary | handled | {1}{R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zhalfirin Commander | handled | {1}{W}{W}: Target Knight creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Cursed Totem
- Pacifism

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of your upkeep, sacrifice ~ unless you sacrifice a pegasus. | 1 | Sacred Mesa | mir |
| change the text of target permanent by replacing all instances of one color word with another or one basic land type with another. (for example, you may change  | 1 | Mind Bend | mir |
| destroy target creature. it can't be regenerated. its controller reveals cards from the top of their library until they reveal a creature card. the player puts  | 1 | Polymorph | mir |
| lands you control are plains. | 1 | Celestial Dawn | mir |
| target opponent discards a card at random, then discards a card. | 1 | Stupor | mir |
| target player untaps all basic lands they control. | 1 | Early Harvest | mir |
| {M}, {M}, sacrifice ~: search target opponent"..."t played it, put it into its owner's graveyard. | 1 | Grinning Totem | mir |
| {M}, {M}: put target creature you control on top of its owner's library. | 1 | Shadow Guildmage | mir |
| ~'s power and toughness are each equal to the number of cards in your hand. | 1 | Maro | mir |

## Notes


