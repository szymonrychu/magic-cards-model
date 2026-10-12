# Dark Ascension (dka)

- Expansion: 122
- Set code: `dka`
- Release date: 2012-02-03
- Cards in scope (Modern/Pioneer/Standard-legal): 154

## Legality

| Format | Legal cards |
|---|---|
| Modern | 154 |
| Pioneer | 16 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 37 | 24.0% |
| Works (untested) | 86 | 55.8% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 31 | 20.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Archangel's Light | silent | You gain 2 life for each card in your graveyard, then shuffle your graveyard into your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Black Cat | silent | When this creature dies, target opponent discards a card at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Call to the Kindred | silent | At the beginning of your upkeep, you may look at the top five cards of your library. If you do, you may put a creature card that shares a creature type with enc | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Curse of Echoes | silent | Whenever enchanted player casts an instant or sorcery spell, each other player may copy that spell and may choose new targets for the copy they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Curse of Misfortunes | silent | At the beginning of your upkeep, you may search your library for a Curse card that doesn't have the same name as a Curse attached to enchanted player, put it on | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Curse of Thirst | silent | At the beginning of enchanted player's upkeep, this Aura deals damage to that player equal to the number of Curses attached to them. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fiend of the Shadows | silent | Whenever this creature deals combat damage to a player, that player exiles a card from their hand. You may play that card for as long as it remains exiled. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gather the Townsfolk | silent | Create two 1/1 white Human creature tokens. Fateful hour — If you have 5 or less life, create five of those tokens instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Havengul Lich | silent | {1}: You may cast target creature card in a graveyard this turn. When you cast it this turn, this creature gains all activated abilities of that card until end  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Havengul Runebinder | silent | {2}{U}, {T}, Exile a creature card from your graveyard: Create a 2/2 black Zombie creature token, then put a +1/+1 counter on each Zombie creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Helvault | silent | When Helvault is put into a graveyard from the battlefield, return all cards exiled with it to the battlefield under their owners' control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Increasing Ambition | silent | Search your library for a card and put that card into your hand. If this spell was cast from a graveyard, instead search your library for two cards and put thos | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Increasing Confusion | silent | Target player mills X cards. If this spell was cast from a graveyard, that player mills twice that many cards instead. Flashback {X}{U} (You may cast this card  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Increasing Devotion | silent | Create five 1/1 white Human creature tokens. If this spell was cast from a graveyard, create ten of those tokens instead. Flashback {7}{W}{W} (You may cast this | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jar of Eyeballs | silent | {3}, {T}, Remove all eyeball counters from this artifact: Look at the top X cards of your library, where X is the number of eyeball counters removed this way. P | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lost in the Woods | silent | Whenever a creature attacks you or a planeswalker you control, reveal the top card of your library. If it's a Forest card, remove that creature from combat. The | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Markov Warlord | silent | When this creature enters, up to two target creatures can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mikaeus, the Unhallowed | silent | Whenever a Human deals damage to you, destroy it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scorch the Fields | silent | Destroy target land. Scorch the Fields deals 1 damage to each Human creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sorin, Lord of Innistrad | silent | −6: Destroy up to three target creatures and/or other planeswalkers. Return each card put into a graveyard this way to the battlefield under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tracker's Instincts | silent | Reveal the top four cards of your library. Put a creature card from among them into your hand and the rest into your graveyard. Flashback {2}{U} (You may cast t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Zombie Apocalypse | silent | Return all Zombie creature cards from your graveyard to the battlefield tapped, then destroy all Humans. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Afflicted Deserter // Werewolf Ransacker | notice | Whenever this creature transforms into Werewolf Ransacker, you may destroy target artifact. If that artifact is put into a graveyard this way, this creature dea | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Counterlash | notice | Counter target spell. You may cast a spell that shares a card type with it from your hand without paying its mana cost. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Deadly Allure | notice | Target creature gains deathtouch until end of turn and must be blocked this turn if able. Flashback {G} (You may cast this card from your graveyard for its flas | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Death's Caress | notice | Destroy target creature. If that creature was a Human, you gain life equal to its toughness. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Faith's Shield | notice | Target permanent you control gains protection from the color of your choice until end of turn. Fateful hour — If you have 5 or less life, instead you and each p | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Feed the Pack | notice | At the beginning of your end step, you may sacrifice a nontoken creature. If you do, create X 2/2 green Wolf creature tokens, where X is the sacrificed creature | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Loyal Cathar // Unhallowed Cathar | notice | When this creature dies, return it to the battlefield transformed under your control at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Sudden Disappearance | notice | Exile all nonland permanents target player controls. Return the exiled cards to the battlefield under their owner's control at the beginning of the next end ste | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Séance | notice | At the beginning of each upkeep, you may exile target creature card from your graveyard. If you do, create a token that's a copy of that card, except it's a Spi | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Altar of the Lost | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Artful Dodge | handled | Target creature can't be blocked this turn. Flashback {U} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Bar the Door | handled | Creatures you control get +0/+4 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Beguiler of Wills | handled | {T}: Gain control of target creature with power less than or equal to the number of creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blood Feud | handled | Target creature fights another target creature. (Each deals damage equal to its power to the other.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Bone to Ash | handled | Counter target creature spell. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Briarpack Alpha | handled | When this creature enters, target creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Burden of Guilt | handled | {1}: Tap enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Burning Oil | handled | Burning Oil deals 3 damage to target attacking or blocking creature. Flashback {3}{W} (You may cast this card from your graveyard for its flashback cost. Then e | the engine reads this text and performs it | Y/-/- | not_tested |
| Chant of the Skifsang | handled | Enchanted creature gets -13/-0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chill of Foreboding | handled | Each player mills five cards. Flashback {7}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Chosen of Markov // Markov's Servant | handled | {T}, Tap an untapped Vampire you control: Transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crushing Vines | handled | Choose one — • Destroy target creature with flying. • Destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dawntreader Elk | handled | {G}, Sacrifice this creature: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deranged Outcast | handled | {1}{G}, Sacrifice a Human: Put two +1/+1 counters on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Diregraf Captain | handled | Other Zombie creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drogskol Captain | handled | Other Spirit creatures you control get +1/+1 and have hexproof. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drogskol Reaver | handled | Whenever you gain life, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Elgaud Inquisitor | handled | When this creature dies, create a 1/1 white Spirit creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Erdwal Ripper | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Executioner's Hood | handled | Equipped creature has intimidate. | the engine reads this text and performs it | Y/-/- | not_tested |
| Falkenrath Aristocrat | handled | Sacrifice a creature: This creature gains indestructible until end of turn. If the sacrificed creature was a Human, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Falkenrath Torturer | handled | Sacrifice a creature: This creature gains flying until end of turn. If the sacrificed creature was a Human, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Farbog Boneflinger | handled | When this creature enters, target creature gets -2/-2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Favor of the Woods | handled | Whenever enchanted creature blocks, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fires of Undeath | handled | Fires of Undeath deals 2 damage to any target. Flashback {5}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Gavony Ironwright | handled | Fateful hour — As long as you have 5 or less life, other creatures you control get +1/+4. | the engine reads this text and performs it | Y/-/- | not_tested |
| Geralf's Mindcrusher | handled | When this creature enters, target player mills five cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghoultree | handled | This spell costs {1} less to cast for each creature card in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gravepurge | handled | Put any number of target creature cards from your graveyard on top of your library. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gravetiller Wurm | handled | Morbid — This creature enters with four +1/+1 counters on it if a creature died this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grim Backwoods | handled | {2}{B}{G}, {T}, Sacrifice a creature: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grim Flowering | handled | Draw a card for each creature card in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Griptide | handled | Put target creature on top of its owner's library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harrowing Journey | handled | Target player draws three cards and loses 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Headless Skaab | handled | As an additional cost to cast this spell, exile a creature card from your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Highborn Ghoul | handled | Intimidate | machines/keywords.py | Y/-/- | not_tested |
| Hinterland Hermit // Hinterland Scourge | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hollowhenge Beast | handled |  |  | Y/-/- | not_tested |
| Hunger of the Howlpack | handled | Put a +1/+1 counter on target creature. Morbid — Put three +1/+1 counters on that creature instead if a creature died this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Increasing Savagery | handled | Put five +1/+1 counters on target creature. If this spell was cast from a graveyard, put ten +1/+1 counters on that creature instead. Flashback {5}{G}{G} (You m | the engine reads this text and performs it | Y/-/- | not_tested |
| Kessig Recluse | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Lambholt Elder // Silverpelt Werewolf | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lingering Souls | handled | Create two 1/1 white Spirit creature tokens with flying. Flashback {1}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Markov Blademaster | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Midnight Guard | handled | Whenever another creature enters, untap this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mondronen Shaman // Tovolar's Magehunter | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moonveil Dragon | handled | {R}: Each creature you control gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mystic Retrieval | handled | Return target instant or sorcery card from your graveyard to your hand. Flashback {2}{R} (You may cast this card from your graveyard for its flashback cost. The | the engine reads this text and performs it | Y/-/- | not_tested |
| Nearheath Stalker | handled | Undying | machines/keywords.py | Y/-/- | not_tested |
| Nephalia Seakite | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Niblis of the Breath | handled | {U}, {T}: You may tap or untap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Niblis of the Mist | handled | When this creature enters, you may tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Niblis of the Urn | handled | Whenever this creature attacks, you may tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pyreheart Wolf | handled | Whenever this creature attacks, creatures you control gain menace until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reap the Seagraf | handled | Create a 2/2 black Zombie creature token. Flashback {4}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Relentless Skaabs | handled | As an additional cost to cast this spell, exile a creature card from your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Requiem Angel | handled | Whenever another non-Spirit creature you control dies, create a 1/1 white Spirit creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Russet Wolves | handled |  |  | Y/-/- | not_tested |
| Sanctuary Cat | handled |  |  | Y/-/- | not_tested |
| Saving Grasp | handled | Return target creature you own to your hand. Flashback {W} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Scorned Villager // Moonscarred Werewolf | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Screeching Skaab | handled | When this creature enters, mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shriekgeist | handled | Whenever this creature deals combat damage to a player, that player mills two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sightless Ghoul | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Silverclaw Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Skillful Lunge | handled | Target creature gets +2/+0 and gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skirsdag Flayer | handled | {3}{B}, {T}, Sacrifice a Human: Destroy target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Somberwald Dryad | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Stromkirk Captain | handled | Other Vampire creatures you control get +1/+1 and have first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Talons of Falkenrath | handled | Enchanted creature has "{1}{R}: This creature gets +2/+0 until end of turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Thraben Doomsayer | handled | {T}: Create a 1/1 white Human creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thraben Heretic | handled | {T}: Exile target creature card from a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Torch Fiend | handled | {R}, Sacrifice this creature: Destroy target artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tower Geist | handled | When this creature enters, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tragic Slip | handled | Target creature gets -1/-1 until end of turn. Morbid — That creature gets -13/-13 until end of turn instead if a creature died this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ulvenwald Bear | handled | Morbid — When this creature enters, if a creature died this turn, put two +1/+1 counters on target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vault of the Archangel | handled | {2}{W}{B}, {T}: Creatures you control gain deathtouch and lifelink until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vengeful Vampire | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Village Survivors | handled | Fateful hour — As long as you have 5 or less life, other creatures you control have vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vorapede | handled | Undying | machines/keywords.py | Y/-/- | not_tested |
| Wakedancer | handled | Morbid — When this creature enters, if a creature died this turn, create a 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wild Hunger | handled | Target creature gets +3/+1 and gains trample until end of turn. Flashback {3}{R} (You may cast this card from your graveyard for its flashback cost. Then exile  | the engine reads this text and performs it | Y/-/- | not_tested |
| Wolfbitten Captive // Krallenhorde Killer | handled | {1}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wolfhunter's Quiver | handled | Equipped creature has "{T}: This creature deals 1 damage to any target" and "{T}: This creature deals 3 damage to target Werewolf creature." | the engine reads this text and performs it | Y/-/- | not_tested |
| Wrack with Madness | handled | Target creature deals damage to itself equal to its power. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>37 cards</summary>

- Alpha Brawl
- Avacyn's Collar
- Break of Day
- Chalice of Life // Chalice of Death
- Clinging Mists
- Curse of Bloodletting
- Curse of Exhaustion
- Dungeon Geists
- Elbrus, the Binding Blade // Withengar Unbound
- Faithless Looting
- Flayer of the Hatebound
- Forge Devil
- Geralf's Messenger
- Grafdigger's Cage
- Gravecrawler
- Gruesome Discovery
- Haunted Fengraf
- Heavy Mattock
- Heckling Fiends
- Hellrider
- Hollowhenge Spirit
- Huntmaster of the Fells // Ravager of the Fells
- Immerwolf
- Increasing Vengeance
- Predator Ooze
- Ravenous Demon // Archdemon of Greed
- Secrets of the Dead
- Shattered Perception
- Soul Seizer // Ghastly Haunting
- Spiteful Shadows
- Stormbound Geist
- Strangleroot Geist
- Thalia, Guardian of Thraben
- Thought Scour
- Undying Evil
- Warden of the Wall
- Young Wolf

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of each upkeep, you may exile target creature card from your graveyard. if you do, create a token that"..."s a spirit in addition to its other  | 1 | Séance | dka |
| at the beginning of enchanted player's upkeep, ~ deals damage to that player equal to the number of curses attached to them. | 1 | Curse of Thirst | dka |
| at the beginning of your end step, you may sacrifice a nontoken creature. if you do, create N N/N green wolf creature tokens, where N is the sacrificed creature | 1 | Feed the Pack | dka |
| at the beginning of your upkeep, you may look at the top five cards of your library. if you do, you may put a creature card that shares a creature type with enc | 1 | Call to the Kindred | dka |
| at the beginning of your upkeep, you may search your library for a curse card that doesn't have the same name as a curse attached to enchanted player, put it on | 1 | Curse of Misfortunes | dka |
| counter target spell. you may cast a spell that shares a card type with it from your hand without paying its mana cost. | 1 | Counterlash | dka |
| create five N/N white human creature tokens. if ~ was cast from a graveyard, create ten of those tokens instead. flashback {M}{M}{M} (you may cast ~ from your g | 1 | Increasing Devotion | dka |
| create two N/N white human creature tokens. fateful hour — if you have N or less life, create five of those tokens instead. | 1 | Gather the Townsfolk | dka |
| destroy target creature. if that creature was a human, you gain life equal to its toughness. | 1 | Death's Caress | dka |
| destroy target land. ~ deals N damage to each human creature. | 1 | Scorch the Fields | dka |
| exile all nonland permanents target player controls. return the exiled cards to the battlefield under their owner's control at the beginning of the next end ste | 1 | Sudden Disappearance | dka |
| return all zombie creature cards from your graveyard to the battlefield tapped, then destroy all humans. | 1 | Zombie Apocalypse | dka |
| reveal the top four cards of your library. put a creature card from among them into your hand and the rest into your graveyard. flashback {M}{M} (you may cast ~ | 1 | Tracker's Instincts | dka |
| search your library for a card and put that card into your hand. if ~ was cast from a graveyard, instead search your library for two cards and put those cards i | 1 | Increasing Ambition | dka |
| target creature gains deathtouch until end of turn and must be blocked ~ if able. flashback {M} (you may cast ~ from your graveyard for its flashback cost. then | 1 | Deadly Allure | dka |
| target permanent you control gains protection from the color of your choice until end of turn. fateful hour — if you have N or less life, instead you and each p | 1 | Faith's Shield | dka |
| target player mills N cards. if ~ was cast from a graveyard, that player mills twice that many cards instead. flashback {M}{M} (you may cast ~ from your graveya | 1 | Increasing Confusion | dka |
| when ~ dies, return it to the battlefield transformed under your control at the beginning of the next end step. | 1 | Loyal Cathar // Unhallowed Cathar | dka |
| when ~ dies, target opponent discards a card at random. | 1 | Black Cat | dka |
| when ~ enters, up to two target creatures can't block ~. | 1 | Markov Warlord | dka |
| when ~ is put into a graveyard from the battlefield, return all cards exiled with it to the battlefield under their owners' control. | 1 | Helvault | dka |
| whenever a creature attacks you or a planeswalker you control, reveal the top card of your library. if it's a forest card, remove that creature from combat. the | 1 | Lost in the Woods | dka |
| whenever a human deals damage to you, destroy it. | 1 | Mikaeus, the Unhallowed | dka |
| whenever enchanted player casts an instant or sorcery spell, each other player may copy that spell and may choose new targets for the copy they control. | 1 | Curse of Echoes | dka |
| whenever ~ deals combat damage to a player, that player exiles a card from their hand. you may play that card for as long as it remains exiled. | 1 | Fiend of the Shadows | dka |
| whenever ~ transforms into werewolf ransacker, you may destroy target artifact. if that artifact is put into a graveyard ~, ~ deals N damage to that artifact's  | 1 | Afflicted Deserter // Werewolf Ransacker | dka |
| you gain N life for each card in your graveyard, then shuffle your graveyard into your library. | 1 | Archangel's Light | dka |
| {M}, {M}, remove all eyeball counters from ~: look at the top N cards of your library, where N is the number of eyeball counters removed ~. put one of them into | 1 | Jar of Eyeballs | dka |
| {M}: you may cast target creature card in a graveyard ~. when you cast it ~, ~ gains all activated abilities of that card until end of turn. | 1 | Havengul Lich | dka |
| {M}{M}, {M}, exile a creature card from your graveyard: create a N/N black zombie creature token, then put a +N/+N counter on each zombie creature you control. | 1 | Havengul Runebinder | dka |
| −N: destroy up to three target creatures and/or other planeswalkers. return each card put into a graveyard ~ to the battlefield under your control. | 1 | Sorin, Lord of Innistrad | dka |

## Notes


