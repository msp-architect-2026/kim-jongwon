# CLAUDE.md -- Stock Backtesting Platform

## 1. Project Overview

| 항목 | 내용 |
|---|---|
| **Project Name** | Kubernetes-based Stock Backtesting Platform |
| **Timeline** | 16일 (2026-02-04 ~ 2026-02-19) |
| **Purpose** | 강의 과제 + 클라우드 엔지니어링 면접 포트폴리오 |
| **Core Goal** | 검증 완료된 Python 백테스트 엔진을 Docker 컨테이너로 감싸고, Kubernetes Job으로 실행하는 클라우드 네이티브 플랫폼 |

**Core Values:**

| Value | Meaning |
|---|---|
| **Scalability** | 각 백테스트는 독립적인 K8s Job으로 실행. 수평 확장은 인프라 레벨에서 해결 |
| **Stateless Design** | Web 계층은 로컬 파일시스템에 의존하지 않음. 결과는 DB 또는 Base64 인라인 반환 |
| **Reproducibility** | 동일 입력(ticker, rule, params, date range)은 반드시 동일 출력 생성 |
| **GitOps** | 모든 K8s 매니페스트는 `k8s/` 디렉터리에 존재. 레포가 인프라의 단일 진실 공급원 |

---

## 2. Project Status

**Current Phase:** Day 4 (2026-02-07) — Ready for Dockerization & Kubernetes

| Phase | Status | Scope |
|---|---|---|
| Day 1-2 | **✅ Completed** | Core engine verification, rules library, technical indicators, MVP pipeline |
| Day 3 | **✅ Completed** | Flask app structure (MVC), immutable engine integration, strategy persistence (SQLite + SQLAlchemy), core web routes & API contracts (`/run_backtest`, `/api/strategies`, `/health`) |
| Day 3.9 | **✅ Completed** | Advanced UI: VectorBT-style 5-tab dashboard, extended JSON schemas, adapter-layer metrics, portfolio visualization refactor (separate Orders & Trade PnL charts), cumulative return chart |
| Day 4 | **📋 Planned** | Dockerization (`Dockerfile`, `docker-compose.yml`, `.env.example`, health check) |
| Day 5 | **📋 Planned** | Kubernetes + MySQL (StatefulSet, Deployment, ConfigMap, Secret) |
| Day 6 | **📋 Planned** | Web → K8s Job integration (worker entrypoint, job launcher, status polling) |

**Implemented APIs:**

| Method | Path | Status |
|---|---|---|
| `GET` | `/` | ✅ Implemented |
| `POST` | `/run_backtest` | ✅ Implemented |
| `GET` | `/api/strategies` | ✅ Implemented |
| `POST` | `/api/strategies` | ✅ Implemented |
| `DELETE` | `/api/strategies/<id>` | ✅ Implemented |
| `GET` | `/health` | ✅ Implemented |

---

## 3. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | Python 3.11 Slim | `python:3.11-slim` Docker base image |
| Package Mgmt | pip + requirements.txt | Poetry/Pipenv 사용 금지 |
| Web Framework | Flask (sync) | Gunicorn 워커; 비동기 불필요 |
| **Frontend** | **Jinja2 + Bootstrap 5** | **Template rendering only. NO React/Vue/SPA frameworks** |
| ORM | Flask-SQLAlchemy | SQLite (local dev) → MySQL (production) |
| Data Processing | Pandas, NumPy | 기존 사용 중 |
| Visualization | Matplotlib (**Agg** backend) | 서버 환경 필수; GUI 의존성 없음 |
| Containerization | Docker | Multi-stage build |
| Orchestration | Kubernetes | Job(Worker), Deployment(Web), Service |
| Database | MySQL 8.0 | K8s StatefulSet + PVC |

---

## 4. UI Specification (Day 3.9+) — VectorBT-Style Dashboard

This section defines the **data contracts and UI expectations** for the advanced dashboard.

