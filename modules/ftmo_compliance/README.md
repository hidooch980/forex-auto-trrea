# FTMO compliance module

This module provides a deterministic pre-trade compliance calculation layer for
FTMO 1-Step, 2-Step and Instant profiles. It is not an FTMO API client and does
not connect to an account or submit orders.

## Profiles encoded

- 1-Step: 3% maximum daily loss; 10% end-of-day balance-trailing maximum loss;
  10% Challenge target; 50% Consistency limit for accounts under the current
  Consistency rule.
- 2-Step: 5% maximum daily loss; 10% static maximum loss; 10% Challenge and 5%
  Verification targets; at least four trading days during evaluation; no
  Consistency rule.
- Instant: 3% maximum daily loss; 10% intraday closed-balance-trailing maximum
  loss; 30% Consistency limit.

The profile calculations use equity for the live breach threshold and require
the correct account snapshots. 1-Step requires the highest end-of-day balance;
Instant requires the highest balance reached from closed positions. The
2-Step maximum-loss floor is static from initial capital.

News execution is blocked within the FTMO selected-event +/-2 minute window
only for funded Standard accounts. Challenge/Verification and Swing accounts
are exempt from this selected-news restriction. This is distinct from the
general Forbidden Trading Practices policy.

## Integration still required

- Read-only account snapshots from the connected FTMO MT5 terminal, including
  balance/equity, day-boundary baseline, high-water marks and closed daily P&L.
- Official FTMO restricted-event calendar ingestion and timezone validation.
- Position/deal reconciliation, symbol-specific trading sessions and account
  type/phase configuration.
- Independent validation against Account MetriX and the latest FTMO terms.

Do not enable order execution based on this module alone. It is a guardrail
calculation, not a guarantee of FTMO compliance. Rules may change; the exact
account's FTMO Client Area and Agreement take precedence.
