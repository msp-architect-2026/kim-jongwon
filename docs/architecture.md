# 🏗️ Architecture (Kubernetes-based Stock Backtesting Platform)

이 문서는 **Stock Backtesting Platform**의 아키텍처를 설명합니다.  

- README: 빠른 이해(요약/대표 이미지)
- docs/architecture.md: 아키텍처 상세(구성요소/흐름/계약)
- docs/ops-guide.md: 운영 관점(배포/롤백/트러블슈팅)

---

## 0) 범위와 전제

### 목표
- 검증된 **레거시 백테스트 엔진(수정 금지)** 을 컨테이너로 격리
- 백테스트 실행을 **Kubernetes Job** 단위로 분리하여 확장
- Web은 **Stateless**, Worker는 **Ephemeral**
- 결과/상태는 **MySQL 단일 진실 공급원(Source of Truth)** 으로 관리
- GitOps: `k8s/` 매니페스트가 인프라 상태의 SSOT, Argo CD가 reconcile

### Phase 기준
- **Phase 0 (완료):** 로컬 동기 실행 기반 UI/Adapter/테스트 완료
- **Phase 1~6 (진행 예정):** Docker → K8s(MySQL) → Web→Job → CI/CD(GitOps) → 관측성 검증 → 문서화

> 본 문서의 “Target Architecture”는 **Phase 3 이후**를 기준으로 설명합니다.

---

## 1) Architecture Overview (Figure 8)

> 아래 이미지는 `docs/images/10_architecture_overview.png` 로 저장하세요.

![Figure 8 - Architecture Overview](images/10_architecture_overview.png)

### TL;DR
- 사용자는 Web(Flask)에 요청
- Web은 `run_id` 발급 + 입력 검증 후 **K8s Job 생성**
- Worker(Job Pod)는 엔진 실행 후 결과를 MySQL에 저장
- 사용자는 `/status/<run_id>`로 상태/결과 조회
- 성공 Job은 Web이 즉시 정리, 실패 Job은 24시간 유지 후 TTL 정리

---

## 2) Detailed Architecture (Figure 9)

> 상세 토폴로지/리소스 레벨(Deployment/StatefulSet/Job/RBAC/Ingress 등)을 표현한 이미지입니다.  
> `docs/images/11_architecture_detail.png` 로 저장하세요.

![Figure 9 - Architecture Detail](images/11_architecture_detail.png)

---

## 3) Phase 0 (현재) vs Target (Phase 3+) 비교

### Phase 0 (현재: 로컬 동기 실행)
- Web 프로세스에서 엔진을 직접 호출(동기)
- 결과는 API 응답으로 즉시 반환(Base64 포함)
- Strategy Preset은 로컬 개발에서 SQLite 사용

```mermaid
flowchart LR
  U[User] --> W[Flask Web (app.py)]
  W --> E[Immutable Engine]
  E --> A[Adapter (derived metrics/charts)]
  A --> W
  W --> U
```

### Target (Phase 3+: Web → K8s Job 비동기)

- Web은 요청/조회만 담당 (Stateless)
- 실행은 Worker(Job Pod)로 분리 (Ephemeral)
- 결과/상태는 MySQL에 persist (SoT)

```mermaid
flowchart LR
  U[User] --> W[Web: Flask Deployment (Stateless)]
  W -->|INSERT PENDING + create Job| J[K8s Job]
  J --> P[Worker Pod (Ephemeral)]
  P --> E[Immutable Engine]
  E --> A[Adapter Layer]
  A --> DB[(MySQL: Source of Truth)]
  W -->|GET /status/<run_id>| DB
  W --> U
```

---

## 4) 핵심 컴포넌트 및 책임 분리 (Web vs Worker)

Phase 3부터 Web↔Worker 분리가 도입되며, 아래 경계를 **엄격히 준수**합니다.

| Responsibility                          | Web (Flask Deployment) | Worker (K8s Job) |
| --------------------------------------- | ---------------------: | ---------------: |
| Request validation / input sanitization |                      ✅ |                — |
| `run_id` 발급(UUID4)                      |                      ✅ |                — |
| K8s Job 생성/삭제 (K8s Python client)       |                      ✅ |                — |
| 백테스트 엔진 실행                              |                      — |                ✅ |
| Adapter 파생(차트/지표/정규화)                   |                      — |                ✅ |
| 결과/상태 persist → MySQL                   |                      — |                ✅ |
| `/status/<run_id>` 제공                   |                      ✅ |                — |
| HTML/JSON 렌더링                           |                      ✅ |                — |

**Invariants**

* Web은 **stateless**: 로컬 파일 I/O 금지, 수평 확장 가능해야 함
* Worker는 **ephemeral**: 단일 백테스트 실행 후 종료
* MySQL은 결과/상태의 **single source of truth**
* Web Pod의 RBAC는 namespace-scoped Role/RoleBinding으로 `jobs.batch`에 대해서만 권한 부여(ClusterRole 금지)
* Web은 `JobLauncher` 인터페이스로 실행 모드를 추상화(LOCAL vs K8S)

---

## 5) Run Execution Contract (상태 머신)

### 상태 머신

```text
PENDING ──→ RUNNING ──→ SUCCEEDED
                    └──→ FAILED
```

