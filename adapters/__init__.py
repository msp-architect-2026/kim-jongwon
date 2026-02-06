"""
Adapter layer for post-processing backtest engine outputs.
Does NOT modify core engine logic.
"""

from adapters.adapter import (
    derive_drawdown_curve,
    derive_portfolio_curve,
    normalize_trades,
    safe_iso8601_utc,
    build_equity_curve,
)

__all__ = [
    "derive_drawdown_curve",
    "derive_portfolio_curve",
    "normalize_trades",
    "safe_iso8601_utc",
    "build_equity_curve",
]