### Data Flow Overview
```
User Input (Backtesting Controls)
  ↓
POST /run_backtest (JSON Request)
  ↓
Flask Controller
  ↓
Backtest Engine (immutable)
  → Outputs: equity_curve, trades, positions
  ↓
Adapter Layer (post-processing)
  → Derives: drawdown_curve, portfolio_curve
  → Computes: win_rate, profit_factor, exposure, etc.
  → Generates: Base64 PNG charts (optional)
  ↓
JSON Response (extended schema)
  ↓
Frontend UI (5 tabs)
  → Stats | Equity | Drawdown | Portfolio | Trades
```

Note: `positions` represent engine-level position state and may be used directly or aggregated downstream for portfolio-level visualizations.

---

### Backtesting Controls (Input UI)

The backtesting form exposes the following inputs:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| Ticker | string | "AAPL" | Stock symbol |
| Start Date | date | - | YYYY-MM-DD format |
| End Date | date | - | YYYY-MM-DD format |
| Rule | dropdown | "RSI" | Options: RSI, MACD, RSI+MACD |
| Initial Capital | number | 100000 | Starting portfolio value |
| Fee Rate | number | 0.001 | Decimal fraction (0.001 = 0.1% per trade) |
| Slippage | number | 0 | Basis points (not implemented Day 3.9) |
| Position Size | number | 10000 | Amount per trade |
| Size Type | dropdown | "value" | Options: "value" (dollars) or "percent" (%) |
| Direction | dropdown | "longonly" | Options: "longonly" or "longshort" |
| Timeframe | dropdown | "1d" | Daily only (Day 3.9); "5m" and "1h" are Phase 2 |


---

### Dashboard Tabs (Data Contracts)

#### Tab A: Backtesting Stats

Displays summary KPI cards.

**Required KPIs (Day 3.9):**
- Total Return (%)
- Sharpe Ratio
- Max Drawdown (%)
- Number of Trades

**Enhanced KPIs (Phase 2):**
- CAGR: `((final_equity / initial_capital) ^ (1 / years)) - 1`
- Volatility: `std(daily_returns) * sqrt(252)` (annualized)
- Win Rate: `(profitable_trades / total_trades) * 100`
- Average Trade Return: `mean(trade_pnl_pct)`
- Exposure %: `(days_in_market / total_days) * 100`
- Profit Factor: `total_profit / abs(total_loss)`

Formulas are **for documentation only** (not prescriptive implementation).

Sharpe Ratio is computed using daily returns, assuming a zero risk-free rate,
and annualized by multiplying by sqrt(252).

---

#### Tab B: List of Trades

Displays detailed trade history in a table.

**Trade Schema:**

| Field | Type | Description |
|-------|------|-------------|
| trade_no | int | 0-indexed sequence |
| side | string | "BUY" or "SELL" |
| size | int | Number of shares |
| entry_timestamp | ISO8601 | Format: `YYYY-MM-DDTHH:MM:SS+00:00` (UTC) |
| entry_price | float | Entry price (2 decimals) |
| entry_fees | float | Fee: `entry_price * size * fee_rate` |
| exit_timestamp | ISO8601 | Exit time (UTC) |
| exit_price | float | Exit price (2 decimals) |
| exit_fees | float | Fee: `exit_price * size * fee_rate` |
| pnl_abs | float | P/L: `(exit_price - entry_price) * size - entry_fees - exit_fees`|
| pnl_pct | float | Return: `pnl_abs / (entry_price * size) * 100` |
| holding_period | float | Days: `(exit_ts - entry_ts).total_seconds() / 86400` |

**Timestamp Convention:**
- Daily data (`timeframe='1d'`): Default to market close
- US market close: 16:00 ET = 21:00 UTC
- Example: `2020-01-15T21:00:00+00:00`

---

#### Tab C: Equity Curve

Time-series chart of portfolio value.

**Data Contract:**
```json
"equity_curve": [
  { "date": "2020-01-01", "equity": 100000 },
  { "date": "2020-01-02", "equity": 100523 }
]
```

Primary canonical time-series. All other series derive from this.

---

