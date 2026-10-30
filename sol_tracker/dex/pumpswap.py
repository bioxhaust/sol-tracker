"""PumpSwap (pump.fun AMM). Accounts from pump-fun/pump-public-docs idl/pump_amm.json.
Most pump.fun graduations land here."""
from .base import DexParser, Layout


class PumpSwap(DexParser):
    name = "pumpswap"
    program_id = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    watch_accounts = {"pump_migration": "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"}
    # Pool accounts: created at 287 bytes, ExtendAccount'ed to 301 (same tx or later).
    # Streams pool writes for the manual (non-migration) CreatePool path.
    pool_account_sizes = (287, 301)
    layouts = [Layout("create_pool", log_name="CreatePool",
                      accounts=dict(pool=0, creator=2, mint_a=3, mint_b=4, lp_mint=5,
                                    vault_a=9, vault_b=10))]
