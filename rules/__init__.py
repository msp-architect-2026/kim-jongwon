"""
Trading Rules System
"""

from .base_rule import BaseRule, RuleMetadata, Signal, CompositeRule
from .technical_rules import (
    MovingAverageCrossRule,
    RSIRule,
    BollingerBandsRule,
    MACDRule,
    VolumeBreakoutRule,
    TrendFollowingRule,
    ATRVolatilityRule
)
from .paper_rules import (
    PaperExtractedRule,
    MomentumRule,
    ValueRule,
    MeanReversionRule,
    BreakoutRule
)
from .rule_validator import RuleValidator, SignalAnalyzer
from .optimizer import ParameterOptimizer

__all__ = [
    # Base classes
    'BaseRule',
    'RuleMetadata',
    'Signal',
    'CompositeRule',

    # Technical rules
    'MovingAverageCrossRule',
    'RSIRule',
    'BollingerBandsRule',
    'MACDRule',
    'VolumeBreakoutRule',
    'TrendFollowingRule',
    'ATRVolatilityRule',

    # Paper-based rules
    'PaperExtractedRule',
    'MomentumRule',
    'ValueRule',
    'MeanReversionRule',
    'BreakoutRule',

    # Validation
    'RuleValidator',
    'SignalAnalyzer',

    # Optimization
    'ParameterOptimizer'
]