#### Tab D: Drawdown

Time-series chart of drawdown percentage.

**Data Contract:**
```json
"drawdown_curve": [
  { "date": "2020-01-01", "drawdown_pct": 0.0 },
  { "date": "2020-01-02", "drawdown_pct": -1.2 }
]
```

**Definition:**
```
drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100
where peak_equity = running maximum of equity_curve
```

**Important:** This is **derivable from equity_curve** in the Adapter layer.
Does NOT require engine modification.

---

#### Tab E: Portfolio Composition

Visualizes cash vs. position value over time.

**Data Contract (Optional / Derivable):**
```json
"portfolio_curve": [
  {
    "date": "2020-01-01",
    "cash": 90000,
    "position": 10000,
    "total": 100000
  }
]
```

**Derivation Source:**
- `equity_curve` (total value)
- `trades` (executed buy/sell actions)
- Cash flow implied by position sizing

This is computed in the **Adapter layer**, NOT the engine.

---

#### Tab F: Candlestick + Signals (Phase 2)

**Status:** Planned for Day 7+ (not Day 3.9).

- OHLC candlestick chart with BUY/SELL markers
- Library: mplfinance (Matplotlib wrapper)
- Intraday timeframes (`5m`, `1h`): Phase 2 only

**Data Contract (Phase 2):**
```json
"price_candles": [
  { "date": "2020-01-01", "open": 150.0, "high": 153.5, "low": 149.2, "close": 152.8, "volume": 1234567 }
],
"signals": [
  { "date": "2020-01-15", "action": "BUY", "price": 153.17 }
]
```

---

## 5. Strict Rules (Non-Negotiable)

### Terminology (IMPORTANT)

To avoid ambiguity in design and implementation, the following terms are used consistently:

- **Rule**:
  A trading logic implementation defined in `rules/`
  (e.g., `RsiRule`, `MacdRule`, `RsiMacdRule`).
  Rules define **how trades are generated** and are part of the immutable core logic.

- **Strategy Preset**:
  A user-defined UI configuration persisted via SQLAlchemy
  (stored in the `Strategy` ORM model).
  Presets store **parameters only** (dates, rule type, UI settings) and
  **do NOT define trading logic**.

Rule logic MUST live in `rules/`.
Strategy Presets MUST NOT introduce or modify trading behavior.


**Quick Reference:**

| Rule | 핵심 내용 | 위반 시 결과 |
|---|---|---|
| **#1** | Engine 수정 금지 | 엔진 크래시, 재현성 파괴 |
| **#2** | API Contract 동결 | Worker-Web 통신 장애 |
| **#3** | 루트에서만 실행 | `ModuleNotFoundError` |
| **#4** | Stateless 아키텍처 | K8s 배포 실패 |
| **#5** | Matplotlib Agg | 서버 환경 렌더링 실패 |
| **#6** | 에러 핸들링 | 400 vs 500 구분 필수 |
| **#7** | 환경변수 설정 | 시크릿 노출 위험 |
| **#8** | run_id 로깅 | 디버깅 불가 |
| **#9** | DB Session Safety | 트랜잭션 손상 |

---

### Rule 1 -- Engine Immutability & Scope Discipline

`backtest/engine.py`와 모든 핵심 백테스트 로직은 레거시 코드이며 **절대 수정 금지**.
엔진 출력이 UI에 부족하면 **README에 제한사항 문서화**. 엔진 수정 금지.
새로운 기능은 반드시 wrapper/adapter 패턴으로 해결.
```python
# CORRECT: 래퍼 패턴
class EnhancedEngine:
    def __init__(self):
        self._engine = BacktestEngine(...)
    def run_with_risk_limit(self, ...):
        result = self._engine.run(data, strategy_func, ticker)
        # post-process result

# WRONG: engine.py 직접 수정
```

#### Post-Processing Allowance (Adapter Layer)

The Controller/Adapter layer MAY compute **derived metrics and visualizations**
from engine outputs WITHOUT modifying engine trading logic.

