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
- Added regression tests for batch power and tax cache/map.
- Added local dev stand scripts and isolated dev-data workflow.
- Added GitHub Actions CI: pytest + critical ruff profile.

Current test status: **221 passed**, 59 test files.
