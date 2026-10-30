# sol-tracker — stage 1: new-pool listener (Solana)

Real-time detection of new liquidity pools on Raydium AMM v4, Raydium CPMM, Orca Whirlpool,
Meteora DLMM, Meteora DAMM v1/v2 and PumpSwap, with USD liquidity filter and LP lock check.
No auto-buy, no LLM (later stages).

## Run
    python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    python -m pytest -q                                  # parser/unit tests (offline, real tx fixtures)
    python -m sol_tracker live                           # run forever, emit pools >= threshold
    python -m sol_tracker live --minutes 5 --all         # also emit pools below threshold
    python -m sol_tracker replay <SIG> [<SIG>...] --all  # re-process historical creation txs
    python scripts/find_creation_sig.py <POOL_ADDR>      # find a pool's creation signature
    HELIUS_API_KEY=... python -m sol_tracker live        # use Helius (key only from env)

Config: `config.toml` (threshold `min_liquidity_usd`, enabled DEXes, endpoints, recheck delay).
Env overrides: `HELIUS_API_KEY`, `RPC_HTTP`, `RPC_WS`, `MIN_LIQUIDITY_USD`, `SOL_TRACKER_CONFIG`.
Output: JSON lines on stdout + `logs/pools.jsonl`; diagnostics on stderr.

## Pipeline
logsSubscribe(mentions=program) per DEX → invoke-stack-aware log parse (only the DEX's own
`Instruction: X` lines) → getTransaction(jsonParsed) → decode instruction by discriminator
(Anchor sha256("global:name")[:8]; AMM v4 tag 1) → account roles by IDL index → reserves
from vault postTokenBalances → USD (SOL via CoinGecko/Binance, USDC/USDT=$1) → lock check →
filter → emit. Pools that fail the filter or aren't burned/locked are re-checked once after
`recheck_delay_s` (CLMM/DLMM liquidity and LP burns usually come in follow-up txs).
