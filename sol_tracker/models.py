from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class PoolInit:
    dex: str
    instruction: str
    pool: str
    mint_a: str
    mint_b: str
    vault_a: Optional[str] = None
    vault_b: Optional[str] = None
    lp_mint: Optional[str] = None
    creator: Optional[str] = None
    position: Optional[str] = None
    reserve_a: Optional[float] = None   # UI amounts
    reserve_b: Optional[float] = None
    lock_model: str = "lp"              # "lp" (fungible LP token) | "position" (CLMM/DLMM/NFT)
    signature: str = ""
    slot: int = 0
    block_time: Optional[int] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
