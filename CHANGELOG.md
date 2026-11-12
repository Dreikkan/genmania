# Changelog

## 2026-11-12

- Synthesis can optionally consume starred generators; the result keeps
  the same star level and the UI warns before using them.
- Mass synthesis can target a maximum generator tier and now lists every
  created generator with its star level. Mass star upgrades also list the
  upgraded generators and their new stars.
- Added mass movement from temporary storage to storage or the energy
  station.
- Added a custom-quantity button to generator purchases.
- Generator shop prices were increased so crafting three copies is
  cheaper than buying the next tier; early craft gem fees were reduced
  and the content migration was bumped to version 7.
- Pets now have a 200-level progression with breakthroughs at
  10, 25, 50, 75, 100, 125, 150, 175 and 200. Every breakthrough
  increases the feeding cost in coins and gems.
- Rebalanced currency exchange: 1 000 coins → 1 gem before fees and
  1 gem → 800 coins before fees.
- Added mass synthesis to the craft screen with success/failure counts
  and an optional catalyst mode.
- Added mass star upgrades to the stars screen with success/failure
  counts and automatic cascading through available copies.
- Grids that are equal to or worse than the current grid are no longer
  offered in upgrades, including gem-purchased grids.
- Added regression tests for mass actions and grid filtering.

## 2026-11-09

- Fixed UI navigation regressions found in the button/menu audit:
  upgrades pagination now selects the `size` column expected by the
  shop view, and back buttons use the existing `back_to_home` helper.
- Added regression tests for upgrades pagination and back navigation.
- Added deterministic coverage for the weekend season XP event.

## 2026-11-05

- P0: battle pass reachability rebalanced — 30 levels now achievable
  at ~1 670 XP/day; level 30 reward is 1 800 coins, 11 gems,
  1 catalyst.
- P0: reset/prestige now release active auction bids and reset the
  lot to its start price.
- Added regression tests for battle pass reachability, rewards and
  auction-bid reset/prestige.
- P1 performance: power leaderboard uses a batched combat-power
  calculation (3 queries for 300 candidates instead of ~1 200),
  tax collector uses a one-pass guild tax map and cached tax rates,
  and top-user names are fetched with bounded concurrency.
- P1 security: indirect admin self-actions now flag top exclusion:
  self titles, own clan treasury/create/join/disband, and early
  auction finish while being the current bidder.
- P1 reliability: global giveaway broadcast is now bounded-parallel
  (semaphore 5) with per-guild transactional message records.
- Added concurrency tests for serialized DB transactions, equal
  auction bids and daily season XP caps.
- Added coverage baseline: 50% gate, current `bot.py` coverage ~51%.
- Added in-process metrics (commands, DB transactions, background
  errors), slow DB transaction logging, `data/health.json`, and
  owner-only `/health`.
- Refactor slice 1: extracted `gen_mania.config` and
  `gen_mania.metrics`; `bot.py` keeps compatibility re-exports.
- Refactor slice 2: extracted `gen_mania.db.transaction`
  (`TransactionRuntime`, `db_transaction`, commit/rollback helpers).
- Refactor slice 3: extracted `gen_mania.repositories.settings`
  (`get_settings`, `save_setting`) and `gen_mania.services.taxes`
  (per-user and per-guild tax rate calculation).
- Refactor slice 4: extracted `gen_mania.repositories.players`
  (accessibility, player stats, prestige points).
- Refactor slice 5: extracted `gen_mania.repositories.inventory`
  (inventory rows, sorting, reslotting and item locks).
- Refactor slice 6: extracted `gen_mania.services.market`
  (pure pricing/sparkline helpers) and
  `gen_mania.repositories.market` (price history).
- Refactor slice 7: extracted `gen_mania.services.auction`
  (bids, buyout, bid refunds and lot history).
- Refactor slice 8: extracted `gen_mania.services.bank`
  (deposits, loans, collateral and expiry).
- Refactor slice 9: extracted `gen_mania.services.pvp`
  (duel resolution, power tolerance and cooldowns).
- Refactor slice 10: extracted `gen_mania.repositories.clans`
  (clan reads, capacity, levels and active war lookup).
- Refactor slice 11: extracted `gen_mania.repositories.raids`
  (parties, invites, cooldowns and last raid target).
- Refactor slice 12: extracted `gen_mania.services.giveaways`
  (reward validation, participation and reward grants).
