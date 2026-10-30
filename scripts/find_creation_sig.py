"""Find the (oldest) creation signature of a pool address -> feed to `replay`.
Usage: python scripts/find_creation_sig.py POOL [POOL...]"""
import asyncio, sys
sys.path.insert(0, ".")
from sol_tracker.config import load
from sol_tracker.rpc import Rpc


async def oldest(rpc, addr):
    before, last = None, None
    for _ in range(50):
        opts = {"limit": 1000}
        if before:
            opts["before"] = before
        page = await rpc.call("getSignaturesForAddress", [addr, opts])
        if not page:
            break
        last = page[-1]["signature"]
        before = last
        if len(page) < 1000:
            break
    return last


async def main():
    rpc = Rpc(load().endpoints, 2)
    for a in sys.argv[1:]:
        owner = (await rpc.get_multiple_accounts([a], "base64"))[0]
        print(a, owner and owner["owner"], await oldest(rpc, a))
    await rpc.close()

asyncio.run(main())
