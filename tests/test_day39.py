"""
Day 3.9 Tests: Extended API Schema and Adapter Layer

This module contains pytest tests for:
1. /run_backtest response schema validation
2. Drawdown derivation edge cases
3. HTTP 400 vs 500 error separation
4. Sharpe Ratio risk-free rate compliance
5. Slippage contract compliance
6. num_trades consistency with trades array
7. Deterministic success path tests (chart generation)
8. Figure memory leak prevention (plt.close verification)

IMPORTANT: System errors are simulated via monkeypatch/mock only.
No application code modifications for error simulation.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
import pandas as pd
import matplotlib.pyplot as plt

# Adapter layer tests (can run without Flask app context)
from adapters.adapter import (
    derive_drawdown_curve,
    normalize_trades,
    safe_iso8601_utc,
    build_equity_curve,
    render_drawdown_chart,
    render_portfolio_plot,
)


# ═══════════════════════════════════════════════════════════════
# ADAPTER LAYER TESTS
# ═══════════════════════════════════════════════════════════════

class TestDeriveDrawdownCurve:
    """Test drawdown curve derivation from equity curve.

    SPECIFICATION (AUTHORITATIVE):
    Drawdown values are NON-POSITIVE (<= 0.0).
    - A value of 0.0 is valid and EXPECTED at new equity peaks.
    - Negative values represent drawdowns below the peak.
    """

    def test_empty_equity_curve(self):
        """Empty input returns empty output."""
        result = derive_drawdown_curve([])
        assert result == []

    def test_single_point(self):
        """Single data point has zero drawdown (it is its own peak)."""
        equity = [{"date": "2020-01-01", "equity": 100000}]
        result = derive_drawdown_curve(equity)
        # Anti-false-confidence: verify we have data to check
        assert len(result) == 1
        assert result[0]["date"] == "2020-01-01"
        # At peak, drawdown is exactly 0.0
        assert result[0]["drawdown_pct"] == 0.0

    def test_monotonic_increasing_no_drawdown(self):
        """Monotonically increasing equity has zero drawdown throughout.

        Each point is a new peak, so drawdown = 0.0 at every point.
        """
        equity = [
            {"date": "2020-01-01", "equity": 100000},
            {"date": "2020-01-02", "equity": 101000},
            {"date": "2020-01-03", "equity": 102000},
            {"date": "2020-01-04", "equity": 103000},
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty before loop
        assert len(result) == 4, "Expected 4 drawdown points"
        for point in result:
            # All points are peaks, so drawdown is exactly 0.0
            assert point["drawdown_pct"] == 0.0

    def test_mixed_up_down_equity(self):
        """Mixed equity correctly computes drawdown percentages."""
        equity = [
            {"date": "2020-01-01", "equity": 100000},  # Peak = 100000, DD = 0
            {"date": "2020-01-02", "equity": 110000},  # Peak = 110000, DD = 0
            {"date": "2020-01-03", "equity": 99000},   # Peak = 110000, DD = -10%
            {"date": "2020-01-04", "equity": 105000},  # Peak = 110000, DD = -4.55%
            {"date": "2020-01-05", "equity": 115000},  # Peak = 115000, DD = 0
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty
        assert len(result) == 5, "Expected 5 drawdown points"
        # Peaks have exactly 0.0 drawdown
        assert result[0]["drawdown_pct"] == 0.0
        assert result[1]["drawdown_pct"] == 0.0
        # Below peak: negative drawdown
        assert result[2]["drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
        assert result[3]["drawdown_pct"] == pytest.approx(-4.55, abs=0.01)
        # New peak: exactly 0.0 drawdown
        assert result[4]["drawdown_pct"] == 0.0

    def test_continuous_decline(self):
        """Continuous decline shows increasing drawdown magnitude."""
        equity = [
            {"date": "2020-01-01", "equity": 100000},
            {"date": "2020-01-02", "equity": 90000},   # -10%
            {"date": "2020-01-03", "equity": 80000},   # -20%
            {"date": "2020-01-04", "equity": 70000},   # -30%
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty
        assert len(result) == 4, "Expected 4 drawdown points"
        # First point is peak, exactly 0.0
        assert result[0]["drawdown_pct"] == 0.0
        # Subsequent points are below peak, negative values
        assert result[1]["drawdown_pct"] == pytest.approx(-10.0, abs=0.01)
        assert result[2]["drawdown_pct"] == pytest.approx(-20.0, abs=0.01)
        assert result[3]["drawdown_pct"] == pytest.approx(-30.0, abs=0.01)

    def test_no_division_by_zero(self):
        """Handles zero equity without division error."""
        equity = [
            {"date": "2020-01-01", "equity": 0},
            {"date": "2020-01-02", "equity": 100},
        ]
        # Should not raise ZeroDivisionError
        result = derive_drawdown_curve(equity)
        # Anti-false-confidence: verify list is non-empty
        assert len(result) == 2, "Expected 2 drawdown points"
        # When peak is 0, drawdown is 0 (edge case handling)
        assert result[0]["drawdown_pct"] == 0.0

    def test_drawdown_values_are_non_positive(self):
        """SPEC CORRECTION: Drawdown values are NON-POSITIVE (<= 0.0).

        This test verifies the corrected specification:
        - Values below peak are strictly negative (< 0)
        - Values at peak are exactly zero (== 0.0)
        """
        equity = [
            {"date": "2020-01-01", "equity": 100000},  # Peak
            {"date": "2020-01-02", "equity": 95000},   # 5% below peak
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty
        assert len(result) == 2, "Expected 2 drawdown points"

        # At peak: drawdown is exactly 0.0 (NON-POSITIVE, valid)
        assert result[0]["drawdown_pct"] == 0.0

        # Below peak: drawdown is strictly negative (NON-POSITIVE)
        assert result[1]["drawdown_pct"] <= 0, "Drawdown must be non-positive"
        assert result[1]["drawdown_pct"] == pytest.approx(-5.0, abs=0.01)

    def test_peak_produces_exactly_zero_drawdown(self):
        """EXPLICIT TEST: New equity peak produces drawdown_pct == 0.0 exactly.

        This is the authoritative test for the corrected specification.
        Zero drawdown at peaks is mathematically correct, not an error.
        """
        equity = [
            {"date": "2020-01-01", "equity": 100000},  # Initial peak
            {"date": "2020-01-02", "equity": 90000},   # Drawdown
            {"date": "2020-01-03", "equity": 110000},  # NEW PEAK
            {"date": "2020-01-04", "equity": 120000},  # NEW PEAK
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty
        assert len(result) == 4, "Expected 4 drawdown points"

        # Verify peaks have EXACTLY 0.0 drawdown
        assert result[0]["drawdown_pct"] == 0.0, "Initial peak must be 0.0"
        assert result[2]["drawdown_pct"] == 0.0, "New peak at day 3 must be 0.0"
        assert result[3]["drawdown_pct"] == 0.0, "New peak at day 4 must be 0.0"

        # Verify non-peak has negative drawdown
        assert result[1]["drawdown_pct"] < 0, "Below peak must be negative"
        assert result[1]["drawdown_pct"] == pytest.approx(-10.0, abs=0.01)

    def test_all_drawdown_values_are_non_positive(self):
        """Verify ALL drawdown values satisfy the NON-POSITIVE (<= 0.0) constraint.

        This test iterates over results to ensure no positive values exist.
        Anti-false-confidence: asserts list is non-empty before looping.
        """
        equity = [
            {"date": "2020-01-01", "equity": 100000},
            {"date": "2020-01-02", "equity": 95000},
            {"date": "2020-01-03", "equity": 105000},
            {"date": "2020-01-04", "equity": 102000},
            {"date": "2020-01-05", "equity": 110000},
        ]
        result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify list is non-empty before loop
        assert len(result) > 0, "Drawdown curve must not be empty"
        assert len(result) == len(equity), "Drawdown curve length must match equity curve"

        # Verify ALL values are non-positive (no epsilon hack)
        for i, point in enumerate(result):
            assert point["drawdown_pct"] <= 0.0, \
                f"Drawdown at index {i} must be non-positive, got {point['drawdown_pct']}"

    def test_no_epsilon_hack_at_peaks(self):
        """REGRESSION TEST: Detect epsilon hacks (artificial tiny negatives at peaks).

        This test MUST FAIL if someone adds an epsilon hack like:
            if drawdown_pct == 0.0: drawdown_pct = -1e-12

        IMPORTANT: We patch `round` to a no-op so we can observe RAW drawdown
        values before rounding. Without this, rounding would erase tiny epsilons
        and the test would be ineffective.

        Uses monotonic non-decreasing equity where every point is a peak.
        At peaks, raw drawdown_pct must be EXACTLY 0.0.
        """
        # Monotonic non-decreasing: every point is a new peak or equal to peak
        equity = [
            {"date": "2020-01-01", "equity": 100000},
            {"date": "2020-01-02", "equity": 100000},  # Equal to peak
            {"date": "2020-01-03", "equity": 105000},  # New peak
            {"date": "2020-01-04", "equity": 105000},  # Equal to peak
            {"date": "2020-01-05", "equity": 110000},  # New peak
            {"date": "2020-01-06", "equity": 115000},  # New peak
        ]

        # Patch round to return value unchanged (no-op) so we see raw values
        # This allows detection of epsilon hacks that would be erased by rounding
        def noop_round(x, ndigits=None):
            return x

        # MAINTENANCE NOTE: Patch target is "adapters.adapter.round" because
        # derive_drawdown_curve uses the module-level `round` builtin.
        # If rounding implementation changes (e.g., builtins.round, numpy.round),
        # this patch target MUST be updated accordingly.
        with patch("adapters.adapter.round", side_effect=noop_round):
            result = derive_drawdown_curve(equity)

        # Anti-false-confidence: verify we have data
        assert len(result) == 6, "Expected 6 drawdown points"

        # Every point is at or above peak, so RAW drawdown must be EXACTLY 0.0
        for i, point in enumerate(result):
            dd = point["drawdown_pct"]

            # Must be exactly 0.0 (not -1e-12 or any tiny negative)
            # This assertion will FAIL if an epsilon hack is introduced
            assert dd == 0.0, \
                f"Peak at index {i} has raw drawdown {dd!r}, expected exactly 0.0 (epsilon hack detected)"


class TestNormalizeTrades:
    """Test trade normalization to extended schema."""

    def test_empty_trades(self):
        """Empty trades list returns empty."""
        result = normalize_trades([])
        assert result == []

    def test_single_round_trip(self):
        """Single buy-sell pair is normalized correctly."""
        raw_trades = [
            {
                "date": "2020-01-15",
                "action": "buy",
                "quantity": 100,
                "price": 150.00,
                "effective_price": 150.30,
                "commission": 15.03,
                "total_cost": 15045.03,
            },
            {
                "date": "2020-03-15",
                "action": "sell",
                "quantity": 100,
                "price": 165.00,
                "effective_price": 164.67,
                "commission": 16.47,
                "net_proceeds": 16450.33,
            },
        ]

        result = normalize_trades(raw_trades, fee_rate=0.001)

        assert len(result) == 1
        trade = result[0]

        assert trade["trade_no"] == 0
        assert trade["side"] == "BUY"
        assert trade["size"] == 100
        assert trade["entry_price"] == 150.00
        assert trade["exit_price"] == 165.00
        assert "entry_timestamp" in trade
        assert "exit_timestamp" in trade
        assert "pnl_abs" in trade
        assert "pnl_pct" in trade
        assert "holding_period" in trade

    def test_multiple_trades(self):
        """Multiple round-trip trades are numbered correctly."""
        raw_trades = [
            {"date": "2020-01-01", "action": "buy", "quantity": 50, "price": 100, "commission": 5},
            {"date": "2020-02-01", "action": "sell", "quantity": 50, "price": 110, "commission": 5.5},
            {"date": "2020-03-01", "action": "buy", "quantity": 60, "price": 105, "commission": 6.3},
            {"date": "2020-04-01", "action": "sell", "quantity": 60, "price": 95, "commission": 5.7},
        ]

        result = normalize_trades(raw_trades, fee_rate=0.001)

        assert len(result) == 2
        assert result[0]["trade_no"] == 0
        assert result[1]["trade_no"] == 1

    def test_open_position_excluded(self):
        """Open position (buy without sell) is excluded."""
        raw_trades = [
            {"date": "2020-01-01", "action": "buy", "quantity": 100, "price": 150, "commission": 15},
            # No corresponding sell
        ]

        result = normalize_trades(raw_trades, fee_rate=0.001)

        # No complete round-trip, so empty
        assert result == []


class TestSafeIso8601Utc:
    """Test ISO8601 UTC timestamp conversion."""

    def test_date_string(self):
        """Date-only string gets 21:00 UTC timestamp."""
        result = safe_iso8601_utc("2020-01-15")
        assert result == "2020-01-15T21:00:00+00:00"

    def test_datetime_naive(self):
        """Naive datetime gets 21:00 UTC timestamp."""
        import pandas as pd
        ts = pd.Timestamp("2020-01-15 10:30:00")
        result = safe_iso8601_utc(ts)
        # Naive timestamp -> assign 21:00 UTC
        assert result == "2020-01-15T21:00:00+00:00"

    def test_datetime_utc_aware(self):
        """UTC-aware timestamp is preserved."""
        import pandas as pd
        ts = pd.Timestamp("2020-01-15 14:30:00", tz="UTC")
        result = safe_iso8601_utc(ts)
        assert result == "2020-01-15T14:30:00+00:00"

    def test_datetime_other_tz(self):
        """Non-UTC timezone is converted to UTC."""
        import pandas as pd
        # 10:00 Eastern = 15:00 UTC (during EST)
        ts = pd.Timestamp("2020-01-15 10:00:00", tz="US/Eastern")
        result = safe_iso8601_utc(ts)
        # Should be converted to UTC
        assert "+00:00" in result


# ═══════════════════════════════════════════════════════════════
# FLASK APP TESTS (require app context)
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def app():
    """Create test Flask application."""
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    with app.test_client() as client:
        with app.app_context():
            from extensions import db
            db.create_all()
        yield client


class TestRunBacktestResponseSchema:
    """Test /run_backtest endpoint response schema."""

    def test_success_response_has_all_required_fields(self, client):
        """Successful backtest returns all required Day 3.9 fields."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000,
            "fee_rate": 0.001,
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        # May succeed or fail depending on data availability
        data = response.get_json()

        # All required keys must be present regardless of success/failure
        assert "run_id" in data
        assert "status" in data
        assert "error_message" in data
        assert "metrics" in data
        assert "equity_curve" in data
        assert "drawdown_curve" in data
        assert "trades" in data
        assert "chart_base64" in data

        # Metrics must have required keys
        metrics = data["metrics"]
        assert "total_return_pct" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown_pct" in metrics
        assert "num_trades" in metrics

    def test_error_response_has_all_required_fields(self, client):
        """Error response also includes all required fields."""
        payload = {
            "ticker": "NONEXISTENT.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()

        # All required keys must be present even on error
        assert "run_id" in data
        assert "status" in data
        assert data["status"] == "failed"
        assert "error_message" in data
        assert data["error_message"] is not None
        assert "metrics" in data
        assert "equity_curve" in data
        assert "drawdown_curve" in data
        assert "trades" in data
        assert "chart_base64" in data

    def test_num_trades_equals_len_trades(self, client):
        """FIX #3: num_trades must equal len(trades) array."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        data = response.get_json()

        # Only check if backtest succeeded
        if data["status"] == "completed":
            assert data["metrics"]["num_trades"] == len(data["trades"])


class TestInputValidation:
    """Test HTTP 400 errors for invalid user input."""

    def test_missing_ticker_returns_400(self, client):
        """Missing ticker field returns 400."""
        payload = {
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "run_id" in data
        assert data["status"] == "failed"

    def test_missing_dates_returns_400(self, client):
        """Missing date parameters return 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_null_start_date_returns_400(self, client):
        """FIX #2: null start_date returns 400, not 500."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": None,  # Explicit null
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        # Must be 400 (input error), NOT 500 (system error)
        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "failed"
        assert "start_date" in data["error_message"].lower()

    def test_null_end_date_returns_400(self, client):
        """FIX #2: null end_date returns 400, not 500."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": None,  # Explicit null
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        # Must be 400 (input error), NOT 500 (system error)
        assert response.status_code == 400
        data = response.get_json()
        assert data["status"] == "failed"
        assert "end_date" in data["error_message"].lower()

    def test_empty_string_start_date_returns_400(self, client):
        """FIX #2: Empty string start_date returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "",  # Empty string
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_empty_string_end_date_returns_400(self, client):
        """FIX #2: Empty string end_date returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "",  # Empty string
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_invalid_timeframe_returns_400(self, client):
        """Unsupported timeframe (5m, 1h) returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "timeframe": "5m",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "5m" in data["error_message"].lower() or "timeframe" in data["error_message"].lower()

    def test_longshort_direction_returns_400(self, client):
        """Unsupported direction 'longshort' returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "direction": "longshort",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "longshort" in data["error_message"].lower() or "direction" in data["error_message"].lower()

    def test_negative_fee_rate_returns_400(self, client):
        """Negative fee_rate returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "fee_rate": -0.001,
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_zero_position_size_returns_400(self, client):
        """Zero or negative position_size returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "position_size": 0,
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_start_after_end_returns_400(self, client):
        """start_date > end_date returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2024-01-01",
            "end_date": "2020-01-01",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_unknown_strategy_returns_400(self, client):
        """Unknown strategy returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "UNKNOWN_STRATEGY",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_negative_slippage_bps_returns_400(self, client):
        """FIX #1: Negative slippage_bps returns 400."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "slippage_bps": -10,  # Negative slippage
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "slippage" in data["error_message"].lower()


class TestSlippageContract:
    """FIX #1: Test slippage contract compliance."""

    def test_zero_slippage_bps_means_zero_slippage(self, client):
        """slippage_bps=0 must result in slippage_decimal=0.0"""
        # We verify this by checking that the engine is called with slippage=0.0
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "slippage_bps": 0,  # Zero slippage
        }

        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "error": "Test stopped"  # Stop early
            }
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            # Verify BacktestEngine was called with slippage=0.0
            MockEngine.assert_called_once()
            call_kwargs = MockEngine.call_args[1]
            assert call_kwargs["slippage"] == 0.0  # STRICT: must be exactly 0.0

    def test_default_slippage_bps_is_zero(self, client):
        """Missing slippage_bps defaults to 0, meaning slippage_decimal=0.0"""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            # slippage_bps not provided - should default to 0
        }

        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "error": "Test stopped"
            }
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            MockEngine.assert_called_once()
            call_kwargs = MockEngine.call_args[1]
            assert call_kwargs["slippage"] == 0.0  # Default must be 0.0

    def test_positive_slippage_bps_converts_correctly(self, client):
        """slippage_bps=20 should result in slippage_decimal=0.002"""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "slippage_bps": 20,  # 20 basis points
        }

        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.return_value = {
                "error": "Test stopped"
            }
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            MockEngine.assert_called_once()
            call_kwargs = MockEngine.call_args[1]
            assert call_kwargs["slippage"] == pytest.approx(0.002)  # 20/10000


