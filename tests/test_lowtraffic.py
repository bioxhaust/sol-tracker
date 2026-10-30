import asyncio
from sol_tracker.config import Config
from sol_tracker.dex import ALL
from sol_tracker.newpools import PoolSet, creation_signature, YOUNG_MAX_SIGS
from sol_tracker.tracker import Tracker

BUSY = {d.program_id for d in ALL.values()}


def test_watch_accounts_not_busy_programs():
    for d in ALL.values():
        for label, acct in d.subscriptions():
            if d.watch_accounts:
                assert acct not in BUSY and acct != d.program_id, label


def test_plan_low_traffic(tmp_path):
    t = Tracker(Config(output_file=str(tmp_path / "o.jsonl")))
    ps = PoolSet(); ps.load_keys(["46fxp9eArE5CVcbkqVyjUnHrXPmwdgx1SarpYTobExjF"])
    t.pool_sets["pumpswap"] = ps
    plan = t.subscription_plan()
    labels = [p[0] for p in plan]
    assert "pumpswap:pump_migration" in labels
    assert "pumpswap:pool_accounts_287" in labels and "pumpswap:pool_accounts_301" in labels
    assert "meteora_dlmm:program" not in labels  # disabled by default
    mentions = [p[3][0]["mentions"][0] for p in plan if p[2] == "logsSubscribe"]
    busy_mentions = [m for m in mentions if m in BUSY]
    assert busy_mentions == [ALL["meteora_damm_v1"].program_id]  # only the quiet DAMM v1 program
    ps_subs = [p[3][1] for p in plan if p[2] == "programSubscribe"]
    assert all(x["dataSlice"] == {"offset": 0, "length": 0} for x in ps_subs)
    assert sorted(x["filters"][0]["dataSize"] for x in ps_subs) == [287, 301]


def test_plan_without_snapshot_skips_pool_stream(tmp_path):
    t = Tracker(Config(output_file=str(tmp_path / "o.jsonl")))
    assert not any(p[2] == "programSubscribe" for p in t.subscription_plan())


def test_poolset_membership():
    ps = PoolSet(); ps.load_keys(["46fxp9eArE5CVcbkqVyjUnHrXPmwdgx1SarpYTobExjF",
                                  "3ak1Stb84FffAtaSW9AdW32tQAZhZJhcFNjANcXykaNR"])
    assert "3ak1Stb84FffAtaSW9AdW32tQAZhZJhcFNjANcXykaNR" in ps
    assert "J8Vxcypk8KduA2Gw2i6pfhpEuu2XJnCwtPhbVEFurP42" not in ps
    ps.add("J8Vxcypk8KduA2Gw2i6pfhpEuu2XJnCwtPhbVEFurP42")
    assert "J8Vxcypk8KduA2Gw2i6pfhpEuu2XJnCwtPhbVEFurP42" in ps and len(ps) == 3


class FakeRpc:
    def __init__(self, n): self.n = n
    async def call(self, method, params):
        assert method == "getSignaturesForAddress"
        return [{"signature": f"s{i}", "err": None} for i in range(self.n)]


def test_creation_signature_young_vs_old():
    assert asyncio.run(creation_signature(FakeRpc(3), "x")) == "s2"
    assert asyncio.run(creation_signature(FakeRpc(YOUNG_MAX_SIGS), "x")) is None


def test_new_pool_account_dispatch(tmp_path):
    t = Tracker(Config(output_file=str(tmp_path / "o.jsonl")))
    ps = PoolSet(); ps.load_keys(["46fxp9eArE5CVcbkqVyjUnHrXPmwdgx1SarpYTobExjF"])
    t.pool_sets["pumpswap"] = ps
    handled = []
    t.rpc = FakeRpc(2)
    async def hs(sig, names=None): handled.append(sig)
    t.handle_signature = hs
    async def go():
        t._on_pool_account(ALL["pumpswap"], "46fxp9eArE5CVcbkqVyjUnHrXPmwdgx1SarpYTobExjF")  # known
        t._on_pool_account(ALL["pumpswap"], "J8Vxcypk8KduA2Gw2i6pfhpEuu2XJnCwtPhbVEFurP42")  # new
        t._on_pool_account(ALL["pumpswap"], "J8Vxcypk8KduA2Gw2i6pfhpEuu2XJnCwtPhbVEFurP42")  # dup
        await asyncio.sleep(0.05)
    asyncio.run(go())
    assert handled == ["s1"] and t.stats["new_pool_accounts"] == 1


def test_get_transaction_accepts_v1():
    import inspect
    from sol_tracker import rpc
    assert '"maxSupportedTransactionVersion": 1' in inspect.getsource(rpc.Rpc.get_transaction)
