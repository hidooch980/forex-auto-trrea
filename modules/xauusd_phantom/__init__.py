"""Research-only four-engine XAUUSD strategy orchestration."""
from .engine import (
    ENGINE_NAMES, EngineSignal, OpenRisk, PhantomConfig, PhantomDecision,
    PendingOrder, Side, evaluate_cycle, plan_oco_cancellations,
    plan_profit_vault, plan_trailing_stop,
)

__all__ = [
    "ENGINE_NAMES", "EngineSignal", "OpenRisk", "PhantomConfig",
    "PhantomDecision", "PendingOrder", "Side", "evaluate_cycle",
    "plan_oco_cancellations", "plan_profit_vault", "plan_trailing_stop",
]