class TestSharpeRatioCompliance:
    """FIX #5: Test Sharpe Ratio risk-free rate compliance."""

    def test_sharpe_ratio_uses_zero_risk_free_rate(self, client):
        """Sharpe Ratio must be computed with risk_free_rate=0.0"""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Patch PerformanceMetrics.calculate_sharpe_ratio to verify args
        with patch("app.PerformanceMetrics.calculate_sharpe_ratio") as mock_sharpe:
            mock_sharpe.return_value = 1.5  # Return a valid Sharpe ratio

            # We also need to patch other metrics calls
            with patch("app.PerformanceMetrics.calculate_sortino_ratio") as mock_sortino:
                mock_sortino.return_value = 1.2

                with patch("app.PerformanceMetrics.calculate_max_drawdown") as mock_dd:
                    mock_dd.return_value = {
                        "max_drawdown": 0.1,
                        "max_drawdown_pct": 10.0,
                        "max_drawdown_duration": 5
                    }

                    with patch("app.PerformanceMetrics.calculate_win_rate") as mock_wr:
                        mock_wr.return_value = {
                            "win_rate": 55.0,
                            "avg_win": 100,
                            "avg_loss": 80,
                            "profit_factor": 1.25
                        }

                        with patch("app.PerformanceMetrics.calculate_calmar_ratio") as mock_calmar:
                            mock_calmar.return_value = 1.0

                            response = client.post(
                                "/run_backtest",
                                data=json.dumps(payload),
                                content_type="application/json"
                            )

                            # Check if sharpe was called
                            if mock_sharpe.called:
                                # Verify risk_free_rate=0.0 was passed
                                call_kwargs = mock_sharpe.call_args[1]
                                assert "risk_free_rate" in call_kwargs
                                assert call_kwargs["risk_free_rate"] == 0.0


