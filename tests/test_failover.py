import asyncio, json
import httpx, pytest
from sol_tracker import config
from sol_tracker.config import Config, Endpoint, redact, http_to_ws
from sol_tracker.rpc import Rpc, RpcError
from sol_tracker.tracker import Tracker

QN = "https://abc-def-ghi.solana-mainnet.quiknode.pro/SECRETTOKEN123/"


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("HELIUS_API_KEY", "QUICKNODE_RPC_URL", "QUICKNODE_WS_URL", "RPC_PROVIDER", "RPC_HTTP", "RPC_WS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SOL_TRACKER_DOTENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("SOL_TRACKER_CONFIG", str(tmp_path / "none.toml"))
    return monkeypatch


def test_endpoints_order_and_ws(env):
    env.setenv("HELIUS_API_KEY", "HKEY")
    env.setenv("QUICKNODE_RPC_URL", QN)
    c = config.load()
    assert [e.name for e in c.endpoints] == ["helius", "quicknode"]
    assert c.endpoints[1].ws == "wss://abc-def-ghi.solana-mainnet.quiknode.pro/SECRETTOKEN123/"
    assert c.rpc_http.startswith("https://mainnet.helius-rpc.com")


def test_force_provider(env):
    env.setenv("HELIUS_API_KEY", "HKEY")
    env.setenv("QUICKNODE_RPC_URL", QN)
    env.setenv("RPC_PROVIDER", "quicknode")
    c = config.load()
    assert [e.name for e in c.endpoints] == ["quicknode"] and c.rpc_http == QN


def test_dotenv_loaded(env, tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"QUICKNODE_RPC_URL={QN}\n")
    env.setenv("SOL_TRACKER_DOTENV", str(f))
    assert config.load().endpoints[0].name == "quicknode"


def test_redact_hides_secrets():
    for u in (QN, http_to_ws(QN), "https://mainnet.helius-rpc.com/?api-key=HKEY"):
        r = redact(u)
        assert "SECRETTOKEN123" not in r and "HKEY" not in r
    assert redact(QN) == "https://abc-***.solana-mainnet.quiknode.pro/***"


def _rpc(handler, **kw):
    r = Rpc([("helius", "https://h/"), ("quicknode", "https://q/")], retries=4, **kw)
    r.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return r


def test_http_failover_on_429():
    seen = []
    def h(req):
        seen.append(req.url.host)
        if req.url.host == "h":
            return httpx.Response(429)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 42})
    r = _rpc(h)
    assert asyncio.run(r.call("getSlot", [])) == 42
    assert seen == ["h", "q"] and r.provider == "quicknode"


def test_http_failover_on_timeout():
    def h(req):
        if req.url.host == "h":
            raise httpx.ReadTimeout("t")
        return httpx.Response(200, json={"result": 1})
    assert asyncio.run(_rpc(h).call("getSlot", [])) == 1


def test_http_returns_to_primary():
    def h(req):
        return httpx.Response(200, json={"result": req.url.host})
    r = _rpc(h, primary_retry_s=0)
    r.active = 1
    assert asyncio.run(r.call("x", [])) == "h" and r.active == 0


def test_rpc_logic_error_no_switch():
    def h(req):
        return httpx.Response(200, json={"error": {"code": -32602}})
    r = _rpc(h)
    r.retries = 2
    with pytest.raises(RpcError):
        asyncio.run(r.call("x", []))


def test_ws_switches_after_failures(monkeypatch, tmp_path):
    cfg = Config(output_file=str(tmp_path / "o.jsonl"), pool_account_streams=False, primary_retry_s=1000, ws_fail_switch=2,
                 endpoints=[Endpoint("helius", "https://h", "wss://h"), Endpoint("quicknode", "https://q", "wss://q")])
    t = Tracker(cfg)
    used = []
    async def fake(ep=None):
        used.append(ep.name)
        if ep.name == "helius":
            raise ConnectionError("down")
        await asyncio.sleep(10)
    t._session = fake
    async def nosleep(*_): pass
    real_sleep = asyncio.sleep
    monkeypatch.setattr("sol_tracker.tracker.asyncio.sleep", lambda d: real_sleep(0))
    asyncio.run(t.run(0.3))
    assert used[:3] == ["helius", "helius", "quicknode"] and t.ws_active == 1


def test_ws_returns_to_primary(monkeypatch, tmp_path):
    cfg = Config(output_file=str(tmp_path / "o.jsonl"), pool_account_streams=False, primary_retry_s=0.1,
                 endpoints=[Endpoint("helius", "https://h", "wss://h"), Endpoint("quicknode", "https://q", "wss://q")])
    t = Tracker(cfg)
    t.ws_active = 1
    used = []
    async def fake(ep=None):
        used.append(ep.name)
        await asyncio.sleep(10)
    t._session = fake
    asyncio.run(t.run(0.4))
    assert used[:2] == ["quicknode", "helius"]
