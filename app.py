"""
Flask Web Dashboard for Stock Backtesting Platform
Controller layer only -- does NOT modify engine logic.
"""

import matplotlib
matplotlib.use("Agg")

import io
import os
import uuid
import base64
import logging

import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from backtest.engine import BacktestEngine
from backtest.metrics import PerformanceMetrics
from extracted.features.technical_indicators import TechnicalIndicators
from rules.technical_rules import RSIRule, MACDRule, RsiMacdRule
from rules.base_rule import RuleMetadata

from extensions import db
from models import Strategy

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Database configuration ---
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///strategies.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

STRATEGY_MAP = {
    "RSI": {
        "name": "RSI (Relative Strength Index)",
        "default_params": {"period": 14, "oversold": 30, "overbought": 70},
    },
    "MACD": {
        "name": "MACD (Moving Average Convergence Divergence)",
        "default_params": {"fast": 12, "slow": 26, "signal": 9},
    },
    "RSI_MACD": {
        "name": "RSI + MACD (Combined)",
        "default_params": {
            "rsi_period": 14, "oversold": 30, "overbought": 70,
            "fast": 12, "slow": 26, "signal": 9,
        },
    },
}


def _scan_tickers():
    """Dynamically scan data/ directory for available CSV files."""
    if not os.path.isdir(DATA_DIR):
        return []
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
    return files


def _build_strategy(strategy_key, rule, df):
    """Build a strategy_func wrapper that bridges Rule.evaluate() -> engine signal."""
    def strategy_func(row):
        signal = rule.evaluate(row)
        if signal.action in ("buy", "sell"):
            return signal.action
        return None
    return strategy_func


