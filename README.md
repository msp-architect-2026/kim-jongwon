# Stock Backtesting Platform (Kubernetes-Native Architecture)

`Python 3.11` | `Flask` | `SQLAlchemy` | `Docker (Planned)` | `Kubernetes (Planned)`

## Description

Stateless web-based stock backtesting platform designed for Kubernetes Job-based execution.
Each backtest runs as an independent unit with reproducible results. Strategy presets are
persisted via SQLAlchemy ORM (SQLite for local development, MySQL for production).

The backtest engine is treated as **immutable legacy code** — all new functionality is added
through wrapper/adapter patterns without modifying core engine logic.

## Key Features (Day 3)

- **Engine Immutability**: Core backtest engine (`backtest/engine.py`) is never modified. All extensions use wrapper patterns.
- **Strategy Persistence**: Save/load/delete strategy presets via REST API backed by SQLAlchemy ORM.
- **Interactive Charts**: Matplotlib Agg backend renders portfolio charts as Base64 PNG — no disk I/O, fully stateless.
- **Date Range Filtering**: Filter backtest data by start/end date with timezone normalization.
- **Supported Strategies**:
  - RSI (Relative Strength Index)
  - MACD (Moving Average Convergence Divergence)
  - RSI + MACD (Combined)

## Quick Start (Local Development)

```bash
pip install -r requirements.txt
python app.py
```

Access the dashboard at: **http://localhost:5000**

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web dashboard |
| `POST` | `/run_backtest` | Execute backtest |
| `GET` | `/api/strategies` | List saved presets |
| `POST` | `/api/strategies` | Save a preset |
| `DELETE` | `/api/strategies/<id>` | Delete a preset |
| `GET` | `/health` | Health check |

## Project Structure

```
stock_backtest/
├── app.py                  # Flask application (controller layer)
├── extensions.py           # SQLAlchemy instance (circular import safe)
├── models.py               # Strategy ORM model
├── requirements.txt        # Python dependencies
├── CLAUDE.md               # Project rules & architecture spec
├── backtest/
│   ├── engine.py           # BacktestEngine (IMMUTABLE)
│   └── metrics.py          # PerformanceMetrics
├── rules/
│   ├── base_rule.py        # BaseRule, Signal, RuleMetadata
│   ├── technical_rules.py  # RSI, MACD, RSI+MACD rules
│   ├── paper_rules.py      # Academic strategy rules
│   ├── rule_validator.py   # Rule validation utilities
│   └── optimizer.py        # Parameter grid search
├── extracted/features/
│   └── technical_indicators.py  # SMA, EMA, RSI, MACD, BB, ATR, etc.
├── scripts/
│   ├── verify_mvp.py       # E2E verification (13 checks)
│   └── ...                 # Config, data loader, QA utilities
├── templates/
│   └── index.html          # Bootstrap 5 dark mode dashboard
└── data/
    └── AAPL.csv            # Demo OHLCV data
```

## Roadmap

| Phase | Status |
|-------|--------|
| Day 1-2: Core engine & rules | Done |
| Day 3: Flask web dashboard + strategy persistence | Done |
| Day 4: Dockerization (multi-stage build) | Planned |
| Day 5: Kubernetes + MySQL deployment | Planned |
| Day 6: Web → K8s Job integration | Planned |

## Constraints

- **Engine immutability**: `backtest/engine.py` must never be modified.
- **Stateless web**: Flask controller writes nothing to local filesystem. Charts are Base64 in-memory.
- **Environment-based config**: All secrets and settings via environment variables.
- **Observability**: Every backtest tagged with `run_id` (UUID4) in all log lines.

See [CLAUDE.md](CLAUDE.md) for the full architecture specification and strict rules.
