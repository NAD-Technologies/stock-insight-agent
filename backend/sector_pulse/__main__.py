import argparse
import asyncio
import json
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)

from . import pipeline  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(prog="sector_pulse")
    ap.add_argument("command", choices=["run", "evaluate", "all"])
    ap.add_argument("--budget", type=int, default=None, help="max Module A stock analyses this run (default env SECTOR_ANALYZE_BUDGET or 40)")
    args = ap.parse_args()
    out = {}
    if args.command in ("run", "all"):
        out["run"] = await pipeline.run(args.budget)
    if args.command in ("evaluate", "all"):
        out["evaluate"] = await pipeline.evaluate()
    print(json.dumps(out, indent=2, default=str))
    return 1 if out.get("run", {}).get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
