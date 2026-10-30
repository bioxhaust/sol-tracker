"""Raydium AMM v4 (OpenBook-based). Non-Anchor: initialize2 = instruction tag 1.
Account order from raydium-io/raydium-amm program/src/instruction.rs (Initialize2)."""
from .base import DexParser, Layout


class RaydiumAmmV4(DexParser):
    name = "raydium_amm_v4"
    program_id = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    watch_accounts = {"create_fee": "7YttLkHDoNj9wyDur5pM1ejNaAvT9X4eqaYcHQqtj2G5"}
    layouts = [Layout("initialize2", log_name="initialize2", discriminator=bytes([1]),
                      accounts=dict(pool=4, lp_mint=7, mint_a=8, mint_b=9,
                                    vault_a=10, vault_b=11, creator=17))]
