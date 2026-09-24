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
| Full (handled + tested) | 6 | 12.2% |
| Partial (unaudited) | 5 | 10.2% |
| Not tested (handled, untested) | 11 | 22.4% |
| Not working (silent / notice / error) | 27 | 55.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Arni Metalbrow | silent | Whenever a creature you control attacks or enters attacking, you may pay {1}{R}. If you do, you may put a creature card with mana value less than that creature' | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blot Out | silent | Target opponent exiles a creature or planeswalker they control with the greatest mana value among creatures and planeswalkers they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Calix, Guided by Fate | silent | Whenever Calix or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you cont | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Coppercoat Vanguard | silent | Each other Human you control gets +1/+0 and has ward {1}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cosmic Rebirth | silent | Choose target permanent card in your graveyard. If it has mana value 3 or less, you may put it onto the battlefield. If you don't put it onto the battlefield, p | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Death-Rattle Oni | silent | When this creature enters, destroy all other creatures that were dealt damage this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Feast of the Victorious Dead | silent | At the beginning of your end step, if one or more creatures died this turn, you gain that much life and distribute that many +1/+1 counters among any number of  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Filter Out | silent | Return all noncreature, nonland permanents to their owners' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Karn, Legacy Reforged | silent | Karn's power and toughness are each equal to the greatest mana value among artifacts you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kiora, Sovereign of the Deep | silent | Whenever you cast a Kraken, Leviathan, Octopus, or Serpent spell from your hand, look at the top X cards of your library, where X is that spell's mana value. Yo | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Metropolis Reformer | silent | Whenever this creature is dealt damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ob Nixilis, Captive Kingpin | silent | Whenever one or more opponents each lose exactly 1 life, put a +1/+1 counter on Ob Nixilis. Exile the top card of your library. Until your next end step, you ma | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Open the Way | silent | X can't be greater than the number of players in the game. Reveal cards from the top of your library until you reveal X land cards. Put those land cards onto th | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
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
| Nahiri's Resolve | notice | At the beginning of your end step, exile any number of nontoken artifacts and/or creatures you control. Return those cards to the battlefield under their owner' | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Nahiri, Forged in Fury | notice | Whenever an equipped creature you control attacks, exile the top card of your library. You may play that card this turn. You may cast Equipment spells this way  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Undercity Upheaval | notice | Undergrowth — Distribute X +1/+1 counters among any number of target creatures you control, where X is the number of creature cards in your graveyard as you cas | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Urborg Scavengers | notice | This creature has flying as long as a card exiled with it has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, indestructi | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Deification | unaudited | As this enchantment enters, choose a planeswalker type. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Gold-Forged Thopteryx | unaudited | Each legendary permanent you control has ward {2}. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Leyline Immersion | unaudited | Enchanted creature has ward {2} and "{T}: Add five mana in any combination of colors. Spend this mana only to cast spells." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Niv-Mizzet, Supreme | unaudited | Each instant and sorcery card in your graveyard that's exactly two colors has jump-start. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Sigarda, Font of Blessings | unaudited | Other permanents you control have hexproof. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Animist's Might | handled | This spell costs {2} less to cast if it targets a legendary creature you control. Target creature you control deals damage equal to twice its power to target cr | the engine reads this text and performs it | Y/Y/- | not_tested |
| Campus Renovation | handled | Return up to one target artifact or enchantment card from your graveyard to the battlefield. Exile the top two cards of your library. Until the end of your next | the engine reads this text and performs it | Y/Y/- | not_tested |
| Danitha, New Benalia's Light | handled | Once during each of your turns, you may cast an Aura or Equipment spell from your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drannith Ruins | handled | {2}, {T}: Put two +1/+1 counters on target non-Human creature that entered this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harnessed Snubhorn | handled | Whenever this creature deals combat damage to a player, return target artifact or enchantment card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jirina, Dauntless General | handled | When Jirina enters, exile target player's graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kolaghan Warmonger | handled | Whenever this creature attacks, look at the top six cards of your library. You may reveal a Dragon card from among them and put it into your hand. Put the rest  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Markov Baron | handled | Other Vampires you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nissa, Resurgent Animist | handled | Landfall — Whenever a land you control enters, add one mana of any color. Then if this is the second time this ability has resolved this turn, reveal cards from | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pia Nalaar, Consul of Revival | handled | Thopters you control have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Samut, Vizier of Naktamun | handled | Whenever a creature you control deals combat damage to a player, if that creature entered this turn, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Ayara's Oathsworn
- Jolrael, Voice of Zhalfir
- Narset, Enlightened Exile
- Nashi, Moon's Legacy
- Rebuild the City
- Reckless Handling

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, each player exiles cards from the top of their library until they exile a nonland card. An opponent chooses a nonland card exil | Feast of the Victorious Dead, Nahiri's Resolve, Plargg and Nassari, Rocco, Street Chef, Tolarian Contempt | 5 |
| As this enchantment enters, choose a planeswalker type. | Deification | 1 |
| At the beginning of each combat, you may reveal the top card of your library. If you reveal a creature card this way, this creature becomes a copy of that card  | Vesuvan Drifter | 1 |
| Choose target permanent card in your graveyard. If it has mana value 3 or less, you may put it onto the battlefield. If you don't put it onto the battlefield, p | Cosmic Rebirth | 1 |
| Each instant and sorcery card in your graveyard that's exactly two colors has jump-start. | Niv-Mizzet, Supreme | 1 |
| Each legendary permanent you control has ward {2}. | Gold-Forged Thopteryx | 1 |
| Each other Human you control gets +1/+0 and has ward {1}. | Coppercoat Vanguard | 1 |
| Each planeswalker with one or more loyalty counters on it loses all abilities and is a creature with power and toughness each equal to the number of loyalty cou | Spark Rupture | 1 |
| Enchanted creature has ward {2} and "{T}: Add five mana in any combination of colors. Spend this mana only to cast spells." | Leyline Immersion | 1 |
| Karn's power and toughness are each equal to the greatest mana value among artifacts you control. | Karn, Legacy Reforged | 1 |
| {W}{U}{B}{R}{G}, {T}: Mill five cards. Put all creature cards with activated abilities that aren't mana abilities from among the milled cards into your hand. | Tazri, Stalwart Survivor | 1 |
| Other permanents you control have hexproof. | Sigarda, Font of Blessings | 1 |
| Return all noncreature, nonland permanents to their owners' hands. | Filter Out | 1 |
| Target opponent exiles a creature or planeswalker they control with the greatest mana value among creatures and planeswalkers they control. | Blot Out | 1 |
| This creature has flying as long as a card exiled with it has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, indestructi | Urborg Scavengers | 1 |
| Undergrowth — Distribute X +1/+1 counters among any number of target creatures you control, where X is the number of creature cards in your graveyard as you cas | Undercity Upheaval | 1 |
| When The Kenriths' Royal Funeral enters, exile up to two target legendary creature cards from your graveyard. You draw X cards and you lose X life, where X is t | The Kenriths' Royal Funeral | 1 |
| When this creature enters, destroy all other creatures that were dealt damage this turn. | Death-Rattle Oni | 1 |
| When this creature enters, you may pay {G} up to three times. When you pay this cost one or more times, choose up to that many — • Destroy target artifact or en | Tranquil Frillback | 1 |
| Whenever a creature you control attacks or enters attacking, you may pay {1}{R}. If you do, you may put a creature card with mana value less than that creature' | Arni Metalbrow | 1 |
| Whenever a Dragon you control enters, you may have Sarkhan become a copy of it until end of turn, except its name is Sarkhan, Soul Aflame and it's legendary in  | Sarkhan, Soul Aflame | 1 |
| Whenever an equipped creature you control attacks, exile the top card of your library. You may play that card this turn. You may cast Equipment spells this way  | Nahiri, Forged in Fury | 1 |
| Whenever Calix or an enchanted creature you control deals combat damage to a player, you may create a token that's a copy of a nonlegendary enchantment you cont | Calix, Guided by Fate | 1 |
| Whenever one or more Elves you control attack, they gain deathtouch until end of turn. | Tyvar the Bellicose | 1 |
| Whenever one or more opponents each lose exactly 1 life, put a +1/+1 counter on Ob Nixilis. Exile the top card of your library. Until your next end step, you ma | Ob Nixilis, Captive Kingpin | 1 |
| Whenever this creature is dealt damage, you gain that much life. | Metropolis Reformer | 1 |
| Whenever you cast a Kraken, Leviathan, Octopus, or Serpent spell from your hand, look at the top X cards of your library, where X is that spell's mana value. Yo | Kiora, Sovereign of the Deep | 1 |
| X can't be greater than the number of players in the game. Reveal cards from the top of your library until you reveal X land cards. Put those land cards onto th | Open the Way | 1 |

## Notes