**Allowed in Adapter:**
- ✅ Deriving `drawdown_curve` from `equity_curve` (peak-to-trough)
- ✅ Computing `portfolio_curve` from `equity_curve` + `trades`
- ✅ Computing `win_rate`, `profit_factor`, `exposure_pct` from `trades`
- ✅ Generating PNG charts via Matplotlib
- ✅ Formatting timestamps to ISO8601

**Still Forbidden:**
- ❌ Modifying signal generation logic
- ❌ Changing trade execution rules
- ❌ Altering engine-internal formulas (Sharpe, returns)

**Important Clarification:**
Re-formatting or re-scaling engine-provided metrics is allowed;
re-computation using different formulas is not.

**Principle:**
> If data can be derived from existing engine outputs (equity, trades),
> compute it in the adapter. Only modify the engine if **internal loop access**
> is required (e.g., tracking peak equity during execution).

### Rule 2 -- Immutable API Contracts

**This is the target Web↔Worker contract, enforced starting Day 5.**

Web(Controller)과 Worker(Job) 간 JSON Schema는 **한번 정의되면 동결**.
기존 필드 삭제/이름 변경 금지. 새 필드 추가 시 기본값 필수.
```json
// Backtest Request (Web -> Worker) - Day 3.9+ Extended
{
  // Core fields (existing, unchanged)
  "run_id": "uuid",
  "ticker": "AAPL",
  "rule_id": "RSI_14_30_70",
  "params": {},
  "start_date": "2020-01-01",  // YYYY-MM-DD
  "end_date": "2024-01-01",

  // NEW: Trading parameters (Day 3.9)
  "initial_capital": 100000,   // Default: 100000
  "fee_rate": 0.001,           // Default: 0.001 (0.1%), decimal fraction
  "slippage_bps": 0,           // Default: 0 (not implemented Day 3.9)
  "position_size": 10000,      // Default: 10000
  "size_type": "value",        // Default: "value" | "percent"
  "direction": "longonly",     // Default: "longonly" | "longshort" 
  "timeframe": "1d" // Default: "1d" | "5m" | "1h" (Phase 2)
}
```

**Backward Compatibility:**
- All new fields have defaults
- Existing fields unchanged
- Additive only (no breaking changes)

```json
// Backtest Result (Worker -> Web/DB) - Day 3.9+ Extended
{
  "run_id": "uuid",
  "status": "completed|failed",
  "error_message": null,

  // Metrics (core + enhanced)
  "metrics": {
    // Day 3.9 (required)
    "total_return_pct": 12.34,
    "sharpe_ratio": 1.45,
    "max_drawdown_pct": 8.21,
    "num_trades": 42,

    // Phase 2 (optional)
    "cagr": 10.5,
    "volatility": 18.2,
    "win_rate": 65.5,
    "avg_trade_return": 2.1,
    "exposure_pct": 82.3,
    "profit_factor": 1.85
  },

  // Time-series data (NEW, required for tabs)
  "equity_curve": [
    { "date": "2020-01-01", "equity": 100000 }
  ],

  "drawdown_curve": [
    { "date": "2020-01-01", "drawdown_pct": 0.0 }
  ],

  // Optional / Derivable
  "portfolio_curve": [
    { "date": "2020-01-01", "cash": 90000, "position": 10000, "total": 100000 }
  ],

  // Trade details (NEW schema)
  "trades": [
    {
      "trade_no": 0,
      "side": "BUY",
      "size": 100,
      "entry_timestamp": "2020-01-15T21:00:00+00:00",
      "entry_price": 153.17,
      "entry_fees": 15.32,
      "exit_timestamp": "2020-05-06T21:00:00+00:00",
      "exit_price": 166.84,
      "exit_fees": 16.68,
      "pnl_abs": 1337.0,
      "pnl_pct": 8.7,
      "holding_period": 112.0
    }
  ],

  // Phase 2 (candlestick tab)
  "price_candles": [
    { "date": "2020-01-01", "open": 150.0, "high": 153.5, "low": 149.2, "close": 152.8, "volume": 1234567 }
  ],

  "signals": [
    { "date": "2020-01-15", "action": "BUY", "price": 153.17 }
  ],

  // Legacy (still supported)
  "chart_base64": "data:image/png;base64,..."
}
```