- Refactor slice 13: extracted `gen_mania.services.progress`
  (story/daily/clan quests and achievements).
- Refactor slice 14: extracted `gen_mania.services.leaderboards`
  (all top types and the 5-minute cache).
- Refactor slice 15: extracted `gen_mania.services.raid_combat`
  (raid combat, loot caps and finalization).
- Refactor slice 16: extracted `gen_mania.services.top_exclusion`
  (self-grant top exclusion and audit notice).
- Refactor slice 17: extracted `gen_mania.services.prestige`
  (point math, rebirth validation and reset).
- Refactor slice 18: extracted `gen_mania.services.clan_wars`
  (war declaration, attacks, cooldowns and rewards).
- Refactor slice 19: extended `gen_mania.repositories.inventory`
  with item placement and mailbox compensation.
- Refactor slice 20: extracted `gen_mania.services.market_orders`
  (buy/sell, order matching, limits, cancel and expiry).
- Refactor slice 21: extracted `gen_mania.services.seasons`
  (season XP, premium pass and reward claims).
- Refactor slice 22: extracted `gen_mania.services.pets`
  (pet feeding, bonuses and autocollector).
- Refactor slice 23: extracted `gen_mania.services.statuses`
  (purchase, bonus recalculation and expiry).
- Refactor slice 24: extracted `gen_mania.services.clan_applications`
  (submission, review and membership acceptance).
- Refactor slice 25: extracted `gen_mania.services.notifications`
  (preferences, cooldowns and DM fallback).
- Refactor slice 26: extracted `gen_mania.services.content`
  (content validation, edits, generators and achievements).
- Refactor slice 27: extracted `gen_mania.services.profile_ui`
  (synthesis statistics and detailed profile embeds).
- Refactor slice 28: extracted `gen_mania.services.shop_ui`
  (shop, achievements and collection embeds).
- Refactor slice 29: extracted `gen_mania.services.upgrades_ui`
  (upgrades, pets and autocollector embeds).
- Refactor slice 30: extracted `gen_mania.services.analytics_ui`
  (detailed player analytics embed).
- Refactor slice 31: extracted `gen_mania.services.admin_ui`
  (player card, season and market admin embeds).
- Refactor slice 32: extracted `gen_mania.repositories.audit`
  (admin action log and paginated log reader).
- Refactor slice 33: extended `gen_mania.services.profile_ui`
  with the public/espionage profile embed.
- Refactor slice 34: moved station and generator-detail embeds
  into `gen_mania.services.profile_ui`.
- Refactor slice 35: moved title-unlock queries and rules into
  `gen_mania.repositories.players`.
- Refactor slice 36: moved the notification center embed into
  `gen_mania.services.notifications`.
- Refactor slice 37: moved guide sections, paging and embeds into
  `gen_mania.services.guide`.
- Refactor slice 38: extracted market history, exchange, trading hub
  and order-book embeds into `gen_mania.services.market_ui`.
- Refactor slice 39: extracted storage and temporary-storage embeds
  into `gen_mania.services.storage_ui`.
- Refactor slice 40: moved top leaderboard embed into
  `gen_mania.services.leaderboards`.
- Refactor slice 41: moved the season overview embed into
  `gen_mania.services.seasons`.
- Refactor slice 42: moved bank and bank-history embeds into
  `gen_mania.services.bank`.
- Refactor slice 43: moved the prestige overview embed into
  `gen_mania.services.prestige`.
- Refactor slice 44: moved the clan-war embed into
  `gen_mania.services.clan_wars`.
- Refactor slice 45: moved guild-access snapshot synchronization into
  `gen_mania.services.guild_access`.
- Refactor slice 46: moved the PvP battle-log embed into
  `gen_mania.services.pvp`.
- Refactor slice 47: moved the raid-party embed into
  `gen_mania.services.raid_combat`.
- Refactor slice 48: extracted advent state, day opening and calendar
  embed into `gen_mania.services.advent`.
- Refactor slice 49: extracted clan overview and browser embeds into
  `gen_mania.services.clan_ui`.
- Refactor slice 50: extracted set synergy calculations and embed into
  `gen_mania.services.sets`; coverage reached 60%.
- Refactor slice 51: moved the hourly notification sweep into
  `gen_mania.services.notifications` and covered it with tests.
- Coverage slice 52: added background-task, navigation, screen,
  embed and economy-modal tests; coverage reached 65%.
