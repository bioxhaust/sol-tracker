"""CLI:
  python -m sol_tracker live [--minutes N] [--all]
  python -m sol_tracker replay SIG [SIG ...] [--all] [--save-fixtures DIR]
"""
import argparse, asyncio, json
from pathlib import Path
from . import config, logger
from .tracker import Tracker


async def amain():
    ap = argparse.ArgumentParser(prog="sol_tracker")
    ap.add_argument("mode", choices=["live", "replay"])
    ap.add_argument("sigs", nargs="*")
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--all", action="store_true", help="emit pools below liquidity threshold too")
    ap.add_argument("--config")
    ap.add_argument("--save-fixtures")
    a = ap.parse_args()
    cfg = config.load(a.config)
    cfg.log_all = cfg.log_all or a.all
    logger.setup(cfg.log_level)
    t = Tracker(cfg)
    try:
        if a.mode == "live":
            await t.run(a.minutes * 60 if a.minutes else None)
        else:
            t.cfg.recheck_delay_s = 0
            for s in a.sigs:
                if a.save_fixtures:
                    tx = await t.rpc.get_transaction(s)
                    Path(a.save_fixtures).mkdir(parents=True, exist_ok=True)
                    Path(a.save_fixtures, f"{s[:16]}.json").write_text(json.dumps(tx))
                await t.handle_signature(s)
    finally:
        await t.close()


asyncio.run(amain())
