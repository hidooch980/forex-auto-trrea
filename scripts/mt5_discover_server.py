"""Print the exact server of the account already logged into MetaTrader 5.

Run this on the Windows computer where the target MT5 terminal is installed and
already logged in. This script is read-only and never asks for credentials.
"""
import json
from modules.mt5_discovery.discovery import discover_connected_terminal
print(json.dumps(discover_connected_terminal(),ensure_ascii=False,indent=2))