- Coverage slice 53: added admin, clan, deep-UI, auction/bank/war,
  giveaway and empty-state tests; coverage reached 70%.
- Coverage slice 54: added remaining admin action modals and clan
  confirmation tests; coverage reached 71%.
- Coverage slice 55: added UI constructors, auction/order screens,
  mailbox, quests, emoji editor and deep UI tests; coverage reached 72%.
- Coverage slice 56: added command, health, shop, order-book, pets,
  daily, taxes and misc modal tests; coverage reached 73%.
- Coverage slice 57: added retention, giveaway rollback, raid invite,
  backup/reset, final admin and UI branch tests; coverage reached 75%.
- Coverage slice 58: added admin-reset, pet switch/removal, prestige,
  quantity purchase and remaining admin-modal tests.
- Coverage slice 59: added season premium, giveaway join, star upgrade,
  mass ops, clan detail, clan war attack and remaining UI tests.
- Coverage slice 60: added upgrade/raid/auction/duel/clan error-path tests.
- Coverage slice 61: added market/admin modals, health writer, backup task,
  status expirer and notifications command tests.
- Coverage slice 62: added remaining command, callback and error-path tests.
- Coverage slice 63: crossed 80% with service-branch, auction, bank, clan-war,
  notification, setup-hook and UI-flow tests.
- Coverage slice 64: added admin modal validation, missing-entity and
  content/settings modal branch tests.
- Coverage slice 65: added duel/PvP/profile/raid-invite, cosmetic, exchange,
  bank, auction, shop, quest and craft UI branch tests.
- Coverage slice 66: added background task wrappers, giveaway helpers,
  clan/admin open helpers and status-role removal tests.
- Coverage slice 67: added clan flows, daily/member helpers, SafeView/AdminView,
  notifications, pets/lock/autocollector, shop and extra callback tests.
  Coverage reached **85%**.
- Coverage slice 68: added view constructors, move/swap callbacks, admin
  advent/give-item/profile/reset and market-order confirmation tests.
- Coverage slice 69: added clan invite/application decisions, pets shop,
  star confirm, bonus line, global giveaway helpers, profile buttons,
  swap pagination, content/settings views and bank-loan select tests.
- Coverage slice 70: added service leftovers (transactions, giveaways,
  market cancel, bank repay, raids, status helpers) and final callbacks
  (social/shop, sort menus, star/PvP, content modals, bulk sell, auction,
  advent and giveaway embed). Coverage reached **88%**.
- Coverage slice 71: added raid invite guards, clan confirmations, build-main
  onboarding, guide split, star/craft edges, cosmetics/clan menus, exchange
  and content selection tests. Coverage reached **89%**.
- Coverage slice 72: added guard/confirm views, open helpers, background error
  branches, shop/bulk/raid edges, settings/sell/profile/season callbacks.
  Coverage reached **90%**.
- Coverage slice 73: added swap/craft branches, clan confirms/invites/menus,
  backup/close/autocollector errors, settings modal, raid guards and misc
  view/open helpers. Coverage reached **91%**.
- Coverage slice 74: added generic view/button and modal probes across all
  single- and multi-argument UI classes, covering happy paths and guard
  branches. Coverage reached **96%**.
- Coverage slice 75: added module-helper probes plus targeted status, content,
  giveaway, background-task and migration branches. Coverage reached **97%**.
- Coverage slice 76: added pagination/select pass in the UI probe, plain module
  helpers, small view branches and bank modal edge cases. Coverage reached
  **98%**.
- Coverage slice 77: expanded modal value sets, added craft/clan/admin guards,
  background cancellation and service error-branch tests. Coverage reached
  **99%**.
- Coverage slice 78: added transaction/bank/raid/season/advent/service edge
  tests and UI history/upgrade branches. Coverage reached **99.51%**.
- Coverage slice 79: added market-order flow, pets/autocollector, notifications
  and remaining service/UI branches. Coverage reached **99.57%**.
- Coverage slice 80: covered the last reachable service/UI branches and removed
  dead guard blocks. Coverage reached **100.00%**.
- Added `bothost.json` and deployment instructions for Bothost
  (Git repo or `.zip` archive with `gen_mania/`).
- Added regression tests for batch power and tax cache/map.
- Added local dev stand scripts and isolated dev-data workflow.
- Added GitHub Actions CI: pytest + coverage + critical ruff profile.

Current test status: **239 passed**, 63 test files.
