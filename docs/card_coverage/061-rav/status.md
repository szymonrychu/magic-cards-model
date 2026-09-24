# Ravnica: City of Guilds (rav)

- Expansion: 061
- Set code: `rav`
- Release date: 2005-10-07
- Cards in scope (Modern/Pioneer/Standard-legal): 245

## Legality

| Format | Legal cards |
|---|---|
| Modern | 245 |
| Pioneer | 19 |
| Standard | 8 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 13 | 5.3% |
| Partial (unaudited) | 16 | 6.5% |
| Not tested (handled, untested) | 110 | 44.9% |
| Not working (silent / notice / error) | 106 | 43.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Agrus Kos, Wojek Veteran | silent | Whenever Agrus Kos attacks, attacking red creatures get +2/+0 and attacking white creatures get +0/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bathe in Light | silent | Radiance — Choose a color. Target creature and each other creature that shares a color with it gain protection from the chosen color until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blockbuster | silent | {1}{R}, Sacrifice this enchantment: It deals 3 damage to each tapped creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blood Funnel | silent | Whenever you cast a noncreature spell, counter that spell unless you sacrifice a creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bloodbond March | silent | Whenever a player casts a creature spell, each player returns all cards with the same name as that spell from their graveyard to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bloodletter Quill | silent | {U}{B}: Remove a blood counter from this artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bottled Cloister | silent | At the beginning of each opponent's upkeep, exile all cards from your hand face down. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Breath of Fury | silent | When enchanted creature deals combat damage to a player, sacrifice it and attach this Aura to a creature you control. If you do, untap all creatures you control | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chant of Vitu-Ghazi | silent | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Prevent all | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Char | silent | Char deals 4 damage to any target and 2 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Circu, Dimir Lobotomist | silent | Whenever you cast a blue spell, exile the top card of target player's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cloudstone Curio | silent | Whenever a nonartifact permanent you control enters, you may return another permanent you control that shares a permanent type with it to its owner's hand. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Coalhauler Swine | silent | Whenever this creature is dealt damage, it deals that much damage to each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Compulsive Research | silent | Target player draws three cards. Then that player discards two cards unless they discard a land card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Conclave's Blessing | silent | Enchanted creature gets +0/+2 for each other creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Congregation at Dawn | silent | Search your library for up to three creature cards, reveal them, then shuffle and put those cards on top in any order. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Crown of Convergence | silent | As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dimir House Guard | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Dimir Machinations | silent | Look at the top three cards of target player's library. Exile any number of those cards, then put the rest back in any order. Transmute {1}{B}{B} ({1}{B}{B}, Di | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dogpile | silent | Dogpile deals damage to any target equal to the number of attacking creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Drake Familiar | silent | When this creature enters, sacrifice it unless you return an enchantment to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dryad's Caress | silent | You gain 1 life for each creature on the battlefield. If {W} was spent to cast this spell, untap all creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Empty the Catacombs | silent | Each player returns all creature cards from their graveyard to their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Eye of the Storm | silent | Whenever a player casts an instant or sorcery card, exile it. Then that player copies each instant or sorcery card exiled with this enchantment. For each copy,  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Festival of the Guildpact | silent | Prevent the next X damage that would be dealt to you this turn. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flame Fusillade | silent | Until end of turn, permanents you control gain "{T}: This permanent deals 1 damage to any target." | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Followed Footsteps | silent | At the beginning of your upkeep, create a token that's a copy of enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Golgari Brownscale | silent | When this card is put into your hand from your graveyard, you gain 2 life. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Golgari Thug | silent | When this creature dies, put target creature card from your graveyard on top of your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Grozoth | silent | When this creature enters, you may search your library for any number of cards that have mana value 9, reveal them, put them into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Halcyon Glaze | silent | Whenever you cast a creature spell, this enchantment becomes a 4/4 Illusion creature with flying in addition to its other types until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hammerfist Giant | silent | {T}: This creature deals 4 damage to each creature without flying and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hour of Reckoning | silent | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Destroy all | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Dragon | silent | When this creature enters, target opponent creates three 2/2 white Knight creature tokens with first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Horror | silent | When this creature enters, target opponent creates two 3/3 green Centaur creature tokens with protection from black. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Lammasu | silent | When this creature enters, target opponent creates a 4/4 black Horror creature token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Phantasm | silent | When this creature enters, target opponent creates five 1/1 red Goblin creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Troll | silent | When this creature enters, target opponent creates four 1/1 blue Faerie creature tokens with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Incite Hysteria | silent | Radiance — Until end of turn, target creature and each other creature that shares a color with it gain "This creature can't block." | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Induce Paranoia | silent | Counter target spell. If {B} was spent to cast this spell, that spell's controller mills X cards, where X is the spell's mana value. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Loxodon Hierarch | silent | {G}{W}, Sacrifice this creature: Regenerate each creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mark of Eviction | silent | At the beginning of your upkeep, return enchanted creature and all Auras attached to that creature to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Master Warcraft | silent | Cast this spell only before attackers are declared. You choose which creatures attack this turn. You choose which creatures block this turn and how those creatu | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mindleech Mass | silent | Whenever this creature deals combat damage to a player, you may look at that player's hand. If you do, you may cast a spell from among those cards without payin | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mindmoil | silent | Whenever you cast a spell, put the cards in your hand on the bottom of your library in any order, then draw that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mnemonic Nexus | silent | Each player shuffles their graveyard into their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Moonlight Bargain | silent | Look at the top five cards of your library. For each card, put that card into your graveyard unless you pay 2 life. Then put the rest into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mortipede | silent | {2}{G}: All creatures able to block this creature this turn do so. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Necroplasm | silent | At the beginning of your end step, destroy each creature with mana value equal to the number of +1/+1 counters on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Netherborn Phalanx | silent | When this creature enters, each opponent loses 1 life for each creature they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ordruun Commando | silent | {W}: Prevent the next 1 damage that would be dealt to this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Peel from Reality | silent | Return target creature you control and target creature you don't control to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Perplex | silent | Counter target spell unless its controller discards their hand. Transmute {1}{U}{B} ({1}{U}{B}, Discard this card: Search your library for a card with the same  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Plague Boiler | silent | {1}{B}{G}: Put a plague counter on this artifact or remove a plague counter from it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pollenbright Wings | silent | Whenever enchanted creature deals combat damage to a player, create that many 1/1 green Saproling creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quickchange | silent | Target creature becomes the color or colors of your choice until end of turn. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rain of Embers | silent | Rain of Embers deals 1 damage to each creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Razia's Purification | silent | Each player chooses three permanents they control, then sacrifices the rest. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Razia, Boros Archangel | silent | {T}: The next 3 damage that would be dealt to target creature you control this turn is dealt to another target creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ribbons of Night | silent | Ribbons of Night deals 4 damage to target creature and you gain 4 life. If {U} was spent to cast this spell, draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rolling Spoil | silent | Destroy target land. If {B} was spent to cast this spell, all creatures get -1/-1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sabertooth Alley Cat | silent | {1}{R}: Creatures without defender can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sadistic Augermage | silent | When this creature dies, each player puts a card from their hand on top of their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Savra, Queen of the Golgari | silent | Whenever you sacrifice a black creature, you may pay 2 life. If you do, each other player sacrifices a creature of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Screeching Griffin | silent | {R}: Target creature can't block this creature this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shadow of Doubt | silent | ({U/B} can be paid with either {U} or {B}.) Players can't search libraries this turn. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shred Memory | silent | Exile up to four target cards from a single graveyard. Transmute {1}{B}{B} ({1}{B}{B}, Discard this card: Search your library for a card with the same mana valu | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sins of the Past | silent | Until end of turn, you may cast target instant or sorcery card from your graveyard without paying its mana cost. If that spell would be put into your graveyard, | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spawnbroker | silent | When this creature enters, you may exchange control of target creature you control and target creature with power less than or equal to that creature's power an | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spectral Searchlight | silent | {T}: Choose a player. That player adds one mana of any color they choose. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stinkweed Imp | silent | Whenever this creature deals combat damage to a creature, destroy that creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Strands of Undeath | silent | {B}: Regenerate enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sunforger | silent | {R}{W}, Unattach this Equipment: Search your library for a red or white instant card with mana value 4 or less and cast that card without paying its mana cost.  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sunhome Enforcer | silent | Whenever this creature deals combat damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Surge of Zeal | silent | Radiance — Target creature and each other creature that shares a color with it gain haste until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Svogthos, the Restless Tomb | silent | {3}{B}{G}: Until end of turn, this land becomes a black and green Plant Zombie creature with "This creature's power and toughness are each equal to the number o | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Telling Time | silent | Look at the top three cards of your library. Put one of those cards into your hand, one on top of your library, and one on the bottom of your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Terraformer | silent | {1}: Choose a basic land type. Each land you control becomes that type until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thoughtpicker Witch | silent | {1}, Sacrifice a creature: Look at the top two cards of target opponent's library, then exile one of them. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thundersong Trumpeter | silent | {T}: Target creature can't attack or block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tidewater Minion | silent | {4}: This creature loses defender until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Torpid Moloch | silent | Sacrifice three lands: This creature loses defender until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tunnel Vision | silent | Choose a card name. Target player reveals cards from the top of their library until a card with that name is revealed. If it is, that player puts the rest of th | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Undercity Shade | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Vindictive Mob | silent | When this creature enters, sacrifice a creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vulturous Zombie | silent | Whenever a card is put into an opponent's graveyard from anywhere, put a +1/+1 counter on this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Warp World | silent | Each player shuffles all permanents they own into their library, then reveals that many cards from the top of their library. Each player puts all artifact, crea | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Woebringer Demon | silent | At the beginning of each player's upkeep, that player sacrifices a creature of their choice. If the player can't, sacrifice this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wojek Embermage | silent | Radiance — {T}: This creature deals 1 damage to target creature and each other creature that shares a color with it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wojek Siren | silent | Radiance — Target creature and each other creature that shares a color with it get +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Woodwraith Corrupter | silent | {1}{B}{G}, {T}: Target Forest becomes a 4/4 black and green Elemental Horror creature. It's still a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Brightflame | notice | Radiance — Brightflame deals X damage to target creature and each other creature that shares a color with it. You gain life equal to the damage dealt this way. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Cleansing Beam | notice | Radiance — Cleansing Beam deals 2 damage to target creature and each other creature that shares a color with it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Dimir Doppelganger | notice | {1}{U}{B}: Exile target creature card from a graveyard. This creature becomes a copy of that card, except it has this ability. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Flash Conscription | notice | Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn. If {W} was spent to cast this spell, the creature g | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Flickerform | notice | {2}{W}{W}: Exile enchanted creature and all Auras attached to it. At the beginning of the next end step, return that card to the battlefield under its owner's c | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Gate Hound | notice | Creatures you control have vigilance as long as this creature is enchanted. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Gaze of the Gorgon | notice | ({B/G} can be paid with either {B} or {G}.) Regenerate target creature. At this turn's next end of combat, destroy all creatures that blocked or were blocked by | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Leave No Trace | notice | Radiance — Destroy target enchantment and each other enchantment that shares a color with it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Lurking Informant | notice | {2}, {T}: Look at the top card of target player's library. You may put that card into that player's graveyard. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Rally the Righteous | notice | Radiance — Untap target creature and each other creature that shares a color with it. Those creatures get +2/+0 until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Remand | notice | Counter target spell. If that spell is countered this way, put it into its owner's hand instead of into that player's graveyard. Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Transluminant | notice | {W}, Sacrifice this creature: Create a 1/1 white Spirit creature token with flying at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Twisted Justice | notice | Target player sacrifices a creature of their choice. You draw cards equal to that creature's power. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Vigor Mortis | notice | Return target creature card from your graveyard to the battlefield. If {G} was spent to cast this spell, that creature enters with an additional +1/+1 counter o | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Voyager Staff | notice | {2}, Sacrifice this artifact: Exile target creature. Return the exiled card to the battlefield under its owner's control at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Chorus of the Conclave | unaudited | As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that creature enters with that many additional +1/+1 counters on it. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Dream Leash | unaudited | You can't choose an untapped permanent as this spell's target as you cast it. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Excruciator | unaudited | Damage that would be dealt by this creature can't be prevented. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Faith's Fetters | unaudited | Enchanted permanent can't attack or block, and its activated abilities can't be activated unless they're mana abilities. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ghosts of the Innocent | unaudited | If a source would deal damage to a permanent or player, it deals half that damage, rounded down, to that permanent or player instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Indentured Oaf | unaudited | Prevent all damage that this creature would deal to red creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Light of Sanction | unaudited | Prevent all damage that would be dealt to creatures you control by sources you control. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Loxodon Gatekeeper | unaudited | Artifacts, creatures, and lands your opponents control enter tapped. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Molten Sentry | unaudited | As this creature enters, flip a coin. If the coin comes up heads, this creature enters as a 5/2 creature with haste. If it comes up tails, this creature enters  | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Pariah's Shield | unaudited | All damage that would be dealt to you is dealt to equipped creature instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Phytohydra | unaudited | If damage would be dealt to this creature, put that many +1/+1 counters on it instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Privileged Position | unaudited | Other permanents you control have hexproof. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Selesnya Sagittars | unaudited | This creature can block an additional creature each combat. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Suppression Field | unaudited | Activated abilities cost {2} more to activate unless they're mana abilities. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Szadek, Lord of Secrets | unaudited | If Szadek would deal combat damage to a player, instead put that many +1/+1 counters on Szadek and that player mills that many cards. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Wizened Snitches | unaudited | Players play with the top card of their libraries revealed. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Autochthon Wurm | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Barbarian Riftcutter | handled | {R}, Sacrifice this creature: Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Benevolent Ancestor | handled | {T}: Prevent the next 1 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boros Garrison | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boros Guildmage | handled | {1}{R}: Target creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boros Recruit | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Boros Signet | handled |  |  | Y/-/- | not_tested |
| Boros Swiftblade | handled | Double strike | machines/combat.py | Y/-/- | not_tested |
| Brainspoil | handled | Destroy target creature that isn't enchanted. It can't be regenerated. Transmute {1}{B}{B} ({1}{B}{B}, Discard this card: Search your library for a card with th | the engine reads this text and performs it | Y/-/- | not_tested |
| Caregiver | handled | {W}, Sacrifice a creature: Prevent the next 1 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Carven Caryatid | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Centaur Safeguard | handled | When this creature dies, you may gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chord of Calling | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Search your | the engine reads this text and performs it | Y/Y/- | not_tested |
| Civic Wayfinder | handled | When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Clinging Darkness | handled | Enchanted creature gets -4/-1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Concerted Effort | handled | At the beginning of each upkeep, creatures you control gain flying until end of turn if a creature you control has flying. The same is true for fear, first stri | the engine reads this text and performs it | Y/-/- | not_tested |
| Conclave Equenaut | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Conclave Phalanx | handled | When this creature enters, you gain 1 life for each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Consult the Necrosages | handled | Choose one — • Target player draws two cards. • Target player discards two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Convolute | handled | Counter target spell unless its controller pays {4}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Copy Enchantment | handled | You may have this enchantment enter as a copy of any enchantment on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Courier Hawk | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Cyclopean Snare | handled | {3}, {T}: Tap target creature, then return this artifact to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Darkblast | handled | Target creature gets -1/-1 until end of turn. Dredge 3 (If you would draw a card, you may mill three cards instead. If you do, return this card from your gravey | the engine reads this text and performs it | Y/-/- | not_tested |
| Devouring Light | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Exile targe | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dimir Aqueduct | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dimir Cutpurse | handled | Whenever this creature deals combat damage to a player, that player discards a card and you draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dimir Signet | handled |  |  | Y/-/- | not_tested |
| Disembowel | handled | Destroy target creature with mana value X. | the engine reads this text and performs it | Y/-/- | not_tested |
| Divebomber Griffin | handled | {T}, Sacrifice this creature: It deals 3 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dizzy Spell | handled | Target creature gets -3/-0 until end of turn. Transmute {1}{U}{U} ({1}{U}{U}, Discard this card: Search your library for a card with the same mana value as this | the engine reads this text and performs it | Y/-/- | not_tested |
| Dowsing Shaman | handled | {2}{G}, {T}: Return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drift of Phantasms | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Dromad Purebred | handled | Whenever this creature is dealt damage, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drooling Groodion | handled | {2}{B}{G}, Sacrifice a creature: Target creature gets +2/+2 until end of turn. Another target creature gets -2/-2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Duskmantle, House of Shadow | handled | {U}{B}, {T}: Target player mills a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elvish Skysweeper | handled | {4}{G}, Sacrifice a creature: Destroy target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ethereal Usher | handled | {U}, {T}: Target creature can't be blocked this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Farseek | handled | Search your library for a Plains, Island, Swamp, or Mountain card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fiery Conclusion | handled | As an additional cost to cast this spell, sacrifice a creature. Fiery Conclusion deals 5 damage to target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Firemane Angel | handled | At the beginning of your upkeep, if Firemane Angel is in your graveyard or on the battlefield, you may gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fists of Ironwood | handled | When this Aura enters, create two 1/1 green Saproling creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flame-Kin Zealot | handled | When this creature enters, creatures you control get +1/+1 and gain haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flow of Ideas | handled | Draw a card for each Island you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Galvanic Arc | handled | When this Aura enters, it deals 3 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gather Courage | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Target crea | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glare of Subdual | handled | Tap an untapped creature you control: Tap target artifact or creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Glass Golem | handled |  |  | Y/-/- | not_tested |
| Glimpse the Unthinkable | handled | Target player mills ten cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golgari Germination | handled | Whenever a nontoken creature you control dies, create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golgari Grave-Troll | handled | This creature enters with a +1/+1 counter on it for each creature card in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golgari Rot Farm | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golgari Rotwurm | handled | {B}, Sacrifice a creature: Target player loses 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Golgari Signet | handled |  |  | Y/-/- | not_tested |
| Goliath Spider | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Grave-Shell Scarab | handled | {1}, Sacrifice this creature: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grayscaled Gharial | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Greater Forgeling | handled | {1}{R}: This creature gets +3/-3 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greater Mossdog | handled | Dredge | machines/keywords.py | Y/-/- | not_tested |
| Guardian of Vitu-Ghazi | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Hex | handled | Destroy six target creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Infectious Host | handled | When this creature dies, target player loses 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Instill Furor | handled | Enchanted creature has "At the beginning of your end step, sacrifice this creature unless it attacked this turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivy Dancer | handled | {T}: Target creature gains forestwalk until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Junktroller | handled | {T}: Put target card from a graveyard on the bottom of its owner's library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Last Gasp | handled | Target creature gets -3/-3 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Leashling | handled | Put a card from your hand on top of your library: Return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Life from the Loam | handled | Return up to three target land cards from your graveyard to your hand. Dredge 3 (If you would draw a card, you may mill three cards instead. If you do, return t | the engine reads this text and performs it | Y/-/- | not_tested |
| Lore Broker | handled | {T}: Each player draws a card, then discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mausoleum Turnkey | handled | When this creature enters, return target creature card of an opponent's choice from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moldervine Cloak | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moroii | handled | At the beginning of your upkeep, you lose 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nightmare Void | handled | Target player reveals their hand. You choose a card from it. That player discards that card. Dredge 2 (If you would draw a card, you may mill two cards instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nullstone Gargoyle | handled | Whenever the first noncreature spell of a turn is cast, counter that spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Oathsworn Giant | handled | Other creatures you control get +0/+2 and have vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Peregrine Mask | handled | Equipped creature has defender, flying, and first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Perilous Forays | handled | {1}, Sacrifice a creature: Search your library for a land card with a basic land type, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Primordial Sage | handled | Whenever you cast a creature spell, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Psychic Drain | handled | Target player mills X cards and you gain X life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Putrefy | handled | Destroy target artifact or creature. It can't be regenerated. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Recollect | handled | Return target card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reroute | handled | Change the target of target activated ability with a single target. (Mana abilities can't be targeted.) Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Roofstalker Wight | handled | {1}{U}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Root-Kin Ally | handled | Tap two untapped creatures you control: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scion of the Wild | handled | Scion of the Wild's power and toughness are each equal to the number of creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Searing Meditation | handled | Whenever you gain life, you may pay {2}. If you do, this enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seeds of Strength | handled | Target creature gets +1/+1 until end of turn. Target creature gets +1/+1 until end of turn. Target creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seismic Spike | handled | Destroy target land. Add {R}{R}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sell-Sword Brute | handled | When this creature dies, it deals 2 damage to you. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sewerdreg | handled | Sacrifice this creature: Exile target card from a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shambling Shell | handled | Sacrifice this creature: Put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Siege Wurm | handled | Trample | machines/combat.py | Y/Y/- | not_tested |
| Sparkmage Apprentice | handled | When this creature enters, it deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stasis Cell | handled | Enchanted creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stone-Seeder Hierophant | handled | Landfall — Whenever a land you control enters, untap this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stoneshaker Shaman | handled | At the beginning of each player's end step, that player sacrifices an untapped land of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sundering Vitae | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Destroy tar | the engine reads this text and performs it | Y/-/- | not_tested |
| Sunhome, Fortress of the Legion | handled | {2}{R}{W}, {T}: Target creature gains double strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Surveilling Sprite | handled | When this creature dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tattered Drake | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trophy Hunter | handled | {1}{G}: This creature deals 1 damage to target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Veteran Armorer | handled | Other creatures you control get +0/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Fangtail | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Slasher | handled | {R}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vinelasher Kudzu | handled | Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vitu-Ghazi, the City-Tree | handled | {2}{G}{W}, {T}: Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Votary of the Conclave | handled | {2}{G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| War-Torch Goblin | handled | {R}, Sacrifice this creature: It deals 2 damage to target blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Woodwraith Strangler | handled | Exile a creature card from your graveyard: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zephyr Spirit | handled | When this creature blocks, return it to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>13 cards</summary>

- Blazing Archon
- Boros Fury-Shield
- Cerulean Sphinx
- Dark Confidant
- Doubling Season
- Lightning Helix
- Muddle the Mixture
- Overgrown Tomb
- Sacred Foundry
- Sisters of Stone Death
- Temple Garden
- Watchwolf
- Watery Grave

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| When this creature enters, target opponent creates two 3/3 green Centaur creature tokens with protection from black. | Hunted Dragon, Hunted Horror, Hunted Lammasu, Hunted Phantasm, Hunted Troll | 5 |
| At the beginning of your end step, destroy each creature with mana value equal to the number of +1/+1 counters on this creature. | Followed Footsteps, Mark of Eviction, Necroplasm | 3 |
| Whenever this creature deals combat damage to a player, you may look at that player's hand. If you do, you may cast a spell from among those cards without payin | Mindleech Mass, Stinkweed Imp, Sunhome Enforcer | 3 |
| At the beginning of each player's upkeep, that player sacrifices a creature of their choice. If the player can't, sacrifice this creature. | Bottled Cloister, Woebringer Demon | 2 |
| ({B/G} can be paid with either {B} or {G}.) Regenerate target creature. At this turn's next end of combat, destroy all creatures that blocked or were blocked by | Gaze of the Gorgon, Shadow of Doubt | 2 |
| Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Prevent all | Chant of Vitu-Ghazi, Hour of Reckoning | 2 |
| Fear | Dimir House Guard, Undercity Shade | 2 |
| Look at the top three cards of target player's library. Exile any number of those cards, then put the rest back in any order. Transmute {1}{B}{B} ({1}{B}{B}, Di | Dimir Machinations, Telling Time | 2 |
| Radiance — Target creature and each other creature that shares a color with it gain haste until end of turn. | Surge of Zeal, Wojek Siren | 2 |
| When this creature enters, sacrifice it unless you return an enchantment to its owner's hand. | Drake Familiar, Vindictive Mob | 2 |
| When this creature enters, you may exchange control of target creature you control and target creature with power less than or equal to that creature's power an | Grozoth, Spawnbroker | 2 |
| Activated abilities cost {2} more to activate unless they're mana abilities. | Suppression Field | 1 |
| {2}{G}: All creatures able to block this creature this turn do so. | Mortipede | 1 |
| All damage that would be dealt to you is dealt to equipped creature instead. | Pariah's Shield | 1 |
| Artifacts, creatures, and lands your opponents control enter tapped. | Loxodon Gatekeeper | 1 |
| As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that creature enters with that many additional +1/+1 counters on it. | Chorus of the Conclave | 1 |
| As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1. | Crown of Convergence | 1 |
| As this creature enters, flip a coin. If the coin comes up heads, this creature enters as a 5/2 creature with haste. If it comes up tails, this creature enters  | Molten Sentry | 1 |
| Cast this spell only before attackers are declared. You choose which creatures attack this turn. You choose which creatures block this turn and how those creatu | Master Warcraft | 1 |
| Char deals 4 damage to any target and 2 damage to you. | Char | 1 |
| {1}: Choose a basic land type. Each land you control becomes that type until end of turn. | Terraformer | 1 |
| Choose a card name. Target player reveals cards from the top of their library until a card with that name is revealed. If it is, that player puts the rest of th | Tunnel Vision | 1 |
| {T}: Choose a player. That player adds one mana of any color they choose. | Spectral Searchlight | 1 |
| Counter target spell. If that spell is countered this way, put it into its owner's hand instead of into that player's graveyard. Draw a card. | Remand | 1 |
| Counter target spell. If {B} was spent to cast this spell, that spell's controller mills X cards, where X is the spell's mana value. | Induce Paranoia | 1 |
| Counter target spell unless its controller discards their hand. Transmute {1}{U}{B} ({1}{U}{B}, Discard this card: Search your library for a card with the same  | Perplex | 1 |
| {1}{R}: Creatures without defender can't block this creature this turn. | Sabertooth Alley Cat | 1 |
| Creatures you control have vigilance as long as this creature is enchanted. | Gate Hound | 1 |
| Damage that would be dealt by this creature can't be prevented. | Excruciator | 1 |
| Destroy target land. If {B} was spent to cast this spell, all creatures get -1/-1 until end of turn. | Rolling Spoil | 1 |
| Dogpile deals damage to any target equal to the number of attacking creatures you control. | Dogpile | 1 |
| Each player chooses three permanents they control, then sacrifices the rest. | Razia's Purification | 1 |
| Each player returns all creature cards from their graveyard to their hand. | Empty the Catacombs | 1 |
| Each player shuffles all permanents they own into their library, then reveals that many cards from the top of their library. Each player puts all artifact, crea | Warp World | 1 |
| Each player shuffles their graveyard into their library. | Mnemonic Nexus | 1 |
| Enchanted creature gets +0/+2 for each other creature you control. | Conclave's Blessing | 1 |
| Enchanted permanent can't attack or block, and its activated abilities can't be activated unless they're mana abilities. | Faith's Fetters | 1 |
| {2}{W}{W}: Exile enchanted creature and all Auras attached to it. At the beginning of the next end step, return that card to the battlefield under its owner's c | Flickerform | 1 |
| {1}{U}{B}: Exile target creature card from a graveyard. This creature becomes a copy of that card, except it has this ability. | Dimir Doppelganger | 1 |
| Exile up to four target cards from a single graveyard. Transmute {1}{B}{B} ({1}{B}{B}, Discard this card: Search your library for a card with the same mana valu | Shred Memory | 1 |
| If a source would deal damage to a permanent or player, it deals half that damage, rounded down, to that permanent or player instead. | Ghosts of the Innocent | 1 |
| If damage would be dealt to this creature, put that many +1/+1 counters on it instead. | Phytohydra | 1 |
| If Szadek would deal combat damage to a player, instead put that many +1/+1 counters on Szadek and that player mills that many cards. | Szadek, Lord of Secrets | 1 |
| {2}, {T}: Look at the top card of target player's library. You may put that card into that player's graveyard. | Lurking Informant | 1 |
| Look at the top five cards of your library. For each card, put that card into your graveyard unless you pay 2 life. Then put the rest into your hand. | Moonlight Bargain | 1 |
| Other permanents you control have hexproof. | Privileged Position | 1 |
| Players play with the top card of their libraries revealed. | Wizened Snitches | 1 |
| Prevent all damage that this creature would deal to red creatures. | Indentured Oaf | 1 |
| Prevent all damage that would be dealt to creatures you control by sources you control. | Light of Sanction | 1 |
| {W}: Prevent the next 1 damage that would be dealt to this creature this turn. | Ordruun Commando | 1 |
| Prevent the next X damage that would be dealt to you this turn. Draw a card. | Festival of the Guildpact | 1 |
| {1}{B}{G}: Put a plague counter on this artifact or remove a plague counter from it. | Plague Boiler | 1 |
| Radiance — Brightflame deals X damage to target creature and each other creature that shares a color with it. You gain life equal to the damage dealt this way. | Brightflame | 1 |
| Radiance — Choose a color. Target creature and each other creature that shares a color with it gain protection from the chosen color until end of turn. | Bathe in Light | 1 |
| Radiance — Cleansing Beam deals 2 damage to target creature and each other creature that shares a color with it. | Cleansing Beam | 1 |
| Radiance — Destroy target enchantment and each other enchantment that shares a color with it. | Leave No Trace | 1 |
| Radiance — {T}: This creature deals 1 damage to target creature and each other creature that shares a color with it. | Wojek Embermage | 1 |
| Radiance — Untap target creature and each other creature that shares a color with it. Those creatures get +2/+0 until end of turn. | Rally the Righteous | 1 |
| Radiance — Until end of turn, target creature and each other creature that shares a color with it gain "This creature can't block." | Incite Hysteria | 1 |
| Rain of Embers deals 1 damage to each creature and each player. | Rain of Embers | 1 |
| {B}: Regenerate enchanted creature. | Strands of Undeath | 1 |
| {U}{B}: Remove a blood counter from this artifact. | Bloodletter Quill | 1 |
| Return target creature card from your graveyard to the battlefield. If {G} was spent to cast this spell, that creature enters with an additional +1/+1 counter o | Vigor Mortis | 1 |
| Return target creature you control and target creature you don't control to their owners' hands. | Peel from Reality | 1 |
| Ribbons of Night deals 4 damage to target creature and you gain 4 life. If {U} was spent to cast this spell, draw a card. | Ribbons of Night | 1 |
| {1}, Sacrifice a creature: Look at the top two cards of target opponent's library, then exile one of them. | Thoughtpicker Witch | 1 |
| {2}, Sacrifice this artifact: Exile target creature. Return the exiled card to the battlefield under its owner's control at the beginning of the next end step. | Voyager Staff | 1 |
| {W}, Sacrifice this creature: Create a 1/1 white Spirit creature token with flying at the beginning of the next end step. | Transluminant | 1 |
| {G}{W}, Sacrifice this creature: Regenerate each creature you control. | Loxodon Hierarch | 1 |
| {1}{R}, Sacrifice this enchantment: It deals 3 damage to each tapped creature and each player. | Blockbuster | 1 |
| Sacrifice three lands: This creature loses defender until end of turn. | Torpid Moloch | 1 |
| Search your library for up to three creature cards, reveal them, then shuffle and put those cards on top in any order. | Congregation at Dawn | 1 |
| Target creature becomes the color or colors of your choice until end of turn. Draw a card. | Quickchange | 1 |
| {T}: Target creature can't attack or block this turn. | Thundersong Trumpeter | 1 |
| {R}: Target creature can't block this creature this turn. | Screeching Griffin | 1 |
| {1}{B}{G}, {T}: Target Forest becomes a 4/4 black and green Elemental Horror creature. It's still a land. | Woodwraith Corrupter | 1 |
| Target player draws three cards. Then that player discards two cards unless they discard a land card. | Compulsive Research | 1 |
| Target player sacrifices a creature of their choice. You draw cards equal to that creature's power. | Twisted Justice | 1 |
| {T}: The next 3 damage that would be dealt to target creature you control this turn is dealt to another target creature instead. | Razia, Boros Archangel | 1 |
| This creature can block an additional creature each combat. | Selesnya Sagittars | 1 |
| {T}: This creature deals 4 damage to each creature without flying and each player. | Hammerfist Giant | 1 |
| {4}: This creature loses defender until end of turn. | Tidewater Minion | 1 |
| {R}{W}, Unattach this Equipment: Search your library for a red or white instant card with mana value 4 or less and cast that card without paying its mana cost.  | Sunforger | 1 |
| Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn. If {W} was spent to cast this spell, the creature g | Flash Conscription | 1 |
| Until end of turn, permanents you control gain "{T}: This permanent deals 1 damage to any target." | Flame Fusillade | 1 |
| {3}{B}{G}: Until end of turn, this land becomes a black and green Plant Zombie creature with "This creature's power and toughness are each equal to the number o | Svogthos, the Restless Tomb | 1 |
| Until end of turn, you may cast target instant or sorcery card from your graveyard without paying its mana cost. If that spell would be put into your graveyard, | Sins of the Past | 1 |
| When enchanted creature deals combat damage to a player, sacrifice it and attach this Aura to a creature you control. If you do, untap all creatures you control | Breath of Fury | 1 |
| When this card is put into your hand from your graveyard, you gain 2 life. | Golgari Brownscale | 1 |
| When this creature dies, each player puts a card from their hand on top of their library. | Sadistic Augermage | 1 |
| When this creature dies, put target creature card from your graveyard on top of your library. | Golgari Thug | 1 |
| When this creature enters, each opponent loses 1 life for each creature they control. | Netherborn Phalanx | 1 |
| Whenever a card is put into an opponent's graveyard from anywhere, put a +1/+1 counter on this creature. | Vulturous Zombie | 1 |
| Whenever a nonartifact permanent you control enters, you may return another permanent you control that shares a permanent type with it to its owner's hand. | Cloudstone Curio | 1 |
| Whenever a player casts a creature spell, each player returns all cards with the same name as that spell from their graveyard to the battlefield. | Bloodbond March | 1 |
| Whenever a player casts an instant or sorcery card, exile it. Then that player copies each instant or sorcery card exiled with this enchantment. For each copy,  | Eye of the Storm | 1 |
| Whenever Agrus Kos attacks, attacking red creatures get +2/+0 and attacking white creatures get +0/+2 until end of turn. | Agrus Kos, Wojek Veteran | 1 |
| Whenever enchanted creature deals combat damage to a player, create that many 1/1 green Saproling creature tokens. | Pollenbright Wings | 1 |
| Whenever this creature is dealt damage, it deals that much damage to each player. | Coalhauler Swine | 1 |
| Whenever you cast a blue spell, exile the top card of target player's library. | Circu, Dimir Lobotomist | 1 |
| Whenever you cast a creature spell, this enchantment becomes a 4/4 Illusion creature with flying in addition to its other types until end of turn. | Halcyon Glaze | 1 |
| Whenever you cast a noncreature spell, counter that spell unless you sacrifice a creature. | Blood Funnel | 1 |
| Whenever you cast a spell, put the cards in your hand on the bottom of your library in any order, then draw that many cards. | Mindmoil | 1 |
| Whenever you sacrifice a black creature, you may pay 2 life. If you do, each other player sacrifices a creature of their choice. | Savra, Queen of the Golgari | 1 |
| You can't choose an untapped permanent as this spell's target as you cast it. | Dream Leash | 1 |
| You gain 1 life for each creature on the battlefield. If {W} was spent to cast this spell, untap all creatures you control. | Dryad's Caress | 1 |

## Notes


