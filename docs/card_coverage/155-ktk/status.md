# Khans of Tarkir (ktk)

- Expansion: 155
- Set code: `ktk`
- Release date: 2014-09-26
- Cards in scope (Modern/Pioneer/Standard-legal): 225

## Legality

| Format | Legal cards |
|---|---|
| Modern | 225 |
| Pioneer | 225 |
| Standard | 14 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 36 | 16.0% |
| Works (untested) | 163 | 72.4% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 26 | 11.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ashcloud Phoenix | silent | When this creature dies, return it to the battlefield face down under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bellowing Saddlebrute | silent | Raid — When this creature enters, you lose 4 life unless you attacked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dragon's Eye Savants | silent | When this creature is turned face up, look at target opponent's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Duneblast | silent | Choose up to one creature. Destroy the rest. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| End Hostilities | silent | Destroy all creatures and all permanents attached to creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Force Away | silent | Return target creature to its owner's hand. Ferocious — If you control a creature with power 4 or greater, you may draw a card. If you do, discard a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Herald of Anafenza | silent | Whenever you activate this creature's outlast ability, create a 1/1 white Warrior creature token. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Howl of the Horde | silent | When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy. Raid — If you attacked this turn, when you n | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Icy Blast | silent | Tap X target creatures. Ferocious — If you control a creature with power 4 or greater, those creatures don't untap during their controllers' next untap steps. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kheru Lich Lord | silent | At the beginning of your upkeep, you may pay {2}{B}. If you do, return a creature card at random from your graveyard to the battlefield. It gains flying, trampl | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Meandering Towershell | silent | Whenever this creature attacks, exile it. Return it to the battlefield under your control tapped and attacking at the beginning of the declare attackers step on | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mindswipe | silent | Counter target spell unless its controller pays {X}. Mindswipe deals X damage to that spell's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Narset, Enlightened Master | silent | Whenever Narset attacks, exile the top four cards of your library. Until end of turn, you may cast noncreature spells from among those cards without paying thei | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pine Walker | silent | Whenever this creature or another creature you control is turned face up, untap that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rakshasa Vizier | silent | Whenever one or more cards are put into exile from your graveyard, put that many +1/+1 counters on this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Roar of Challenge | silent | All creatures able to block target creature this turn do so. Ferocious — That creature gains indestructible until end of turn if you control a creature with pow | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sarkhan, the Dragonspeaker | silent | +1: Until end of turn, Sarkhan becomes a legendary 4/4 red Dragon creature with flying, indestructible, and haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Secret Plans | silent | Face-down creatures you control get +0/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| See the Unwritten | silent | Reveal the top eight cards of your library. You may put a creature card from among them onto the battlefield. Put the rest into your graveyard. Ferocious — If y | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Smoke Teller | silent | {1}{U}: Look at target face-down creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sorin, Solemn Visitor | silent | +1: Until your next turn, creatures you control get +1/+0 and gain lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| High Sentinels of Arashin | notice | This creature gets +1/+1 for each other creature you control with a +1/+1 counter on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Ride Down | notice | Destroy target blocking creature. Creatures that were blocked by that creature this combat gain trample until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Rite of the Serpent | notice | Destroy target creature. If that creature had a +1/+1 counter on it, create a 1/1 green Snake creature token. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Temur Charm | notice | Choose one — • Target creature you control gets +1/+1 until end of turn. It fights target creature you don't control. • Counter target spell unless its controll | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Villainous Wealth | notice | Target opponent exiles the top X cards of their library. You may cast any number of spells with mana value X or less from among them without paying their mana c | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Abomination of Gudul | handled | Whenever this creature deals combat damage to a player, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Abzan Ascendancy | handled | When this enchantment enters, put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Abzan Banner | handled | {W}{B}{G}, {T}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Abzan Battle Priest | handled | Each creature you control with a +1/+1 counter on it has lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Abzan Guide | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Ainok Tracker | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Alabaster Kirin | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Alpine Grizzly | handled |  |  | Y/Y/- | not_tested |
| Altar of the Brood | handled | Whenever another permanent you control enters, each opponent mills a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ankle Shanker | handled | Whenever this creature attacks, creatures you control gain first strike and deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Archers' Parapet | handled | {1}{B}, {T}: Each opponent loses 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Armament Corps | handled | When this creature enters, distribute two +1/+1 counters among one or two target creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Arrow Storm | handled | Arrow Storm deals 4 damage to any target. Raid — If you attacked this turn, instead Arrow Storm deals 5 damage to that permanent or player and the damage can't  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Awaken the Bear | handled | Target creature gets +3/+3 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bear's Companion | handled | When this creature enters, create a 4/4 green Bear creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Become Immense | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Target creature gets +6/+6 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bitter Revelation | handled | Look at the top four cards of your library. Put two of them into your hand and the rest into your graveyard. You lose 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blinding Spray | handled | Creatures your opponents control get -4/-0 until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bloodfell Caves | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bloodfire Expert | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Bloodfire Mentor | handled | {2}{U}, {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bloodsoaked Champion | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blossoming Sands | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Briber's Purse | handled | This artifact enters with X gem counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Butcher of the Horde | handled | Sacrifice another creature: This creature gains your choice of vigilance, lifelink, or haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Canyon Lurkers | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Chief of the Edge | handled | Other Warrior creatures you control get +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chief of the Scale | handled | Other Warrior creatures you control get +0/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dazzling Ramparts | handled | {1}{W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dead Drop | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Target player sacrifices two creatures of their choice. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Debilitating Injury | handled | Enchanted creature gets -2/-2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Defiant Strike | handled | Target creature gets +1/+0 until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dig Through Time | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Look at the top seven cards of your library. Put two of them into your ha | the engine reads this text and performs it | Y/Y/- | not_tested |
| Disdainful Stroke | handled | Counter target spell with mana value 4 or greater. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dismal Backwater | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Disowned Ancestor | handled | Outlast | machines/keywords.py | Y/Y/- | not_tested |
| Dragon Throne of Tarkir | handled | Equipped creature has defender and "{2}, {T}: Other creatures you control gain trample and get +X/+X until end of turn, where X is this creature's power." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dragon-Style Twins | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Dragonscale Boon | handled | Put two +1/+1 counters on target creature and untap it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dutiful Return | handled | Return up to two target creature cards from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Efreet Weaponmaster | handled | When this creature enters or is turned face up, another target creature you control gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Embodiment of Spring | handled | {1}{G}, {T}, Sacrifice this creature: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Empty the Pits | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Create X tapped 2/2 black Zombie creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Feed the Clan | handled | You gain 5 life. Ferocious — You gain 10 life instead if you control a creature with power 4 or greater. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Firehoof Cavalry | handled | {3}{R}: This creature gets +2/+0 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flying Crane Technique | handled | Untap all creatures you control. They gain flying and double strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frontier Bivouac | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Glacial Stalker | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Goblinslide | handled | Whenever you cast a noncreature spell, you may pay {1}. If you do, create a 1/1 red Goblin creature token with haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grim Haruspex | handled | Whenever another nontoken creature you control dies, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gurmag Swiftwing | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Heart-Piercer Bow | handled | Whenever equipped creature attacks, this Equipment deals 1 damage to target creature defending player controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heir of the Wilds | handled | Ferocious — Whenever this creature attacks, if you control a creature with power 4 or greater, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highland Game | handled | When this creature dies, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highspire Mantis | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Horde Ambusher | handled | Whenever this creature blocks, it deals 1 damage to you. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hordeling Outburst | handled | Create three 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Icefeather Aven | handled | When this creature is turned face up, you may return another target creature to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jeskai Banner | handled | {U}{R}{W}, {T}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jeskai Charm | handled | Choose one — • Put target creature on top of its owner's library. • Jeskai Charm deals 4 damage to target opponent or planeswalker. • Creatures you control get  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jeskai Student | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Jeskai Windscout | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Jungle Hollow | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Kheru Bloodsucker | handled | Whenever a creature you control with toughness 4 or greater dies, each opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kill Shot | handled | Destroy target attacking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kin-Tree Invocation | handled | Create an X/X black and green Spirit Warrior creature token, where X is the greatest toughness among creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kin-Tree Warden | handled | {2}: Regenerate this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Krumar Bond-Kin | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Leaping Master | handled | {2}{W}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Longshot Squad | handled | Each creature you control with a +1/+1 counter on it has reach. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mantis Rider | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Mardu Ascendancy | handled | Whenever a nontoken creature you control attacks, create a 1/1 red Goblin creature token that's tapped and attacking. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Banner | handled | {R}{W}{B}, {T}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Blazebringer | handled | When this creature attacks or blocks, sacrifice it at end of combat. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Charm | handled | Choose one — • Mardu Charm deals 4 damage to target creature. • Create two 1/1 white Warrior creature tokens. They gain first strike until end of turn. • Target | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Hateblade | handled | {B}: This creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Hordechief | handled | Raid — When this creature enters, if you attacked this turn, create a 1/1 white Warrior creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Roughrider | handled | Whenever this creature attacks, target creature can't block this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Skullhunter | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mardu Warshrieker | handled | Raid — When this creature enters, if you attacked this turn, add {R}{W}{B}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Master of Pearls | handled | When this creature is turned face up, creatures you control get +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Master the Way | handled | Draw a card. Master the Way deals damage to any target equal to the number of cards in your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mer-Ek Nightblade | handled | Each creature you control with a +1/+1 counter on it has deathtouch. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mistfire Weaver | handled | When this creature is turned face up, target creature you control gains hexproof until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Molting Snakeskin | handled | Enchanted creature gets +2/+0 and has "{2}{B}: Regenerate this creature." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Monastery Flock | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Murderous Cut | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Destroy target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mystic of the Hidden Way | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Opulent Palace | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pearl Lake Ancient | handled | This spell can't be countered. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ponyback Brigade | handled | When this creature enters or is turned face up, create three 1/1 red Goblin creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Quiet Contemplation | handled | Whenever you cast a noncreature spell, you may pay {1}. If you do, tap target creature an opponent controls and it doesn't untap during its controller's next un | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raiders' Spoils | handled | Creatures you control get +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rakshasa Deathdealer | handled | {B}{G}: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rakshasa's Secret | handled | Target opponent discards two cards. You mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rattleclaw Mystic | handled | When this creature is turned face up, add {G}{U}{R}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Retribution of the Ancients | handled | {B}, Remove X +1/+1 counters from among creatures you control: Target creature gets -X/-X until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Riverwheel Aerialists | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Rotting Mastodon | handled |  |  | Y/Y/- | not_tested |
| Rugged Highlands | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Ruthless Ripper | handled | When this creature is turned face up, target player loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sage of the Inward Eye | handled | Whenever you cast a noncreature spell, creatures you control gain lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sage-Eye Harrier | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Sagu Archer | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Sagu Mauler | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Salt Road Patrol | handled | Outlast | machines/keywords.py | Y/Y/- | not_tested |
| Sandsteppe Citadel | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Savage Knuckleblade | handled | {2}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scaldkin | handled | {2}{R}, Sacrifice this creature: It deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scion of Glaciers | handled | {U}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scoured Barrens | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Scout the Borders | handled | Reveal the top five cards of your library. You may put a creature or land card from among them into your hand. Put the rest into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seeker of the Way | handled | Whenever you cast a noncreature spell, this creature gains lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Set Adrift | handled | Delve (Each card you exile from your graveyard while casting this spell pays for {1}.) Put target nonland permanent on top of its owner's library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shambling Attendants | handled | Delve | machines/keywords.py | Y/Y/- | not_tested |
| Sidisi's Pet | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Sidisi, Brood Tyrant | handled | Whenever Sidisi enters or attacks, mill three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Siege Rhino | handled | When this creature enters, each opponent loses 3 life and you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Siegecraft | handled | Enchanted creature gets +2/+4. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Singing Bell Strike | handled | When this Aura enters, tap enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snowhorn Rider | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Sultai Ascendancy | handled | At the beginning of your upkeep, surveil 2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sultai Banner | handled | {B}{G}{U}, {T}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sultai Charm | handled | Choose one — • Destroy target monocolored creature. • Destroy target artifact or enchantment. • Draw two cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sultai Flayer | handled | Whenever a creature you control with toughness 4 or greater dies, you gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sultai Scavenger | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Sultai Soothsayer | handled | When this creature enters, look at the top four cards of your library. Put one of them into your hand and the rest into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Summit Prowler | handled |  |  | Y/Y/- | not_tested |
| Surrak Dragonclaw | handled | This spell can't be countered. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Suspension Field | handled | When this enchantment enters, you may exile target creature with toughness 3 or greater until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swarm of Bloodflies | handled | This creature enters with two +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swift Kick | handled | Target creature you control gets +1/+0 until end of turn. It fights target creature you don't control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swiftwater Cliffs | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Taigam's Scheming | handled | Surveil 5. (Look at the top five cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Take Up Arms | handled | Create three 1/1 white Warrior creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Temur Ascendancy | handled | Creatures you control have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Temur Banner | handled | {G}{U}{R}, {T}, Sacrifice this artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Temur Charger | handled | When this creature is turned face up, target creature gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thornwood Falls | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Throttle | handled | Target creature gets -4/-4 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Timely Hordemate | handled | Raid — When this creature enters, if you attacked this turn, return target creature card with mana value 2 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tomb of the Spirit Dragon | handled | {2}, {T}: You gain 1 life for each colorless creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tormenting Voice | handled | As an additional cost to cast this spell, discard a card. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Trail of Mystery | handled | Whenever a face-down creature you control enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tranquil Cove | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Trap Essence | handled | Counter target creature spell. Put two +1/+1 counters on up to one target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tusked Colossodon | handled |  |  | Y/Y/- | not_tested |
| Tuskguard Captain | handled | Each creature you control with a +1/+1 counter on it has trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Unyielding Krumar | handled | {1}{W}: This creature gains first strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Valley Dasher | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Venerable Lammasu | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| War Behemoth | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Warden of the Eye | handled | When this creature enters, return target noncreature, nonland card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Watcher of the Roost | handled | When this creature is turned face up, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Waterwhirl | handled | Return up to two target creatures to their owners' hands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Weave Fate | handled | Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wetland Sambar | handled |  |  | Y/Y/- | not_tested |
| Whirlwind Adept | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Wind-Scarred Crag | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Wingmate Roc | handled | Raid — When this creature enters, if you attacked this turn, create a 3/4 white Bird creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Winterflame | handled | Choose one or both — • Tap target creature. • Winterflame deals 2 damage to target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Witness of the Ages | handled | Morph | machines/casting.py | Y/Y/- | not_tested |
| Woolly Loxodon | handled | Morph | machines/casting.py | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>36 cards</summary>

- Abzan Charm
- Abzan Falconer
- Ainok Bond-Kin
- Anafenza, the Foremost
- Avalanche Tusker
- Barrage of Boulders
- Brave the Sands
- Bring Low
- Burn Away
- Clever Impersonator
- Crackling Doom
- Cranial Archive
- Crater's Claws
- Death Frenzy
- Deflecting Palm
- Dragon Grip
- Feat of Resistance
- Ghostfire Blade
- Hardened Scales
- Hooded Hydra
- Hooting Mandrills
- Ivorytusk Fortress
- Jeering Instigator
- Jeskai Ascendancy
- Kheru Dreadmaw
- Kheru Spellsnatcher
- Lens of Clarity
- Monastery Swiftspear
- Necropolis Fiend
- Rush of Battle
- Savage Punch
- Stubborn Denial
- Treasure Cruise
- Ugin's Nexus
- Utter End
- War-Name Aspirant

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Choose one | 1 | Temur Charm | ktk |
| Raid | 1 | Bellowing Saddlebrute | ktk |
| +N: until end of turn, sarkhan becomes a legendary N/N red dragon creature with flying, indestructible, and haste. | 1 | Sarkhan, the Dragonspeaker | ktk |
| +N: until your next turn, creatures you control get +N/+N and gain lifelink. | 1 | Sorin, Solemn Visitor | ktk |
| all creatures able to block target creature ~ do so. ferocious — that creature gains indestructible until end of turn if you control a creature with power N or  | 1 | Roar of Challenge | ktk |
| at the beginning of your upkeep, you may pay {M}{M}. if you do, return a creature card at random from your graveyard to the battlefield. it gains flying, trampl | 1 | Kheru Lich Lord | ktk |
| choose up to one creature. destroy the rest. | 1 | Duneblast | ktk |
| counter target spell unless its controller pays {M}. ~ deals N damage to that spell's controller. | 1 | Mindswipe | ktk |
| destroy all creatures and all permanents attached to creatures. | 1 | End Hostilities | ktk |
| destroy target blocking creature. creatures that were blocked by that creature ~ gain trample until end of turn. | 1 | Ride Down | ktk |
| destroy target creature. if that creature had a +N/+N counter on it, create a N/N green snake creature token. | 1 | Rite of the Serpent | ktk |
| face-down creatures you control get +N/+N. | 1 | Secret Plans | ktk |
| return target creature to its owner's hand. ferocious — if you control a creature with power N or greater, you may draw a card. if you do, discard a card. | 1 | Force Away | ktk |
| reveal the top eight cards of your library. you may put a creature card from among them onto the battlefield. put the rest into your graveyard. ferocious — if y | 1 | See the Unwritten | ktk |
| tap N target creatures. ferocious — if you control a creature with power N or greater, those creatures don"..." next untap steps. | 1 | Icy Blast | ktk |
| target opponent exiles the top N cards of their library. you may cast any number of spells with mana value N or less from among them without paying their mana c | 1 | Villainous Wealth | ktk |
| when you next cast an instant or sorcery spell ~, copy that spell. you may choose new targets for the copy. raid — if you attacked ~, when you next cast an inst | 1 | Howl of the Horde | ktk |
| when ~ dies, return it to the battlefield face down under your control. | 1 | Ashcloud Phoenix | ktk |
| when ~ is turned face up, look at target opponent's hand. | 1 | Dragon's Eye Savants | ktk |
| whenever narset attacks, exile the top four cards of your library. until end of turn, you may cast noncreature spells from among those cards without paying thei | 1 | Narset, Enlightened Master | ktk |
| whenever one or more cards are put into exile from your graveyard, put that many +N/+N counters on ~. | 1 | Rakshasa Vizier | ktk |
| whenever you activate ~ outlast ability, create a N/N white warrior creature token. | 1 | Herald of Anafenza | ktk |
| whenever ~ attacks, exile it. return it to the battlefield under your control tapped and attacking at the beginning of the declare attackers step on your next t | 1 | Meandering Towershell | ktk |
| whenever ~ or another creature you control is turned face up, untap that creature. | 1 | Pine Walker | ktk |
| {M}{M}: look at target face-down creature. | 1 | Smoke Teller | ktk |
| ~ gets +N/+N for each other creature you control with a +N/+N counter on it. | 1 | High Sentinels of Arashin | ktk |

## Notes


