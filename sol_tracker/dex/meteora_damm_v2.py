"""Meteora DAMM v2 (cp-amm). Accounts from MeteoraAg/damm-v2-sdk src/idl/cp_amm.json.
Liquidity is an NFT position (can be permanently locked in the same tx)."""
from .base import DexParser, Layout


def _l(name, log, off):
    return Layout(name, log_name=log, accounts=dict(
        creator=0, position_nft_mint=1, pool=5 + off, position=6 + off,
        mint_a=7 + off, mint_b=8 + off, vault_a=9 + off, vault_b=10 + off))


class MeteoraDammV2(DexParser):
    name = "meteora_damm_v2"
    program_id = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
    watch_accounts = {"dynamic_config": "A8gMrEPJkacWkcb3DGwtJwTe16HktSEfvwtuDh2MCtck",
                      "dbc_migration": "8dnhmayAP3LA957YgSdP3Nw48ZJM6C4248qfFeyfnxTP"}
    lock_model = "position"
    layouts = [
        _l("initialize_customizable_pool", "InitializeCustomizablePool", 0),
        _l("initialize_pool", "InitializePool", 1),
        _l("initialize_pool_with_dynamic_config", "InitializePoolWithDynamicConfig", 2),
    ]
