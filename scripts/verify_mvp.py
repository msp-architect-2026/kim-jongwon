"""
Day 1 & Day 2 MVP 검증 스크립트
데이터 로드 → 지표 계산 → 룰 평가 → 백테스트 → 성과 분석 전체 파이프라인 검증
"""
import sys
import os
import glob

# 프로젝트 루트를 경로에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

passed = 0
failed = 0


def check(step_name, func):
    """단계별 검증 실행"""
    global passed, failed
    try:
        result = func()
        print(f"  [PASS] {step_name}")
        passed += 1
        return result
    except Exception as e:
        print(f"  [FAIL] {step_name}")
        print(f"         원인: {e}")
        failed += 1
        return None


# ============================================================
# STEP 1: 데이터 로드
# ============================================================
print("=" * 60)
print("STEP 1: 데이터 로드")
print("=" * 60)

import pandas as pd

def load_csv():
    csv_files = sorted(glob.glob(os.path.join(PROJECT_ROOT, 'data', '*.csv')))
    assert len(csv_files) > 0, "data/ 폴더에 CSV 파일이 없습니다"
    csv_path = csv_files[0]
    ticker = os.path.basename(csv_path).replace('.csv', '')
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    assert len(df) > 0, "DataFrame이 비어있습니다"
    print(f"         파일: {ticker}.csv ({len(df)} rows)")
    return df, ticker

result = check("CSV 파일 로드", load_csv)
df, ticker = result if result else (None, None)

if df is not None:
    def check_columns():
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        assert not missing, f"필수 컬럼 누락: {missing}"
        return True

    check("OHLCV 컬럼 존재 확인", check_columns)

# ============================================================
# STEP 2: 기술지표 계산
# ============================================================
print()
print("=" * 60)
print("STEP 2: 기술지표 계산")
print("=" * 60)

TechnicalIndicators = None

def import_indicators():
    from extracted.features.technical_indicators import TechnicalIndicators as TI
    return TI

TechnicalIndicators = check("TechnicalIndicators 임포트", import_indicators)

if df is not None and TechnicalIndicators is not None:
    def calc_rsi():
        rsi = TechnicalIndicators.rsi(df['close'], period=14)
        assert rsi is not None, "RSI 결과가 None"
        assert len(rsi) == len(df), "RSI 길이 불일치"
        valid_count = rsi.dropna().shape[0]
        assert valid_count > 0, "유효한 RSI 값이 없음"
        print(f"         유효 데이터: {valid_count}/{len(df)} rows")
        return rsi

    rsi_series = check("RSI(14) 계산", calc_rsi)

    def calc_macd():
        macd_line, signal_line, histogram = TechnicalIndicators.macd(df['close'])
        assert macd_line is not None, "MACD 결과가 None"
        valid_count = macd_line.dropna().shape[0]
        assert valid_count > 0, "유효한 MACD 값이 없음"
        print(f"         유효 데이터: {valid_count}/{len(df)} rows")
        return macd_line, signal_line, histogram

    macd_result = check("MACD(12,26,9) 계산", calc_macd)

    # 지표를 df에 추가
    if rsi_series is not None:
        df['rsi'] = rsi_series
    if macd_result is not None:
        df['macd'] = macd_result[0]
        df['macd_signal'] = macd_result[1]
        df['macd_histogram'] = macd_result[2]

# ============================================================
# STEP 3: 컬럼명 정합성 검증
# ============================================================
print()
print("=" * 60)
print("STEP 3: 컬럼명 정합성 검증 (지표 → 룰)")
print("=" * 60)

RSIRule = None
MACDRule = None

def import_rules():
    from rules.technical_rules import RSIRule as _RSI, MACDRule as _MACD
    from rules.base_rule import RuleMetadata
    return _RSI, _MACD, RuleMetadata

rule_imports = check("룰 클래스 임포트 (RSIRule, MACDRule)", import_rules)

if rule_imports and df is not None:
    RSIRule, MACDRule, RuleMetadata = rule_imports

    def verify_rsi_columns():
        meta = RuleMetadata(rule_id="v_rsi", name="RSI", description="verify", source="technical")
        rule = RSIRule(metadata=meta, period=14, oversold=30, overbought=70)
        required = rule.get_required_features()
        missing = [f for f in required if f not in df.columns]
        assert not missing, f"RSIRule 필요 컬럼 누락: {missing} (현재: {list(df.columns)})"
        print(f"         필요: {required} → 모두 존재")
        return rule

    rsi_rule = check("RSIRule 컬럼 매칭", verify_rsi_columns)

    def verify_macd_columns():
        meta = RuleMetadata(rule_id="v_macd", name="MACD", description="verify", source="technical")
        rule = MACDRule(metadata=meta)
        required = rule.get_required_features()
        missing = [f for f in required if f not in df.columns]
        assert not missing, f"MACDRule 필요 컬럼 누락: {missing}"
        print(f"         필요: {required} → 모두 존재")
        return rule

    macd_rule = check("MACDRule 컬럼 매칭", verify_macd_columns)

