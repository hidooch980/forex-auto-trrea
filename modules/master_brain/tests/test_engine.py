import unittest

from modules.master_brain.engine import (
    Action, AgentSignal, BrainConfig, MarketContext, RiskProfile, evaluate_market,
)


def bullish_signals():
    return [
        AgentSignal("technical", 0.8, 0.9, "trend and momentum agree"),
        AgentSignal("institutional", 0.6, 0.8, "public positioning proxy"),
        AgentSignal("smart_money", 0.7, 0.8, "liquidity structure"),
        AgentSignal("news", 0.4, 0.7, "timestamped headline baseline"),
    ]


class MasterBrainTests(unittest.TestCase):
    def test_balanced_hybrid_returns_auditable_buy(self):
        result = evaluate_market(MarketContext("EURUSD"), bullish_signals())
        self.assertEqual(result.action, Action.BUY)
        self.assertTrue(result.approved)
        self.assertGreater(result.score, 0)
        self.assertAlmostEqual(sum(result.effective_weights.values()), 1.0, places=5)
        self.assertEqual(result.risk_pct, 0.25)
        self.assertIn("committee_consensus_passed", result.reasons)

    def test_requested_risk_is_capped(self):
        result = evaluate_market(
            MarketContext("EURUSD", requested_risk_pct=2.0), bullish_signals()
        )
        self.assertEqual(result.risk_pct, 0.25)

    def test_emergency_stop_blocks_trade(self):
        result = evaluate_market(
            MarketContext("EURUSD", emergency_stop=True), bullish_signals()
        )
        self.assertEqual(result.action, Action.HOLD)
        self.assertFalse(result.approved)
        self.assertIn("emergency_stop_active", result.reasons)
        self.assertEqual(result.risk_pct, 0.0)

    def test_missing_calendar_fails_closed(self):
        result = evaluate_market(
            MarketContext("EURUSD", calendar_valid=False), bullish_signals()
        )
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("economic_calendar_missing_or_invalid", result.reasons)

    def test_high_impact_blackout_blocks(self):
        result = evaluate_market(
            MarketContext("EURUSD", high_impact_blackout=True), bullish_signals()
        )
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("high_impact_event_blackout", result.reasons)

    def test_stale_signals_are_not_counted(self):
        signals = [
            AgentSignal("technical", 0.8, 0.9, age_seconds=1200),
            AgentSignal("news", 0.8, 0.9, age_seconds=50000),
        ]
        result = evaluate_market(MarketContext("EURUSD"), signals)
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("insufficient_fresh_agent_evidence", result.reasons)

    def test_disagreement_results_in_hold(self):
        signals = [
            AgentSignal("technical", 0.9, 0.9),
            AgentSignal("institutional", -0.9, 0.9),
            AgentSignal("macro", 0.0, 0.9),
        ]
        result = evaluate_market(MarketContext("GBPUSD"), signals)
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("edge_below_threshold", result.reasons)

    def test_daily_loss_and_spread_guards(self):
        result = evaluate_market(
            MarketContext("EURUSD", daily_loss_pct=1.0, spread_pips=4.0),
            bullish_signals(),
        )
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("daily_loss_limit_reached", result.reasons)
        self.assertIn("spread_above_limit", result.reasons)

    def test_unknown_agent_is_ignored_and_duplicates_rejected(self):
        result = evaluate_market(
            MarketContext("EURUSD"),
            bullish_signals() + [AgentSignal("experimental", 1.0, 1.0)],
        )
        self.assertEqual(result.action, Action.BUY)
        with self.assertRaises(ValueError):
            evaluate_market(
                MarketContext("EURUSD"),
                bullish_signals() + [AgentSignal("technical", 0.2, 0.5)],
            )

    def test_invalid_signal_values_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_market(
                MarketContext("EURUSD"),
                [AgentSignal("technical", 1.2, 0.9), AgentSignal("news", 0.2, 0.8)],
            )


    def test_xauusd_uses_lower_instrument_risk_cap(self):
        result = evaluate_market(MarketContext("XAUUSD"), bullish_signals())
        self.assertEqual(result.action, Action.BUY)
        self.assertEqual(result.risk_pct, 0.10)

    def test_requested_xauusd_risk_cannot_exceed_instrument_cap(self):
        result = evaluate_market(
            MarketContext("XAUUSD", requested_risk_pct=0.25), bullish_signals()
        )
        self.assertEqual(result.risk_pct, 0.10)

    def test_xau_broker_suffix_keeps_gold_risk_cap(self):
        for symbol in ("XAUUSD.a", "XAUUSDm", "XAUEUR.pro"):
            with self.subTest(symbol=symbol):
                result = evaluate_market(
                    MarketContext(symbol, requested_risk_pct=0.25), bullish_signals()
                )
                self.assertEqual(result.risk_pct, 0.10)

    def test_config_cannot_raise_hard_xau_cap(self):
        profile = RiskProfile(instrument_risk_caps_pct={"XAUUSD": 0.50})
        config = BrainConfig(profile=profile)
        for symbol in ("XAUUSD", "XAUUSD.a"):
            with self.subTest(symbol=symbol):
                result = evaluate_market(
                    MarketContext(symbol, requested_risk_pct=0.50),
                    bullish_signals(), config,
                )
                self.assertEqual(result.risk_pct, 0.10)

    def test_invalid_market_data_and_drawdown_fail_closed(self):
        result = evaluate_market(
            MarketContext("EURUSD", market_data_valid=False, drawdown_pct=5.0),
            bullish_signals(),
        )
        self.assertEqual(result.action, Action.HOLD)
        self.assertIn("market_data_missing_or_invalid", result.reasons)
        self.assertIn("drawdown_limit_reached", result.reasons)

    def test_reliability_multiplier_is_bounded(self):
        context = MarketContext("EURUSD", reliability={"technical": 99.0})
        result = evaluate_market(context, bullish_signals())
        self.assertLessEqual(result.effective_weights["technical"], 0.5)


if __name__ == "__main__":
    unittest.main()
