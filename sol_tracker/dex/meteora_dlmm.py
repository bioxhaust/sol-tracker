"""Meteora DLMM. Accounts from MeteoraAg/dlmm-sdk idls/dlmm.json. lock_model=position."""
from .base import DexParser, Layout

_STD = dict(pool=0, mint_a=2, mint_b=3, vault_a=4, vault_b=5, creator=8)


class MeteoraDlmm(DexParser):
    name = "meteora_dlmm"
    program_id = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
    lock_model = "position"
    layouts = [
        Layout("initialize_lb_pair", log_name="InitializeLbPair", accounts=_STD),
        Layout("initialize_lb_pair2", log_name="InitializeLbPair2", accounts=_STD),
        Layout("initialize_customizable_permissionless_lb_pair",
               log_name="InitializeCustomizablePermissionlessLbPair", accounts=_STD),
        Layout("initialize_customizable_permissionless_lb_pair2",
               log_name="InitializeCustomizablePermissionlessLbPair2", accounts=_STD),
        Layout("initialize_permission_lb_pair", log_name="InitializePermissionLbPair",
               accounts=dict(pool=1, mint_a=3, mint_b=4, vault_a=5, vault_b=6, creator=8)),
    ]
