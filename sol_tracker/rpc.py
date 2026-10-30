"""Minimal async JSON-RPC client with retry/backoff (public RPC rate-limits hard)."""
from __future__ import annotations
import asyncio, itertools, logging, time
import httpx
from .config import redact

log = logging.getLogger("sol_tracker.rpc")


class RpcError(Exception):
    pass


class Rpc:
    def __init__(self, url, concurrency: int = 4, retries: int = 10, primary_retry_s: float = 300.0):
        # url: str, or list of (name, url) / Endpoint in priority order (primary first)
        if isinstance(url, str):
            url = [("default", url)]
        self.providers = [(e.name, e.http) if hasattr(e, "http") else (e[0], e[1]) for e in url]
        self.active, self.retries, self.primary_retry_s = 0, retries, primary_retry_s
        self._since = time.monotonic()
        self.http = httpx.AsyncClient(timeout=20)
        self.sem = asyncio.Semaphore(concurrency)
        self.ids = itertools.count(1)

    @property
    def url(self):
        return self.providers[self.active][1]

    @property
    def provider(self):
        return self.providers[self.active][0]

    def _switch(self, to: int, why):
        if to == self.active or len(self.providers) < 2:
            return
        log.warning("HTTP RPC provider %s -> %s (%s) url=%s", self.provider, self.providers[to][0],
                    why, redact(self.providers[to][1]))
        self.active, self._since = to, time.monotonic()

    def _maybe_return_primary(self):
        if self.active and time.monotonic() - self._since >= self.primary_retry_s:
            self._switch(0, "retrying primary")

    async def call(self, method: str, params: list, retries: int | None = None):
        delay = 0.5
        retries = retries or self.retries
        for attempt in range(retries):
            self._maybe_return_primary()
            idx = self.active
            async with self.sem:
                try:
                    r = await self.http.post(self.providers[idx][1], json={
                        "jsonrpc": "2.0", "id": next(self.ids), "method": method, "params": params})
                    if r.status_code == 429 or r.status_code >= 500:
                        raise RpcError(f"HTTP {r.status_code}")
                    body = r.json()
                    if "error" in body:
                        raise RpcError(body["error"])
                    return body["result"]
                except (httpx.HTTPError, RpcError) as e:
                    if attempt == retries - 1:
                        raise
                    why = type(e).__name__ if isinstance(e, httpx.HTTPError) else str(e)
                    log.debug("%s retry %d on %s: %s", method, attempt + 1, self.providers[idx][0], why)
                    transport = isinstance(e, httpx.HTTPError) or str(e).startswith("HTTP ")
                    if transport and len(self.providers) > 1:
                        if idx == self.active:
                            self._switch((idx + 1) % len(self.providers), why)
                        continue  # retry immediately on the other provider
            await asyncio.sleep(delay)
            delay = min(delay * 2, 16)

    async def get_transaction(self, sig: str, commitment: str = "confirmed", tries: int = 8):
        # a freshly-notified tx may not be queryable yet -> poll until non-null
        for i in range(tries):
            tx = await self.call("getTransaction", [sig, {
                "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
                "commitment": commitment}])
            if tx:
                return tx
            await asyncio.sleep(1 + i)
        return None

    async def get_multiple_accounts(self, keys: list[str], encoding="jsonParsed"):
        out = []
        for i in range(0, len(keys), 100):
            opts = {"encoding": encoding}
            if encoding == "base64":
                opts["dataSlice"] = {"offset": 0, "length": 0}
            res = await self.call("getMultipleAccounts", [keys[i:i + 100], opts])
            out.extend(res["value"])
        return out

    async def close(self):
        await self.http.aclose()
