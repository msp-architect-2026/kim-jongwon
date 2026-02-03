"""
백테스트 엔진: 전략 시뮬레이션 및 성과 평가
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class BacktestEngine:
    """간단한 백테스트 엔진

    ASSUMPTION: This engine simulates 'Market-On-Close' (MOC) execution.
    Trades are executed at the closing price of the same bar where the
    signal is generated. This means signals at time T use information
    available at T (including T's close) and execute at T's close price.
    Users should be aware of this potential look-ahead bias when
    interpreting backtest results.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,  # 0.1%
        slippage: float = 0.002  # 0.2%
    ):
        """
        초기화

        Args:
            initial_capital: 초기 자본금 (USD)
            commission: 수수료율 (percentage)
            slippage: 슬리피지율 (percentage)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

        # 백테스트 상태
        self.cash = initial_capital
        self.holdings = {}  # {ticker: quantity}
        self.portfolio_value_history = []
        self.trades = []

        logger.info(f"BacktestEngine initialized with ${initial_capital:,.2f}")

    def run(
        self,
        data: pd.DataFrame,
        strategy_func: Callable,
        ticker: str = "STOCK"
    ) -> Dict:
        """
        백테스트 실행

        Args:
            data: OHLCV 데이터 + 피처 (DataFrame)
            strategy_func: 전략 함수 (row -> signal: 'buy'/'sell'/None)
            ticker: 티커 심볼

        Returns:
            백테스트 결과 딕셔너리
        """
        logger.info(f"Running backtest on {ticker} with {len(data)} bars")

        # 초기화
        self.cash = self.initial_capital
        self.holdings = {ticker: 0}
        self.portfolio_value_history = []
        self.trades = []

        # 각 시점에서 전략 실행
        for idx, row in data.iterrows():
            # 현재 가격 (NaN이면 스킵)
            current_price = row['close']
            if pd.isna(current_price):
                continue

            # 전략 시그널 생성
            signal = strategy_func(row)

            # 포지션 실행
            if signal == 'buy' and self.cash > 0:
                self._execute_buy(ticker, current_price, idx)
            elif signal == 'sell' and self.holdings[ticker] > 0:
                self._execute_sell(ticker, current_price, idx)

            # 포트폴리오 가치 기록
            portfolio_value = self._calculate_portfolio_value(ticker, current_price)
            self.portfolio_value_history.append({
                'date': idx,
                'value': portfolio_value,
                'cash': self.cash,
                'holdings_value': portfolio_value - self.cash
            })

        # 최종 결과 계산
        return self._generate_report(ticker, data)

    def _execute_buy(self, ticker: str, price: float, timestamp) -> None:
        """매수 실행"""
        # 슬리피지 적용
        effective_price = price * (1 + self.slippage)

        # 최대 매수 가능 수량
        max_quantity = int(self.cash / (effective_price * (1 + self.commission)))

        if max_quantity > 0:
            # 거래 비용
            cost = max_quantity * effective_price
            commission_cost = cost * self.commission
            total_cost = cost + commission_cost

            # 포지션 업데이트
            self.holdings[ticker] += max_quantity
            self.cash -= total_cost

            # 거래 기록
            self.trades.append({
                'date': timestamp,
                'ticker': ticker,
                'action': 'buy',
                'quantity': max_quantity,
                'price': price,
                'effective_price': effective_price,
                'commission': commission_cost,
                'total_cost': total_cost
            })

            logger.debug(f"BUY {max_quantity} {ticker} @ ${effective_price:.2f}")

    def _execute_sell(self, ticker: str, price: float, timestamp) -> None:
        """매도 실행 (전량 청산)"""
        quantity = self.holdings[ticker]

        if quantity > 0:
            # 슬리피지 적용
            effective_price = price * (1 - self.slippage)

            # 거래 금액
            proceeds = quantity * effective_price
            commission_cost = proceeds * self.commission
            net_proceeds = proceeds - commission_cost

            # 포지션 업데이트
            self.holdings[ticker] = 0
            self.cash += net_proceeds

            # 거래 기록
            self.trades.append({
                'date': timestamp,
                'ticker': ticker,
                'action': 'sell',
                'quantity': quantity,
                'price': price,
                'effective_price': effective_price,
                'commission': commission_cost,
                'net_proceeds': net_proceeds
            })

            logger.debug(f"SELL {quantity} {ticker} @ ${effective_price:.2f}")

    def _calculate_portfolio_value(self, ticker: str, current_price: float) -> float:
        """현재 포트폴리오 가치 계산"""
        holdings_value = self.holdings[ticker] * current_price
        return self.cash + holdings_value

    def _generate_report(self, ticker: str, data: pd.DataFrame) -> Dict:
        """백테스트 리포트 생성"""
        if not self.portfolio_value_history:
            return {"error": "No trades executed"}

        # 포트폴리오 가치 DataFrame
        portfolio_df = pd.DataFrame(self.portfolio_value_history)
        portfolio_df.set_index('date', inplace=True)

        # 최종 가치
        final_value = portfolio_df['value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital
        total_return_pct = total_return * 100

        # 거래 통계
        num_trades = len(self.trades)
        buy_trades = [t for t in self.trades if t['action'] == 'buy']
        sell_trades = [t for t in self.trades if t['action'] == 'sell']

        # 수익 거래 계산
        profitable_trades = 0
        total_profit = 0
        total_loss = 0

        for i, sell in enumerate(sell_trades):
            if i < len(buy_trades):
                buy = buy_trades[i]
                profit = (sell['effective_price'] - buy['effective_price']) * sell['quantity']
                if profit > 0:
                    profitable_trades += 1
                    total_profit += profit
                else:
                    total_loss += abs(profit)

        win_rate = (profitable_trades / len(sell_trades) * 100) if sell_trades else 0

        report = {
            'ticker': ticker,
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'num_trades': num_trades,
            'num_buy_trades': len(buy_trades),
            'num_sell_trades': len(sell_trades),
            'win_rate': win_rate,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'portfolio_history': portfolio_df,
            'trades': self.trades
        }

        logger.info(
            f"Backtest complete: Return={total_return_pct:.2f}%, "
            f"Trades={num_trades}, Win Rate={win_rate:.1f}%"
        )

        return report


if __name__ == "__main__":
    # 테스트 코드
    def simple_ma_strategy(row):
        """간단한 이동평균 전략"""
        if 'sma_20' in row and 'sma_50' in row:
            if row['sma_20'] > row['sma_50']:
                return 'buy'
            elif row['sma_20'] < row['sma_50']:
                return 'sell'
        return None

    # 샘플 데이터 생성
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'close': np.random.randn(100).cumsum() + 100,
        'sma_20': np.random.randn(100).cumsum() + 100,
        'sma_50': np.random.randn(100).cumsum() + 100
    }, index=dates)

    engine = BacktestEngine(initial_capital=10000)
    result = engine.run(data, simple_ma_strategy, ticker='TEST')
    print(f"Total Return: {result['total_return_pct']:.2f}%")
