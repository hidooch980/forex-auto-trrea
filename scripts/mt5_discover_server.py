"""Read exact server and a closed-bar market snapshot from logged-in MetaTrader 5."""
import argparse
import json
from modules.mt5_discovery.discovery import discover_market_snapshot

parser=argparse.ArgumentParser(description="Read-only MT5 terminal discovery")
parser.add_argument("--symbol",default="EURUSD")
parser.add_argument("--timeframe",default="M15",choices=["M1","M5","M15","M30","H1","H4","D1"])
parser.add_argument("--bars",type=int,default=100)
args=parser.parse_args()
print(json.dumps(discover_market_snapshot(args.symbol,timeframe=args.timeframe,bars=args.bars),
                 ensure_ascii=False,indent=2))
