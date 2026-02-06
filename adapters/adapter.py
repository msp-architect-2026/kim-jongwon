"""
Adapter Layer for Day 3.9 Extended Response Schema.

This module provides helper functions to transform engine outputs
into the extended JSON schema defined in CLAUDE.md Section 4.

IMPORTANT: This module does NOT modify engine logic.
It only performs post-processing on engine outputs.
"""

import logging
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union

# Module-level logger (does NOT depend on Flask)
logger = logging.getLogger(__name__)


# Default US market close time (16:00 ET = 21:00 UTC)
DEFAULT_DAILY_CLOSE_UTC = "21:00:00+00:00"


def safe_iso8601_utc(
    date_input: Union[str, datetime, pd.Timestamp, None],
    daily_close_utc: str = DEFAULT_DAILY_CLOSE_UTC
) -> Optional[str]:
    """
    Convert date/timestamp to ISO8601 UTC string.

    For daily data (timeframe='1d'):
    - If timestamp is timezone-aware -> convert to UTC
    - If timestamp is naive/date-only -> assign US market close (21:00 UTC)

    Args:
        date_input: Input date (string, datetime, or pd.Timestamp)
        daily_close_utc: Time to assign for date-only inputs (default: 21:00:00+00:00)

    Returns:
        ISO8601 formatted string: YYYY-MM-DDTHH:MM:SS+00:00
        Returns None if input cannot be parsed (schema safety).

    Note:
        On parse failure, emits a WARNING log and returns None.
        This ensures downstream consumers receive a valid ISO8601 string or null,
        never an unparseable raw value that violates the schema contract.
    """
    # Handle None/null input explicitly
    if date_input is None:
        logger.warning("safe_iso8601_utc received None input, returning None")
        return None

    if isinstance(date_input, str):
        # Parse string to timestamp
        try:
            ts = pd.Timestamp(date_input)
            # Check for NaT (Not a Timestamp) - happens with empty string
            if pd.isna(ts):
                logger.warning(
                    f"safe_iso8601_utc parsed NaT from string '{date_input}', returning None"
                )
                return None
        except Exception as e:
            logger.warning(
                f"safe_iso8601_utc failed to parse string '{date_input}': {e}"
            )
            return None  # Return None on parse failure (schema safety)
    elif isinstance(date_input, (datetime, pd.Timestamp)):
        ts = pd.Timestamp(date_input)
        # Check for NaT
        if pd.isna(ts):
            logger.warning("safe_iso8601_utc received NaT timestamp, returning None")
            return None
    else:
        # Handle other types (e.g., date objects)
        try:
            ts = pd.Timestamp(str(date_input))
            if pd.isna(ts):
                logger.warning(
                    f"safe_iso8601_utc parsed NaT from type {type(date_input).__name__}, returning None"
                )
                return None
        except Exception as e:
            logger.warning(
                f"safe_iso8601_utc failed to parse type {type(date_input).__name__}: {e}"
            )
            return None

    # Check if timestamp is timezone-aware
    if ts.tzinfo is not None:
        # Convert to UTC
        ts_utc = ts.tz_convert("UTC")
        return ts_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    else:
        # Naive timestamp - assign daily close time (21:00 UTC)
        # Parse the time component
        time_parts = daily_close_utc.split("+")[0].split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        second = int(time_parts[2]) if len(time_parts) > 2 else 0

        # Create UTC datetime
        dt = datetime(
            ts.year, ts.month, ts.day,
            hour, minute, second,
            tzinfo=timezone.utc
        )
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def build_equity_curve(portfolio_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Build equity_curve from engine's portfolio_history DataFrame.

    Args:
        portfolio_df: DataFrame with 'value' column and DatetimeIndex

    Returns:
        List of {"date": "YYYY-MM-DD", "equity": float}
    """
    if portfolio_df is None or portfolio_df.empty:
        return []

    equity_curve = []
    for idx, row in portfolio_df.iterrows():
        equity_curve.append({
            "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
            "equity": round(float(row["value"]), 2)
        })

    return equity_curve


def derive_drawdown_curve(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Derive drawdown_curve from equity_curve.

    SPECIFICATION (AUTHORITATIVE):
    Returns NON-POSITIVE values (<= 0.0).
    A value of 0.0 indicates a new equity peak (no drawdown).
    Negative values indicate drawdown below the running peak.

    Examples:
    - drawdown_pct = 0.0   -> at peak (valid and expected)
    - drawdown_pct = -10.0 -> 10% below peak

    This aligns with standard financial definitions:
    1. Matches CLAUDE.md example: {"date": "2020-01-02", "drawdown_pct": -1.2}
    2. Follows industry convention (drawdown represents loss from peak)
    3. Enables intuitive UI coloring (negative = red, zero = green/neutral)

    Formula:
        drawdown_pct = ((current_equity - peak_equity) / peak_equity) * 100
    where peak_equity = running maximum of equity_curve

    Args:
        equity_curve: List of {"date": str, "equity": float}

    Returns:
        List of {"date": str, "drawdown_pct": float}
        - Values are NON-POSITIVE (<= 0.0)
        - Zero at new peaks, negative below peaks

    Note:
        - Handles edge cases (empty list, single point, monotonic increase)
        - Zero peak equity returns 0.0 drawdown (avoids division by zero)
        - NO epsilon hacks: 0.0 is mathematically correct at peaks
    """
    if not equity_curve:
        return []

    drawdown_curve = []
    peak_equity = 0.0

    for point in equity_curve:
        equity = point["equity"]

        # Update running peak
        if equity > peak_equity:
            peak_equity = equity

        # Calculate drawdown percentage (NEGATIVE values for loss from peak)
        if peak_equity > 0:
            drawdown_pct = ((equity - peak_equity) / peak_equity) * 100
        else:
            drawdown_pct = 0.0

        # Rounding rationale:
        # - Round to 2 decimals for UI readability and JSON stability
        # - Rounding can turn very small negatives (e.g., -0.001%) into 0.0
        # - This is acceptable: drawdown is defined as NON-POSITIVE (<= 0.0),
        #   so 0.0 is a valid value at or near peaks
        drawdown_curve.append({
            "date": point["date"],
            "drawdown_pct": round(drawdown_pct, 2)
        })

    return drawdown_curve


def derive_portfolio_curve(
    equity_curve: List[Dict[str, Any]],
    portfolio_df: pd.DataFrame
) -> List[Dict[str, Any]]:
    """
    Derive portfolio_curve showing cash vs position breakdown.

    Args:
        equity_curve: List of {"date": str, "equity": float}
        portfolio_df: DataFrame with 'cash' and 'holdings_value' columns

    Returns:
        List of {"date": str, "cash": float, "position": float, "total": float}

    Note:
        Returns empty list if portfolio_df lacks required columns.
    """
    if portfolio_df is None or portfolio_df.empty:
        return []

    if "cash" not in portfolio_df.columns or "holdings_value" not in portfolio_df.columns:
        return []

    portfolio_curve = []
    for idx, row in portfolio_df.iterrows():
        portfolio_curve.append({
            "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
            "cash": round(float(row["cash"]), 2),
            "position": round(float(row["holdings_value"]), 2),
            "total": round(float(row["value"]), 2)
        })

    return portfolio_curve


def normalize_trades(
    raw_trades: List[Dict[str, Any]],
    fee_rate: float = 0.001
) -> List[Dict[str, Any]]:
    """
    Normalize engine trades to the extended schema defined in CLAUDE.md.

    The engine outputs trades as a flat list of buy/sell actions.
    This function pairs them and computes P&L, holding period, etc.

    Args:
        raw_trades: Engine's trades list (from BacktestEngine.trades)
        fee_rate: Fee rate for fee calculation verification

    Returns:
        List of normalized trades matching CLAUDE.md schema:
        {
            "trade_no": int,
            "side": "BUY" | "SELL",
            "size": int,
            "entry_timestamp": ISO8601,
            "entry_price": float,
            "entry_fees": float,
            "exit_timestamp": ISO8601,
            "exit_price": float,
            "exit_fees": float,
            "pnl_abs": float,
            "pnl_pct": float,
            "holding_period": float (days)
        }

    Note:
        - Only completed round-trip trades (buy+sell pairs) are returned
        - Open positions at end of backtest are excluded
        - num_trades in API response should equal len(normalize_trades())
    """
    if not raw_trades:
        return []

    # Separate buy and sell trades
    buy_trades = [t for t in raw_trades if t.get("action") == "buy"]
    sell_trades = [t for t in raw_trades if t.get("action") == "sell"]

    normalized = []

    # Pair buy/sell trades
    for i, (buy, sell) in enumerate(zip(buy_trades, sell_trades)):
        # Extract timestamps
        entry_ts = buy.get("date")
        exit_ts = sell.get("date")

        # Convert to ISO8601
        entry_timestamp = safe_iso8601_utc(entry_ts)
        exit_timestamp = safe_iso8601_utc(exit_ts)

        # Get prices and size
        entry_price = float(buy.get("price", 0))
        exit_price = float(sell.get("price", 0))
        size = int(sell.get("quantity", buy.get("quantity", 0)))

        # Get fees from engine (or compute from fee_rate)
        entry_fees = float(buy.get("commission", entry_price * size * fee_rate))
        exit_fees = float(sell.get("commission", exit_price * size * fee_rate))

        # Calculate P&L
        # Note: Engine uses effective_price (with slippage), but we report market price
        # P&L formula from CLAUDE.md:
        # pnl_abs = (exit_price - entry_price) * size - entry_fees - exit_fees
        pnl_abs = (exit_price - entry_price) * size - entry_fees - exit_fees

        # P&L percentage
        # pnl_pct = pnl_abs / (entry_price * size) * 100
        entry_cost = entry_price * size
        pnl_pct = (pnl_abs / entry_cost * 100) if entry_cost > 0 else 0.0

        # Calculate holding period in days
        try:
            entry_dt = pd.Timestamp(entry_ts)
            exit_dt = pd.Timestamp(exit_ts)
            holding_seconds = (exit_dt - entry_dt).total_seconds()
            holding_period = holding_seconds / 86400  # Convert to days
        except Exception:
            holding_period = 0.0

        normalized.append({
            "trade_no": i,
            "side": "BUY",  # The trade type (entry side)
            "size": size,
            "entry_timestamp": entry_timestamp,
            "entry_price": round(entry_price, 2),
            "entry_fees": round(entry_fees, 2),
            "exit_timestamp": exit_timestamp,
            "exit_price": round(exit_price, 2),
            "exit_fees": round(exit_fees, 2),
            "pnl_abs": round(pnl_abs, 2),
            "pnl_pct": round(pnl_pct, 2),
            "holding_period": round(holding_period, 1)
        })

    return normalized
