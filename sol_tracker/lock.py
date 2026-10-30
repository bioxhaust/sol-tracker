"""LP lock analysis.

lock_model == "lp": read the LP mint supply + largest holders, then classify each holder:
  burned  - token account owned by the incinerator / system null address, or LP supply==0
            after a burn (Raydium-style burn reduces supply, see note)
  locked  - holder wallet is a PDA owned by a known locker program
            (Streamflow, Jupiter Lock, Raydium LP-lock) or by the DEX program itself
            (e.g. Meteora DAMM v1 lock escrows)
  unlocked- anything else (EOA / creator)
lock_model == "position" (Orca/DLMM/DAMM v2): liquidity is in NFT positions; creator-owned
  positions are reported unlocked, DAMM v2 positions locked in the init tx as locked.
"""
from __future__ import annotations
from dataclasses import dataclass, field

BURN_OWNERS = {
    "1nc1nerator11111111111111111111111111111111": "incinerator",
    "11111111111111111111111111111111": "null",
}
LOCKER_PROGRAMS = {
    "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m": "streamflow",
    "LocpQgucEQHbqNABEYvBvwoxCPsSbG91A1QaQhQQqjn": "jupiter_lock",
    "LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE": "raydium_lp_lock",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "meteora_damm_v1_escrow",
}
DAMM_V2_LOCK_IX = {"PermanentLockPosition", "LockPosition", "LockInnerPosition"}


@dataclass
class LockResult:
    status: str                      # burned | locked | unlocked | unknown
    burned_pct: float = 0.0
    locked_pct: float = 0.0
    unlocked_pct: float = 0.0
    lockers: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self):
        return {"status": self.status, "burned_pct": round(self.burned_pct, 2),
                "locked_pct": round(self.locked_pct, 2),
                "unlocked_pct": round(self.unlocked_pct, 2),
                "lockers": self.lockers, "note": self.note}


def classify(holders: list[tuple[float, str, str | None]], supply: float,
             extra_locker_programs: dict[str, str] | None = None) -> LockResult:
    """holders: (amount, token_account_owner, owner_program). Pure function (unit-tested)."""
    lockers = dict(LOCKER_PROGRAMS, **(extra_locker_programs or {}))
    if supply <= 0:
        return LockResult("burned", 100.0, note="LP supply is 0 (all burned)")
    b = l = u = 0.0
    names = set()
    for amt, owner, owner_prog in holders:
        pct = 100.0 * amt / supply
        if owner in BURN_OWNERS:
            b += pct
        elif owner_prog in lockers:
            l += pct
            names.add(lockers[owner_prog])
        else:
            u += pct
    covered = b + l + u
    note = "" if covered > 99 else f"top holders cover {covered:.1f}% of supply"
    if b >= 95:
        st = "burned"
    elif b + l >= 95:
        st = "locked"
    elif u > 5 or covered > 99:
        st = "unlocked"
    else:
        st = "unknown"
    return LockResult(st, b, l, u, sorted(names), note)


def tx_lp_holders(tx: dict | None, lp_mint: str) -> list[tuple[float, str]]:
    """LP holders visible in the init tx's postTokenBalances (owner field included)."""
    out = []
    for b in ((tx or {}).get("meta") or {}).get("postTokenBalances") or []:
        if b.get("mint") == lp_mint and b.get("owner"):
            out.append((float(b["uiTokenAmount"]["uiAmountString"] or 0), b["owner"]))
    return out


async def check_lp(rpc, lp_mint: str, dex_program: str | None = None,
                   tx: dict | None = None) -> LockResult:
    source = "largest_accounts"
    try:
        sup = await rpc.call("getTokenSupply", [lp_mint])
        supply = float(sup["value"]["uiAmountString"])
        if supply <= 0:
            return classify([], 0)
        holders, owners = [], []
        try:
            # public RPC rate-limits this method hard -> fail fast, fall back to tx balances
            largest = (await rpc.call("getTokenLargestAccounts", [lp_mint], retries=3))["value"]
            accs = await rpc.get_multiple_accounts([a["address"] for a in largest])
            for a, info in zip(largest, accs):
                owner = info["data"]["parsed"]["info"]["owner"] if info else None
                holders.append([float(a["uiAmountString"] or 0), owner, None])
                owners.append(owner)
        except Exception:  # noqa: BLE001
            source = "init_tx_balances"
            for amt, owner in tx_lp_holders(tx, lp_mint):
                holders.append([amt, owner, None])
                owners.append(owner)
            if not holders:
                raise
        uniq = [o for o in dict.fromkeys(owners) if o]
        progs = dict(zip(uniq, [x["owner"] if x else None for x in
                                await rpc.get_multiple_accounts(uniq, "base64")]))
        for h in holders:
            h[2] = progs.get(h[1])
        extra = {dex_program: "dex_program_pda"} if dex_program else None
        r = classify([tuple(h) for h in holders], supply, extra)
        r.note = (r.note + "; " if r.note else "") + f"holders from {source}"
        return r
    except Exception as e:  # noqa: BLE001
        return LockResult("unknown", note=f"lp check failed: {e}")


def check_position(dex: str, logs_ix: list[str]) -> LockResult:
    if dex == "meteora_damm_v2" and DAMM_V2_LOCK_IX & set(logs_ix):
        return LockResult("locked", locked_pct=100.0, lockers=["damm_v2_position_lock"],
                          note="creator position locked in init tx")
    return LockResult("unlocked", unlocked_pct=100.0,
                      note="CLMM/DLMM liquidity held as creator-owned positions; not locked at init")
