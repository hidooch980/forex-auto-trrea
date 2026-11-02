"""Read-only MT5 web bridge."""
from .api import BridgeSnapshot, build_mt5_bridge_router
__all__ = ["BridgeSnapshot", "build_mt5_bridge_router"]
