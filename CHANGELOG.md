# Changelog

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
- Added regression tests for batch power and tax cache/map.
- Added local dev stand scripts and isolated dev-data workflow.
- Added GitHub Actions CI: pytest + coverage + critical ruff profile.

Current test status: **239 passed**, 63 test files.
