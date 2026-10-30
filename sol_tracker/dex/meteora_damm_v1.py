"""Meteora DAMM v1 (dynamic AMM, LP token). Accounts from damm-v1-sdk ts-client idl.json.
Token vaults are shared Meteora dynamic vaults, so reserves are taken from the
creator's deposit (pre - post balance of payer_token_a/b) instead of vault balances."""
from .base import DexParser, Layout

_P = dict(pool=0, lp_mint=1, mint_a=2, mint_b=3, payer_a=12, payer_b=13, creator=17)
_C = dict(pool=0, lp_mint=2, mint_a=3, mint_b=4, payer_a=13, payer_b=14, creator=18)


class MeteoraDammV1(DexParser):
    name = "meteora_damm_v1"
    program_id = "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB"
    layouts = [
        Layout("initialize_permissionless_pool", log_name="InitializePermissionlessPool", accounts=_P),
        Layout("initialize_permissionless_pool_with_fee_tier",
               log_name="InitializePermissionlessPoolWithFeeTier", accounts=_P),
        Layout("initialize_customizable_permissionless_constant_product_pool",
               log_name="InitializeCustomizablePermissionlessConstantProductPool", accounts=_P),
        Layout("initialize_permissionless_constant_product_pool_with_config",
               log_name="InitializePermissionlessConstantProductPoolWithConfig", accounts=_C),
        Layout("initialize_permissionless_constant_product_pool_with_config2",
               log_name="InitializePermissionlessConstantProductPoolWithConfig2", accounts=_C),
    ]

    @staticmethod
    def _delta(tx, account):
        keys = DexParser.account_keys(tx)
        meta = tx.get("meta") or {}
        def bal(lst):
            for b in lst or []:
                if keys[b["accountIndex"]] == account:
                    return float(b["uiTokenAmount"]["uiAmountString"] or 0)
            return None
        pre, post = bal(meta.get("preTokenBalances")), bal(meta.get("postTokenBalances"))
        if pre is None and post is None:
            return None
        return max((pre or 0) - (post or 0), 0.0)

    def fill_reserves(self, tx, p, acc):
        p.reserve_a = self._delta(tx, acc.get("payer_a"))
        p.reserve_b = self._delta(tx, acc.get("payer_b"))
        p.extra["reserves_from"] = "creator_deposit"
