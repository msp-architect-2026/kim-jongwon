# test_structure.py (새 프로젝트 폴더 루트에 생성)
import pandas as pd
import sys
import os

# 경로 설정 (현재 폴더를 경로에 추가)
sys.path.append(os.getcwd())

try:
    print("1. 모듈 임포트 테스트...")
    from extracted.features.technical_indicators import TechnicalIndicators
    from rules.technical_rules import RSIRule
    from backtest.engine import BacktestEngine
    print("   ✅ 모듈 임포트 성공")

    print("2. 데이터 로드 테스트...")
    # 데이터 경로 확인 (본인 환경에 맞게 수정 필요할 수 있음)
    df = pd.read_csv('data/AAPL.csv', index_col=0, parse_dates=True)
    print(f"   ✅ 데이터 로드 성공 ({len(df)} rows)")

    print("3. 지표 계산 테스트...")
    # 여기서 에러나면 컬럼명이나 계산식 문제
    df['rsi'] = TechnicalIndicators.rsi(df['close'], period=14)
    print("   ✅ RSI 계산 성공")

    print("4. 룰 객체 생성 테스트...")
    from rules.base_rule import RuleMetadata
    metadata = RuleMetadata(rule_id="test_rsi", name="RSI Test", description="Test RSI rule", source="technical")
    rule = RSIRule(metadata=metadata, period=14, oversold=30, overbought=70)
    print("   ✅ 룰 생성 성공")

    print("5. 백테스트 실행 + 수익률 확인...")
    # RSI 지표를 데이터에 추가
    df['rsi'] = TechnicalIndicators.rsi(df['close'], period=14)

    # 룰 시그널 → 엔진 시그널 변환 래퍼
    def rsi_strategy(row):
        signal = rule.evaluate(row)
        if signal.action in ('buy', 'sell'):
            return signal.action
        return None

    engine = BacktestEngine(initial_capital=100000)
    result = engine.run(df, rsi_strategy, ticker='AAPL')

    print(f"   초기자본:    ${result['initial_capital']:>12,.2f}")
    print(f"   최종가치:    ${result['final_value']:>12,.2f}")
    print(f"   총 수익률:   {result['total_return_pct']:>11.2f}%")
    print(f"   거래 횟수:   {result['num_trades']:>6}회")
    print(f"   승률:        {result['win_rate']:>11.1f}%")
    print("   ✅ 백테스트 실행 성공")

    print("\n🎉 축하합니다! 파일 이사가 완벽하게 되었습니다.")

except Exception as e:
    print(f"\n❌ 오류 발생! 이사 과정에서 문제가 생겼습니다:\n{e}")