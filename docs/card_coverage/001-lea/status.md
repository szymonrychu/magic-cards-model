# Limited Edition Alpha (lea)

- Expansion: 001
- Set code: `lea`
- Release date: 1993-08-05
- Cards in scope (Modern/Pioneer/Standard-legal): 116

## Legality

| Format | Legal cards |
|---|---|
| Modern | 116 |
| Pioneer | 33 |
| Standard | 14 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 44 | 37.9% |
| Works (untested) | 62 | 53.4% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 10 | 8.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Dingus Egg | silent | Whenever a land is put into a graveyard from the battlefield, this artifact deals 2 damage to that land's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flashfires | silent | Destroy all Plains. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Force of Nature | silent | At the beginning of your upkeep, this creature deals 8 damage to you unless you pay {G}{G}{G}{G}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gaea's Liege | silent | As long as Gaea's Liege isn't attacking, its power and toughness are each equal to the number of Forests you control. As long as Gaea's Liege is attacking, its  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hypnotic Specter | silent | Whenever this creature deals damage to an opponent, that player discards a card at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jade Statue | silent | {2}: This artifact becomes a 3/6 Golem artifact creature until end of combat. Activate only during combat. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Regeneration | silent | {G}: Regenerate enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cockatrice | notice | Whenever this creature blocks or becomes blocked by a non-Wall creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Disintegrate | notice | Disintegrate deals X damage to any target. If it's a creature, it can't be regenerated this turn, and if it would die this turn, exile it instead. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Dragon Whelp | notice | {R}: This creature gets +1/+0 until end of turn. If this ability has been activated four or more times this turn, sacrifice this creature at the beginning of th | unparsed remainder: If this ability has been activated four or more times this turn, sacrifice this creature at the beginning of the next end step. | Y/Y/- | not_working |
| Air Elemental | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Bad Moon | handled | Black creatures get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blessing | handled | {W}: Enchanted creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bog Wraith | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Circle of Protection: Blue | handled | {1}: The next time a blue source of your choice would deal damage to you this turn, prevent that damage. | the engine reads this text and performs it | Y/-/- | not_tested |
| Circle of Protection: Green | handled | {1}: The next time a green source of your choice would deal damage to you this turn, prevent that damage. | the engine reads this text and performs it | Y/-/- | not_tested |
| Circle of Protection: White | handled | {1}: The next time a white source of your choice would deal damage to you this turn, prevent that damage. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crystal Rod | handled | Whenever a player casts a blue spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drudge Skeletons | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dwarven Demolition Team | handled | {T}: Destroy target Wall. | the engine reads this text and performs it | Y/-/- | not_tested |
| Earth Elemental | handled |  |  | Y/-/- | not_tested |
| Evil Presence | handled | Enchanted land is a Swamp. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fear | handled | Enchanted creature has fear. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fire Elemental | handled |  |  | Y/Y/Y | not_tested |
| Firebreathing | handled | {R}: Enchanted creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flight | handled | Enchanted creature has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fungusaur | handled | Whenever this creature is dealt damage, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Balloon Brigade | handled | {R}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin King | handled | Other Goblins get +1/+1 and have mountainwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Holy Strength | handled | Enchanted creature gets +1/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Howling Mine | handled | At the beginning of each player's draw step, if this artifact is untapped, that player draws an additional card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Iron Star | handled | Whenever a player casts a red spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivory Cup | handled | Whenever a player casts a white spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jayemdae Tome | handled | {4}, {T}: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ley Druid | handled | {T}: Untap target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mahamoti Djinn | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Manabarbs | handled | Whenever a player taps a land for mana, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk of the Pearl Trident | handled |  |  | Y/-/- | not_tested |
| Nevinyrral's Disk | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nightmare | handled | Nightmare's power and toughness are each equal to the number of Swamps you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Orcish Artillery | handled | {T}: This creature deals 2 damage to any target and 3 damage to you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Prodigal Sorcerer | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Regrowth | handled | Return target card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Resurrection | handled | Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Righteousness | handled | Target blocking creature gets +7/+7 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rod of Ruin | handled | {3}, {T}: This artifact deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Royal Assassin | handled | {T}: Destroy target tapped creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Samite Healer | handled | {T}: Prevent the next 1 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scathe Zombies | handled |  |  | Y/-/- | not_tested |
| Sengir Vampire | handled | Whenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shatter | handled | Destroy target artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spell Blast | handled | Counter target spell with mana value X. (For example, if that spell's mana cost is {3}{U}{U}, X is 5.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stone Giant | handled | {T}: Target creature you control with toughness less than this creature's power gains flying until end of turn. Destroy that creature at the beginning of the ne | the engine reads this text and performs it | Y/-/- | not_tested |
| Stone Rain | handled | Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stream of Life | handled | Target player gains X life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Terror | handled | Destroy target nonartifact, nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| The Hive | handled | {5}, {T}: Create a 1/1 colorless Insect artifact creature token with flying named Wasp. | the engine reads this text and performs it | Y/-/- | not_tested |
| Throne of Bone | handled | Whenever a player casts a black spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Twiddle | handled | You may tap or untap target artifact, creature, or land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Unholy Strength | handled | Enchanted creature gets +2/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Uthden Troll | handled | {R}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Verduran Enchantress | handled | Whenever you cast an enchantment spell, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Air | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Wall of Bone | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Fire | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wall of Stone | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Wall of Swords | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Wall of Wood | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Weakness | handled | Enchanted creature gets -2/-1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Web | handled | Enchanted creature gets +0/+2 and has reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Will-o'-the-Wisp | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wooden Sphere | handled | Whenever a player casts a green spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>44 cards</summary>

- Birds of Paradise
- Black Knight
- Circle of Protection: Red
- Clone
- Consecrate Land
- Counterspell
- Craw Wurm
- Disenchant
- Disrupting Scepter
- Earthquake
- Fireball
- Fog
- Forest
- Giant Growth
- Giant Spider
- Grizzly Bears
- Healing Salve
- Hill Giant
- Hurricane
- Icy Manipulator
- Invisibility
- Island
- Juggernaut
- Jump
- Karma
- Lightning Bolt
- Llanowar Elves
- Lord of Atlantis
- Lord of the Pit
- Lure
- Mountain
- Pirate Ship
- Plains
- Psionic Blast
- Raise Dead
- Reverse Damage
- Savannah Lions
- Serra Angel
- Shivan Dragon
- Steal Artifact
- Swamp
- Unsummon
- White Knight
- Wrath of God

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| as long as ~ isn't attacking, its power and toughness are each equal to the number of forests you control. as long as ~ is attacking, its power and toughness ar | 1 | Gaea's Liege | lea |
| at the beginning of your upkeep, ~ deals N damage to you unless you pay {M}{M}{M}{M}. | 1 | Force of Nature | lea |
| destroy all plains. | 1 | Flashfires | lea |
| whenever a land is put into a graveyard from the battlefield, ~ deals N damage to that land's controller. | 1 | Dingus Egg | lea |
| whenever ~ blocks or becomes blocked by a non-wall creature, destroy that creature at end of combat. | 1 | Cockatrice | lea |
| whenever ~ deals damage to an opponent, that player discards a card at random. | 1 | Hypnotic Specter | lea |
| {M}: regenerate enchanted creature. | 1 | Regeneration | lea |
| {M}: ~ becomes a N/N golem artifact creature until end of combat. activate only during combat. | 1 | Jade Statue | lea |
| {M}: ~ gets +N/+N until end of turn. if ~ has been activated four or more times ~, sacrifice ~ at the beginning of the next end step. | 1 | Dragon Whelp | lea |
| ~ deals N damage to any target. if it"..."t be regenerated ~, and if it would die ~, exile it instead. | 1 | Disintegrate | lea |

## Notes


