# March of the Machine: The Aftermath (mat)

- Expansion: 239
- Set code: `mat`
- Release date: 2023-05-12
- Cards in scope (Modern/Pioneer/Standard-legal): 49

## Legality

| Format | Legal cards |
|---|---|
| Modern | 49 |
| Pioneer | 49 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 14 | 28.6% |
| Works (untested) | 13 | 26.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 22 | 44.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Arni Metalbrow | silent | Whenever a creature you control attacks or enters attacking, you may pay {1}{R}. If you do, you may put a creature card with mana value less than that creature' | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Calix, Guided by Fate | silent | Whenever Calix or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you cont | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cosmic Rebirth | silent | Choose target permanent card in your graveyard. If it has mana value 3 or less, you may put it onto the battlefield. If you don't put it onto the battlefield, p | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Death-Rattle Oni | silent | When this creature enters, destroy all other creatures that were dealt damage this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Feast of the Victorious Dead | silent | At the beginning of your end step, if one or more creatures died this turn, you gain that much life and distribute that many +1/+1 counters among any number of  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Filter Out | silent | Return all noncreature, nonland permanents to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Karn, Legacy Reforged | silent | At the beginning of your upkeep, add {C} for each artifact you control. This mana can't be spent to cast nonartifact spells. Until end of turn, you don't lose t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kiora, Sovereign of the Deep | silent | Whenever you cast a Kraken, Leviathan, Octopus, or Serpent spell from your hand, look at the top X cards of your library, where X is that spell's mana value. Yo | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Metropolis Reformer | silent | Whenever this creature is dealt damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ob Nixilis, Captive Kingpin | silent | Whenever one or more opponents each lose exactly 1 life, put a +1/+1 counter on Ob Nixilis. Exile the top card of your library. Until your next end step, you ma | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Plargg and Nassari | silent | At the beginning of your upkeep, each player exiles cards from the top of their library until they exile a nonland card. An opponent chooses a nonland card exil | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rocco, Street Chef | silent | At the beginning of your end step, each player exiles the top card of their library. Until your next end step, each player may play the card they exiled this wa | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sarkhan, Soul Aflame | silent | Whenever a Dragon you control enters, you may have Sarkhan become a copy of it until end of turn, except its name is Sarkhan, Soul Aflame and it's legendary in  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Spark Rupture | silent | Each planeswalker with one or more loyalty counters on it loses all abilities and is a creature with power and toughness each equal to the number of loyalty cou | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tazri, Stalwart Survivor | silent | {W}{U}{B}{R}{G}, {T}: Mill five cards. Put all creature cards with activated abilities that aren't mana abilities from among the milled cards into your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The Kenriths' Royal Funeral | silent | When The Kenriths' Royal Funeral enters, exile up to two target legendary creature cards from your graveyard. You draw X cards and you lose X life, where X is t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tolarian Contempt | silent | At the beginning of your end step, for each opponent, choose up to one target creature they control with a rejection counter on it. That creature's owner puts i | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tranquil Frillback | silent | When this creature enters, you may pay {G} up to three times. When you pay this cost one or more times, choose up to that many — • Destroy target artifact or en | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tyvar the Bellicose | silent | Whenever one or more Elves you control attack, they gain deathtouch until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vesuvan Drifter | silent | At the beginning of each combat, you may reveal the top card of your library. If you reveal a creature card this way, this creature becomes a copy of that card  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nahiri, Forged in Fury | notice | Whenever an equipped creature you control attacks, exile the top card of your library. You may play that card this turn. You may cast Equipment spells this way  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Urborg Scavengers | notice | This creature has flying as long as a card exiled with it has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, indestructi | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Animist's Might | handled | This spell costs {2} less to cast if it targets a legendary creature you control. Target creature you control deals damage equal to twice its power to target cr | the engine reads this text and performs it | Y/Y/- | not_tested |
| Campus Renovation | handled | Return up to one target artifact or enchantment card from your graveyard to the battlefield. Exile the top two cards of your library. Until the end of your next | the engine reads this text and performs it | Y/Y/- | not_tested |
| Coppercoat Vanguard | handled | Each other Human you control gets +1/+0 and has ward {1}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Danitha, New Benalia's Light | handled | Once during each of your turns, you may cast an Aura or Equipment spell from your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drannith Ruins | handled | {2}, {T}: Put two +1/+1 counters on target non-Human creature that entered this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harnessed Snubhorn | handled | Whenever this creature deals combat damage to a player, return target artifact or enchantment card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jirina, Dauntless General | handled | When Jirina enters, exile target player's graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kolaghan Warmonger | handled | Whenever this creature attacks, look at the top six cards of your library. You may reveal a Dragon card from among them and put it into your hand. Put the rest  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Markov Baron | handled | Other Vampires you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nahiri's Resolve | handled | Creatures you control get +1/+0 and have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nissa, Resurgent Animist | handled | Landfall — Whenever a land you control enters, add one mana of any color. Then if this is the second time this ability has resolved this turn, reveal cards from | the engine reads this text and performs it | Y/Y/- | not_tested |
| Open the Way | handled | X can't be greater than the number of players in the game. Reveal cards from the top of your library until you reveal X land cards. Put those land cards onto th | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pia Nalaar, Consul of Revival | handled | Thopters you control have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>14 cards</summary>

