"""Shared config. Values: defaults < config.toml < environment variables. No secrets in code."""
from __future__ import annotations
import os, re, tomllib
from dataclasses import dataclass, field
from pathlib import Path

PUBLIC_HTTP = "https://api.mainnet-beta.solana.com"
PUBLIC_WS = "wss://api.mainnet-beta.solana.com"


@dataclass
class Config:
    rpc_http: str = PUBLIC_HTTP
    rpc_ws: str = PUBLIC_WS
    commitment: str = "confirmed"
    min_liquidity_usd: float = 10_000.0
    enabled_dexes: list[str] = field(default_factory=lambda: [
        "raydium_amm_v4", "raydium_cpmm", "orca_whirlpool",
        "meteora_damm_v1", "meteora_damm_v2", "pumpswap"])  # meteora_dlmm: see config.toml
    log_all: bool = False            # also emit pools below threshold (passed=false)
    recheck_delay_s: float = 90.0    # re-evaluate liquidity/lock once after N s (0 = off)
    max_concurrent_fetches: int = 4
    price_ttl_s: float = 60.0
    output_file: str = "logs/pools.jsonl"
    log_level: str = "INFO"
    # failover: ordered list of Endpoint (primary first). Empty -> single rpc_http/rpc_ws.
    endpoints: list = field(default_factory=list)
    primary_retry_s: float = 300.0   # while on fallback, try primary again after N s
    ws_fail_switch: int = 2
    # PumpSwap manual CreatePool has no low-traffic account; stream pool accounts instead
    # (~1.8 MB/min). Set false to rely on pump.fun-migration mentions only (~0.03 MB/min).
    pool_account_streams: bool = True
    snapshot_rpc: str = PUBLIC_HTTP   # free source for the one-off getProgramAccounts snapshot
    stats_interval_s: float = 600.0          # consecutive WS failures before switching provider


@dataclass
class Endpoint:
    name: str
    http: str
    ws: str


def _load_dotenv(path: str = ".env"):
    """Minimal .env loader; never overrides real environment variables."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load(path: str | None = None) -> Config:
    _load_dotenv(os.environ.get("SOL_TRACKER_DOTENV", ".env"))
    cfg = Config()
    p = Path(path or os.environ.get("SOL_TRACKER_CONFIG", "config.toml"))
    if p.exists():
        for k, v in tomllib.loads(p.read_text()).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
    if os.environ.get("RPC_HTTP"):
        cfg.rpc_http = os.environ["RPC_HTTP"]
    if os.environ.get("RPC_WS"):
        cfg.rpc_ws = os.environ["RPC_WS"]
    key = os.environ.get("HELIUS_API_KEY")
    if key:  # Helius overrides public endpoints; key only ever read from env
        cfg.rpc_http = f"https://mainnet.helius-rpc.com/?api-key={key}"
        cfg.rpc_ws = f"wss://mainnet.helius-rpc.com/?api-key={key}"
    eps = []
    if key:
        eps.append(Endpoint("helius", cfg.rpc_http, cfg.rpc_ws))
    qn = os.environ.get("QUICKNODE_RPC_URL", "").strip()
    if qn:
        eps.append(Endpoint("quicknode", qn, os.environ.get("QUICKNODE_WS_URL") or http_to_ws(qn)))
    force = os.environ.get("RPC_PROVIDER", "").strip().lower()
    if force:
        eps = [e for e in eps if e.name == force]
        if not eps:
            raise SystemExit(f"RPC_PROVIDER={force} not configured")
    if not eps:
        eps = [Endpoint("default", cfg.rpc_http, cfg.rpc_ws)]
    cfg.endpoints = eps
    cfg.rpc_http, cfg.rpc_ws = eps[0].http, eps[0].ws
    if os.environ.get("MIN_LIQUIDITY_USD"):
        cfg.min_liquidity_usd = float(os.environ["MIN_LIQUIDITY_USD"])
    return cfg


def http_to_ws(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):]
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):]
    return url


def redact(url: str) -> str:
    """scheme://host/*** — drops path tokens and query keys entirely."""
    m = re.match(r"^([a-z]+://)?([^/?#]+)(.*)$", url or "")
    if not m:
        return "***"
    scheme, host, rest = m.group(1) or "", m.group(2), m.group(3)
    host = re.sub(r"^[^.]+(?=\.[^.]+\.quiknode\.pro$)", lambda h: h.group(0)[:4] + "***", host)
    return scheme + host + ("/***" if rest.strip("/") else "")
