# Avacyn Restored (avr)

- Expansion: 125
- Set code: `avr`
- Release date: 2012-05-04
- Cards in scope (Modern/Pioneer/Standard-legal): 217

## Legality

| Format | Legal cards |
|---|---|
| Modern | 217 |
| Pioneer | 20 |
| Standard | 4 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 55 | 25.3% |
| Works (untested) | 131 | 60.4% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 31 | 14.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Alchemist's Refuge | silent | {G}{U}, {T}: You may cast spells this turn as though they had flash. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Angel of Glory's Rise | silent | When this creature enters, exile all Zombies, then return all Human creature cards from your graveyard to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Angel's Tomb | silent | Whenever a creature you control enters, you may have this artifact become a 3/3 white Angel artifact creature with flying until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Angelic Armaments | silent | Equipped creature gets +2/+2, has flying, and is a white Angel in addition to its other colors and types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bladed Bracers | silent | As long as equipped creature is a Human or an Angel, it has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bruna, Light of Alabaster | silent | Whenever Bruna attacks or blocks, you may attach to it any number of Auras on the battlefield and you may put onto the battlefield attached to it any number of  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Builder's Blessing | silent | Untapped creatures you control get +0/+2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Demonlord of Ashmouth | silent | When this creature enters, exile it unless you sacrifice another creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Descendants' Path | silent | At the beginning of your upkeep, reveal the top card of your library. If it's a creature card that shares a creature type with a creature you control, you may c | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dread Slaver | silent | Whenever a creature dealt damage by this creature this turn dies, return it to the battlefield under your control. That creature is a black Zombie in addition t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Exquisite Blood | silent | Whenever an opponent loses life, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fettergeist | silent | At the beginning of your upkeep, sacrifice this creature unless you pay {1} for each other creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Havengul Skaab | silent | Whenever this creature attacks, return another creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Homicidal Seclusion | silent | As long as you control exactly one creature, that creature gets +3/+1 and has lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Killing Wave | silent | For each creature, its controller sacrifices it unless they pay X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lair Delve | silent | Reveal the top two cards of your library. Put all creature and land cards revealed this way into your hand and the rest on the bottom of your library in any ord | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Outwit | silent | Counter target spell that targets a player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Primal Surge | silent | Exile the top card of your library. If it's a permanent card, you may put it onto the battlefield. If you do, repeat this process. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rite of Ruin | silent | Choose an order for artifacts, creatures, and lands. Each player sacrifices one permanent of their choice of the first type, sacrifices two of their choice of t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tibalt, the Fiend-Blooded | silent | +1: Draw a card, then discard a card at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Treacherous Pit-Dweller | silent | When this creature enters from a graveyard, target opponent gains control of it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tyrant of Discord | silent | When this creature enters, target opponent chooses a permanent they control at random and sacrifices it. If a nonland permanent is sacrificed this way, repeat t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Undead Executioner | silent | When this creature dies, you may have target creature get -2/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vanguard's Shield | silent | Equipped creature gets +0/+3 and can block an additional creature each combat. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vexing Devil | silent | When this creature enters, any opponent may have it deal 4 damage to them. If a player does, sacrifice this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Appetite for Brains | notice | Target opponent reveals their hand. You choose a card from it with mana value 4 or greater and exile that card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Defy Death | notice | Return target creature card from your graveyard to the battlefield. If it's an Angel, put two +1/+1 counters on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Eaten by Spiders | notice | Destroy target creature with flying and all Equipment attached to that creature. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Joint Assault | notice | Target creature gets +2/+2 until end of turn. If it's paired with a creature, that creature also gets +2/+2 until end of turn. | unparsed remainder: If it's paired with a creature, that creature also gets +2/+2 until end of turn. | Y/-/- | not_working |
| Necrobite | notice | Target creature gains deathtouch until end of turn. Regenerate it. (The next time that creature would be destroyed this turn, instead tap it, remove it from com | unparsed remainder: Regenerate it. | Y/Y/- | not_working |
| Revenge of the Hunted | notice | Until end of turn, target creature gets +6/+6 and gains trample, and all creatures able to block it this turn do so. Miracle {G} (You may cast this card for its | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Abundant Growth | handled | When this Aura enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Alchemist's Apprentice | handled | Sacrifice this creature: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Amass the Components | handled | Draw three cards, then put a card from your hand on the bottom of your library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Archwing Dragon | handled | At the beginning of the end step, return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Banishing Stroke | handled | Put target artifact, creature, or enchantment on the bottom of its owner's library. Miracle {W} (You may cast this card for its miracle cost when you draw it if | the engine reads this text and performs it | Y/-/- | not_tested |
| Banners Raised | handled | Creatures you control get +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blessings of Nature | handled | Distribute four +1/+1 counters among any number of target creatures. Miracle {G} (You may cast this card for its miracle cost when you draw it if it's the first | the engine reads this text and performs it | Y/-/- | not_tested |
| Bloodflow Connoisseur | handled | Sacrifice a creature: Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bonfire of the Damned | handled | Bonfire of the Damned deals X damage to target player or planeswalker and each creature that player or that planeswalker's controller controls. Miracle {X}{R} ( | the engine reads this text and performs it | Y/-/- | not_tested |
| Butcher Ghoul | handled | Undying | machines/keywords.py | Y/-/- | not_tested |
| Call to Serve | handled | Enchanted creature gets +1/+2, has flying, and is an Angel in addition to its other types. | the engine reads this text and performs it | Y/-/- | not_tested |
| Captain of the Mists | handled | Whenever another Human you control enters, untap this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cathars' Crusade | handled | Whenever a creature you control enters, put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cathedral Sanctifier | handled | When this creature enters, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cloudshift | handled | Exile target creature you control, then return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Commander's Authority | handled | Enchanted creature has "At the beginning of your upkeep, create a 1/1 white Human creature token." | the engine reads this text and performs it | Y/-/- | not_tested |
| Conjurer's Closet | handled | At the beginning of your end step, you may exile target creature you control, then return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corpse Traders | handled | {2}{B}, Sacrifice a creature: Target opponent reveals their hand. You choose a card from it. That player discards that card. Activate only as a sorcery. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cursebreak | handled | Destroy target enchantment. You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dangerous Wager | handled | Discard your hand, then draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dark Impostor | handled | {4}{B}{B}: Exile target creature and put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Death Wind | handled | Target creature gets -X/-X until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desolate Lighthouse | handled | {1}{U}{R}, {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Devastation Tide | handled | Return all nonland permanents to their owners' hands. Miracle {1}{U} (You may cast this card for its miracle cost when you draw it if it's the first card you dr | the engine reads this text and performs it | Y/-/- | not_tested |
| Devout Chaplain | handled | {T}, Tap two untapped Humans you control: Exile target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Driver of the Dead | handled | When this creature dies, return target creature card with mana value 2 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Druid's Familiar | handled | As long as this creature is paired with another creature, each of those creatures gets +2/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Druids' Repository | handled | Whenever a creature you control attacks, put a charge counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dual Casting | handled | Enchanted creature has "{R}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy." | the engine reads this text and performs it | Y/-/- | not_tested |
| Elgaud Shieldmate | handled | As long as this creature is paired with another creature, both creatures have hexproof. | the engine reads this text and performs it | Y/-/- | not_tested |
| Emancipation Angel | handled | When this creature enters, return a permanent you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Essence Harvest | handled | Target player loses X life and you gain X life, where X is the greatest power among creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Evernight Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Falkenrath Exterminator | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Farbog Explorer | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Favorable Winds | handled | Creatures you control with flying get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fervent Cathar | handled | When this creature enters, target creature can't block this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gallows at Willow Hill | handled | {3}, {T}, Tap three untapped Humans you control: Destroy target creature. Its controller creates a 1/1 white Spirit creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gang of Devils | handled | When this creature dies, it deals 3 damage divided as you choose among one, two, or three targets. | the engine reads this text and performs it | Y/-/- | not_tested |
| Geist Snatch | handled | Counter target creature spell. Create a 1/1 blue Spirit creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Geist Trappers | handled | As long as this creature is paired with another creature, both creatures have reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghostly Flicker | handled | Exile two target artifacts, creatures, and/or lands you control, then return those cards to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghostly Touch | handled | Enchanted creature has "Whenever this creature attacks, you may tap or untap target permanent." | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghoulflesh | handled | Enchanted creature gets -1/-1 and is a black Zombie in addition to its other colors and types. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goldnight Commander | handled | Whenever another creature you control enters, creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goldnight Redeemer | handled | When this creature enters, you gain 2 life for each other creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grave Exchange | handled | Return target creature card from your graveyard to your hand. Target player sacrifices a creature of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gryff Vanguard | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guise of Fire | handled | Enchanted creature gets +1/-1 and attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hanweir Lancer | handled | As long as this creature is paired with another creature, both creatures have first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Harvester of Souls | handled | Whenever another nontoken creature dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Haunted Guardian | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Havengul Vampire | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heirs of Stromkirk | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Herald of War | handled | Whenever this creature attacks, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Holy Justiciar | handled | {2}{W}, {T}: Tap target creature. If that creature is a Zombie, exile it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hound of Griselbrand | handled | Undying | machines/keywords.py | Y/-/- | not_tested |
| Human Frailty | handled | Destroy target Human creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hunted Ghoul | handled | This creature can't block Humans. | the engine reads this text and performs it | Y/-/- | not_tested |
| Into the Void | handled | Return up to two target creatures to their owners' hands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kessig Malcontents | handled | When this creature enters, it deals damage to target player or planeswalker equal to the number of Humans you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kruin Striker | handled | Whenever another creature you control enters, this creature gets +1/+0 and gains trample until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Latch Seeker | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Mauler | handled | As long as this creature is paired with another creature, both creatures have haste. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Prowess | handled | Enchanted creature has haste and "{T}: This creature deals 1 damage to any target." | the engine reads this text and performs it | Y/-/- | not_tested |
| Lunar Mystic | handled | Whenever you cast an instant spell, you may pay {1}. If you do, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Maalfeld Twins | handled | When this creature dies, create two 2/2 black Zombie creature tokens. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Mad Prophet | handled | {T}, Discard a card: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Malicious Intent | handled | Enchanted creature has "{T}: Target creature can't block this turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Marrow Bats | handled | Pay 4 life: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mass Appeal | handled | Draw a card for each Human you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mental Agony | handled | Target player discards two cards and loses 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Midvast Protector | handled | When this creature enters, target creature you control gains protection from the color of your choice until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mist Raven | handled | When this creature enters, return target creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moonsilver Spear | handled | Equipped creature has first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moorland Inquisitor | handled | {2}{W}: This creature gains first strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Narstad Scrapper | handled | {2}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Natural End | handled | Destroy target artifact or enchantment. You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nearheath Pilgrim | handled | As long as this creature is paired with another creature, both creatures have lifelink. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nephalia Smuggler | handled | {3}{U}, {T}: Exile another target creature you control, then return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nettle Swine | handled |  |  | Y/-/- | not_tested |
| Nightshade Peddler | handled | As long as this creature is paired with another creature, both creatures have deathtouch. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pathbreaker Wurm | handled | As long as this creature is paired with another creature, both creatures have trample. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pillar of Flame | handled | Pillar of Flame deals 2 damage to any target. If a creature dealt damage this way would die this turn, exile it instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Polluted Dead | handled | When this creature dies, destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Raging Poltergeist | handled |  |  | Y/-/- | not_tested |
| Rain of Thorns | handled | Choose one or more — • Destroy target artifact. • Destroy target enchantment. • Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Renegade Demon | handled |  |  | Y/-/- | not_tested |
| Restoration Angel | handled | When this creature enters, you may exile target non-Angel creature you control, then return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Righteous Blow | handled | Righteous Blow deals 2 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Riot Ringleader | handled | Whenever this creature attacks, Human creatures you control get +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rotcrown Ghoul | handled | When this creature dies, target player mills five cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scalding Devil | handled | {2}{R}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scroll of Avacyn | handled | {1}, Sacrifice this artifact: Draw a card. If you control an Angel, you gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scroll of Griselbrand | handled | {1}, Sacrifice this artifact: Target opponent discards a card. If you control a Demon, that player loses 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Searchlight Geist | handled | {3}{B}: This creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Second Guess | handled | Counter target spell that's the second spell cast this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seraph Sanctuary | handled | When this land enters, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seraph of Dawn | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Slayers' Stronghold | handled | {R}{W}, {T}: Target creature gets +2/+0 and gains vigilance and haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Snare the Skies | handled | Target creature gets +1/+1 and gains reach until end of turn. (It can block creatures with flying.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Somberwald Sage | handled |  |  | Y/-/- | not_tested |
| Somberwald Vigilante | handled | Whenever this creature becomes blocked by a creature, this creature deals 1 damage to that creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soul of the Harvest | handled | Whenever another nontoken creature you control enters, you may draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soulcage Fiend | handled | When this creature dies, each player loses 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spectral Gateguards | handled | As long as this creature is paired with another creature, both creatures have vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spectral Prison | handled | Enchanted creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spirit Away | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stonewright | handled | As long as Stonewright is paired with another creature, each of those creatures has "{R}: This creature gets +1/+0 until end of turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Temporal Mastery | handled | Take an extra turn after this one. Exile Temporal Mastery. Miracle {1}{U} (You may cast this card for its miracle cost when you draw it if it's the first card y | the engine reads this text and performs it | Y/-/- | not_tested |
| Thatcher Revolt | handled | Create three 1/1 red Human creature tokens with haste. Sacrifice those tokens at the beginning of the next end step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thraben Valiant | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Timberland Guide | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tormentor's Trident | handled | Equipped creature gets +3/+0 and attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Triumph of Cruelty | handled | At the beginning of your upkeep, target opponent discards a card if you control the creature with the greatest power or tied for the greatest power. | the engine reads this text and performs it | Y/-/- | not_tested |
| Triumph of Ferocity | handled | At the beginning of your upkeep, draw a card if you control the creature with the greatest power or tied for the greatest power. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trusted Forcemage | handled | As long as this creature is paired with another creature, each of those creatures gets +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ulvenwald Tracker | handled | {1}{G}, {T}: Target creature you control fights another target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Uncanny Speed | handled | Target creature gets +3/+0 and gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vanishment | handled | Put target nonland permanent on top of its owner's library. Miracle {U} (You may cast this card for its miracle cost when you draw it if it's the first card you | the engine reads this text and performs it | Y/-/- | not_tested |
| Vessel of Endless Rest | handled | When this artifact enters, put target card from a graveyard on the bottom of its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vigilante Justice | handled | Whenever a Human you control enters, this enchantment deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Voice of the Provinces | handled | When this creature enters, create a 1/1 white Human creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vorstclaw | handled |  |  | Y/Y/- | not_tested |
| Wildwood Geist | handled | During your turn, this creature gets +2/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wingcrafter | handled | As long as this creature is paired with another creature, both creatures have flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wolfir Avenger | handled | {1}{G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wolfir Silverheart | handled | As long as this creature is paired with another creature, each of those creatures gets +4/+4. | the engine reads this text and performs it | Y/-/- | not_tested |
| Yew Spirit | handled | {2}{G}{G}: This creature gets +X/+X until end of turn, where X is its power. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zealous Conscripts | handled | When this creature enters, gain control of target permanent until end of turn. Untap that permanent. It gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zealous Strike | handled | Target creature gets +2/+2 and gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>55 cards</summary>

- Aggravate
- Angel of Jubilation
- Arcane Melee
- Avacyn, Angel of Hope
- Battle Hymn
- Blood Artist
- Bower Passage
- Burn at the Stake
- Cavern of Souls
- Champion of Lambholt
- Craterhoof Behemoth
- Crippling Chill
- Deadeye Navigator
- Defang
- Demonic Rising
- Demonic Taskmaster
- Descent into Madness
- Diregraf Escort
- Divine Deflection
- Dreadwaters
- Entreat the Angels
- Flowering Lumberknot
- Galvanic Alchemist
- Ghostform
- Gisela, Blade of Goldnight
- Gloom Surgeon
- Griselbrand
- Grounded
- Howlgeist
- Infinite Reflection
- Leap of Faith
- Lone Revenant
- Malignus
- Midnight Duelist
- Misthollow Griffin
- Moonlight Geist
- Otherworld Atlas
- Predator's Gambit
- Reforge the Soul
- Riders of Gavony
- Rush of Blood
- Scrapskin Drake
- Sheltering Word
- Sigarda, Host of Herons
- Silverblade Paladin
- Stern Mentor
- Stolen Goods
- Tamiyo, the Moon Sage
- Tandem Lookout
- Terminus
- Terrifying Presence
- Thunderous Wrath
- Unhallowed Pact
- Wandering Wolf
- Wild Defiance

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| +N: draw a card, then discard a card at random. | 1 | Tibalt, the Fiend-Blooded | avr |
| as long as equipped creature is a human or an angel, it has vigilance. | 1 | Bladed Bracers | avr |
| as long as you control exactly one creature, that creature gets +N/+N and has lifelink. | 1 | Homicidal Seclusion | avr |
| at the beginning of your upkeep, reveal the top card of your library. if it"..."t cast it, put it on the bottom of your library. | 1 | Descendants' Path | avr |
| at the beginning of your upkeep, sacrifice ~ unless you pay {M} for each other creature you control. | 1 | Fettergeist | avr |
| choose an order for artifacts, creatures, and lands. each player sacrifices one permanent of their choice of the first type, sacrifices two of their choice of t | 1 | Rite of Ruin | avr |
| counter target spell that targets a player. | 1 | Outwit | avr |
| destroy target creature with flying and all equipment attached to that creature. | 1 | Eaten by Spiders | avr |
| equipped creature gets +N/+N and can block an additional creature each combat. | 1 | Vanguard's Shield | avr |
| equipped creature gets +N/+N, has flying, and is a white angel in addition to its other colors and types. | 1 | Angelic Armaments | avr |
| exile the top card of your library. if it's a permanent card, you may put it onto the battlefield. if you do, repeat ~. | 1 | Primal Surge | avr |
| for each creature, its controller sacrifices it unless they pay N life. | 1 | Killing Wave | avr |
| return target creature card from your graveyard to the battlefield. if it's an angel, put two +N/+N counters on it. | 1 | Defy Death | avr |
| reveal the top two cards of your library. put all creature and land cards revealed ~ into your hand and the rest on the bottom of your library in any order. | 1 | Lair Delve | avr |
| target creature gains deathtouch until end of turn. regenerate it. (the next time that creature would be destroyed ~, instead tap it, remove it from combat, and | 1 | Necrobite | avr |
| target creature gets +N/+N until end of turn. if it's paired with a creature, that creature also gets +N/+N until end of turn. | 1 | Joint Assault | avr |
| target opponent reveals their hand. you choose a card from it with mana value N or greater and exile that card. | 1 | Appetite for Brains | avr |
| untapped creatures you control get +N/+N. | 1 | Builder's Blessing | avr |
| until end of turn, target creature gets +N/+N and gains trample, and all creatures able to block it ~ do so. miracle {M} (you may cast ~ for its miracle cost wh | 1 | Revenge of the Hunted | avr |
| when ~ dies, you may have target creature get -N/-N until end of turn. | 1 | Undead Executioner | avr |
| when ~ enters from a graveyard, target opponent gains control of it. | 1 | Treacherous Pit-Dweller | avr |
| when ~ enters, any opponent may have it deal N damage to them. if a player does, sacrifice ~. | 1 | Vexing Devil | avr |
| when ~ enters, exile all zombies, then return all human creature cards from your graveyard to the battlefield. | 1 | Angel of Glory's Rise | avr |
| when ~ enters, exile it unless you sacrifice another creature. | 1 | Demonlord of Ashmouth | avr |
| when ~ enters, target opponent chooses a permanent they control at random and sacrifices it. if a nonland permanent is sacrificed ~, repeat ~. | 1 | Tyrant of Discord | avr |
| whenever a creature dealt damage by ~ ~ dies, return it to the battlefield under your control. that creature is a black zombie in addition to its other colors a | 1 | Dread Slaver | avr |
| whenever a creature you control enters, you may have ~ become a N/N white angel artifact creature with flying until end of turn. | 1 | Angel's Tomb | avr |
| whenever an opponent loses life, you gain that much life. | 1 | Exquisite Blood | avr |
| whenever bruna attacks or blocks, you may attach to it any number of auras on the battlefield and you may put onto the battlefield attached to it any number of  | 1 | Bruna, Light of Alabaster | avr |
| whenever ~ attacks, return another creature you control to its owner's hand. | 1 | Havengul Skaab | avr |
| {M}{M}, {M}: you may cast spells ~ as though they had flash. | 1 | Alchemist's Refuge | avr |

## Notes


