# CLAUDE.md -- Stock Backtesting Platform

## 1. Project Overview

| 항목 | 내용 |
|---|---|
| **Project Name** | Kubernetes-based Stock Backtesting Platform |
| **Purpose** | 검증 완료된 Python 백테스트 엔진을 Docker 컨테이너로 감싸고, Kubernetes Job으로 실행하는 클라우드 네이티브 플랫폼 |

**Core Values:**

| Value | Meaning |
|---|---|
| **Scalability** | 각 백테스트는 독립적인 K8s Job으로 실행. 수평 확장은 인프라 레벨에서 해결 |
| **Stateless Design** | Web 계층은 로컬 파일시스템에 의존하지 않음. 결과는 DB 또는 Base64 인라인 반환 |
| **Reproducibility** | 동일 입력(ticker, rule, params, date range)은 반드시 동일 출력 생성 |
| **GitOps** | 모든 K8s 매니페스트는 `k8s/` 디렉터리에 존재. 레포가 인프라의 단일 진실 공급원 |

---

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | Python 3.11 Slim | `python:3.11-slim` Docker base image |
| Package Mgmt | pip + requirements.txt | Poetry/Pipenv 사용 금지 |
| Web Framework | Flask (sync) | Gunicorn 워커; 비동기 불필요 |
| Data Processing | Pandas, NumPy | 기존 사용 중 |
| Visualization | Matplotlib (**Agg** backend) | 서버 환경 필수; GUI 의존성 없음 |
| Containerization | Docker | Multi-stage build |
| Orchestration | Kubernetes | Job(Worker), Deployment(Web), Service |
| Database | MySQL 8.0 | K8s StatefulSet + PVC |

---

## 3. Strict Rules (Non-Negotiable)

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

### Rule 2 -- Immutable API Contracts

Web(Controller)과 Worker(Job) 간 JSON Schema는 **한번 정의되면 동결**.
기존 필드 삭제/이름 변경 금지. 새 필드 추가 시 기본값 필수.

```json
// Backtest Request (Web -> Worker)
{
    "run_id": "uuid",
    "ticker": "AAPL",
    "rule_id": "RSI_14_30_70",
    "params": {},
    "start_date": "2020-01-01",
    "end_date": "2024-01-01",
    "initial_capital": 100000
}

// Backtest Result (Worker -> DB)
{
    "run_id": "uuid",
    "status": "completed|failed",
    "total_return_pct": 12.34,
    "sharpe_ratio": 1.45,
    "max_drawdown_pct": 8.21,
    "num_trades": 42,
    "chart_base64": "data:image/png;base64,...",
    "error_message": null
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
백테스트 결과는 MySQL에 저장, 로컬 파일 저장 금지.

```python
# Correct
buf = io.BytesIO()
fig.savefig(buf, format="png")
chart_b64 = base64.b64encode(buf.getvalue()).decode()

# Wrong
fig.savefig("/tmp/chart.png")
```

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

---

## 4. Directory Structure

`[PLANNED]` 표시 항목은 아직 존재하지 않으며, 로드맵에 따라 생성 예정.

```
stock_backtest/
|
|-- CLAUDE.md                          # 이 파일 (프로젝트 규칙 및 컨텍스트)
|-- requirements.txt                   # Python 의존성
|-- test_structure.py                  # 구조 검증 테스트
|-- app.py                             # [PLANNED] Flask 애플리케이션 진입점
|-- Dockerfile                         # [PLANNED] Multi-stage Docker 빌드
|-- docker-compose.yml                 # [PLANNED] 로컬 개발: app + MySQL
|-- .env.example                       # [PLANNED] 환경변수 템플릿
|-- .dockerignore                      # [PLANNED] data/, logs/, __pycache__/ 제외
|
|-- backtest/                          # 핵심 엔진 (IMMUTABLE)
|   |-- __init__.py
|   |-- engine.py                      # BacktestEngine -- 수정 금지
|   +-- metrics.py                     # PerformanceMetrics
|
|-- rules/                             # 트레이딩 룰 라이브러리
|   |-- __init__.py
|   |-- base_rule.py                   # BaseRule, Signal, RuleMetadata, CompositeRule
|   |-- technical_rules.py             # MA Cross, RSI, BB, MACD, Volume, Trend, ATR
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
|-- templates/                         # [PLANNED] Jinja2 HTML 템플릿
|   |-- base.html
|   |-- dashboard.html
|   +-- result.html
|
|-- static/                            # [PLANNED] CSS/JS 정적 파일
|   +-- style.css
|
|-- k8s/                               # [PLANNED] Kubernetes 매니페스트
|   |-- namespace.yaml
|   |-- configmap.yaml
|   |-- secret.yaml
|   |-- web-deployment.yaml
|   |-- worker-job-template.yaml
|   |-- mysql-statefulset.yaml
|   +-- ingress.yaml
|
|-- data/                              # OHLCV CSV 데이터 (10 종목)

```

---

## 5. Short-Term Roadmap

### Day 3 -- Flask Web Dashboard

| Task | Detail |
|---|---|
| `app.py` 생성 | `GET /` (대시보드), `POST /backtest` (실행), `GET /result/<run_id>` |
| HTML 템플릿 | `dashboard.html` (종목/룰/파라미터 폼), `result.html` (메트릭 테이블 + 차트) |
| Rule-Engine 어댑터 | `verify_mvp.py`의 래퍼 패턴 재사용 |
| 차트 렌더링 | Matplotlib Agg -> Base64 `<img>` 태그 |
| requirements.txt 갱신 | flask, gunicorn, matplotlib 추가 |

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
