"""Raydium CPMM (CP-Swap). Accounts from raydium-idl raydium_cpmm/raydium_cp_swap.json."""
from .base import DexParser, Layout


class RaydiumCpmm(DexParser):
    name = "raydium_cpmm"
    program_id = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
    watch_accounts = {"create_pool_fee": "DNXgeM9EiiaAbaWvwjHj9fQQLAX5ZsfHyvmYUNRAdNC8"}
    layouts = [
        Layout("initialize", log_name="Initialize",
               accounts=dict(creator=0, pool=3, mint_a=4, mint_b=5, lp_mint=6,
                             vault_a=10, vault_b=11)),
        Layout("initialize_with_permission", log_name="InitializeWithPermission",
               accounts=dict(creator=1, pool=4, mint_a=5, mint_b=6, lp_mint=7,
                             vault_a=11, vault_b=12)),
    ]
