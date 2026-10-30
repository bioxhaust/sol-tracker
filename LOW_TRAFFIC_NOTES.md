# Low-traffic pool-creation detection (measured 2026-10-29, Helius WS, commitment=confirmed)

Full feed (`logsSubscribe mentions=<program>` for all 7 DEXes) = **~106–130 MB/min**
(pumpswap 52–74, damm_v2 12–15, dlmm 9–13, whirlpool 6–10, cpmm ~2, amm_v4 ~2, damm_v1 0.17).
Low-traffic set below = **~1.8–2.9 MB/min** (≈50x less), **25/25 creations matched** vs a
parallel full-feed sample (6 min, 15:50–15:56 MSK); earlier 6-min samples were also used to find the accounts.

Billing: Helius standard WSS = 20 credits/MB (2 per 0.1 MB, uncompressed), +1 credit per
connection. QuickNode Solana WSS = 15 credits per 0.1 MB (150/MB) since mid-2026.

## Per DEX: logsSubscribe `mentions` accounts that work (creation-only)

| DEX | account (role) | MB/min | verified |
|---|---|---|---|
| Raydium AMM v4 | `7YttLkHDoNj9wyDur5pM1ejNaAvT9X4eqaYcHQqtj2G5` (create fee dest, initialize2 acct #14) | ~0 | 4/4 historical initialize2 txs |
| Raydium CPMM | `DNXgeM9EiiaAbaWvwjHj9fQQLAX5ZsfHyvmYUNRAdNC8` (create_pool_fee) | ~0.001 | live Initialize + InitializeWithPermission |
| Orca Whirlpool | `2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ` (main WhirlpoolsConfig) | 0.002–0.008 | live InitializePoolV2 |
| Meteora DAMM v2 | `A8gMrEPJkacWkcb3DGwtJwTe16HktSEfvwtuDh2MCtck` (dynamic config) | ~0.01 | live InitializePoolWithDynamicConfig |
| Meteora DAMM v2 | `8dnhmayAP3LA957YgSdP3Nw48ZJM6C4248qfFeyfnxTP` (in DBC-migration / customizable txs) | 0.01–0.03 | live; caught all customizable pools in last sample |
| Meteora DAMM v1 | whole program `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` (already quiet) | 0.17–0.28 | — |
| PumpSwap (pump.fun migrations) | `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` (pump.fun migration authority) | ~0.005 | live CreatePool(+InitBoost) |

Rejected (too busy): DAMM v2 `FhVo3mqL8PW5pH5U2CN4XE33DokiyZnUwuGpH2hmHLuM` 2.2 MB/min;
`TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM` 0.2 MB/min; event authorities
(pumpswap `GS4CU59F…`, damm_v2 `3rmHSu74…`, dlmm `D1ZN9Wj1…`), PumpSwap global config `ADyA8hde…`,
DAMM v2 pool authority `HLnpSz9h…` — all touched by every swap.

## PumpSwap manual CreatePool (the majority of big pumpswap pools: 50–580 SOL)
No creation-only account exists (only busy global config/event authority). Solution:
`programSubscribe pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` with
`dataSlice {offset:0,length:0}` and **two** subs `dataSize 287` and `dataSize 301`
(pools are created at 287 bytes and ExtendAccount'ed to 301, same tx or later).
~2.0 MB/min (301) + ~0.45 MB/min (287). Pool writes happen on every swap, so:
1. at startup snapshot known pools via `getProgramAccounts` (same filters, zero slice) from the
   free public RPC — ~760k pools, ~170 MB download, ~7 s; store 8-byte pubkey prefixes in a sorted
   u64 array (~6 MB);
2. unseen pubkey -> `getSignaturesForAddress(pool, limit=1000, commitment=confirmed)` (retry if
   empty); if <1000 sigs, the oldest successful one is the creation tx -> parse it.
   NOTE: a limit of 20 is NOT enough, sniper bots put 20+ swaps on a new pool within seconds.

## Dropped
Meteora DLMM: creation tx only has the preset_parameter as a non-busy account and there are 392
preset accounts (getProgramAccounts dataSize=192); full program feed is ~9–13 MB/min. Disabled by
default (2 DLMM creations missed per ~8 min in the earlier sample, mostly tiny).

## Other gotcha found
Some txs are now **version 1**: getTransaction must use `maxSupportedTransactionVersion: 1`
(with 0 it fails with -32015 and the pool is lost).
