"""Orchestration: WebSocket logsSubscribe -> cheap log prefilter -> getTransaction ->
DEX parser -> enrichment (price, symbol, lock) -> threshold filter -> structured output."""
from __future__ import annotations
import asyncio, json, logging, time
from datetime import datetime, timezone
import websockets

from .config import Config, Endpoint, redact
from .dex import ALL
from .lock import check_lp, check_position
from .logger import PoolSink
from .logparse import program_instructions
from .metadata import token_info
from .models import PoolInit
from .newpools import PoolSet, creation_signature
from .price import PriceFeed, QUOTES, liquidity_usd
from .rpc import Rpc

log = logging.getLogger("sol_tracker")


class Tracker:
    def __init__(self, cfg: Config, sink: PoolSink | None = None):
        self.cfg = cfg
        self.dexes = {n: ALL[n] for n in cfg.enabled_dexes}
        self.endpoints = cfg.endpoints or [Endpoint("default", cfg.rpc_http, cfg.rpc_ws)]
        self.rpc = Rpc(self.endpoints, cfg.max_concurrent_fetches, primary_retry_s=cfg.primary_retry_s)
        self.ws_active = 0
        self.ws_connected = False
        self.prices = PriceFeed(cfg.price_ttl_s)
        self.sink = sink or PoolSink(cfg.output_file)
        self.seen: set[str] = set()
        self.stats = {"notifications": 0, "init_candidates": 0, "pools": 0, "emitted": 0,
                      "ws_bytes": 0, "new_pool_accounts": 0}
        self.pool_sets: dict[str, PoolSet] = {}
        self.sub_bytes: dict[str, int] = {}

    def subscription_plan(self):
        """[(label, dex, method, params)] for one WS session."""
        plan = []
        for d in self.dexes.values():
            for label, acct in d.subscriptions():
                plan.append((label, d, "logsSubscribe",
                             [{"mentions": [acct]}, {"commitment": self.cfg.commitment}]))
            ps = self.pool_sets.get(d.name)
            if d.pool_account_sizes and self.cfg.pool_account_streams and ps and ps.ready:
                for size in d.pool_account_sizes:
                    plan.append((f"{d.name}:pool_accounts_{size}", d, "programSubscribe", [d.program_id, {
                        "encoding": "base64", "commitment": self.cfg.commitment,
                        "dataSlice": {"offset": 0, "length": 0},
                        "filters": [{"dataSize": size}]}]))
        return plan

    async def prepare(self):
        if not self.cfg.pool_account_streams:
            return
        for d in self.dexes.values():
            if d.pool_account_sizes and d.name not in self.pool_sets:
                ps = PoolSet()
                urls = [self.cfg.snapshot_rpc] + [e.http for e in self.endpoints]
                if await ps.snapshot([u for u in urls if u], d.program_id, d.pool_account_sizes):
                    self.pool_sets[d.name] = ps
                else:
                    log.warning("%s: no pool snapshot -> pool-account stream disabled", d.name)

    # ---------- live ----------
    async def run(self, duration: float | None = None):
        log.info("providers=%s dexes=%s min_liq=$%.0f",
                 [f"{e.name}:{redact(e.http)}" for e in self.endpoints], list(self.dexes),
                 self.cfg.min_liquidity_usd)
        await self.prepare()
        reporter = asyncio.create_task(self._report_loop())
        stop = time.monotonic() + duration if duration else None
        backoff, fails = 1, 0
        while stop is None or time.monotonic() < stop:
            ep = self.endpoints[self.ws_active]
            remaining = (stop - time.monotonic()) if stop else None
            # on fallback: cap session length so we periodically try the primary again
            cap = self.cfg.primary_retry_s if self.ws_active else None
            opts = [x for x in (remaining, cap) if x is not None]
            log.info("websocket provider=%s url=%s", ep.name, redact(ep.ws))
            try:
                await asyncio.wait_for(self._session(ep), timeout=min(opts) if opts else None)
            except asyncio.TimeoutError:
                if stop is not None and time.monotonic() >= stop - 0.05:
                    break
                log.info("fallback window over; retrying primary websocket %s", self.endpoints[0].name)
                self.ws_active, fails, backoff = 0, 0, 1
                continue
            except Exception as e:  # noqa: BLE001  (WS drops happen)
                fails = 1 if self.ws_connected else fails + 1
                if self.ws_connected:
                    backoff = 1
                nxt = self.next_ws_index(fails)
                if nxt != self.ws_active:
                    log.warning("websocket %s failed %dx (%s); switching to %s", ep.name, fails,
                                type(e).__name__, self.endpoints[nxt].name)
                    self.ws_active, fails, backoff = nxt, 0, 1
                    continue
                log.warning("websocket %s dropped (%s); reconnecting in %ss", ep.name, type(e).__name__, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        reporter.cancel()
        await asyncio.sleep(0)  # let in-flight tasks be cancelled cleanly
        log.info("stats %s", self.stats)

    async def _report_loop(self):
        t0 = time.monotonic()
        while True:
            await asyncio.sleep(self.cfg.stats_interval_s)
            log.info("%s | stats %s", self.bandwidth_report(time.monotonic() - t0), self.stats)

    def next_ws_index(self, fails: int) -> int:
        if len(self.endpoints) > 1 and fails >= self.cfg.ws_fail_switch:
            return (self.ws_active + 1) % len(self.endpoints)
        return self.ws_active

    async def _session(self, ep: Endpoint | None = None):
        ep = ep or self.endpoints[self.ws_active]
        self.ws_connected = False
        async with websockets.connect(ep.ws, max_size=None, ping_interval=20) as ws:
            plan = self.subscription_plan()
            for i, (_, _, method, params) in enumerate(plan):
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}))
            subs = {}
            async for raw in ws:
                msg = json.loads(raw)
                if "id" in msg:
                    if "result" not in msg:
                        log.warning("subscribe %s failed: %s", plan[msg["id"]][0], msg.get("error"))
                        continue
                    subs[msg["result"]] = plan[msg["id"]]
                    if len(subs) == len(plan):
                        self.ws_connected = True
                        log.info("subscribed %d streams via %s: %s", len(subs), ep.name,
                                 ", ".join(p[0] for p in plan))
                    continue
                if msg.get("method") not in ("logsNotification", "programNotification"):
                    continue
                self.stats["notifications"] += 1
                self.stats["ws_bytes"] += len(raw)
                k = f"notif_{ep.name}"
                self.stats[k] = self.stats.get(k, 0) + 1
                sub = subs.get(msg["params"]["subscription"])
                if not sub:
                    continue
                label, dex, method, _ = sub
                self.sub_bytes[label] = self.sub_bytes.get(label, 0) + len(raw)
                v = msg["params"]["result"]["value"]
                if method == "programSubscribe":
                    self._on_pool_account(dex, v["pubkey"])
                    continue
                if v.get("err"):
                    continue
                self._on_logs(dex, v["signature"], v["logs"])

    def _on_logs(self, dex, sig, logs):
        names = program_instructions(logs, dex.program_id)
        if dex.wants(names) and sig not in self.seen:
            self.seen.add(sig)
            self.stats["init_candidates"] += 1
            log.info("init candidate %s %s %s", dex.name, names, sig)
            asyncio.create_task(self._guard(self.handle_signature(sig, names)))

    def _on_pool_account(self, dex, pubkey):
        ps = self.pool_sets.get(dex.name)
        if ps is None or pubkey in ps:
            return
        ps.add(pubkey)
        self.stats["new_pool_accounts"] += 1
        asyncio.create_task(self._guard(self._new_pool_account(dex, pubkey)))

    async def _new_pool_account(self, dex, pubkey):
        sig = await creation_signature(self.rpc, pubkey)
        if not sig:
            log.info("pool account %s %s: not young / no signature, skipped", dex.name, pubkey)
            return
        if sig in self.seen:
            return
        self.seen.add(sig)
        self.stats["init_candidates"] += 1
        log.info("init candidate %s (new pool account %s) %s", dex.name, pubkey, sig)
        await self.handle_signature(sig)

    def bandwidth_report(self, elapsed_s: float) -> str:
        mins = max(elapsed_s / 60, 1e-9)
        parts = [f"{k}={v / 1e6 / mins:.3f}" for k, v in sorted(self.sub_bytes.items(), key=lambda x: -x[1])]
        return f"ws MB/min total={self.stats['ws_bytes'] / 1e6 / mins:.3f} " + " ".join(parts)

    async def _guard(self, coro):
        try:
            await coro
        except Exception:  # noqa: BLE001
            log.exception("handler failed")

    # ---------- per tx ----------
    async def handle_signature(self, sig: str, names: list[str] | None = None) -> list[dict]:
        tx = await self.rpc.get_transaction(sig, self.cfg.commitment)
        if not tx:
            log.warning("tx %s not found", sig)
            return []
        logs = (tx.get("meta") or {}).get("logMessages") or []
        out = []
        for dex in self.dexes.values():
            for pool in dex.parse(tx, sig):
                self.stats["pools"] += 1
                ix_names = program_instructions(logs, dex.program_id)
                rec = await self.enrich(pool, ix_names, tx=tx)
                out.append(rec)
                self._maybe_emit(rec)
                if (self.cfg.recheck_delay_s and not rec["passed"]) or \
                   (self.cfg.recheck_delay_s and rec["lock"]["status"] not in ("burned", "locked")):
                    asyncio.create_task(self._guard(self._recheck(pool, ix_names, tx)))
        return out

    async def enrich(self, p: PoolInit, ix_names: list[str], event: str = "new_pool", tx: dict | None = None) -> dict:
        token = p.mint_b if p.mint_a in QUOTES else p.mint_a
        quote = p.mint_a if token == p.mint_b else p.mint_b
        pa, pb = await self.prices.unit_price(p.mint_a), await self.prices.unit_price(p.mint_b)
        liq = liquidity_usd(p.mint_a, p.reserve_a, p.mint_b, p.reserve_b, pa, pb)
        meta, lock = await asyncio.gather(
            token_info(self.rpc, token),
            check_lp(self.rpc, p.lp_mint, self.dexes[p.dex].program_id, tx)
            if p.lock_model == "lp" and p.lp_mint else asyncio.sleep(0, check_position(p.dex, ix_names)))
        ts = p.block_time or int(time.time())
        rec = {
            "event": event,
            "time": datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z"),
            "detected_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "dex": p.dex, "instruction": p.instruction,
            "token_mint": token, "symbol": meta.get("symbol"), "name": meta.get("name"),
            "quote_mint": quote, "quote": QUOTES.get(quote),
            "liquidity_usd": round(liq, 2) if liq is not None else None,
            "reserves": {p.mint_a: p.reserve_a, p.mint_b: p.reserve_b},
            "lock": lock.to_dict(),
            "mint_authority": meta.get("mint_authority"),
            "freeze_authority": meta.get("freeze_authority"),
            "pool": p.pool, "lp_mint": p.lp_mint, "vaults": [p.vault_a, p.vault_b],
            "creator": p.creator, "slot": p.slot, "tx": p.signature,
        }
        rec["passed"] = liq is not None and liq >= self.cfg.min_liquidity_usd
        return rec

    def _maybe_emit(self, rec):
        if rec["passed"] or self.cfg.log_all:
            self.stats["emitted"] += 1
            self.sink.emit(rec)
        else:
            log.info("below threshold: %s %s liq=%s lock=%s", rec["dex"], rec["symbol"] or rec["token_mint"][:8],
                     rec["liquidity_usd"], rec["lock"]["status"])

    async def _recheck(self, p: PoolInit, ix_names, tx=None):
        """CLMM/DLMM pools are often funded right after init; LP burns/locks also follow
        a few seconds later. Re-read vault balances + lock once."""
        await asyncio.sleep(self.cfg.recheck_delay_s)
        if p.vault_a and p.vault_b and p.dex != "meteora_damm_v1":
            for attr, vault in (("reserve_a", p.vault_a), ("reserve_b", p.vault_b)):
                try:
                    r = await self.rpc.call("getTokenAccountBalance", [vault])
                    setattr(p, attr, float(r["value"]["uiAmountString"]))
                except Exception:  # noqa: BLE001
                    pass
        rec = await self.enrich(p, ix_names, event="recheck", tx=tx)
        self._maybe_emit(rec)

    async def close(self):
        await self.rpc.close()