- Ayara's Oathsworn
- Blot Out
- Deification
- Gold-Forged Thopteryx
- Jolrael, Voice of Zhalfir
- Leyline Immersion
- Narset, Enlightened Exile
- Nashi, Moon's Legacy
- Niv-Mizzet, Supreme
- Rebuild the City
- Reckless Handling
- Samut, Vizier of Naktamun
- Sigarda, Font of Blessings
- Undercity Upheaval

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of each combat, you may reveal the top card of your library. if you reveal a creature card ~, ~ becomes a copy of that card until end of turn,  | 1 | Vesuvan Drifter | mat |
| at the beginning of your end step, each player exiles the top card of their library. until your next end step, each player may play the card they exiled ~. | 1 | Rocco, Street Chef | mat |
| at the beginning of your end step, for each opponent, choose up to one target creature they control with a rejection counter on it. that creature's owner puts i | 1 | Tolarian Contempt | mat |
| at the beginning of your end step, if one or more creatures died ~, you gain that much life and distribute that many +N/+N counters among any number of creature | 1 | Feast of the Victorious Dead | mat |
| at the beginning of your upkeep, add {M} for each artifact you control. ~ can"..."t lose ~ as steps and phases end. | 1 | Karn, Legacy Reforged | mat |
| at the beginning of your upkeep, each player exiles cards from the top of their library until they exile a nonland card. an opponent chooses a nonland card exil | 1 | Plargg and Nassari | mat |
| choose target permanent card in your graveyard. if it has mana value N or less, you may put it onto the battlefield. if you don't put it onto the battlefield, p | 1 | Cosmic Rebirth | mat |
| each planeswalker with one or more loyalty counters on it loses all abilities and is a creature with power and toughness each equal to the number of loyalty cou | 1 | Spark Rupture | mat |
| return all noncreature, nonland permanents to their owners' hands. | 1 | Filter Out | mat |
| when ~ enters, destroy all other creatures that were dealt damage ~. | 1 | Death-Rattle Oni | mat |
| when ~ enters, exile up to two target legendary creature cards from your graveyard. you draw N cards and you lose N life, where N is the greatest mana value amo | 1 | The Kenriths' Royal Funeral | mat |
| when ~ enters, you may pay {M} up to three times. when you pay ~ one or more times, choose up to that many — • destroy target artifact or enchantment. • exile t | 1 | Tranquil Frillback | mat |
| whenever a creature you control attacks or enters attacking, you may pay {M}{M}. if you do, you may put a creature card with mana value less than that creature' | 1 | Arni Metalbrow | mat |
| whenever a dragon you control enters, you may have sarkhan become a copy of it until end of turn, except its name is ~ and it's legendary in addition to its oth | 1 | Sarkhan, Soul Aflame | mat |
| whenever an equipped creature you control attacks, exile the top card of your library. you may play that card ~. you may cast equipment spells ~ without paying  | 1 | Nahiri, Forged in Fury | mat |
| whenever calix or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you cont | 1 | Calix, Guided by Fate | mat |
| whenever one or more elves you control attack, they gain deathtouch until end of turn. | 1 | Tyvar the Bellicose | mat |
| whenever one or more opponents each lose exactly N life, put a +N/+N counter on ob nixilis. exile the top card of your library. until your next end step, you ma | 1 | Ob Nixilis, Captive Kingpin | mat |
| whenever you cast a kraken, leviathan, octopus, or serpent spell from your hand, look at the top N cards of your library, where N is that spell's mana value. yo | 1 | Kiora, Sovereign of the Deep | mat |
| whenever ~ is dealt damage, you gain that much life. | 1 | Metropolis Reformer | mat |
| {M}{M}{M}{M}{M}, {M}: mill five cards. put all creature cards with activated abilities that aren't mana abilities from among the milled cards into your hand. | 1 | Tazri, Stalwart Survivor | mat |
| ~ has flying as long as a card exiled with it has flying. the same is true for first strike, double strike, deathtouch, haste, hexproof, indestructible, lifelin | 1 | Urborg Scavengers | mat |

## Notes


