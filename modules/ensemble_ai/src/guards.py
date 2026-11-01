from dataclasses import dataclass

@dataclass
class GuardInput:
    confidence: float
    spread_ok: bool
    news_clear: bool
    daily_loss_fraction: float
    emergency_stop: bool
    data_fresh: bool
    stop_loss_present: bool

def permit_signal(g: GuardInput, threshold=0.65, daily_limit=0.01):
    reasons = []
    if g.emergency_stop: reasons.append("emergency_stop")
    if not g.data_fresh: reasons.append("stale_data")
    if not g.spread_ok: reasons.append("spread_filter")
    if not g.news_clear: reasons.append("news_block")
    if g.daily_loss_fraction >= daily_limit: reasons.append("daily_loss_limit")
    if g.confidence < threshold: reasons.append("low_confidence")
    if not g.stop_loss_present: reasons.append("missing_stop_loss")
    return {"allowed": not reasons, "reasons": reasons}
