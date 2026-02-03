"""
Rule Validation and Testing Framework
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime
from .base_rule import BaseRule, Signal
from backtest.engine import BacktestEngine
from backtest.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


class RuleValidator:
    """Validate and test trading rules"""

    def __init__(self, min_sharpe: float = 0.5, min_win_rate: float = 0.40):
        """
        Initialize validator

        Args:
            min_sharpe: Minimum Sharpe ratio for validation
            min_win_rate: Minimum win rate (0-1) for validation
        """
        self.min_sharpe = min_sharpe
        self.min_win_rate = min_win_rate

    def validate_rule(
        self,
        rule: BaseRule,
        data: pd.DataFrame,
        initial_capital: float = 100000.0
    ) -> Dict:
        """
        Validate rule with backtesting

        Args:
            rule: Rule to validate
            data: Historical OHLCV + features data
            initial_capital: Starting capital for backtest

        Returns:
            Validation results dictionary
        """
        logger.info(f"Validating rule: {rule.metadata.name} (ID: {rule.metadata.rule_id})")

        # Check feature availability
        if not rule.validate(data):
            errors = rule.get_validation_errors()
            logger.error(f"Feature validation failed: {errors}")
            return {
                'rule_id': rule.metadata.rule_id,
                'is_valid': False,
                'errors': errors,
                'backtest_result': None
            }

        # Run backtest
        try:
            engine = BacktestEngine(initial_capital=initial_capital)

            # Strategy function wrapper
            def strategy_func(row: pd.Series) -> Optional[str]:
                signal = rule.evaluate(row)
                if signal.action in ['buy', 'sell']:
                    return signal.action
                return None

            backtest_result = engine.run(data, strategy_func, ticker=rule.metadata.rule_id)

            # Calculate performance metrics
            metrics_report = PerformanceMetrics.generate_full_report(backtest_result)

            # Validate against thresholds
            sharpe = metrics_report['risk_metrics']['sharpe_ratio']
            win_rate = metrics_report['trading_metrics']['win_rate'] / 100

            is_valid = (
                sharpe >= self.min_sharpe and
                win_rate >= self.min_win_rate
            )

            # Update rule metadata
            if is_valid:
                rule.metadata.is_validated = True
                rule.metadata.backtest_sharpe = sharpe
                rule.metadata.backtest_win_rate = win_rate

            result = {
                'rule_id': rule.metadata.rule_id,
                'is_valid': is_valid,
                'errors': [],
                'backtest_result': backtest_result,
                'metrics': metrics_report,
                'validation_summary': {
                    'sharpe_ratio': sharpe,
                    'sharpe_threshold': self.min_sharpe,
                    'sharpe_passed': sharpe >= self.min_sharpe,
                    'win_rate': win_rate,
                    'win_rate_threshold': self.min_win_rate,
                    'win_rate_passed': win_rate >= self.min_win_rate,
                    'total_return_pct': backtest_result['total_return_pct'],
                    'num_trades': backtest_result['num_trades']
                }
            }

            logger.info(
                f"Validation complete: {rule.metadata.name} - "
                f"Valid={is_valid}, Sharpe={sharpe:.2f}, WinRate={win_rate:.1%}"
            )

            return result

        except Exception as e:
            logger.error(f"Backtest failed for rule {rule.metadata.rule_id}: {e}")
            return {
                'rule_id': rule.metadata.rule_id,
                'is_valid': False,
                'errors': [f"Backtest error: {str(e)}"],
                'backtest_result': None
            }

    def batch_validate(
        self,
        rules: List[BaseRule],
        data: pd.DataFrame,
        initial_capital: float = 100000.0
    ) -> List[Dict]:
        """
        Validate multiple rules

        Args:
            rules: List of rules to validate
            data: Historical data
            initial_capital: Starting capital

        Returns:
            List of validation results
        """
        logger.info(f"Batch validating {len(rules)} rules")

        results = []
        for i, rule in enumerate(rules):
            logger.info(f"Processing rule {i+1}/{len(rules)}: {rule.metadata.name}")
            result = self.validate_rule(rule, data, initial_capital)
            results.append(result)

        # Summary
        valid_count = sum(1 for r in results if r['is_valid'])
        logger.info(f"Batch validation complete: {valid_count}/{len(rules)} rules passed")

        return results

    def compare_rules(
        self,
        rules: List[BaseRule],
        data: pd.DataFrame,
        initial_capital: float = 100000.0
    ) -> pd.DataFrame:
        """
        Compare performance of multiple rules

        Args:
            rules: List of rules to compare
            data: Historical data
            initial_capital: Starting capital

        Returns:
            Comparison DataFrame
        """
        logger.info(f"Comparing {len(rules)} rules")

        results = self.batch_validate(rules, data, initial_capital)

        # Extract comparison metrics
        comparison_data = []
        for result in results:
            if result['backtest_result']:
                summary = result['validation_summary']
                comparison_data.append({
                    'rule_id': result['rule_id'],
                    'is_valid': result['is_valid'],
                    'total_return_pct': summary['total_return_pct'],
                    'sharpe_ratio': summary['sharpe_ratio'],
                    'win_rate': summary['win_rate'],
                    'num_trades': summary['num_trades']
                })

        df = pd.DataFrame(comparison_data)

        # Sort by Sharpe ratio
        if not df.empty:
            df = df.sort_values('sharpe_ratio', ascending=False)

        return df

    def generate_validation_report(
        self,
        validation_result: Dict,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate human-readable validation report

        Args:
            validation_result: Result from validate_rule()
            output_path: Optional file path to save report

        Returns:
            Report text
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"RULE VALIDATION REPORT")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"Rule ID: {validation_result['rule_id']}")
        lines.append(f"Validation Status: {'PASSED' if validation_result['is_valid'] else 'FAILED'}")
        lines.append("")

        if validation_result['errors']:
            lines.append("ERRORS:")
            for error in validation_result['errors']:
                lines.append(f"  - {error}")
            lines.append("")

        if validation_result['backtest_result']:
            summary = validation_result['validation_summary']
            metrics = validation_result['metrics']

            lines.append("VALIDATION CRITERIA:")
            lines.append(f"  Sharpe Ratio: {summary['sharpe_ratio']:.2f} (threshold: {summary['sharpe_threshold']:.2f}) {'✓' if summary['sharpe_passed'] else '✗'}")
            lines.append(f"  Win Rate: {summary['win_rate']:.1%} (threshold: {summary['win_rate_threshold']:.1%}) {'✓' if summary['win_rate_passed'] else '✗'}")
            lines.append("")

            lines.append("BACKTEST RESULTS:")
            basic = metrics['basic_metrics']
            lines.append(f"  Initial Capital: ${basic['initial_capital']:,.2f}")
            lines.append(f"  Final Value: ${basic['final_value']:,.2f}")
            lines.append(f"  Total Return: {basic['total_return_pct']:.2f}%")
            lines.append(f"  Number of Trades: {basic['num_trades']}")
            lines.append("")

            lines.append("RISK METRICS:")
            risk = metrics['risk_metrics']
            lines.append(f"  Sharpe Ratio: {risk['sharpe_ratio']:.2f}")
            lines.append(f"  Sortino Ratio: {risk['sortino_ratio']:.2f}")
            lines.append(f"  Max Drawdown: {risk['max_drawdown_pct']:.2f}%")
            lines.append(f"  Max Drawdown Duration: {risk['max_drawdown_duration']} days")
            lines.append(f"  Calmar Ratio: {risk['calmar_ratio']:.2f}")
            lines.append("")

            lines.append("TRADING METRICS:")
            trading = metrics['trading_metrics']
            lines.append(f"  Win Rate: {trading['win_rate']:.2f}%")
            lines.append(f"  Average Win: ${trading['avg_win']:,.2f}")
            lines.append(f"  Average Loss: ${trading['avg_loss']:,.2f}")
            lines.append(f"  Profit Factor: {trading['profit_factor']:.2f}")
            lines.append("")

        lines.append("=" * 80)

        report = "\n".join(lines)

        if output_path:
            with open(output_path, 'w') as f:
                f.write(report)
            logger.info(f"Validation report saved to {output_path}")

        return report


class SignalAnalyzer:
    """Analyze signal quality and patterns"""

    @staticmethod
    def analyze_signals(
        rule: BaseRule,
        data: pd.DataFrame,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Analyze all signals generated by a rule

        Args:
            rule: Rule to analyze
            data: Historical data
            context: Optional context

        Returns:
            Signal analysis dictionary
        """
        logger.info(f"Analyzing signals for rule: {rule.metadata.name}")

        signals = []
        for idx, row in data.iterrows():
            signal = rule.evaluate(row, context)
            signals.append({
                'date': idx,
                'action': signal.action,
                'confidence': signal.confidence,
                'reasoning': signal.reasoning
            })

        signals_df = pd.DataFrame(signals)

        # Calculate statistics
        total_signals = len(signals_df)
        buy_signals = (signals_df['action'] == 'buy').sum()
        sell_signals = (signals_df['action'] == 'sell').sum()
        hold_signals = (signals_df['action'] == 'hold').sum()

        buy_avg_conf = signals_df[signals_df['action'] == 'buy']['confidence'].mean()
        sell_avg_conf = signals_df[signals_df['action'] == 'sell']['confidence'].mean()

        analysis = {
            'rule_id': rule.metadata.rule_id,
            'total_signals': total_signals,
            'buy_signals': int(buy_signals),
            'sell_signals': int(sell_signals),
            'hold_signals': int(hold_signals),
            'buy_pct': buy_signals / total_signals * 100 if total_signals > 0 else 0,
            'sell_pct': sell_signals / total_signals * 100 if total_signals > 0 else 0,
            'hold_pct': hold_signals / total_signals * 100 if total_signals > 0 else 0,
            'avg_buy_confidence': float(buy_avg_conf) if not pd.isna(buy_avg_conf) else 0.0,
            'avg_sell_confidence': float(sell_avg_conf) if not pd.isna(sell_avg_conf) else 0.0,
            'signals_df': signals_df
        }

        logger.info(
            f"Signal analysis complete: {buy_signals} buys, {sell_signals} sells, "
            f"{hold_signals} holds"
        )

        return analysis


if __name__ == "__main__":
    # Test code
    from rules.technical_rules import MovingAverageCrossRule
    from datetime import datetime

    # Create test data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, 100),
        'sma_20': np.random.randn(100).cumsum() + 100,
        'sma_50': np.random.randn(100).cumsum() + 100
    }, index=dates)

    # Create rule
    from rules.base_rule import RuleMetadata
    metadata = RuleMetadata(
        rule_id="TEST_MA_001",
        name="Test MA Cross",
        description="Test moving average crossover",
        source="technical"
    )
    rule = MovingAverageCrossRule(metadata, fast_period=20, slow_period=50)

    # Validate
    validator = RuleValidator(min_sharpe=0.0, min_win_rate=0.0)
    result = validator.validate_rule(rule, data, initial_capital=10000)

    print(f"Validation passed: {result['is_valid']}")
    if result['backtest_result']:
        print(f"Total return: {result['backtest_result']['total_return_pct']:.2f}%")
        print(f"Sharpe ratio: {result['validation_summary']['sharpe_ratio']:.2f}")

    # Generate report
    report = validator.generate_validation_report(result)
    print("\n" + report)
