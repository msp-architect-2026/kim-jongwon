"""
Base Rule Classes for Trading Strategy Rules
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class RuleMetadata:
    """Rule metadata for tracking and validation"""
    rule_id: str
    name: str
    description: str
    source: str  # 'paper', 'technical', 'manual'
    created_at: datetime = field(default_factory=datetime.now)
    paper_title: Optional[str] = None
    paper_section: Optional[str] = None
    backtest_sharpe: Optional[float] = None
    backtest_win_rate: Optional[float] = None
    is_validated: bool = False
    tags: List[str] = field(default_factory=list)


@dataclass
class Signal:
    """Trading signal with confidence and reasoning"""
    action: str  # 'buy', 'sell', 'hold'
    confidence: float  # 0.0 to 1.0
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate signal"""
        if self.action not in ['buy', 'sell', 'hold']:
            raise ValueError(f"Invalid action: {self.action}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0-1, got {self.confidence}")


class BaseRule(ABC):
    """Abstract base class for all trading rules"""

    def __init__(self, metadata: RuleMetadata, params: Optional[Dict[str, Any]] = None):
        """
        Initialize rule

        Args:
            metadata: Rule metadata
            params: Rule-specific parameters
        """
        self.metadata = metadata
        self.params = params or {}
        self._validation_errors = []

        logger.info(f"Rule initialized: {metadata.name} (ID: {metadata.rule_id})")

    @abstractmethod
    def evaluate(self, row: pd.Series, context: Optional[Dict[str, Any]] = None) -> Signal:
        """
        Evaluate rule on a single data row

        Args:
            row: OHLCV + features row
            context: Optional context (portfolio state, market conditions, etc.)

        Returns:
            Trading signal
        """
        pass

    @abstractmethod
    def get_required_features(self) -> List[str]:
        """
        Get list of required features for this rule

        Returns:
            List of feature column names
        """
        pass

    def validate(self, data: pd.DataFrame) -> bool:
        """
        Validate that data contains required features

        Args:
            data: DataFrame with features

        Returns:
            True if valid, False otherwise
        """
        self._validation_errors = []
        required = self.get_required_features()
        missing = [f for f in required if f not in data.columns]

        if missing:
            error = f"Missing required features: {missing}"
            self._validation_errors.append(error)
            logger.error(f"{self.metadata.name}: {error}")
            return False

        return True

    def get_validation_errors(self) -> List[str]:
        """Get validation errors from last validate() call"""
        return self._validation_errors

    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary for serialization"""
        return {
            'metadata': {
                'rule_id': self.metadata.rule_id,
                'name': self.metadata.name,
                'description': self.metadata.description,
                'source': self.metadata.source,
                'created_at': self.metadata.created_at.isoformat(),
                'paper_title': self.metadata.paper_title,
                'paper_section': self.metadata.paper_section,
                'backtest_sharpe': self.metadata.backtest_sharpe,
                'backtest_win_rate': self.metadata.backtest_win_rate,
                'is_validated': self.metadata.is_validated,
                'tags': self.metadata.tags
            },
            'params': self.params,
            'required_features': self.get_required_features()
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.metadata.rule_id}: {self.metadata.name}>"

# 복합적으로 전략을 구현할 떄, ex: MACD + RSI
class CompositeRule(BaseRule): 
    """Composite rule that combines multiple rules"""

    def __init__(
        self,
        metadata: RuleMetadata,
        rules: List[BaseRule],
        combination_logic: str = 'AND',  # 'AND', 'OR', 'WEIGHTED'
        weights: Optional[List[float]] = None
    ):
        """
        Initialize composite rule

        Args:
            metadata: Rule metadata
            rules: List of child rules
            combination_logic: How to combine signals ('AND', 'OR', 'WEIGHTED')
            weights: Weights for WEIGHTED logic (must sum to 1.0)
        """
        super().__init__(metadata, params={
            'combination_logic': combination_logic,
            'weights': weights
        })
        self.rules = rules
        self.combination_logic = combination_logic
        self.weights = weights

        if combination_logic == 'WEIGHTED':
            if not weights or len(weights) != len(rules):
                raise ValueError("WEIGHTED logic requires weights for each rule")
            if abs(sum(weights) - 1.0) > 1e-6:
                raise ValueError(f"Weights must sum to 1.0, got {sum(weights)}")

    def evaluate(self, row: pd.Series, context: Optional[Dict[str, Any]] = None) -> Signal:
        """Evaluate all child rules and combine signals"""
        signals = [rule.evaluate(row, context) for rule in self.rules]

        if self.combination_logic == 'AND':
            return self._combine_and(signals)
        elif self.combination_logic == 'OR':
            return self._combine_or(signals)
        elif self.combination_logic == 'WEIGHTED':
            return self._combine_weighted(signals)
        else:
            raise ValueError(f"Unknown combination logic: {self.combination_logic}")

    def _combine_and(self, signals: List[Signal]) -> Signal:
        """All rules must agree (buy/sell), otherwise hold"""
        actions = [s.action for s in signals]

        if all(a == 'buy' for a in actions):
            avg_confidence = sum(s.confidence for s in signals) / len(signals)
            reasoning = " AND ".join(s.reasoning for s in signals)
            return Signal('buy', avg_confidence, reasoning)
        elif all(a == 'sell' for a in actions):
            avg_confidence = sum(s.confidence for s in signals) / len(signals)
            reasoning = " AND ".join(s.reasoning for s in signals)
            return Signal('sell', avg_confidence, reasoning)
        else:
            return Signal('hold', 0.0, "Rules disagree - holding")

    def _combine_or(self, signals: List[Signal]) -> Signal:
        """Any rule triggers (take strongest signal)"""
        buy_signals = [s for s in signals if s.action == 'buy']
        sell_signals = [s for s in signals if s.action == 'sell']

        if buy_signals:
            strongest = max(buy_signals, key=lambda s: s.confidence)
            return strongest
        elif sell_signals:
            strongest = max(sell_signals, key=lambda s: s.confidence)
            return strongest
        else:
            return Signal('hold', 0.0, "No strong signals")

    def _combine_weighted(self, signals: List[Signal]) -> Signal:
        """Weighted combination of signals"""
        buy_score = sum(w * s.confidence for w, s in zip(self.weights, signals) if s.action == 'buy')
        sell_score = sum(w * s.confidence for w, s in zip(self.weights, signals) if s.action == 'sell')

        if buy_score > sell_score and buy_score > 0.5:
            reasoning = f"Weighted buy score: {buy_score:.2f}"
            return Signal('buy', buy_score, reasoning)
        elif sell_score > buy_score and sell_score > 0.5:
            reasoning = f"Weighted sell score: {sell_score:.2f}"
            return Signal('sell', sell_score, reasoning)
        else:
            return Signal('hold', 0.0, f"Inconclusive: buy={buy_score:.2f}, sell={sell_score:.2f}")

    def get_required_features(self) -> List[str]:
        """Combine required features from all child rules"""
        all_features = []
        for rule in self.rules:
            all_features.extend(rule.get_required_features())
        return list(set(all_features))  # Remove duplicates


if __name__ == "__main__":
    # Test code
    metadata = RuleMetadata(
        rule_id="TEST_001",
        name="Test Rule",
        description="Test rule for validation",
        source="manual"
    )

    signal = Signal(
        action='buy',
        confidence=0.75,
        reasoning="Test signal"
    )

    print(f"Signal: {signal.action} (confidence: {signal.confidence})")
    print(f"Metadata: {metadata.name} from {metadata.source}")
