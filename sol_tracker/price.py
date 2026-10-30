"""USD pricing of reserves. Only 'quote' assets with public prices are valued
(SOL/WSOL via CoinGecko -> Binance fallback, USDC/USDT = $1). A pool's USD liquidity
is the known side x 2 (constant-product assumption) or the sum if both sides are known."""
from __future__ import annotations
import logging, time
import httpx

log = logging.getLogger("sol_tracker.price")
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
QUOTES = {WSOL: "SOL", USDC: "USDC", USDT: "USDT"}


class PriceFeed:
    def __init__(self, ttl: float = 60):
        self.ttl, self._sol, self._ts = ttl, None, 0.0
        self.http = httpx.AsyncClient(timeout=10)

    async def sol_usd(self) -> float | None:
        if self._sol and time.time() - self._ts < self.ttl:
            return self._sol
        for fetch in (self._coingecko, self._binance):
            try:
                self._sol, self._ts = await fetch(), time.time()
                return self._sol
            except Exception as e:  # noqa: BLE001
                log.warning("price source failed: %s", e)
        return self._sol  # stale value better than none

    async def _coingecko(self):
        r = await self.http.get("https://api.coingecko.com/api/v3/simple/price",
                                params={"ids": "solana", "vs_currencies": "usd"})
        return float(r.json()["solana"]["usd"])

    async def _binance(self):
        r = await self.http.get("https://api.binance.com/api/v3/ticker/price",
                                params={"symbol": "SOLUSDT"})
        return float(r.json()["price"])

    async def unit_price(self, mint: str) -> float | None:
        if mint == WSOL:
            return await self.sol_usd()
        if mint in (USDC, USDT):
            return 1.0
        return None


def liquidity_usd(mint_a, res_a, mint_b, res_b, price_a, price_b) -> float | None:
    va = res_a * price_a if (res_a is not None and price_a is not None) else None
    vb = res_b * price_b if (res_b is not None and price_b is not None) else None
    if va is not None and vb is not None:
        return va + vb
    if va is not None:
        return 2 * va
    if vb is not None:
        return 2 * vb
    return None
