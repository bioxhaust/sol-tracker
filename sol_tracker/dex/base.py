"""Common DEX parser: locate the pool-init instruction in a jsonParsed transaction
(top-level or CPI), map account indices from the program IDL, read vault reserves."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Optional
from ..b58 import b58decode
from ..models import PoolInit


def anchor_disc(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


@dataclass
class Layout:
    name: str                      # instruction name as in IDL (snake_case)
    accounts: dict[str, int]       # role -> account index
    log_name: str                  # name as it appears in "Program log: Instruction: X"
    discriminator: Optional[bytes] = None
    min_accounts: int = 0

    def __post_init__(self):
        if self.discriminator is None:
            self.discriminator = anchor_disc(self.name)
        self.min_accounts = max(self.accounts.values()) + 1


class DexParser:
    name: str = ""
    program_id: str = ""
    layouts: list[Layout] = []
    lock_model: str = "lp"
    # Low-traffic accounts touched (almost) only by pool-creation txs. If set, the WS
    # subscribes `mentions` of these instead of the whole (busy) program -> ~100x less data.
    watch_accounts: dict[str, str] = {}
    # If set, also programSubscribe (dataSize filter, zero-length slice) to this program's
    # pool accounts and treat never-seen pool pubkeys as new pools (see newpools.py).
    pool_account_sizes: tuple[int, ...] = ()

    def subscriptions(self) -> list[tuple[str, str]]:
        """(label, pubkey) pairs to logsSubscribe-mention."""
        if self.watch_accounts:
            return [(f"{self.name}:{k}", v) for k, v in self.watch_accounts.items()]
        return [(f"{self.name}:program", self.program_id)]

    @property
    def log_names(self) -> set[str]:
        return {l.log_name for l in self.layouts}

    def wants(self, ix_names: list[str]) -> bool:
        return any(n in self.log_names for n in ix_names)

    # ---- tx walking ----
    @staticmethod
    def account_keys(tx: dict) -> list[str]:
        return [k["pubkey"] if isinstance(k, dict) else k
                for k in tx["transaction"]["message"]["accountKeys"]]

    def iter_instructions(self, tx: dict):
        for ix in tx["transaction"]["message"]["instructions"]:
            yield ix
        for inner in (tx.get("meta") or {}).get("innerInstructions") or []:
            for ix in inner["instructions"]:
                yield ix

    def match_layout(self, data: bytes) -> Optional[Layout]:
        for l in self.layouts:
            if data[: len(l.discriminator)] == l.discriminator:
                return l
        return None

    def parse(self, tx: dict, signature: str = "") -> list[PoolInit]:
        out = []
        for ix in self.iter_instructions(tx):
            if ix.get("programId") != self.program_id or "data" not in ix:
                continue
            data = b58decode(ix["data"])
            layout = self.match_layout(data)
            if not layout or len(ix["accounts"]) < layout.min_accounts:
                continue
            acc = {role: ix["accounts"][i] for role, i in layout.accounts.items()}
            p = PoolInit(dex=self.name, instruction=layout.name, pool=acc["pool"],
                         mint_a=acc["mint_a"], mint_b=acc["mint_b"],
                         vault_a=acc.get("vault_a"), vault_b=acc.get("vault_b"),
                         lp_mint=acc.get("lp_mint"), creator=acc.get("creator"),
                         position=acc.get("position"), lock_model=self.lock_model,
                         signature=signature or tx["transaction"]["signatures"][0],
                         slot=tx.get("slot", 0), block_time=tx.get("blockTime"))
            self.fill_reserves(tx, p, acc)
            out.append(p)
        return out

    # ---- reserves ----
    @staticmethod
    def post_balance(tx: dict, account: Optional[str]) -> Optional[float]:
        if not account:
            return None
        keys = DexParser.account_keys(tx)
        for b in (tx.get("meta") or {}).get("postTokenBalances") or []:
            if keys[b["accountIndex"]] == account:
                return float(b["uiTokenAmount"]["uiAmountString"] or 0)
        return None

    def fill_reserves(self, tx: dict, p: PoolInit, acc: dict) -> None:
        p.reserve_a = self.post_balance(tx, p.vault_a)
        p.reserve_b = self.post_balance(tx, p.vault_b)