### Rule 3 -- Execution Context (Root Only)

모든 명령(Docker build, Python 실행, 테스트)은 **프로젝트 루트에서 실행**.
하위 폴더로 `cd`하여 스크립트를 실행하면 `ModuleNotFoundError` 발생.
```bash
# Correct
python scripts/verify_mvp.py
python -m flask run
docker build -t stock-backtest .

# Wrong
cd scripts && python verify_mvp.py
```

### Rule 4 -- Stateless Web Architecture

Flask 서버는 로컬 파일시스템에 쓰기 금지.
생성된 아티팩트(차트, 이미지)는 메모리에서 처리하고 Base64로 반환.

**Backtest results storage:**
- **Day 3-4 (Current):** Results returned inline as Base64-encoded JSON response
- **Day 5+ (Future):** Results persisted to MySQL; Base64 chart stored in `backtest_results` table

Strategy definitions (user-created rules) are stored in SQLite via SQLAlchemy.
```python
# Correct
buf = io.BytesIO()
fig.savefig(buf, format="png")
chart_b64 = base64.b64encode(buf.getvalue()).decode()

# Wrong
fig.savefig("/tmp/chart.png")
```

**Note on Local SQLite Usage (IMPORTANT):**

- SQLite is used **ONLY for local development (Day 3–4)** to persist UI strategy presets.
- The SQLite file (`strategies.db`) is **NOT a production dependency** and is **never committed**.
- Starting Day 5, all persistent state (presets & results) moves to **MySQL via StatefulSet**.
- The Web tier remains stateless in production; local SQLite is a **development-only exception**.



### Rule 5 -- Server-Safe Visualization

- pyplot import 전에 반드시 `matplotlib.use("Agg")` 설정
- 렌더링 후 반드시 `plt.close(fig)`로 figure 해제 (메모리 누수 방지)
```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
# ... render ...
buf = io.BytesIO()
fig.savefig(buf, format="png")
plt.close(fig)  # REQUIRED
```

### Rule 6 -- Error Handling Discipline

- User/Input 에러: **HTTP 400** (누락 필드, 잘못된 날짜, 알 수 없는 rule_id)
- System/Execution 에러: **HTTP 500** (DB 다운, 엔진 크래시)
- 사용자 메시지는 간결하게, 상세 스택 트레이스는 **서버 로그에만** 기록
```python
@app.errorhandler(Exception)
def handle_error(e):
    logger.exception(f"[run_id={g.run_id}] Unhandled error")
    return jsonify({"error": "Internal server error", "run_id": g.run_id}), 500
```

### Rule 7 -- Configuration & Secrets

- 모든 설정은 **환경변수**로 주입
- 로컬: `.env.example` 커밋 (실제 `.env`는 `.gitignore`)
- K8s: ConfigMap(비밀 아닌 값) + Secret(DB 비밀번호 등)
- **하드코딩된 시크릿 커밋 절대 금지**
```bash
# .env.example (committed)
FLASK_ENV=development
DB_HOST=localhost
DB_PORT=3306
DB_NAME=stock_backtest
DB_USER=backtest
DB_PASSWORD=changeme
LOG_LEVEL=INFO
```

### Rule 8 -- Observability

- 모든 백테스트 실행에 `run_id` (UUID4) 부여
- 모든 로그에 `run_id` 포함
- K8s 로그 수집을 위해 Stdout/Stderr로만 로깅
```python
import uuid
run_id = str(uuid.uuid4())
logger.info(f"[run_id={run_id}] Backtest started: ticker={ticker}, rule={rule_id}")
logger.info(f"[run_id={run_id}] Backtest completed: return={result['total_return_pct']:.2f}%")
```

### Rule 9 -- Database Session Safety

