"""
Paper-based Rules extracted from research papers via RAG
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Callable
import logging
from .base_rule import BaseRule, RuleMetadata, Signal

logger = logging.getLogger(__name__)


class PaperExtractedRule(BaseRule):
    """Rule extracted from academic paper via RAG system"""

    def __init__(
        self,
        metadata: RuleMetadata,
        condition_func: Callable[[pd.Series], bool],
        signal_type: str,  # 'buy' or 'sell'
        confidence_func: Optional[Callable[[pd.Series], float]] = None,
        required_features: Optional[List[str]] = None
    ):
        """
        Initialize paper-extracted rule

        Args:
            metadata: Rule metadata (should include paper_title and paper_section)
            condition_func: Function that takes a row and returns True if condition met
            signal_type: 'buy' or 'sell'
            confidence_func: Optional function to calculate confidence (0-1)
            required_features: List of required feature columns
        """
        super().__init__(metadata, params={
            'signal_type': signal_type,
            'required_features': required_features or []
        })
        self.condition_func = condition_func
        self.signal_type = signal_type
        self.confidence_func = confidence_func or (lambda row: 0.7)  # Default confidence
        self._required_features = required_features or []

    def evaluate(self, row: pd.Series, context: Optional[Dict[str, Any]] = None) -> Signal:
        """Evaluate paper condition"""
        try:
            condition_met = self.condition_func(row)

            if condition_met:
                confidence = self.confidence_func(row)
                confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

                reasoning = f"Paper rule triggered: {self.metadata.description}"
                if self.metadata.paper_title:
                    reasoning += f" (from: {self.metadata.paper_title})"

                return Signal(self.signal_type, confidence, reasoning)
            else:
                return Signal('hold', 0.0, "Condition not met")

        except Exception as e:
            logger.error(f"Error evaluating paper rule {self.metadata.rule_id}: {e}")
            return Signal('hold', 0.0, f"Evaluation error: {str(e)}")

    def get_required_features(self) -> List[str]:
        return self._required_features


class MomentumRule(PaperExtractedRule):
    """
    Momentum strategy from papers like Jegadeesh & Titman (1993)
    Buy winners, sell losers
    """

    def __init__(
        self,
        metadata: RuleMetadata,
        lookback_period: int = 252,  # 1 year
        holding_period: int = 63,    # 3 months
        threshold: float = 0.10      # 10% return threshold
    ):
        """
        Momentum strategy

        Args:
            metadata: Rule metadata
            lookback_period: Period to calculate past returns (days)
            holding_period: Holding period (days)
            threshold: Return threshold for signal
        """
        metadata.tags.append('momentum')

        def condition_func(row: pd.Series) -> bool:
            """Check if past return exceeds threshold"""
            past_return_col = f'return_{lookback_period}d'
            if past_return_col not in row:
                return False
            return row[past_return_col] > threshold

        def confidence_func(row: pd.Series) -> float:
            """Confidence based on momentum strength"""
            past_return_col = f'return_{lookback_period}d'
            if past_return_col not in row:
                return 0.5
            excess_return = row[past_return_col] - threshold
            return min(0.5 + excess_return * 2, 1.0)

        super().__init__(
            metadata=metadata,
            condition_func=condition_func,
            signal_type='buy',
            confidence_func=confidence_func,
            required_features=[f'return_{lookback_period}d']
        )

        self.params.update({
            'lookback_period': lookback_period,
            'holding_period': holding_period,
            'threshold': threshold
        })


class ValueRule(PaperExtractedRule):
    """
    Value strategy based on fundamental ratios
    Example: Fama-French value factor
    """

    def __init__(
        self,
        metadata: RuleMetadata,
        metric: str = 'pb_ratio',  # Price-to-Book
        threshold: float = 1.0,     # Buy if P/B < 1.0
        direction: str = 'low'      # 'low' = buy low values, 'high' = buy high values
    ):
        """
        Value strategy

        Args:
            metadata: Rule metadata
            metric: Fundamental metric column name
            threshold: Threshold value
            direction: 'low' or 'high'
        """
        metadata.tags.append('value')

        def condition_func(row: pd.Series) -> bool:
            """Check if metric meets threshold"""
            if metric not in row or pd.isna(row[metric]):
                return False
            if direction == 'low':
                return row[metric] < threshold
            else:
                return row[metric] > threshold

        def confidence_func(row: pd.Series) -> float:
            """Confidence based on distance from threshold"""
            if metric not in row or pd.isna(row[metric]):
                return 0.5
            distance = abs(row[metric] - threshold) / threshold
            return min(0.5 + distance * 0.5, 1.0)

        super().__init__(
            metadata=metadata,
            condition_func=condition_func,
            signal_type='buy',
            confidence_func=confidence_func,
            required_features=[metric]
        )

        self.params.update({
            'metric': metric,
            'threshold': threshold,
            'direction': direction
        })


class MeanReversionRule(PaperExtractedRule):
    """
    Mean reversion strategy
    Example: DeBondt & Thaler (1985) overreaction hypothesis
    """

    def __init__(
        self,
        metadata: RuleMetadata,
        lookback_period: int = 21,    # 1 month
        std_threshold: float = 2.0,   # 2 standard deviations
        reversion_target: str = 'sma_50'
    ):
        """
        Mean reversion strategy

        Args:
            metadata: Rule metadata
            lookback_period: Period to calculate deviation
            std_threshold: Standard deviation threshold
            reversion_target: Target mean column (e.g., 'sma_50')
        """
        metadata.tags.append('mean_reversion')

        def condition_func(row: pd.Series) -> bool:
            """Check if price deviated significantly from mean"""
            if reversion_target not in row or pd.isna(row[reversion_target]):
                return False
            price = row['close']
            mean = row[reversion_target]
            std_col = f'std_{lookback_period}'
            if std_col not in row or pd.isna(row[std_col]):
                return False
            std = row[std_col]
            if std == 0:
                return False
            z_score = (price - mean) / std
            return abs(z_score) > std_threshold

        def confidence_func(row: pd.Series) -> float:
            """Confidence based on z-score"""
            if reversion_target not in row:
                return 0.5
            price = row['close']
            mean = row[reversion_target]
            std_col = f'std_{lookback_period}'
            if std_col not in row or pd.isna(row[std_col]):
                return 0.5
            std = row[std_col]
            if std == 0:
                return 0.5
            z_score = abs((price - mean) / std)
            return min(z_score / (std_threshold * 2), 1.0)

        # Signal type depends on deviation direction
        def dynamic_condition(row: pd.Series) -> tuple:
            """Returns (condition_met, signal_type)"""
            if reversion_target not in row:
                return False, 'hold'
            price = row['close']
            mean = row[reversion_target]
            std_col = f'std_{lookback_period}'
            if std_col not in row or pd.isna(row[std_col]):
                return False, 'hold'
            std = row[std_col]
            if std == 0:
                return False, 'hold'
            z_score = (price - mean) / std

            if z_score < -std_threshold:  # Oversold -> buy
                return True, 'buy'
            elif z_score > std_threshold:  # Overbought -> sell
                return True, 'sell'
            else:
                return False, 'hold'

        super().__init__(
            metadata=metadata,
            condition_func=condition_func,
            signal_type='buy',  # Will be overridden in evaluate()
            confidence_func=confidence_func,
            required_features=['close', reversion_target, f'std_{lookback_period}']
        )

        self.params.update({
            'lookback_period': lookback_period,
            'std_threshold': std_threshold,
            'reversion_target': reversion_target
        })
        self.dynamic_condition = dynamic_condition

    def evaluate(self, row: pd.Series, context: Optional[Dict[str, Any]] = None) -> Signal:
        """Override to handle dynamic signal type"""
        try:
            condition_met, signal_type = self.dynamic_condition(row)

            if condition_met:
                confidence = self.confidence_func(row)
                confidence = max(0.0, min(1.0, confidence))

                reasoning = f"Mean reversion: Price deviated {self.params['std_threshold']}σ from {self.params['reversion_target']}"
                if self.metadata.paper_title:
                    reasoning += f" (from: {self.metadata.paper_title})"

                return Signal(signal_type, confidence, reasoning)
            else:
                return Signal('hold', 0.0, "Within normal range")

        except Exception as e:
            logger.error(f"Error evaluating mean reversion rule {self.metadata.rule_id}: {e}")
            return Signal('hold', 0.0, f"Evaluation error: {str(e)}")


class BreakoutRule(PaperExtractedRule):
    """
    Breakout strategy
    Example: High/low breakout systems from various papers
    """

    def __init__(
        self,
        metadata: RuleMetadata,
        lookback_period: int = 20,  # 20-day high/low
        breakout_type: str = 'high'  # 'high' or 'low'
    ):
        """
        Breakout strategy

        Args:
            metadata: Rule metadata
            lookback_period: Period to calculate high/low
            breakout_type: 'high' (bullish breakout) or 'low' (bearish breakdown)
        """
        metadata.tags.append('breakout')

        def condition_func(row: pd.Series) -> bool:
            """Check if price breaks high/low"""
            high_col = f'high_{lookback_period}d'
            low_col = f'low_{lookback_period}d'
            price = row['close']

            if breakout_type == 'high':
                if high_col not in row or pd.isna(row[high_col]):
                    return False
                return price >= row[high_col]
            else:  # 'low'
                if low_col not in row or pd.isna(row[low_col]):
                    return False
                return price <= row[low_col]

        def confidence_func(row: pd.Series) -> float:
            """Confidence based on breakout strength"""
            price = row['close']
            if breakout_type == 'high':
                high_col = f'high_{lookback_period}d'
                if high_col not in row or pd.isna(row[high_col]) or row[high_col] == 0:
                    return 0.7
                breakout_pct = (price - row[high_col]) / row[high_col]
            else:
                low_col = f'low_{lookback_period}d'
                if low_col not in row or pd.isna(row[low_col]) or row[low_col] == 0:
                    return 0.7
                breakout_pct = (row[low_col] - price) / row[low_col]

            return min(0.7 + breakout_pct * 10, 1.0)

        signal_type = 'buy' if breakout_type == 'high' else 'sell'
        required_col = f'high_{lookback_period}d' if breakout_type == 'high' else f'low_{lookback_period}d'

        super().__init__(
            metadata=metadata,
            condition_func=condition_func,
            signal_type=signal_type,
            confidence_func=confidence_func,
            required_features=['close', required_col]
        )

        self.params.update({
            'lookback_period': lookback_period,
            'breakout_type': breakout_type
        })


if __name__ == "__main__":
    # Test code
    from datetime import datetime

    # Test Momentum Rule
    metadata = RuleMetadata(
        rule_id="PAPER_MOM_001",
        name="Momentum Strategy",
        description="12-month momentum from Jegadeesh & Titman (1993)",
        source="paper",
        paper_title="Jegadeesh & Titman (1993): Returns to Buying Winners and Selling Losers"
    )

    rule = MomentumRule(metadata, lookback_period=252, threshold=0.10)
    print(f"Required features: {rule.get_required_features()}")

    # Test with sample data
    test_row = pd.Series({
        'close': 110,
        'return_252d': 0.15  # 15% return over past year
    })

    signal = rule.evaluate(test_row)
    print(f"Signal: {signal.action} (confidence: {signal.confidence:.2f})")
    print(f"Reasoning: {signal.reasoning}")
