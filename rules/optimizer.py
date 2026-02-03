"""
전략 파라미터 최적화
Grid Search를 통한 최적 파라미터 탐색
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Callable
import logging
from itertools import product
from rules.base_rule import BaseRule, RuleMetadata
from rules.rule_validator import RuleValidator

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """전략 파라미터 최적화"""

    def __init__(
        self,
        metric: str = 'sharpe_ratio',  # 'sharpe_ratio', 'total_return_pct', 'win_rate'
        min_trades: int = 5  # 최소 거래 횟수
    ):
        """
        파라미터 최적화 초기화

        Args:
            metric: 최적화 기준 지표
            min_trades: 유효한 것으로 간주할 최소 거래 횟수
        """
        self.metric = metric
        self.min_trades = min_trades

    def optimize_ma_crossover(
        self,
        data: pd.DataFrame,
        fast_periods: List[int] = [10, 20, 30],
        slow_periods: List[int] = [50, 100, 200],
        initial_capital: float = 100000
    ) -> Dict:
        """
        MA Crossover 전략 파라미터 최적화

        Args:
            data: 백테스트 데이터
            fast_periods: 빠른 MA 기간 후보
            slow_periods: 느린 MA 기간 후보
            initial_capital: 초기 자본

        Returns:
            최적화 결과
        """
        from rules.technical_rules import MovingAverageCrossRule

        logger.info(f"Optimizing MA Crossover: {len(fast_periods)}x{len(slow_periods)} combinations")

        results = []
        validator = RuleValidator()

        for fast, slow in product(fast_periods, slow_periods):
            if fast >= slow:  # 빠른 MA는 느린 MA보다 작아야 함
                continue

            # 필요한 특성 확인
            required_features = [f'sma_{fast}', f'sma_{slow}']
            if not all(feat in data.columns for feat in required_features):
                logger.warning(f"Skipping fast={fast}, slow={slow}: missing features")
                continue

            # 룰 생성
            rule = MovingAverageCrossRule(
                RuleMetadata(
                    rule_id=f"MA_{fast}_{slow}",
                    name=f"MA {fast}/{slow}",
                    description=f"MA Crossover {fast}/{slow}",
                    source="technical"
                ),
                fast_period=fast,
                slow_period=slow
            )

            # 백테스트
            try:
                result = validator.validate_rule(rule, data, initial_capital)

                if result['backtest_result']:
                    summary = result['validation_summary']
                    num_trades = summary['num_trades']

                    # 최소 거래 횟수 체크
                    if num_trades < self.min_trades:
                        continue

                    results.append({
                        'fast_period': fast,
                        'slow_period': slow,
                        'sharpe_ratio': summary['sharpe_ratio'],
                        'total_return_pct': summary['total_return_pct'],
                        'win_rate': summary['win_rate'],
                        'num_trades': num_trades,
                        'metric_value': summary[self.metric]
                    })

                    logger.debug(
                        f"MA {fast}/{slow}: {self.metric}={summary[self.metric]:.2f}, "
                        f"trades={num_trades}"
                    )

            except Exception as e:
                logger.error(f"Error testing MA {fast}/{slow}: {e}")

        if not results:
            logger.warning("No valid results found")
            return {'best_params': None, 'all_results': []}

        # 결과 정렬
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('metric_value', ascending=False)

        best = results_df.iloc[0]
        logger.info(
            f"Best MA params: fast={best['fast_period']}, slow={best['slow_period']} "
            f"({self.metric}={best['metric_value']:.2f})"
        )

        return {
            'best_params': {
                'fast_period': int(best['fast_period']),
                'slow_period': int(best['slow_period'])
            },
            'best_performance': {
                'sharpe_ratio': best['sharpe_ratio'],
                'total_return_pct': best['total_return_pct'],
                'win_rate': best['win_rate'],
                'num_trades': int(best['num_trades'])
            },
            'all_results': results_df.to_dict('records')
        }

    def optimize_rsi(
        self,
        data: pd.DataFrame,
        periods: List[int] = [7, 14, 21],
        oversold_levels: List[float] = [20, 25, 30],
        overbought_levels: List[float] = [70, 75, 80],
        initial_capital: float = 100000
    ) -> Dict:
        """
        RSI 전략 파라미터 최적화

        Args:
            data: 백테스트 데이터
            periods: RSI 기간 후보
            oversold_levels: 과매도 수준 후보
            overbought_levels: 과매수 수준 후보
            initial_capital: 초기 자본

        Returns:
            최적화 결과
        """
        from rules.technical_rules import RSIRule

        logger.info(
            f"Optimizing RSI: {len(periods)}x{len(oversold_levels)}x{len(overbought_levels)} "
            f"combinations"
        )

        results = []
        validator = RuleValidator()

        for period, oversold, overbought in product(periods, oversold_levels, overbought_levels):
            if oversold >= overbought:  # 과매도 < 과매수
                continue

            # 필요한 특성 확인
            if f'rsi_{period}' not in data.columns:
                logger.warning(f"Skipping period={period}: missing rsi_{period}")
                continue

            # 룰 생성
            rule = RSIRule(
                RuleMetadata(
                    rule_id=f"RSI_{period}_{oversold}_{overbought}",
                    name=f"RSI {period}",
                    description=f"RSI {period} ({oversold}/{overbought})",
                    source="technical"
                ),
                period=period,
                oversold=oversold,
                overbought=overbought
            )

            # 백테스트
            try:
                result = validator.validate_rule(rule, data, initial_capital)

                if result['backtest_result']:
                    summary = result['validation_summary']
                    num_trades = summary['num_trades']

                    if num_trades < self.min_trades:
                        continue

                    results.append({
                        'period': period,
                        'oversold': oversold,
                        'overbought': overbought,
                        'sharpe_ratio': summary['sharpe_ratio'],
                        'total_return_pct': summary['total_return_pct'],
                        'win_rate': summary['win_rate'],
                        'num_trades': num_trades,
                        'metric_value': summary[self.metric]
                    })

                    logger.debug(
                        f"RSI {period} ({oversold}/{overbought}): "
                        f"{self.metric}={summary[self.metric]:.2f}"
                    )

            except Exception as e:
                logger.error(f"Error testing RSI {period}: {e}")

        if not results:
            logger.warning("No valid results found")
            return {'best_params': None, 'all_results': []}

        # 결과 정렬
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('metric_value', ascending=False)

        best = results_df.iloc[0]
        logger.info(
            f"Best RSI params: period={best['period']}, "
            f"oversold={best['oversold']}, overbought={best['overbought']} "
            f"({self.metric}={best['metric_value']:.2f})"
        )

        return {
            'best_params': {
                'period': int(best['period']),
                'oversold': float(best['oversold']),
                'overbought': float(best['overbought'])
            },
            'best_performance': {
                'sharpe_ratio': best['sharpe_ratio'],
                'total_return_pct': best['total_return_pct'],
                'win_rate': best['win_rate'],
                'num_trades': int(best['num_trades'])
            },
            'all_results': results_df.to_dict('records')
        }

    def optimize_bollinger_bands(
        self,
        data: pd.DataFrame,
        periods: List[int] = [10, 20, 30],
        std_devs: List[float] = [1.5, 2.0, 2.5],
        initial_capital: float = 100000
    ) -> Dict:
        """
        Bollinger Bands 전략 파라미터 최적화

        Args:
            data: 백테스트 데이터
            periods: BB 기간 후보
            std_devs: 표준편차 배수 후보
            initial_capital: 초기 자본

        Returns:
            최적화 결과
        """
        from rules.technical_rules import BollingerBandsRule

        logger.info(f"Optimizing Bollinger Bands: {len(periods)}x{len(std_devs)} combinations")

        results = []
        validator = RuleValidator()

        for period, std_dev in product(periods, std_devs):
            # 필요한 특성 확인
            required = [f'bb_middle_{period}', f'bb_upper_{period}', f'bb_lower_{period}']
            if not all(feat in data.columns for feat in required):
                logger.warning(f"Skipping period={period}: missing BB features")
                continue

            # 룰 생성
            rule = BollingerBandsRule(
                RuleMetadata(
                    rule_id=f"BB_{period}_{std_dev}",
                    name=f"BB {period}",
                    description=f"Bollinger Bands {period} ({std_dev}σ)",
                    source="technical"
                ),
                period=period,
                std_dev=std_dev
            )

            # 백테스트
            try:
                result = validator.validate_rule(rule, data, initial_capital)

                if result['backtest_result']:
                    summary = result['validation_summary']
                    num_trades = summary['num_trades']

                    if num_trades < self.min_trades:
                        continue

                    results.append({
                        'period': period,
                        'std_dev': std_dev,
                        'sharpe_ratio': summary['sharpe_ratio'],
                        'total_return_pct': summary['total_return_pct'],
                        'win_rate': summary['win_rate'],
                        'num_trades': num_trades,
                        'metric_value': summary[self.metric]
                    })

                    logger.debug(
                        f"BB {period} ({std_dev}σ): {self.metric}={summary[self.metric]:.2f}"
                    )

            except Exception as e:
                logger.error(f"Error testing BB {period}: {e}")

        if not results:
            logger.warning("No valid results found")
            return {'best_params': None, 'all_results': []}

        # 결과 정렬
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values('metric_value', ascending=False)

        best = results_df.iloc[0]
        logger.info(
            f"Best BB params: period={best['period']}, std_dev={best['std_dev']} "
            f"({self.metric}={best['metric_value']:.2f})"
        )

        return {
            'best_params': {
                'period': int(best['period']),
                'std_dev': float(best['std_dev'])
            },
            'best_performance': {
                'sharpe_ratio': best['sharpe_ratio'],
                'total_return_pct': best['total_return_pct'],
                'win_rate': best['win_rate'],
                'num_trades': int(best['num_trades'])
            },
            'all_results': results_df.to_dict('records')
        }

    def generate_optimization_report(self, results: Dict, strategy_name: str) -> str:
        """최적화 결과 리포트 생성"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"PARAMETER OPTIMIZATION REPORT: {strategy_name}")
        lines.append("=" * 80)
        lines.append("")

        if results['best_params'] is None:
            lines.append("No valid parameter combinations found.")
            return "\n".join(lines)

        lines.append("BEST PARAMETERS:")
        for key, value in results['best_params'].items():
            lines.append(f"  {key}: {value}")
        lines.append("")

        lines.append("BEST PERFORMANCE:")
        perf = results['best_performance']
        lines.append(f"  Sharpe Ratio:    {perf['sharpe_ratio']:>8.2f}")
        lines.append(f"  Total Return:    {perf['total_return_pct']:>8.2f}%")
        lines.append(f"  Win Rate:        {perf['win_rate']:>8.1%}")
        lines.append(f"  Number of Trades:{perf['num_trades']:>8}")
        lines.append("")

        lines.append(f"TESTED COMBINATIONS: {len(results['all_results'])}")
        lines.append("=" * 80)

        return "\n".join(lines)


if __name__ == "__main__":
    # 테스트 코드
    from tests.test_integration_simple import generate_test_data

    logging.basicConfig(level=logging.INFO)

    data = generate_test_data(days=600)

    # MA Crossover 최적화
    optimizer = ParameterOptimizer(metric='sharpe_ratio', min_trades=3)
    ma_results = optimizer.optimize_ma_crossover(
        data,
        fast_periods=[10, 20, 30],
        slow_periods=[50, 100]
    )

    print(optimizer.generate_optimization_report(ma_results, "MA Crossover"))

    if ma_results['best_params']:
        print(f"\n✓ Best MA: {ma_results['best_params']}")