# ============================================================
# STEP 4: 백테스트 실행
# ============================================================
print()
print("=" * 60)
print("STEP 4: 백테스트 실행 (RSI 전략)")
print("=" * 60)

BacktestEngine = None

def import_engine():
    from backtest.engine import BacktestEngine as BE
    return BE

BacktestEngine = check("BacktestEngine 임포트", import_engine)

backtest_result = None
if BacktestEngine and rsi_rule and df is not None:
    def run_backtest():
        def strategy(row):
            signal = rsi_rule.evaluate(row)
            if signal.action in ('buy', 'sell'):
                return signal.action
            return None

        engine = BacktestEngine(initial_capital=100000)
        result = engine.run(df, strategy, ticker=ticker)
        assert 'total_return_pct' in result, "결과에 total_return_pct 없음"
        assert 'final_value' in result, "결과에 final_value 없음"
        assert result['num_trades'] > 0, "거래가 한 건도 없음"
        print(f"         거래 횟수: {result['num_trades']}회")
        return result

    backtest_result = check("백테스트 실행 완료", run_backtest)

# ============================================================
# STEP 5: 성과 지표 (PerformanceMetrics)
# ============================================================
print()
print("=" * 60)
print("STEP 5: 성과 지표 계산 (PerformanceMetrics)")
print("=" * 60)

PerformanceMetrics = None

def import_metrics():
    from backtest.metrics import PerformanceMetrics as PM
    return PM

PerformanceMetrics = check("PerformanceMetrics 임포트", import_metrics)

full_report = None
if PerformanceMetrics and backtest_result:
    def calc_metrics():
        report = PerformanceMetrics.generate_full_report(backtest_result)
        assert 'basic_metrics' in report, "basic_metrics 누락"
        assert 'risk_metrics' in report, "risk_metrics 누락"
        assert 'trading_metrics' in report, "trading_metrics 누락"
        return report

    full_report = check("종합 성과 리포트 생성", calc_metrics)

# ============================================================
# STEP 6: 최종 수익률 타입 검증
# ============================================================
print()
print("=" * 60)
print("STEP 6: 최종 수익률 검증")
print("=" * 60)

if backtest_result and full_report:
    def verify_return_type():
        ret = backtest_result['total_return_pct']
        assert isinstance(ret, (int, float)), f"수익률 타입이 float이 아님: {type(ret)}"
        sharpe = full_report['risk_metrics']['sharpe_ratio']
        assert isinstance(sharpe, (int, float)), f"Sharpe 타입이 float이 아님: {type(sharpe)}"
        return ret, sharpe

    result = check("수익률/Sharpe가 float 타입", verify_return_type)

    if result:
        ret, sharpe = result
        print()
        print("-" * 60)
        print(f"  종목:         {ticker}")
        print(f"  초기자본:     ${backtest_result['initial_capital']:>14,.2f}")
        print(f"  최종가치:     ${backtest_result['final_value']:>14,.2f}")
        print(f"  총 수익률:    {ret:>13.2f}%")
        print(f"  거래 횟수:    {backtest_result['num_trades']:>8}회")
        print(f"  승률:         {backtest_result['win_rate']:>13.1f}%")
        print(f"  Sharpe Ratio: {sharpe:>13.2f}")
        print(f"  Sortino Ratio:{full_report['risk_metrics']['sortino_ratio']:>13.2f}")
        print(f"  Max Drawdown: {full_report['risk_metrics']['max_drawdown_pct']:>13.2f}%")
        print("-" * 60)

# ============================================================
# 최종 결과
# ============================================================
print()
print("=" * 60)
total = passed + failed
print(f"검증 결과: {passed}/{total} PASSED, {failed}/{total} FAILED")
print("=" * 60)

if failed == 0:
    print(">>> Day 1 + Day 2 MVP 파이프라인 검증 완료 <<<")
else:
    print(f">>> {failed}개 항목에서 문제 발견. 위 [FAIL] 항목을 확인하세요 <<<")

sys.exit(0 if failed == 0 else 1)
