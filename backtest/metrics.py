"""
백테스트 성과 지표 계산
"""

import pandas as pd
import numpy as np
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """백테스트 성과 지표 계산"""

    @staticmethod
    def calculate_sharpe_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """
        Sharpe Ratio 계산

        Args:
            returns: 일일 수익률 시리즈
            risk_free_rate: 무위험 이자율 (연 기준)
            periods_per_year: 연간 거래일 수 (주식: 252)

        Returns:
            Sharpe Ratio
        """
        if len(returns) == 0:
            return 0.0

        # 초과 수익률
        excess_returns = returns - (risk_free_rate / periods_per_year)

        # Sharpe Ratio
        if excess_returns.std() == 0:
            return 0.0

        sharpe = np.sqrt(periods_per_year) * (excess_returns.mean() / excess_returns.std())
        return sharpe

    @staticmethod
    def calculate_sortino_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """
        Sortino Ratio 계산 (하방 위험만 고려)

        Args:
            returns: 일일 수익률 시리즈
            risk_free_rate: 무위험 이자율
            periods_per_year: 연간 거래일 수

        Returns:
            Sortino Ratio
        """
        if len(returns) == 0:
            return 0.0

        # 초과 수익률
        excess_returns = returns - (risk_free_rate / periods_per_year)

        # 하방 편차 (음수 수익률만 고려)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0

        downside_std = downside_returns.std()
        sortino = np.sqrt(periods_per_year) * (excess_returns.mean() / downside_std)
        return sortino

    @staticmethod
    def calculate_max_drawdown(portfolio_values: pd.Series) -> Dict[str, float]:
        """
        Maximum Drawdown 계산

        Args:
            portfolio_values: 포트폴리오 가치 시계열

        Returns:
            {
                'max_drawdown': 최대 낙폭 (percentage),
                'max_drawdown_duration': 최대 낙폭 기간 (days)
            }
        """
        if len(portfolio_values) == 0:
            return {'max_drawdown': 0.0, 'max_drawdown_duration': 0}

        # 누적 최고점
        cumulative_max = portfolio_values.cummax()

        # Drawdown 계산
        drawdown = (portfolio_values - cumulative_max) / cumulative_max

        # 최대 Drawdown
        max_drawdown = drawdown.min()

        # Drawdown 기간 계산
        is_in_drawdown = drawdown < 0
        drawdown_periods = is_in_drawdown.astype(int).groupby(
            (is_in_drawdown != is_in_drawdown.shift()).cumsum()
        ).sum()
        max_drawdown_duration = drawdown_periods.max() if len(drawdown_periods) > 0 else 0

        return {
            'max_drawdown': abs(max_drawdown),
            'max_drawdown_pct': abs(max_drawdown) * 100,
            'max_drawdown_duration': max_drawdown_duration
        }

    @staticmethod
    def calculate_calmar_ratio(
        total_return: float,
        max_drawdown: float,
        years: float = 1.0
    ) -> float:
        """
        Calmar Ratio 계산 (연평균 수익률 / 최대 낙폭)

        Args:
            total_return: 총 수익률
            max_drawdown: 최대 낙폭 (decimal)
            years: 백테스트 기간 (년)

        Returns:
            Calmar Ratio
        """
        if max_drawdown == 0:
            return 0.0

        annualized_return = (1 + total_return) ** (1 / years) - 1
        calmar = annualized_return / abs(max_drawdown)
        return calmar

    @staticmethod
    def calculate_win_rate(trades: list) -> Dict[str, float]:
        """
        승률 계산

        Args:
            trades: 거래 리스트 (BacktestEngine.trades)

        Returns:
            {
                'win_rate': 승률 (%),
                'avg_win': 평균 수익,
                'avg_loss': 평균 손실,
                'profit_factor': 수익 팩터
            }
        """
        if not trades:
            return {
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0
            }

        # 매수/매도 쌍 찾기
        buy_trades = [t for t in trades if t['action'] == 'buy']
        sell_trades = [t for t in trades if t['action'] == 'sell']

        wins = []
        losses = []

        for i, sell in enumerate(sell_trades):
            if i < len(buy_trades):
                buy = buy_trades[i]
                profit = (sell['effective_price'] - buy['effective_price']) * sell['quantity']
                if profit > 0:
                    wins.append(profit)
                else:
                    losses.append(abs(profit))

        total_trades = len(wins) + len(losses)
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0
        profit_factor = (sum(wins) / sum(losses)) if sum(losses) > 0 else 0.0

        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor
        }

    @staticmethod
    def generate_full_report(backtest_result: Dict) -> Dict:
        """
        종합 성과 리포트 생성

        Args:
            backtest_result: BacktestEngine.run() 결과

        Returns:
            종합 리포트 딕셔너리
        """
        portfolio_df = backtest_result['portfolio_history']
        trades = backtest_result['trades']

        # 일일 수익률 계산
        returns = portfolio_df['value'].pct_change().dropna()

        # 거래 없을 때 빈 returns 처리
        if len(returns) == 0 or len(portfolio_df) < 2:
            returns = pd.Series([0.0])  # 더미 수익률

        # 각종 지표 계산
        sharpe = PerformanceMetrics.calculate_sharpe_ratio(returns)
        sortino = PerformanceMetrics.calculate_sortino_ratio(returns)
        drawdown_info = PerformanceMetrics.calculate_max_drawdown(portfolio_df['value'])
        win_info = PerformanceMetrics.calculate_win_rate(trades)

        # 백테스트 기간 (년)
        days = len(portfolio_df)
        years = days / 252.0

        # Calmar Ratio
        calmar = PerformanceMetrics.calculate_calmar_ratio(
            backtest_result['total_return'],
            drawdown_info['max_drawdown'],
            years
        )

        report = {
            'basic_metrics': {
                'initial_capital': backtest_result['initial_capital'],
                'final_value': backtest_result['final_value'],
                'total_return_pct': backtest_result['total_return_pct'],
                'num_trades': backtest_result['num_trades']
            },
            'risk_metrics': {
                'sharpe_ratio': sharpe,
                'sortino_ratio': sortino,
                'max_drawdown_pct': drawdown_info['max_drawdown_pct'],
                'max_drawdown_duration': drawdown_info['max_drawdown_duration'],
                'calmar_ratio': calmar
            },
            'trading_metrics': {
                'win_rate': win_info['win_rate'],
                'avg_win': win_info['avg_win'],
                'avg_loss': win_info['avg_loss'],
                'profit_factor': win_info['profit_factor']
            },
            'period': {
                'days': days,
                'years': years
            }
        }

        logger.info(f"Performance report generated: Sharpe={sharpe:.2f}, Sortino={sortino:.2f}")
        return report


if __name__ == "__main__":
    # 테스트 코드
    sample_values = pd.Series([100, 105, 103, 110, 108, 115, 112, 120])
    returns = sample_values.pct_change().dropna()

    sharpe = PerformanceMetrics.calculate_sharpe_ratio(returns)
    print(f"Sharpe Ratio: {sharpe:.2f}")

    drawdown = PerformanceMetrics.calculate_max_drawdown(sample_values)
    print(f"Max Drawdown: {drawdown['max_drawdown_pct']:.2f}%")