class TestErrorResponseSchema:
    """FIX #4: Test error response schema completeness."""

    def test_400_error_has_chart_base64_null(self, client):
        """HTTP 400 error response must include chart_base64: null"""
        payload = {
            "ticker": "NONEXISTENT.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()

        # chart_base64 key must exist and be null
        assert "chart_base64" in data
        assert data["chart_base64"] is None

    def test_500_error_has_chart_base64_null(self, client):
        """HTTP 500 error response must include chart_base64: null"""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Monkeypatch to simulate system error
        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = RuntimeError("Simulated engine crash")
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 500
            data = response.get_json()

            # chart_base64 key must exist and be null
            assert "chart_base64" in data
            assert data["chart_base64"] is None


class TestSystemErrors:
    """Test HTTP 500 errors for system failures.

    IMPORTANT: System errors are simulated via monkeypatch ONLY.
    No application code modifications for error simulation.
    """

    def test_engine_crash_returns_500(self, client):
        """Simulated engine crash returns 500."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Monkeypatch the BacktestEngine.run method to raise an exception
        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = RuntimeError("Simulated engine crash")
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 500
            data = response.get_json()
            assert "run_id" in data
            assert data["status"] == "failed"
            # Error message should be generic (no stack trace)
            assert "Internal server error" in data["error_message"]

    def test_csv_parse_error_returns_500(self, client):
        """CSV parsing failure returns 500."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Monkeypatch pandas.read_csv to simulate file corruption
        with patch("app.pd.read_csv") as mock_read_csv:
            mock_read_csv.side_effect = Exception("Simulated CSV parse error")

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 500
            data = response.get_json()
            assert data["status"] == "failed"


class TestBackwardCompatibility:
    """Test backward compatibility with existing API."""

    def test_old_request_format_works(self, client):
        """Request without new Day 3.9 fields still works."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            # No initial_capital, fee_rate, slippage_bps, etc.
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        # Should not return 400 for missing optional fields
        # (may be 400 for other reasons like missing data file)
        data = response.get_json()
        assert "run_id" in data

    def test_chart_image_backward_compat(self, client):
        """Response includes both chart_base64 and chart_image keys."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        data = response.get_json()
        # Both keys should exist for backward compatibility
        assert "chart_base64" in data
        # chart_image is only present on success, not on error
        if data["status"] == "completed":
            assert "chart_image" in data


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_returns_ok(self, client):
        """Health endpoint returns status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"


class TestPortfolioCurveOnError:
    """Test portfolio_curve key existence on error responses."""

    def test_400_error_has_portfolio_curve_array(self, client):
        """HTTP 400 error response must include portfolio_curve as array."""
        payload = {
            "ticker": "NONEXISTENT.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()

        # portfolio_curve key must exist
        assert "portfolio_curve" in data
        # portfolio_curve must be an array (empty is acceptable)
        assert isinstance(data["portfolio_curve"], list)

    def test_500_error_has_portfolio_curve_array(self, client):
        """HTTP 500 error response must include portfolio_curve as array."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Monkeypatch to simulate system error
        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = RuntimeError("Simulated engine crash")
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 500
            data = response.get_json()

            # portfolio_curve key must exist
            assert "portfolio_curve" in data
            # portfolio_curve must be an array (empty is acceptable)
            assert isinstance(data["portfolio_curve"], list)

    def test_400_error_has_chart_image_null(self, client):
        """HTTP 400 error response must include chart_image: null for backward compat."""
        payload = {
            "ticker": "NONEXISTENT.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()

        # chart_image key must exist and be null (backward compatibility)
        assert "chart_image" in data
        assert data["chart_image"] is None

    def test_500_error_has_chart_image_null(self, client):
        """HTTP 500 error response must include chart_image: null for backward compat."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Monkeypatch to simulate system error
        with patch("app.BacktestEngine") as MockEngine:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = RuntimeError("Simulated engine crash")
            MockEngine.return_value = mock_instance

            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            assert response.status_code == 500
            data = response.get_json()

            # chart_image key must exist and be null (backward compatibility)
            assert "chart_image" in data
            assert data["chart_image"] is None


class TestSharpeRatioExecutionPath:
    """Test Sharpe Ratio is computed via real execution path, not mock-only."""

    def test_sharpe_ratio_populated_on_successful_backtest(self, client):
        """Sharpe Ratio is populated from engine metrics on successful backtest.

        This test verifies the REAL execution path is exercised,
        not just mocked call verification.
        """
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        data = response.get_json()

        # Only validate if backtest succeeded (data file exists)
        if data["status"] == "completed":
            # Sharpe ratio must be a real number (not mocked)
            sharpe = data["metrics"]["sharpe_ratio"]
            assert isinstance(sharpe, (int, float))
            # Sharpe ratio should be finite (not NaN or Inf)
            import math
            assert math.isfinite(sharpe), f"Sharpe ratio is not finite: {sharpe}"

    def test_sharpe_ratio_uses_zero_risk_free_rate_in_execution(self, client):
        """Verify risk_free_rate=0.0 is passed during actual execution.

        This test monkeypatches the metrics module to capture the actual
        arguments passed, while still allowing the backtest to execute
        through the real code path.
        """
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Track the actual call arguments
        captured_kwargs = {}
        original_calculate_sharpe = None

        def capture_sharpe_call(returns, **kwargs):
            """Wrapper that captures kwargs and calls original."""
            nonlocal captured_kwargs, original_calculate_sharpe
            captured_kwargs = kwargs
            # Call the original function to exercise real path
            return original_calculate_sharpe(returns, **kwargs)

        # Patch at module level to capture actual call
        from backtest import metrics as metrics_module
        original_calculate_sharpe = metrics_module.PerformanceMetrics.calculate_sharpe_ratio

        with patch.object(
            metrics_module.PerformanceMetrics,
            'calculate_sharpe_ratio',
            side_effect=capture_sharpe_call
        ):
            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

            data = response.get_json()

            # Only validate if backtest succeeded and sharpe was called
            if data["status"] == "completed" and captured_kwargs:
                # Verify risk_free_rate=0.0 was explicitly passed
                assert "risk_free_rate" in captured_kwargs, \
                    "risk_free_rate kwarg was not passed to calculate_sharpe_ratio"
                assert captured_kwargs["risk_free_rate"] == 0.0, \
                    f"Expected risk_free_rate=0.0, got {captured_kwargs['risk_free_rate']}"


class TestSafeIso8601UtcParseFailure:
    """Test safe_iso8601_utc returns None on parse failure."""

    def test_unparseable_string_returns_none(self):
        """Unparseable string returns None, not original value."""
        result = safe_iso8601_utc("not-a-valid-date-at-all")
        assert result is None

    def test_none_input_returns_none(self):
        """None input returns None."""
        result = safe_iso8601_utc(None)
        assert result is None

    def test_valid_date_still_works(self):
        """Valid date input still works correctly."""
        result = safe_iso8601_utc("2020-01-15")
        assert result == "2020-01-15T21:00:00+00:00"

    def test_empty_string_returns_none(self):
        """Empty string returns None (unparseable)."""
        result = safe_iso8601_utc("")
        assert result is None


class TestChartsObject:
    """Test charts object in API response (Day 3.9+ drawdown/portfolio charts)."""

    def test_success_response_has_charts_object(self, client):
        """Success response must include charts object."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        data = response.get_json()

        # Charts object must always exist
        assert "charts" in data, "Response must include 'charts' object"

        if data["status"] == "completed":
            charts = data["charts"]
            assert "drawdown_curve_base64" in charts
            assert "portfolio_plot_base64" in charts

    def test_success_charts_have_base64_content(self, client):
        """On success, charts should contain Base64 PNG data."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        data = response.get_json()

        if data["status"] == "completed":
            charts = data["charts"]

            # Drawdown chart should be non-empty Base64
            dd_chart = charts.get("drawdown_curve_base64")
            assert dd_chart is not None, "drawdown_curve_base64 should not be None on success"
            assert dd_chart.startswith("data:image/png;base64,"), \
                "drawdown_curve_base64 should be a Base64 PNG data URI"

            # Portfolio plot should be non-empty Base64
            pf_chart = charts.get("portfolio_plot_base64")
            assert pf_chart is not None, "portfolio_plot_base64 should not be None on success"
            assert pf_chart.startswith("data:image/png;base64,"), \
                "portfolio_plot_base64 should be a Base64 PNG data URI"

    def test_400_error_has_charts_null(self, client):
        """Error response (400) must have charts with null values."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "INVALID_STRATEGY",  # Triggers 400
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()

        assert "charts" in data, "Error response must include 'charts' object"
        charts = data["charts"]
        assert charts["drawdown_curve_base64"] is None
        assert charts["portfolio_plot_base64"] is None

    def test_500_error_has_charts_null(self, client):
        """Error response (500) must have charts with null values."""
        payload = {
            "ticker": "AAPL.csv",
            "strategy": "RSI",
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }

        # Patch to cause internal error
        with patch("app.BacktestEngine.run", side_effect=Exception("Simulated crash")):
            response = client.post(
                "/run_backtest",
                data=json.dumps(payload),
                content_type="application/json"
            )

        assert response.status_code == 500
        data = response.get_json()

        assert "charts" in data, "Error response must include 'charts' object"
        charts = data["charts"]
        assert charts["drawdown_curve_base64"] is None
        assert charts["portfolio_plot_base64"] is None


class TestRenderDrawdownChart:
    """Test render_drawdown_chart adapter function."""

    def test_empty_curve_returns_none(self):
        """Empty drawdown curve returns None."""
        from adapters.adapter import render_drawdown_chart
        result = render_drawdown_chart([])
        assert result is None

    def test_valid_curve_returns_base64(self):
        """Valid drawdown curve returns Base64 PNG."""
        from adapters.adapter import render_drawdown_chart

        curve = [
            {"date": "2020-01-01", "drawdown_pct": 0.0},
            {"date": "2020-01-02", "drawdown_pct": -1.5},
            {"date": "2020-01-03", "drawdown_pct": -3.2},
            {"date": "2020-01-04", "drawdown_pct": -2.0},
            {"date": "2020-01-05", "drawdown_pct": 0.0},
        ]

        result = render_drawdown_chart(curve)
        assert result is not None
        assert result.startswith("data:image/png;base64,")
        # Verify Base64 content is non-empty
        b64_content = result.replace("data:image/png;base64,", "")
        assert len(b64_content) > 100, "Base64 content should be substantial"


class TestRenderPortfolioPlot:
    """Test render_portfolio_plot adapter function."""

    def test_empty_df_returns_none(self):
        """Empty price DataFrame returns None."""
        from adapters.adapter import render_portfolio_plot
        import pandas as pd

        result = render_portfolio_plot(pd.DataFrame(), [])
        assert result is None

    def test_missing_close_column_returns_none(self):
        """DataFrame without Close column returns None."""
        from adapters.adapter import render_portfolio_plot
        import pandas as pd

        df = pd.DataFrame({
            "Open": [100, 101, 102],
            "High": [105, 106, 107],
        }, index=pd.date_range("2020-01-01", periods=3))

        result = render_portfolio_plot(df, [])
        assert result is None

    def test_valid_data_returns_base64(self):
        """Valid price data returns Base64 PNG."""
        from adapters.adapter import render_portfolio_plot
        import pandas as pd

        df = pd.DataFrame({
            "Close": [100, 105, 110, 108, 115],
        }, index=pd.date_range("2020-01-01", periods=5))

        trades = [
            {
                "trade_no": 0,
                "entry_timestamp": "2020-01-02T21:00:00+00:00",
                "exit_timestamp": "2020-01-04T21:00:00+00:00",
                "pnl_pct": 3.5
            }
        ]

        result = render_portfolio_plot(df, trades)
        assert result is not None
        assert result.startswith("data:image/png;base64,")
        # Verify Base64 content is non-empty
        b64_content = result.replace("data:image/png;base64,", "")
        assert len(b64_content) > 100, "Base64 content should be substantial"


# ═══════════════════════════════════════════════════════════════
# DETERMINISTIC SUCCESS PATH TESTS
# ═══════════════════════════════════════════════════════════════

def _build_mock_engine_result():
    """Build a deterministic engine result for testing success path.

    Returns a dict mimicking BacktestEngine.run() output with:
    - equity_curve data (via portfolio_history)
    - trades (buy/sell pairs for normalization)
    - metrics needed for response building

    NOTE: Trade dicts must include 'effective_price' for PerformanceMetrics.calculate_win_rate
    """
    # Build portfolio_history DataFrame (source for equity_curve)
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    portfolio_df = pd.DataFrame({
        "value": [100000, 100500, 101200, 100800, 101500, 102000, 101000, 102500, 103000, 103500],
        "cash": [90000, 90000, 90000, 100000, 90000, 90000, 100000, 90000, 90000, 103500],
        "holdings_value": [10000, 10500, 11200, 800, 11500, 12000, 1000, 12500, 13000, 0],
    }, index=dates)

    # Build raw trades (buy/sell pairs as engine outputs)
    # NOTE: effective_price is required by PerformanceMetrics.calculate_win_rate
    raw_trades = [
        # Trade 1: Buy on day 1, sell on day 4 (profit)
        {"date": "2020-01-01", "action": "buy", "quantity": 100, "price": 100.0,
         "effective_price": 100.10, "commission": 10.0, "total_cost": 10010.0},
        {"date": "2020-01-04", "action": "sell", "quantity": 100, "price": 108.0,
         "effective_price": 107.89, "commission": 10.8, "net_proceeds": 10778.2},
        # Trade 2: Buy on day 5, sell on day 7 (loss)
        {"date": "2020-01-05", "action": "buy", "quantity": 100, "price": 110.0,
         "effective_price": 110.11, "commission": 11.0, "total_cost": 11011.0},
        {"date": "2020-01-07", "action": "sell", "quantity": 100, "price": 105.0,
         "effective_price": 104.90, "commission": 10.5, "net_proceeds": 10479.5},
        # Trade 3: Buy on day 8, sell on day 10 (profit)
        {"date": "2020-01-08", "action": "buy", "quantity": 100, "price": 115.0,
         "effective_price": 115.12, "commission": 11.5, "total_cost": 11512.0},
        {"date": "2020-01-10", "action": "sell", "quantity": 100, "price": 120.0,
         "effective_price": 119.88, "commission": 12.0, "net_proceeds": 11976.0},
    ]

    return {
        "portfolio_history": portfolio_df,
        "trades": raw_trades,
        "total_return": 0.035,  # 3.5%
        "total_return_pct": 3.5,
        "initial_capital": 100000,
        "final_value": 103500,
    }


def _build_mock_price_df():
    """Build a deterministic price DataFrame for chart rendering."""
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    return pd.DataFrame({
        "Open": [99, 100, 101, 100, 102, 103, 101, 104, 105, 106],
        "High": [101, 102, 103, 102, 104, 105, 103, 106, 107, 108],
        "Low": [98, 99, 100, 99, 101, 102, 100, 103, 104, 105],
        "Close": [100, 101, 102, 101, 103, 104, 102, 105, 106, 107],
        "close": [100, 101, 102, 101, 103, 104, 102, 105, 106, 107],  # lowercase alias
        "Volume": [1000000] * 10,
    }, index=dates)


@pytest.fixture
def deterministic_backtest_patches():
    """Fixture providing all patches needed for deterministic success-path tests.

    Patches:
    - app.os.path.isfile: Always returns True (bypasses file existence check)
    - app.pd.read_csv: Returns controlled price DataFrame
    - app.BacktestEngine: Returns deterministic backtest result

    This ensures tests are fully isolated from filesystem state.
    """
    mock_result = _build_mock_engine_result()
    mock_df = _build_mock_price_df().reset_index()
    mock_df = mock_df.rename(columns={"index": "Date"})

    with patch("app.os.path.isfile", return_value=True):
        with patch("app.pd.read_csv", return_value=mock_df):
            with patch("app.BacktestEngine") as MockEngineClass:
                mock_engine = MagicMock()
                mock_engine.run.return_value = mock_result
                MockEngineClass.return_value = mock_engine
                yield


class TestDeterministicSuccessPath:
    """Deterministic success path tests for /run_backtest.

    These tests patch the backtest execution (engine.run) to return
    a fixed result, ensuring:
    1. Real chart renderers are exercised (not mocked)
    2. Response contains valid Base64 PNG charts
    3. No dependence on external data availability or filesystem state

    IMPORTANT: We patch ONLY the engine result and file I/O, NOT the chart renderers.
    This validates the full integration from adapter layer to chart output.
    """

    def test_charts_generated_on_deterministic_success(self, client, deterministic_backtest_patches):
        """Charts are generated with valid Base64 when engine returns success.

        This test ensures:
        - drawdown_curve_base64 is a valid PNG data URI
        - portfolio_plot_base64 is a valid PNG data URI
        - Real chart rendering code is exercised
        """
        payload = {
            "ticker": "TEST.csv",  # Arbitrary name; file existence is mocked
            "strategy": "RSI",
            "params": {"period": 14, "oversold": 30, "overbought": 70},
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
            "initial_capital": 100000,
            "fee_rate": 0.001,
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.get_json()

        # Verify status is completed
        assert data["status"] == "completed", f"Expected completed, got {data['status']}"

        # Verify charts object exists
        assert "charts" in data, "Response must include 'charts' object"
        charts = data["charts"]

        # CRITICAL ASSERTIONS: Charts must be real Base64 PNGs
        dd_chart = charts.get("drawdown_curve_base64")
        assert dd_chart is not None, "drawdown_curve_base64 must not be None"
        assert isinstance(dd_chart, str), "drawdown_curve_base64 must be a string"
        assert dd_chart.startswith("data:image/png;base64,"), \
            f"drawdown_curve_base64 must start with 'data:image/png;base64,', got: {dd_chart[:50]}"
        # Verify substantial content (not empty)
        dd_b64_content = dd_chart.replace("data:image/png;base64,", "")
        assert len(dd_b64_content) > 100, \
            f"drawdown_curve_base64 content too short: {len(dd_b64_content)} chars"

        pf_chart = charts.get("portfolio_plot_base64")
        assert pf_chart is not None, "portfolio_plot_base64 must not be None"
        assert isinstance(pf_chart, str), "portfolio_plot_base64 must be a string"
        assert pf_chart.startswith("data:image/png;base64,"), \
            f"portfolio_plot_base64 must start with 'data:image/png;base64,', got: {pf_chart[:50]}"
        # Verify substantial content (not empty)
        pf_b64_content = pf_chart.replace("data:image/png;base64,", "")
        assert len(pf_b64_content) > 100, \
            f"portfolio_plot_base64 content too short: {len(pf_b64_content)} chars"

    def test_trades_normalized_on_deterministic_success(self, client, deterministic_backtest_patches):
        """Trades are properly normalized and num_trades matches array length."""
        payload = {
            "ticker": "TEST.csv",  # Arbitrary name; file existence is mocked
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()

        # Verify trades array
        trades = data["trades"]
        assert isinstance(trades, list), "trades must be a list"
        assert len(trades) == 3, f"Expected 3 paired trades, got {len(trades)}"

        # Verify num_trades consistency
        assert data["metrics"]["num_trades"] == len(trades), \
            "num_trades must equal len(trades)"

        # Verify trade schema
        for trade in trades:
            assert "trade_no" in trade
            assert "entry_timestamp" in trade
            assert "exit_timestamp" in trade
            assert "pnl_abs" in trade
            assert "pnl_pct" in trade

    def test_equity_and_drawdown_curves_on_deterministic_success(self, client, deterministic_backtest_patches):
        """Equity and drawdown curves are properly generated."""
        payload = {
            "ticker": "TEST.csv",  # Arbitrary name; file existence is mocked
            "strategy": "RSI",
            "params": {},
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
        }

        response = client.post(
            "/run_backtest",
            data=json.dumps(payload),
            content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()

        # Verify equity_curve
        equity_curve = data["equity_curve"]
        assert isinstance(equity_curve, list), "equity_curve must be a list"
        assert len(equity_curve) > 0, "equity_curve must not be empty"
        for point in equity_curve:
            assert "date" in point
            assert "equity" in point

        # Verify drawdown_curve
        drawdown_curve = data["drawdown_curve"]
        assert isinstance(drawdown_curve, list), "drawdown_curve must be a list"
        assert len(drawdown_curve) == len(equity_curve), \
            "drawdown_curve length must match equity_curve"
        for point in drawdown_curve:
            assert "date" in point
            assert "drawdown_pct" in point
            # Drawdown values must be non-positive
            assert point["drawdown_pct"] <= 0, \
                f"Drawdown must be non-positive, got {point['drawdown_pct']}"


# ═══════════════════════════════════════════════════════════════
# FIGURE MEMORY LEAK PREVENTION TESTS
# ═══════════════════════════════════════════════════════════════

class TestFigureLeakPrevention:
    """Test that chart rendering functions properly close matplotlib figures.

    Memory leak prevention is critical for long-running server processes.
    These tests verify that render_drawdown_chart() and render_portfolio_plot()
    do not leave open figures after execution.

    Verification method:
    1. Record open figure count before calling the function
    2. Call the rendering function
    3. Record open figure count after
    4. Assert no new figures remain open
    """

    def test_render_drawdown_chart_closes_figure(self):
        """render_drawdown_chart leaves no open figures after execution."""
        # Minimal valid drawdown curve (5 points)
        drawdown_curve = [
            {"date": "2020-01-01", "drawdown_pct": 0.0},
            {"date": "2020-01-02", "drawdown_pct": -2.5},
            {"date": "2020-01-03", "drawdown_pct": -5.0},
            {"date": "2020-01-04", "drawdown_pct": -3.0},
            {"date": "2020-01-05", "drawdown_pct": 0.0},
        ]

        # Record figures before
        before_fignums = set(plt.get_fignums())

        # Call the function - should render and close figure
        result = render_drawdown_chart(drawdown_curve)

        # Record figures after
        after_fignums = set(plt.get_fignums())

        # Verify chart was generated successfully
        assert result is not None, "render_drawdown_chart should return a result"
        assert result.startswith("data:image/png;base64,"), \
            "Result should be a Base64 PNG data URI"

        # CRITICAL: No new figures should remain open
        new_figures = after_fignums - before_fignums
        assert new_figures == set(), \
            f"render_drawdown_chart left open figures: {new_figures}"

    def test_render_drawdown_chart_closes_figure_on_large_input(self):
        """render_drawdown_chart closes figures even with large data."""
        # Larger drawdown curve (100 points)
        drawdown_curve = [
            {"date": f"2020-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
             "drawdown_pct": -float(i % 10)}
            for i in range(100)
        ]

        before_fignums = set(plt.get_fignums())
        result = render_drawdown_chart(drawdown_curve)
        after_fignums = set(plt.get_fignums())

        assert result is not None
        assert after_fignums == before_fignums, \
            f"Figures leaked: {after_fignums - before_fignums}"

    def test_render_portfolio_plot_closes_figure(self):
        """render_portfolio_plot leaves no open figures after execution."""
        # Minimal valid price DataFrame (5 points)
        price_df = pd.DataFrame({
            "Close": [100.0, 102.0, 101.0, 104.0, 106.0],
        }, index=pd.date_range("2020-01-01", periods=5, freq="D"))

        # Minimal trades list (1 completed trade)
        trades = [
            {
                "trade_no": 0,
                "entry_timestamp": "2020-01-02T21:00:00+00:00",
                "exit_timestamp": "2020-01-04T21:00:00+00:00",
                "pnl_pct": 2.5,
            }
        ]

        before_fignums = set(plt.get_fignums())
        result = render_portfolio_plot(price_df, trades)
        after_fignums = set(plt.get_fignums())

        # Verify chart was generated
        assert result is not None, "render_portfolio_plot should return a result"
        assert result.startswith("data:image/png;base64,"), \
            "Result should be a Base64 PNG data URI"

        # CRITICAL: No new figures should remain open
        new_figures = after_fignums - before_fignums
        assert new_figures == set(), \
            f"render_portfolio_plot left open figures: {new_figures}"

    def test_render_portfolio_plot_closes_figure_with_multiple_trades(self):
        """render_portfolio_plot closes figures with multiple trades."""
        price_df = pd.DataFrame({
            "Close": [100, 102, 104, 103, 105, 107, 106, 108, 110, 112],
        }, index=pd.date_range("2020-01-01", periods=10, freq="D"))

        # Multiple trades
        trades = [
            {
                "trade_no": 0,
                "entry_timestamp": "2020-01-02T21:00:00+00:00",
                "exit_timestamp": "2020-01-04T21:00:00+00:00",
                "pnl_pct": 2.0,
            },
            {
                "trade_no": 1,
                "entry_timestamp": "2020-01-05T21:00:00+00:00",
                "exit_timestamp": "2020-01-07T21:00:00+00:00",
                "pnl_pct": -1.5,
            },
            {
                "trade_no": 2,
                "entry_timestamp": "2020-01-08T21:00:00+00:00",
                "exit_timestamp": "2020-01-10T21:00:00+00:00",
                "pnl_pct": 3.0,
            },
        ]

        before_fignums = set(plt.get_fignums())
        result = render_portfolio_plot(price_df, trades)
        after_fignums = set(plt.get_fignums())

        assert result is not None
        assert after_fignums == before_fignums, \
            f"Figures leaked: {after_fignums - before_fignums}"

    def test_render_drawdown_chart_closes_figure_on_empty_input(self):
        """render_drawdown_chart handles empty input without leaking."""
        before_fignums = set(plt.get_fignums())
        result = render_drawdown_chart([])  # Empty input
        after_fignums = set(plt.get_fignums())

        # Empty input should return None (no chart)
        assert result is None

        # No figures should be left open
        assert after_fignums == before_fignums, \
            f"Figures leaked on empty input: {after_fignums - before_fignums}"

    def test_render_portfolio_plot_closes_figure_on_empty_df(self):
        """render_portfolio_plot handles empty DataFrame without leaking."""
        before_fignums = set(plt.get_fignums())
        result = render_portfolio_plot(pd.DataFrame(), [])
        after_fignums = set(plt.get_fignums())

        # Empty input should return None
        assert result is None

        # No figures should be left open
        assert after_fignums == before_fignums, \
            f"Figures leaked on empty input: {after_fignums - before_fignums}"

    def test_consecutive_renders_do_not_accumulate_figures(self):
        """Multiple consecutive renders do not accumulate open figures."""
        drawdown_curve = [
            {"date": "2020-01-01", "drawdown_pct": 0.0},
            {"date": "2020-01-02", "drawdown_pct": -5.0},
            {"date": "2020-01-03", "drawdown_pct": 0.0},
        ]

        price_df = pd.DataFrame({
            "Close": [100.0, 102.0, 104.0],
        }, index=pd.date_range("2020-01-01", periods=3, freq="D"))

        trades = [{"trade_no": 0, "entry_timestamp": "2020-01-01T21:00:00+00:00",
                   "exit_timestamp": "2020-01-02T21:00:00+00:00", "pnl_pct": 1.0}]

        before_fignums = set(plt.get_fignums())

        # Call multiple times
        for _ in range(5):
            render_drawdown_chart(drawdown_curve)
            render_portfolio_plot(price_df, trades)

        after_fignums = set(plt.get_fignums())

        # No accumulation of figures
        assert after_fignums == before_fignums, \
            f"Figures accumulated after consecutive renders: {after_fignums - before_fignums}"