| State       | Set By     | Trigger                        |
| ----------- | ---------- | ------------------------------ |
| `PENDING`   | Web        | `run_id` 발급 및 DB에 최초 insert 완료 |
| `RUNNING`   | Worker     | Worker 프로세스 시작 및 엔진 실행 개시      |
| `SUCCEEDED` | Worker     | 엔진 완료 + 결과/지표 persist 성공       |
| `FAILED`    | Web/Worker | 검증 실패(400) 또는 시스템 오류(500)      |

### 중요한 규칙(요약)

* 상태 전이는 **forward-only**
* 모든 전이는 **UTC timestamp**와 함께 MySQL에 저장
* Web은 Job 생성 전에 반드시 `PENDING`를 DB에 기록
* Job 생성 실패도 `FAILED(system_error)`로 기록하고 PENDING에 남겨두지 않음

---

## 6) 데이터 및 영속성 (MySQL SoT)

### 저장 원칙

* MySQL은 **결과/상태의 유일한 진실 공급원**
* Derived 데이터(드로우다운/차트 등)는 원칙적으로 **재생성 가능**하므로 최소 저장

### Canonical(필수)로 저장하는 데이터(요약)

* `run_id`, `ticker`, `rule_type`, `rule_id`, `params_json`
* `status`, `error_message`
* `metrics_json`
* `equity_curve_json`, `trades_json`
* `created_at`, `started_at`, `completed_at` (UTC)

> 정확한 컬럼/계약은 `CLAUDE.md`의 “Result Persistence Boundaries” 섹션을 따릅니다.

---

## 7) Reproducibility (재현성 보장)

동일 입력으로 동일 출력을 보장하기 위해 아래 식별자를 결과 row에 남깁니다.

* `data_hash`: 입력 OHLCV CSV의 SHA-256
* `rule_type + params`: 요청 시점 그대로 스냅샷 저장(정규화/변형 금지)
* `engine_version`: Git SHA(이미지 태그와 동일한 의미)
* `image_tag`: `:<git-sha-short>` (불변 태그 정책, `latest` 금지)

---

## 8) Kubernetes 리소스 토폴로지 (Phase 2~3)

> 모든 매니페스트는 `k8s/` 디렉터리에 존재하며 GitOps의 SSOT 입니다.

### 네임스페이스

* `stock-backtest`

### Web (Deployment)

* `k8s/web-deployment.yaml`
* stateless web
* ConfigMap/Secret로 환경변수 주입
* Service + Ingress로 외부 접근

### MySQL (StatefulSet + PVC)

* `k8s/mysql-statefulset.yaml`
* PVC로 데이터 영속화
* Web/Worker가 결과/상태를 DB로 교환

### Worker (Job Template)

* `k8s/worker-job-template.yaml`
* `backoffLimit: 1`
* `ttlSecondsAfterFinished: 86400` (실패 디버깅 위해 24h)

### RBAC (최소 권한)

* `k8s/rbac.yaml`
* ServiceAccount + Role + RoleBinding
* `jobs.batch`에 대해 `create/get/list/delete`만, **ClusterRole 금지**

---

## 9) Job Lifecycle Policy (정리 정책)

* **성공한 Job**

  * Worker가 DB에 `SUCCEEDED` 기록
  * Web이 결과 persist 확인 후 **즉시 Job 삭제**

* **실패한 Job**

  * Worker가 DB에 `FAILED + error_message` 기록
  * Job은 **24시간 보존**
  * TTLAfterFinished가 24시간 후 자동 정리 (`ttlSecondsAfterFinished: 86400`)

---

## 10) GitOps Deployment Flow (CI vs CD)

### CI (GitHub Actions)

1. `pytest`
2. `docker build` + GHCR push (`ghcr.io/<owner>/stock-backtest:<git-sha-short>`)
3. `k8s/web-deployment.yaml`의 image tag를 새 SHA로 업데이트
4. 매니페스트 변경 commit/push (직접 push 또는 PR)

### CD (Argo CD)

* `main` 브랜치의 `k8s/` 디렉터리를 감시
* 매니페스트 변경 감지 → auto-sync 적용
* drift 발생 시 self-heal

> 이미지 태그는 **불변 정책**을 따릅니다. (`latest` 금지)

---

## 11) Observability (Rule 8 요약)

* 모든 백테스트 실행은 `run_id(UUID4)`를 가진다
* Web/Worker/DB 로그 모두 `run_id`를 포함해야 한다
* 로그는 stdout/stderr로만 출력(파일 로깅 금지)
* 운영 시 `kubectl logs ... | grep <run_id>` 형태로 end-to-end 추적 가능해야 한다

---

## 12) 관련 문서

* 설계/규칙/계약(필독): **[`../CLAUDE.md`](../CLAUDE.md)**
* 운영 가이드: **[`ops-guide.md`](ops-guide.md)**
* UI 스크린샷 갤러리: **[`screenshots.md`](screenshots.md)**
* 프로젝트 소개(요약): **[`../README.md`](../README.md)**

---

## 13) 이미지 파일 체크리스트

아래 파일을 준비하면 문서가 완성됩니다.

* `docs/images/architecture_overview.png` (Figure 8)
* `docs/images/architecture_detail.png` (Figure 9)
* (README/UI) `docs/images/dashboard_hero.png`
* (UI) `docs/images/ui_stats_kpi.png`
* (UI) `docs/images/ui_equity_curve.png`
* (UI) `docs/images/ui_drawdown_curve.png`
* (UI) `docs/images/ui_portfolio_analysis.png`
* (UI) `docs/images/ui_cumulative_return.png`
* (UI) `docs/images/ui_trades_table.png`