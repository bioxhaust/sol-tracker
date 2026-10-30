from .raydium_amm_v4 import RaydiumAmmV4
from .raydium_cpmm import RaydiumCpmm
from .orca_whirlpool import OrcaWhirlpool
from .meteora_dlmm import MeteoraDlmm
from .meteora_damm_v1 import MeteoraDammV1
from .meteora_damm_v2 import MeteoraDammV2
from .pumpswap import PumpSwap

ALL = {c.name: c() for c in (RaydiumAmmV4, RaydiumCpmm, OrcaWhirlpool, MeteoraDlmm,
                             MeteoraDammV1, MeteoraDammV2, PumpSwap)}
BY_PROGRAM = {p.program_id: p for p in ALL.values()}
