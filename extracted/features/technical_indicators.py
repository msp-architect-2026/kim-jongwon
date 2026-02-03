# extracted/features/technical_indicators.py
"""
기술적 지표 계산 모듈

주요 지표:
- 이동평균 (SMA, EMA)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- 볼린저 밴드 (Bollinger Bands)
- ATR (Average True Range)
- Stochastic Oscillator
- ADX (Average Directional Index)
- OBV (On-Balance Volume)
- VWAP (Volume-Weighted Average Price)
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from scripts.logger_config import setup_logger

logger = setup_logger("technical_indicators")


class TechnicalIndicators:
    """기술적 지표 계산 클래스"""

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """
        Simple Moving Average (단순 이동평균)

        Args:
            series: 가격 시리즈
            period: 기간

        Returns:
            SMA 시리즈
        """
        return series.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """
        Exponential Moving Average (지수 이동평균)

        Args:
            series: 가격 시리즈
            period: 기간

        Returns:
            EMA 시리즈
        """
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index

        Args:
            series: 가격 시리즈
            period: 기간 (기본값 14)

        Returns:
            RSI 시리즈 (0-100)
        """
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence)

        Args:
            series: 가격 시리즈
            fast: 빠른 EMA 기간
            slow: 느린 EMA 기간
            signal: 시그널 라인 기간

        Returns:
            (macd_line, signal_line, histogram)
        """
        ema_fast = TechnicalIndicators.ema(series, fast)
        ema_slow = TechnicalIndicators.ema(series, slow)

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands (볼린저 밴드)

        Args:
            series: 가격 시리즈
            period: 이동평균 기간
            std: 표준편차 배수

        Returns:
            (upper_band, middle_band, lower_band)
        """
        middle_band = TechnicalIndicators.sma(series, period)
        rolling_std = series.rolling(window=period).std()

        upper_band = middle_band + (rolling_std * std)
        lower_band = middle_band - (rolling_std * std)

        return upper_band, middle_band, lower_band

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        Average True Range (평균 진정한 범위)

        Args:
            high: 최고가 시리즈
            low: 최저가 시리즈
            close: 종가 시리즈
            period: 기간

        Returns:
            ATR 시리즈
        """
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr

    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                   k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Stochastic Oscillator (스토캐스틱 오실레이터)

        Args:
            high: 최고가 시리즈
            low: 최저가 시리즈
            close: 종가 시리즈
            k_period: %K 기간
            d_period: %D 기간 (이동평균)

        Returns:
            (%K, %D)
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        denom = highest_high - lowest_low
        k_percent = np.where(denom == 0, 50.0, 100 * ((close - lowest_low) / denom))
        k_percent = pd.Series(k_percent, index=close.index)
        d_percent = k_percent.rolling(window=d_period).mean()

        return k_percent, d_percent

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        Average Directional Index (평균 방향성 지수)
        추세의 강도를 측정 (0-100)

        Args:
            high: 최고가 시리즈
            low: 최저가 시리즈
            close: 종가 시리즈
            period: 기간

        Returns:
            ADX 시리즈
        """
        # True Range 계산
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional Movement 계산
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smoothed TR, +DM, -DM
        atr = true_range.rolling(window=period).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=high.index).rolling(window=period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm, index=high.index).rolling(window=period).mean() / atr)

        # ADX 계산
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()

        return adx

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        On-Balance Volume (온밸런스 볼륨)

        Args:
            close: 종가 시리즈
            volume: 거래량 시리즈

        Returns:
            OBV 시리즈
        """
        direction = np.sign(close.diff())
        directed_volume = direction * volume
        directed_volume.iloc[0] = volume.iloc[0]
        return directed_volume.cumsum()

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        Volume-Weighted Average Price (거래량 가중 평균 가격)

        Args:
            high: 최고가 시리즈
            low: 최저가 시리즈
            close: 종가 시리즈
            volume: 거래량 시리즈

        Returns:
            VWAP 시리즈
        """
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        return vwap

    @staticmethod
    def calculate_all(df: pd.DataFrame, config: dict) -> pd.DataFrame:
        """
        모든 기술적 지표를 한 번에 계산

        Args:
            df: OHLCV 데이터프레임
            config: TechnicalIndicatorConfig의 딕셔너리

        Returns:
            지표가 추가된 데이터프레임
        """
        result = df.copy()

        try:
            # SMA
            for period in config.get('sma_periods', []):
                result[f'sma_{period}'] = TechnicalIndicators.sma(df['close'], period)
                logger.debug(f"Calculated SMA_{period}")

            # EMA
            for period in config.get('ema_periods', []):
                result[f'ema_{period}'] = TechnicalIndicators.ema(df['close'], period)
                logger.debug(f"Calculated EMA_{period}")

            # RSI
            rsi_period = config.get('rsi_period', 14)
            result['rsi'] = TechnicalIndicators.rsi(df['close'], rsi_period)
            logger.debug(f"Calculated RSI_{rsi_period}")

            # MACD
            macd_fast = config.get('macd_fast', 12)
            macd_slow = config.get('macd_slow', 26)
            macd_signal = config.get('macd_signal', 9)
            macd_line, signal_line, histogram = TechnicalIndicators.macd(
                df['close'], macd_fast, macd_slow, macd_signal
            )
            result['macd'] = macd_line
            result['macd_signal'] = signal_line
            result['macd_histogram'] = histogram
            logger.debug("Calculated MACD")

            # Bollinger Bands
            bb_period = config.get('bb_period', 20)
            bb_std = config.get('bb_std', 2.0)
            bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(
                df['close'], bb_period, bb_std
            )
            result['bb_upper'] = bb_upper
            result['bb_middle'] = bb_middle
            result['bb_lower'] = bb_lower
            result['bb_width'] = (bb_upper - bb_lower) / bb_middle  # 밴드 폭
            logger.debug("Calculated Bollinger Bands")

            # ATR
            atr_period = config.get('atr_period', 14)
            result['atr'] = TechnicalIndicators.atr(df['high'], df['low'], df['close'], atr_period)
            logger.debug(f"Calculated ATR_{atr_period}")

            # Stochastic
            stoch_k = config.get('stoch_k_period', 14)
            stoch_d = config.get('stoch_d_period', 3)
            k_percent, d_percent = TechnicalIndicators.stochastic(
                df['high'], df['low'], df['close'], stoch_k, stoch_d
            )
            result['stoch_k'] = k_percent
            result['stoch_d'] = d_percent
            logger.debug("Calculated Stochastic")

            # ADX
            adx_period = config.get('adx_period', 14)
            result['adx'] = TechnicalIndicators.adx(df['high'], df['low'], df['close'], adx_period)
            logger.debug(f"Calculated ADX_{adx_period}")

            # Volume MA (for VolumeBreakoutRule)
            vol_ma_period = config.get('volume_ma_period', 20)
            result[f'volume_ma_{vol_ma_period}'] = df['volume'].rolling(window=vol_ma_period).mean()
            logger.debug(f"Calculated Volume_MA_{vol_ma_period}")

            # Price Change Pct (for VolumeBreakoutRule)
            result['price_change_pct'] = df['close'].pct_change()
            logger.debug("Calculated price_change_pct")

            # OBV
            if config.get('obv_enabled', True):
                result['obv'] = TechnicalIndicators.obv(df['close'], df['volume'])
                logger.debug("Calculated OBV")

            # VWAP
            if config.get('vwap_enabled', True):
                result['vwap'] = TechnicalIndicators.vwap(
                    df['high'], df['low'], df['close'], df['volume']
                )
                logger.debug("Calculated VWAP")

            logger.info(f"Successfully calculated all technical indicators")

        except Exception as e:
            logger.error(f"Error calculating technical indicators: {e}")
            raise

        return result
