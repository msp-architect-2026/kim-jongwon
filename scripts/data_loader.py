# scripts/data_loader.py

import os
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
import time
from typing import List, Dict, Optional
from logger_config import setup_logger
from config import Config

# .env 파일에서 환경 변수 로드
load_dotenv()

# 로거 설정
logger = setup_logger("data_loader")

# 설정 확인 및 디렉토리 생성
Config.ensure_directories()
DATA_DIR = Config.DATA_DIR
TICKERS = Config.DEFAULT_TICKERS

# 데이터 다운로드 기간 설정
START_DATE = "2000-01-01"
END_DATE = pd.to_datetime("today").strftime("%Y-%m-%d")

def fix_price_anomalies(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    가격 데이터의 논리적 오류를 자동으로 수정합니다.

    Args:
        data: 가격 데이터 DataFrame
        ticker: 티커 심볼

    Returns:
        수정된 데이터 DataFrame
    """
    fixed_count = 0

    # 1. High < Low 수정: High와 Low를 교체
    high_low_violations = data['high'] < data['low']
    if high_low_violations.any():
        count = high_low_violations.sum()
        logger.warning(f"{ticker}: Fixing {count} rows where high < low (swapping values)")
        data.loc[high_low_violations, ['high', 'low']] = data.loc[high_low_violations, ['low', 'high']].values
        fixed_count += count

    # 2. High < Open or High < Close 수정: High를 max(Open, Close, High)로 설정
    high_violations = (data['high'] < data['open']) | (data['high'] < data['close'])
    if high_violations.any():
        count = high_violations.sum()
        logger.warning(f"{ticker}: Fixing {count} rows where high < open/close")
        data.loc[high_violations, 'high'] = data.loc[high_violations, ['open', 'close', 'high']].max(axis=1)
        fixed_count += count

    # 3. Low > Open or Low > Close 수정: Low를 min(Open, Close, Low)로 설정
    low_violations = (data['low'] > data['open']) | (data['low'] > data['close'])
    if low_violations.any():
        count = low_violations.sum()
        logger.warning(f"{ticker}: Fixing {count} rows where low > open/close")
        data.loc[low_violations, 'low'] = data.loc[low_violations, ['open', 'close', 'low']].min(axis=1)
        fixed_count += count

    if fixed_count > 0:
        logger.info(f"{ticker}: Fixed {fixed_count} price anomalies")

    return data

def validate_price_data(data: pd.DataFrame, ticker: str) -> Dict[str, bool]:
    """
    다운로드된 가격 데이터의 기본적인 논리적 검증을 수행합니다.

    Args:
        data: 가격 데이터 DataFrame
        ticker: 티커 심볼

    Returns:
        검증 결과 딕셔너리
    """
    validation_results = {}

    try:
        # 1. High >= Low 검증
        high_low_valid = (data['high'] >= data['low']).all()
        validation_results['high_gte_low'] = high_low_valid

        # 2. High >= Open, Close 검증
        high_open_valid = (data['high'] >= data['open']).all()
        high_close_valid = (data['high'] >= data['close']).all()
        validation_results['high_gte_open_close'] = high_open_valid and high_close_valid

        # 3. Low <= Open, Close 검증
        low_open_valid = (data['low'] <= data['open']).all()
        low_close_valid = (data['low'] <= data['close']).all()
        validation_results['low_lte_open_close'] = low_open_valid and low_close_valid

        # 4. 양수 가격 검증
        positive_prices = (data[['open', 'high', 'low', 'close']] > 0).all().all()
        validation_results['positive_prices'] = positive_prices

        # 5. 양수 거래량 검증
        positive_volume = (data['volume'] >= 0).all()
        validation_results['non_negative_volume'] = positive_volume

        # 6. 극단적 가격 변동 검증
        daily_returns = data['close'].pct_change().abs()
        extreme_moves = (daily_returns > Config.VALIDATION_THRESHOLDS['max_daily_return']).sum()
        validation_results['reasonable_moves'] = extreme_moves < len(data) * Config.VALIDATION_THRESHOLDS['extreme_move_threshold']

        logger.info(f"Validation completed for {ticker}: {validation_results}")

    except Exception as e:
        logger.error(f"Validation failed for {ticker}: {e}")
        validation_results['validation_error'] = False  # Boolean flag for filtering
        validation_results['validation_error_message'] = str(e)  # Keep error message for debugging

    return validation_results

def download_ticker_data(ticker: str, start_date: str, end_date: str,
                        max_retries: int = 3) -> Optional[pd.DataFrame]:
    """
    개별 티커의 데이터를 다운로드합니다.

    Args:
        ticker: 티커 심볼
        start_date: 시작 날짜
        end_date: 종료 날짜
        max_retries: 최대 재시도 횟수

    Returns:
        다운로드된 데이터 또는 None
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading data for {ticker} (attempt {attempt + 1}/{max_retries})")

            # yfinance를 사용하여 데이터 다운로드
            # auto_adjust=False로 설정하여 원본 가격과 Adj Close를 모두 가져옴
            # ticker은 종목 번호를 뜻함. 예: AAPL, MSFT 등
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)

            # 멀티인덱스 컬럼을 단일 레벨로 변환 (yfinance가 때때로 멀티인덱스를 반환함)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            if data.empty:
                logger.warning(f"No data found for {ticker}")
                return None

            # CLAUDE.md 가이드라인에 따라 컬럼명을 소문자로 표준화
            data.columns = [col.lower() for col in data.columns]

            # 'adj close' 컬럼을 'adj_close'로 변경
            if 'adj close' in data.columns:
                data.rename(columns={'adj close': 'adj_close'}, inplace=True)

            # yfinance 원본 순서대로 컬럼 재정렬: Open, High, Low, Close, Adj Close, Volume
            column_order = ['open', 'high', 'low', 'close', 'adj_close', 'volume']
            # 존재하는 컬럼만 선택 (일부 데이터는 adj_close가 없을 수 있음)
            existing_columns = [col for col in column_order if col in data.columns]
            data = data[existing_columns]

            # 가격 이상치 자동 수정
            data = fix_price_anomalies(data, ticker)

            # 데이터 검증
            validation_results = validate_price_data(data, ticker)
            failed_validations = [k for k, v in validation_results.items() if not v]

            if failed_validations:
                logger.warning(f"Validation warnings for {ticker}: {failed_validations}")

                # validation_error가 있으면 에러 메시지도 로깅
                if 'validation_error' in failed_validations and 'validation_error_message' in validation_results:
                    logger.error(f"Validation error details for {ticker}: {validation_results['validation_error_message']}")

            logger.info(f"Successfully downloaded {len(data)} rows for {ticker}")
            return data

        except Exception as e:
            logger.error(f"Failed to download data for {ticker} (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 지수 백오프
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Max retries exceeded for {ticker}")

    return None

def download_price_data(ticker_groups: Optional[List[str]] = None):
    """
    지정된 티커들의 일봉 데이터를 다운로드하여 CSV 파일로 저장합니다.

    Args:
        ticker_groups: 다운로드할 티커 그룹 리스트 (기본값: 모든 그룹)
    """
    logger.info("Starting stock price data download...")

    # 데이터 디렉토리가 없으면 생성
    os.makedirs(DATA_DIR, exist_ok=True)

    # 다운로드할 티커 그룹 결정
    if ticker_groups is None:
        ticker_groups = list(TICKERS.keys())

    # 모든 티커 수집
    all_tickers = []
    for group in ticker_groups:
        if group in TICKERS:
            all_tickers.extend(TICKERS[group])
            logger.info(f"Added {len(TICKERS[group])} tickers from {group} group")
        else:
            logger.warning(f"Unknown ticker group: {group}")

    # 중복 제거 (순서 유지를 위해 dict.fromkeys 사용)
    # dict.fromkeys()는 순서를 유지합니다.
    all_tickers = list(dict.fromkeys(all_tickers))
    logger.info(f"Total {len(all_tickers)} unique tickers to download")

    success_count = 0
    failed_tickers = []

    for i, ticker in enumerate(all_tickers, 1):
        logger.info(f"Processing {ticker} ({i}/{len(all_tickers)})")

        # 데이터 다운로드
        data = download_ticker_data(ticker, START_DATE, END_DATE)

        if data is not None:
            try:
                # 파일 저장 경로 설정
                file_path = os.path.join(DATA_DIR, f"{ticker}.csv")

                # CSV 파일로 저장
                data.to_csv(file_path)

                logger.info(f"Successfully saved data for {ticker} to {file_path}")
                success_count += 1

                # API 요청 제한을 피하기 위해 딜레이 추가
                time.sleep(1)

            except Exception as e:
                logger.error(f"Failed to save data for {ticker}: {e}")
                failed_tickers.append(ticker)
        else:
            failed_tickers.append(ticker)

    # 결과 요약
    logger.info(f"Download process completed: {success_count}/{len(all_tickers)} successful")
    if failed_tickers:
        logger.warning(f"Failed tickers: {failed_tickers}")

if __name__ == "__main__":
    download_price_data()