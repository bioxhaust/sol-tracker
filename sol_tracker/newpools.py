"""Detect brand-new pool accounts from a programSubscribe stream (zero-length data slice).

A busy AMM writes its pool accounts on every swap, so the stream shows *existing* pools
too. We keep a compact set of known pool pubkeys (8-byte prefixes, sorted array, ~6 MB for
~750k pools) built once from getProgramAccounts at startup, streamed so peak RAM stays low.
A pubkey not in the set is verified with getSignaturesForAddress: a new pool has only a
few signatures (<1000 even with sniper bots in the first seconds) and the oldest
one is its creation tx (handle_signature re-parses it, so a non-create tx yields nothing)."""
from __future__ import annotations
import array, asyncio, bisect, logging, re
import httpx
from .b58 import b58decode

log = logging.getLogger("sol_tracker.newpools")
_PUBKEY = re.compile(rb'"pubkey":"([1-9A-HJ-NP-Za-km-z]{32,44})"')
YOUNG_MAX_SIGS = 1000  # busy new pools get 20+ swaps within seconds; old ones have far more


def key64(pubkey: str) -> int:
    return int.from_bytes(b58decode(pubkey)[:8], "big")


class PoolSet:
    def __init__(self):
        self.base = array.array("Q")
        self.extra: set[int] = set()
        self.ready = False

    def __len__(self):
        return len(self.base) + len(self.extra)

    def __contains__(self, pubkey: str) -> bool:
        k = key64(pubkey)
        if k in self.extra:
            return True
        i = bisect.bisect_left(self.base, k)
        return i < len(self.base) and self.base[i] == k

    def add(self, pubkey: str):
        self.extra.add(key64(pubkey))

    def load_keys(self, pubkeys):
        self.base = array.array("Q", sorted({key64(p) for p in pubkeys}))
        self.ready = True

    async def snapshot(self, urls: list[str], program_id: str, sizes, timeout: float = 180):
        sizes = [sizes] if isinstance(sizes, int) else list(sizes)
        for url in urls:
            keys = []
            try:
                for size in sizes:
                    keys += await self._fetch(url, program_id, size, timeout)
                if len(keys) < 1000:
                    raise RuntimeError(f"only {len(keys)} accounts")
                self.load_keys(keys)
                log.info("pool snapshot: %d pools (sizes %s)", len(self.base), sizes)
                return True
            except Exception as e:  # noqa: BLE001
                log.warning("pool snapshot failed (%s); trying next source", type(e).__name__)
        return False

    @staticmethod
    async def _fetch(url, program_id, size, timeout):
        body = {"jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts", "params": [program_id, {
            "encoding": "base64", "dataSlice": {"offset": 0, "length": 0},
            "filters": [{"dataSize": size}]}]}
        keys, tail = [], b""
        async with httpx.AsyncClient(timeout=timeout) as c:
            async with c.stream("POST", url, json=body) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                async for chunk in r.aiter_bytes():
                    buf = tail + chunk
                    last = 0
                    for m in _PUBKEY.finditer(buf):
                        keys.append(m.group(1).decode())
                        last = m.end()
                    tail = buf[max(last, len(buf) - 128):]
        return keys


async def creation_signature(rpc, pubkey: str, tries: int = 5, delay: float = 1.0) -> str | None:
    """Oldest signature if the account is young (few sigs), else None (old pool).
    The stream is at `confirmed`; the signature index can lag a moment -> retry if empty."""
    sigs = []
    for i in range(tries):
        sigs = await rpc.call("getSignaturesForAddress",
                              [pubkey, {"limit": YOUNG_MAX_SIGS, "commitment": "confirmed"}])
        if sigs:
            break
        await asyncio.sleep(delay * (i + 1))
    if not sigs or len(sigs) >= YOUNG_MAX_SIGS:
        return None
    ok = [s for s in sigs if not s.get("err")]
    return ok[-1]["signature"] if ok else None