- 모든 `db.session.commit()`은 `try/except` 안에서 호출
- Exception 발생 시 반드시 `db.session.rollback()` 실행
- `IntegrityError`(중복)와 일반 `Exception`(시스템 장애) 분리 처리
- `db.create_all()`은 `if __name__ == "__main__"` 블록 안에서만 호출 (Gunicorn/K8s 호환)


**Git Safety Rule:**
- `strategies.db` (SQLite file) MUST be listed in `.gitignore` and never committed.


---

## 6. Directory Structure
```
stock_backtest/
|
|-- CLAUDE.md                          # 이 파일 (프로젝트 규칙 및 컨텍스트)
|-- README.md                          # 프로젝트 소개 및 Quick Start
|-- RETROSPECTIVE.md                   # 기술 회고 및 아키텍처 설명
|-- requirements.txt                   # Python 의존성
|-- .gitignore                         # Git 제외 규칙
|-- test_structure.py                  # 구조 검증 테스트
|-- app.py                             # ✅ Flask 애플리케이션 진입점 (Controller)
|-- extensions.py                      # ✅ SQLAlchemy 인스턴스 (순환 import 방지)
|-- models.py                          # ✅ Strategy ORM 모델
|-- Dockerfile                         # [Day 4] Multi-stage Docker 빌드
|-- docker-compose.yml                 # [Day 4] 로컬 개발: app + MySQL
|-- .env.example                       # [Day 4] 환경변수 템플릿
|-- .dockerignore                      # [Day 4] data/, logs/, __pycache__/ 제외
|
|-- backtest/                          # 핵심 엔진 (IMMUTABLE)
|   |-- __init__.py
|   |-- engine.py                      # BacktestEngine -- 수정 금지
|   +-- metrics.py                     # PerformanceMetrics
|
|-- rules/                             # 트레이딩 룰 라이브러리
|   |-- __init__.py
|   |-- base_rule.py                   # BaseRule, Signal, RuleMetadata, CompositeRule
|   |-- technical_rules.py             # ✅ Implemented: RSI, MACD, RSI+MACD, MA Cross, BB, Volume, Trend, ATR
|   |-- paper_rules.py                 # Momentum, Value, MeanReversion, Breakout
|   |-- rule_validator.py              # RuleValidator, SignalAnalyzer
|   +-- optimizer.py                   # ParameterOptimizer (Grid Search)
|
|-- extracted/
|   +-- features/
|       |-- __init__.py
|       +-- technical_indicators.py    # SMA, EMA, RSI, MACD, BB, ATR, Stochastic, ADX, OBV, VWAP
|
|-- scripts/
|   |-- config.py                      # 환경변수 기반 설정 (Config 클래스)
|   |-- data_loader.py                 # yfinance 다운로드 + 검증
|   |-- logger_config.py               # 로깅 설정 (file + console)
|   |-- qa_prices.py                   # 데이터 품질 검증
|   +-- verify_mvp.py                  # E2E 파이프라인 검증 스크립트
|
|-- templates/
|   +-- index.html                     # ✅ Bootstrap 5 Dark Mode 대시보드
|
|-- k8s/                               # [Day 5-6] Kubernetes 매니페스트
|   |-- namespace.yaml
|   |-- configmap.yaml
|   |-- secret.yaml
|   |-- web-deployment.yaml
|   |-- worker-job-template.yaml
|   |-- mysql-statefulset.yaml
|   +-- ingress.yaml
|
|-- data/                              # OHLCV CSV 데이터 (AAPL.csv 데모 포함)
```

---

## 7. Short-Term Roadmap

**Note:** Roadmap is high-level only. Detailed task lists belong in `RETROSPECTIVE.md` or Issues.

### Day 3 -- Flask Web Dashboard (✅ Completed)