def _render_chart(portfolio_df, ticker, run_id):
    """Render portfolio value chart to Base64 PNG string. No disk I/O."""
    fig = None
    try:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(portfolio_df.index, portfolio_df["value"],
                color="#ff9900", linewidth=1.0)
        ax.fill_between(portfolio_df.index, portfolio_df["value"],
                        alpha=0.08, color="#ff9900")
        ax.set_title(f"{ticker}", fontsize=11, color="#ff9900",
                     fontfamily="monospace", loc="left", pad=8)
        ax.set_xlabel("")
        ax.set_ylabel("VALUE ($)", color="#666666", fontsize=8,
                      fontfamily="monospace")
        ax.tick_params(colors="#555555", labelsize=8)
        ax.set_facecolor("#000000")
        fig.patch.set_facecolor("#000000")
        ax.grid(True, alpha=0.15, color="#1e1e1e", linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_color("#1e1e1e")
        fig.tight_layout(pad=1.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    finally:
        if fig:
            plt.close(fig)


@app.route("/")
def index():
    tickers = _scan_tickers()
    strategies = {k: v["name"] for k, v in STRATEGY_MAP.items()}
    return render_template("index.html", tickers=tickers, strategies=strategies)


@app.route("/run_backtest", methods=["POST"])
def run_backtest():
    run_id = str(uuid.uuid4())
    logger.info(f"[run_id={run_id}] Backtest request received")

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "Request body is empty"}), 400

        ticker_file = data.get("ticker")
        strategy_key = data.get("strategy")
        params = data.get("params", {})

        # --- Mandatory date parameters ---
        if "start_date" not in data or "end_date" not in data:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "Missing required parameters: start_date, end_date"}), 400

        # --- Input validation (400 errors) ---
        if not ticker_file:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "Missing 'ticker' field"}), 400

        # Sanitize filename to prevent path traversal
        ticker_file = secure_filename(ticker_file)

        if strategy_key not in STRATEGY_MAP:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": f"Unknown strategy: {strategy_key}"}), 400

        csv_path = os.path.join(DATA_DIR, ticker_file)
        if not os.path.isfile(csv_path):
            return jsonify({"status": "error", "run_id": run_id,
                            "message": f"Data file not found: {ticker_file}"}), 400

        ticker_name = ticker_file.replace(".csv", "")
        logger.info(f"[run_id={run_id}] Running {strategy_key} on {ticker_name}")

        # --- Load CSV + Date conversion & timezone normalization ---
        try:
            df = pd.read_csv(csv_path)
            df["Date"] = pd.to_datetime(df["Date"])
            df["Date"] = df["Date"].dt.tz_localize(None)
        except Exception as e:
            logger.exception(f"[run_id={run_id}] Failed to load or parse CSV data")
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "Failed to load or parse CSV data"}), 500

        # --- Date range filtering ---
        try:
            start_date = pd.Timestamp(data["start_date"])
        except ValueError:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": f"Invalid start_date format: {data['start_date']}"}), 400

        try:
            end_date = pd.Timestamp(data["end_date"])
        except ValueError:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": f"Invalid end_date format: {data['end_date']}"}), 400

        if start_date > end_date:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "start_date must be before end_date"}), 400

        df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]

        if df.empty:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": "No data in selected date range"}), 400

        df = df.set_index("Date")

        # --- Calculate indicators & build rule ---
        if strategy_key == "RSI":
            period = int(params.get("period", 14))
            oversold = float(params.get("oversold", 30))
            overbought = float(params.get("overbought", 70))
            df["rsi"] = TechnicalIndicators.rsi(df["close"], period=period)
            meta = RuleMetadata(rule_id=f"WEB_RSI_{run_id[:8]}",
                                name="RSI Strategy", description="RSI Web",
                                source="technical")
            rule = RSIRule(metadata=meta, period=period,
                          oversold=oversold, overbought=overbought)

        elif strategy_key == "MACD":
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            sig = int(params.get("signal", 9))
            macd_line, signal_line, histogram = TechnicalIndicators.macd(
                df["close"], fast=fast, slow=slow, signal=sig)
            df["macd"] = macd_line
            df["macd_signal"] = signal_line
            df["macd_histogram"] = histogram
            meta = RuleMetadata(rule_id=f"WEB_MACD_{run_id[:8]}",
                                name="MACD Strategy", description="MACD Web",
                                source="technical")
            rule = MACDRule(metadata=meta)

        elif strategy_key == "RSI_MACD":
            rsi_period = int(params.get("rsi_period", 14))
            oversold = float(params.get("oversold", 30))
            overbought = float(params.get("overbought", 70))
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            sig = int(params.get("signal", 9))

            df["rsi"] = TechnicalIndicators.rsi(df["close"], period=rsi_period)
            macd_line, signal_line, histogram = TechnicalIndicators.macd(
                df["close"], fast=fast, slow=slow, signal=sig)
            df["macd"] = macd_line
            df["macd_signal"] = signal_line
            df["macd_histogram"] = histogram

            meta = RuleMetadata(rule_id=f"WEB_RSI_MACD_{run_id[:8]}",
                                name="RSI+MACD Strategy", description="RSI+MACD Web",
                                source="technical")
            rule = RsiMacdRule(metadata=meta, rsi_period=rsi_period,
                               rsi_oversold=oversold, rsi_overbought=overbought,
                               macd_fast=fast, macd_slow=slow, macd_signal=sig)

        # --- Run backtest (engine untouched) ---
        strategy_func = _build_strategy(strategy_key, rule, df)
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(df, strategy_func, ticker=ticker_name)

        if "error" in result:
            return jsonify({"status": "error", "run_id": run_id,
                            "message": result["error"]}), 400

        # --- Performance metrics (from existing PerformanceMetrics) ---
        full_report = PerformanceMetrics.generate_full_report(result)

        # --- Chart (in-memory Base64) ---
        chart_b64 = _render_chart(result["portfolio_history"], ticker_name, run_id)

        # --- Build response using engine-returned values only ---
        response = {
            "status": "success",
            "run_id": run_id,
            "metrics": {
                "ticker": ticker_name,
                "initial_capital": float(result["initial_capital"]),
                "final_value": float(result["final_value"]),
                "total_return_pct": float(result["total_return_pct"]),
                "num_trades": int(result["num_trades"]),
                "win_rate": float(result["win_rate"]),
                "sharpe_ratio": float(full_report["risk_metrics"]["sharpe_ratio"]),
                "sortino_ratio": float(full_report["risk_metrics"]["sortino_ratio"]),
                "max_drawdown_pct": float(full_report["risk_metrics"]["max_drawdown_pct"]),
                "calmar_ratio": float(full_report["risk_metrics"]["calmar_ratio"]),
                "profit_factor": float(full_report["trading_metrics"]["profit_factor"]),
            },
            "chart_image": chart_b64,
        }

        logger.info(f"[run_id={run_id}] Backtest completed: "
                     f"return={result['total_return_pct']:.2f}%")
        return jsonify(response), 200

    except Exception as e:
        logger.exception(f"[run_id={run_id}] Unhandled error")
        return jsonify({"status": "error", "run_id": run_id,
                        "message": "Internal server error"}), 500


@app.route("/api/strategies", methods=["GET"])
def get_strategies():
    strategies = Strategy.query.order_by(Strategy.created_at.desc()).all()
    return jsonify([s.to_dict() for s in strategies]), 200


@app.route("/api/strategies", methods=["POST"])
def create_strategy():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body is empty"}), 400

    name = data.get("name")
    type_ = data.get("type")
    params = data.get("params")

    if not name or not type_ or params is None:
        return jsonify({"status": "error",
                        "message": "Missing required fields: name, type, params"}), 400

    strategy = Strategy(name=name, type=type_, params=params)
    try:
        db.session.add(strategy)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "error",
                        "message": "Strategy name already exists"}), 409
    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to save strategy")
        return jsonify({"status": "error",
                        "message": "Database error"}), 500

    return jsonify(strategy.to_dict()), 201


@app.route("/api/strategies/<int:strategy_id>", methods=["DELETE"])
def delete_strategy(strategy_id):
    strategy = db.session.get(Strategy, strategy_id)
    if not strategy:
        return jsonify({"status": "error", "message": "Strategy not found"}), 404

    try:
        db.session.delete(strategy)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to delete strategy")
        return jsonify({"status": "error", "message": "Database error"}), 500

    return jsonify({"status": "success", "message": "Strategy deleted"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug)
