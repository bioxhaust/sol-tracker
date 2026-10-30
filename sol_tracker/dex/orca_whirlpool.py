"""Orca Whirlpool (CLMM). Accounts from orca-so/whirlpools programs/whirlpool/src/
instructions/{initialize_pool.rs, v2/initialize_pool.rs}. Liquidity lives in position
NFTs, added in separate txs -> lock_model=position."""
from .base import DexParser, Layout


class OrcaWhirlpool(DexParser):
    name = "orca_whirlpool"
    program_id = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    watch_accounts = {"whirlpools_config": "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ"}
    lock_model = "position"
    layouts = [
        Layout("initialize_pool", log_name="InitializePool",
               accounts=dict(mint_a=1, mint_b=2, creator=3, pool=4, vault_a=5, vault_b=6)),
        Layout("initialize_pool_v2", log_name="InitializePoolV2",
               accounts=dict(mint_a=1, mint_b=2, creator=5, pool=6, vault_a=7, vault_b=8)),
    ]