| Task | Status |
|---|---|
| `app.py` 생성 (`GET /`, `POST /run_backtest`, `GET /health`) | ✅ Done |
| HTML 템플릿 (`index.html` — Bootstrap 5 Dark Mode, AJAX) | ✅ Done |
| Rule-Engine 어댑터 (`_build_strategy` wrapper 패턴) | ✅ Done |
| 차트 렌더링 (Matplotlib Agg → Base64 `<img>`) | ✅ Done |
| Strategy Persistence (`extensions.py`, `models.py`, REST API) | ✅ Done |
| Date range filtering (explicit `pd.to_datetime` + `tz_localize`) | ✅ Done |
| RSI + MACD Combined Strategy (`RsiMacdRule`) | ✅ Done |
| Security hardening (path traversal, memory leak, production config) | ✅ Done |

### Day 3.9 -- Advanced UI Features (✅ Completed)

| Task | Status | Time |
|---|---|---|
| 5-tab interface (Stats, Equity, Drawdown, Portfolio, Trades) | ✅ Done | 1.5h |
| Extended JSON response schema (equity_curve, drawdown_curve, trades) | ✅ Done | 1h |
| Enhanced metrics calculation (adapter layer) | ✅ Done | 1h |
| Drawdown chart derivation & rendering | ✅ Done | 1h |
| Portfolio visualization refactor (separate Orders & Trade PnL charts) | ✅ Done | 1h |
| Cumulative return chart | ✅ Done | 30min |
| Trading fees + slippage UI controls | ✅ Done | 30min |
| Typography improvements (14px min, monospace numbers) | ✅ Done | 30min |
| Bloomberg Terminal aesthetic refinement | ✅ Done | 1h |

**Day 3.9 Log:** Completed UI polish, cumulative return chart, and portfolio visualization refactor (split Orders + Trade PnL into separate full-width charts with fixed-position legends, removed deprecated combined chart).

**Phase 2 Features (Day 7+):**
- Candlestick chart with buy/sell overlays (mplfinance)
- Benchmark overlay on equity curve (Buy & Hold comparison)
- Intraday timeframes (5m, 1h)
- Sortable/filterable trade table
- Additional metrics (CAGR, volatility, win_rate, profit_factor, exposure)

### Day 4 -- Docker

| Task | Detail |
|---|---|
| `Dockerfile` | Multi-stage: builder(deps 설치) + runtime(slim 이미지). Port 5000 |
| `.dockerignore` | `data/`, `logs/`, `__pycache__/`, `.env`, `.git/`, `.claude/` 제외 |
| `docker-compose.yml` | web(Flask:5000) + db(MySQL:3306). 공유 네트워크, MySQL 볼륨 |
| `.env.example` | 모든 환경변수 + 안전한 기본값 |
| 헬스체크 | `GET /health` -> `{"status": "ok"}` |

### Day 5 -- Kubernetes + MySQL

| Task | Detail |
|---|---|
| `k8s/namespace.yaml` | `stock-backtest` 네임스페이스 |
| `k8s/configmap.yaml` | DB_HOST, DB_PORT, DB_NAME, LOG_LEVEL |
| `k8s/secret.yaml` | DB_USER, DB_PASSWORD (base64) |
| `k8s/mysql-statefulset.yaml` | MySQL 8.0, 1 replica, 5Gi PVC, ClusterIP Service |
| `k8s/web-deployment.yaml` | Flask Deployment (2 replicas), envFrom, Service (NodePort) |
| DB 스키마 | backtest_results 테이블 (run_id, ticker, rule_id, status, metrics, chart_base64, created_at) |

### Day 6 -- Web -> K8s Job Integration

| Task | Detail |
|---|---|
| `k8s/worker-job-template.yaml` | backoffLimit: 1, ttlSecondsAfterFinished: 3600 |
| Job Launcher | Flask -> K8s Python client -> Job 생성 (run_id, ticker, rule params 환경변수 주입) |
| Worker 진입점 | `worker.py`: 환경변수 읽기 -> 백테스트 실행 -> MySQL 결과 저장 -> 종료 |
| 상태 폴링 | `GET /status/<run_id>` -> MySQL 조회 -> completed/failed 반환 |
| 정리 | K8s TTL controller가 완료된 Job Pod 자동 삭제 |
