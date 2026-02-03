# scripts/qa_prices.py

import os
import json
import pandas as pd
import hashlib
from dotenv import load_dotenv
from typing import Dict, Any
from logger_config import setup_logger
from config import Config

# .env 파일에서 환경 변수 로드
load_dotenv()

# 로거 설정
logger = setup_logger("qa_prices")

# 설정 확인 및 디렉토리 생성
Config.ensure_directories()
DATA_DIR = Config.DATA_DIR
REPORTS_DIR = Config.REPORTS_DIR

# CSV 파일에서 티커 목록 자동 감지
def get_available_tickers() -> list:
    """데이터 디렉토리에서 사용 가능한 티커 목록을 가져옵니다."""
    try:
        if not os.path.exists(DATA_DIR):
            logger.warning(f"Data directory does not exist: {DATA_DIR}")
            return []

        csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
        tickers = [os.path.splitext(f)[0] for f in csv_files]
        logger.debug(f"Found {len(tickers)} ticker files in {DATA_DIR}")
        return sorted(tickers)
    except Exception as e:
        logger.error(f"Error reading ticker files: {e}")
        return []

# 다이나믹 티커 리스트
TICKERS = get_available_tickers()

def ensure_bool(value: Any) -> bool:
    """Convert truthy values to native bool for JSON serialization compatibility."""
    return bool(value)

def get_file_hash(file_path):
    """파일의 SHA256 해시를 계산합니다."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def validate_price_logic(df: pd.DataFrame, ticker: str) -> Dict[str, Any]:
    """
    가격 데이터의 논리적 유효성을 검증합니다.

    Args:
        df: 가격 데이터 DataFrame
        ticker: 티커 심볼

    Returns:
        검증 결과 딕셔너리
    """
    checks = {}

    try:
        # 1. High >= Low 검증
        high_low_violations = (df['high'] < df['low']).sum()
        checks['high_gte_low'] = {
            'pass': ensure_bool(high_low_violations == 0),
            'violations': int(high_low_violations),
            'details': f'{high_low_violations} days where high < low'
        }

        # 2. High >= Open, Close 검증
        high_open_violations = (df['high'] < df['open']).sum()
        high_close_violations = (df['high'] < df['close']).sum()
        total_high_violations = high_open_violations + high_close_violations
        checks['high_gte_open_close'] = {
            'pass': ensure_bool(total_high_violations == 0),
            'violations': int(total_high_violations),
            'details': f'{high_open_violations} high<open, {high_close_violations} high<close'
        }

        # 3. Low <= Open, Close 검증
        low_open_violations = (df['low'] > df['open']).sum()
        low_close_violations = (df['low'] > df['close']).sum()
        total_low_violations = low_open_violations + low_close_violations
        checks['low_lte_open_close'] = {
            'pass': ensure_bool(total_low_violations == 0),
            'violations': int(total_low_violations),
            'details': f'{low_open_violations} low>open, {low_close_violations} low>close'
        }

        # 4. 양수 가격 검증
        price_columns = ['open', 'high', 'low', 'close']
        # adj_close가 있으면 추가
        if 'adj_close' in df.columns:
            price_columns.append('adj_close')

        negative_prices = (df[price_columns] <= 0).any(axis=1).sum()
        checks['positive_prices'] = {
            'pass': ensure_bool(negative_prices == 0),
            'violations': int(negative_prices),
            'details': f'{negative_prices} days with non-positive prices'
        }

        # 5. 양수 거래량 검증
        negative_volume = (df['volume'] < 0).sum()
        checks['non_negative_volume'] = {
            'pass': ensure_bool(negative_volume == 0),
            'violations': int(negative_volume),
            'details': f'{negative_volume} days with negative volume'
        }

        # 6. 극단적 가격 변동 검증 (Config 임계값 사용)
        daily_returns = df['close'].pct_change().abs()
        max_daily_return = Config.VALIDATION_THRESHOLDS['max_daily_return']
        extreme_moves = (daily_returns > max_daily_return).sum()
        extreme_threshold = max(1, len(df) * Config.VALIDATION_THRESHOLDS['extreme_move_threshold'])
        checks['reasonable_price_moves'] = {
            'pass': ensure_bool(extreme_moves <= extreme_threshold),
            'violations': int(extreme_moves),
            'details': f'{extreme_moves} days with >{max_daily_return*100}% price change (threshold: {extreme_threshold:.0f})'
        }

        # 7. 데이터 연속성 검증 (과도한 가격 간격 체크, 0으로 나누기 방지)
        df_sorted = df.sort_index()
        prev_close = df_sorted['close'].shift(1)

        # 0이나 NaN인 이전 종가를 마스킹하여 0으로 나누기 방지
        valid_mask = (prev_close > 0) & prev_close.notna()
        close_gaps = pd.Series(0.0, index=df_sorted.index)
        close_gaps[valid_mask] = (df_sorted['close'].diff().abs() / prev_close)[valid_mask]

        max_price_gap = Config.VALIDATION_THRESHOLDS['max_price_gap']
        large_gaps = (close_gaps > max_price_gap).sum()
        gap_threshold = max(1, len(df) * Config.VALIDATION_THRESHOLDS['large_gap_threshold'])
        checks['price_continuity'] = {
            'pass': ensure_bool(large_gaps <= gap_threshold),
            'violations': int(large_gaps),
            'details': f'{large_gaps} large price gaps >{max_price_gap*100}% (threshold: {gap_threshold:.0f})'
        }

        # 8. 거래량 이상치 검증 (개선: 스파이크 감지 강화)
        volume_median = df['volume'].median()
        volume_multiplier = Config.VALIDATION_THRESHOLDS['volume_outlier_multiplier']

        if volume_median > 0:
            # 중앙값이 양수인 경우 정상적으로 계산
            volume_outliers = (df['volume'] > volume_median * volume_multiplier).sum()
            baseline_description = f"median={volume_median:.0f}"
        else:
            # 중앙값이 0인 경우 75% 분위수 사용
            volume_q75 = df['volume'].quantile(0.75)
            if volume_q75 > 0:
                volume_outliers = (df['volume'] > volume_q75 * volume_multiplier).sum()
                baseline_description = f"Q75={volume_q75:.0f}"
            else:
                # 거래량이 거의 없는 경우: 양수 거래량의 최대값을 기준으로 스파이크 감지
                positive_volumes = df['volume'][df['volume'] > 0]

                if len(positive_volumes) > 0:
                    # 양수 거래량이 있는 경우: 비율에 따라 다른 전략 사용
                    positive_ratio = len(positive_volumes) / len(df)

                    if positive_ratio < 0.5:
                        # 거래일이 절반 미만: 스파이크 감지 모드
                        # 최대값을 기준으로 상위 이상치 탐지
                        volume_max = positive_volumes.max()
                        volume_90th = positive_volumes.quantile(0.9)

                        # 90분위수 이상 또는 최대값의 70% 이상을 스파이크로 간주
                        if volume_90th > 0:
                            volume_outliers = (df['volume'] >= volume_90th).sum()
                            baseline_description = f"Q90={volume_90th:.0f}"
                        else:
                            volume_outliers = (df['volume'] >= volume_max * 0.7).sum()
                            baseline_description = f"max*0.7={volume_max*0.7:.0f}"

                        logger.info(f"Sparse trading detected for {ticker} ({positive_ratio:.1%} trading days), using spike detection")
                    else:
                        # 거래일이 절반 이상: 평균 기준 사용
                        volume_mean_positive = positive_volumes.mean()

                        if volume_mean_positive > 0:
                            # 평균의 배수로 이상치 판단
                            volume_outliers = (df['volume'] > volume_mean_positive * volume_multiplier).sum()
                            baseline_description = f"positive_mean={volume_mean_positive:.0f}"
                            logger.info(f"Volume median/Q75 are zero for {ticker}, using positive mean: {volume_mean_positive:.0f}")
                        else:
                            # 모든 양수 거래량이 매우 작은 경우: 최대값 기준
                            volume_max = positive_volumes.max()
                            volume_outliers = (df['volume'] >= volume_max * 0.5).sum()
                            baseline_description = f"max*0.5={volume_max*0.5:.0f}"
                            logger.info(f"Using max volume spike detection for {ticker}: max={volume_max:.0f}")
                else:
                    # 모든 거래량이 0인 경우만 검증 스킵
                    volume_outliers = 0
                    baseline_description = "all_zero"
                    logger.warning(f"All volume is zero for {ticker}, skipping outlier check")

        outlier_threshold = max(1, len(df) * 0.005)  # 0.5%
        checks['volume_outliers'] = {
            'pass': ensure_bool(volume_outliers <= outlier_threshold),
            'violations': int(volume_outliers),
            'details': f'{volume_outliers} extreme volume days (threshold: {outlier_threshold:.0f}, baseline: {baseline_description})'
        }

        logger.debug(f"Logic validation completed for {ticker}")

    except Exception as e:
        logger.error(f"Logic validation failed for {ticker}: {e}")
        checks['validation_error'] = {'pass': False, 'error': str(e)}

    return checks

def qa_price_data():
    """
    저장된 가격 데이터의 품질을 검사하고 결과를 JSON 파일로 저장합니다.
    """
    logger.info("Starting price data quality assurance process...")

    if not TICKERS:
        logger.warning("No CSV files found in data directory")
        return
    
    # 리포트 디렉토리가 없으면 생성
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    qa_results = {}
    
    for i, ticker in enumerate(TICKERS, 1):
        logger.info(f"QA for {ticker} ({i}/{len(TICKERS)})...")
        file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
        ticker_result = {"pass": False, "checks": {}, "logic_checks": {}}
        
        # 1. 파일 존재 여부 확인
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            ticker_result["checks"]["file_exists"] = {"pass": False, "details": "File not found"}
            qa_results[ticker] = ticker_result
            continue
        
        ticker_result["checks"]["file_exists"] = {"pass": True}
        
        try:
            df = pd.read_csv(file_path, index_col='Date', parse_dates=True)
            
            # 2. 데이터 row 수 확인
            row_count = len(df)
            ticker_result["row_count"] = row_count
            ticker_result["checks"]["has_data"] = {"pass": ensure_bool(row_count > 0), "details": f"{row_count} rows"}

            # 3. 결측치(NaN) 확인
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            # adj_close는 선택적 (optional)으로 체크

            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                ticker_result["checks"]["required_columns"] = {
                    "pass": False,
                    "details": f"Missing columns: {missing_columns}"
                }
            else:
                # 필수 컬럼의 NaN 체크
                check_columns = required_columns.copy()
                # adj_close가 있으면 체크 대상에 포함
                if 'adj_close' in df.columns:
                    check_columns.append('adj_close')

                nan_count = df[check_columns].isnull().sum().sum()
                ticker_result["checks"]["no_missing_values"] = {
                    "pass": ensure_bool(nan_count == 0),
                    "details": f"{nan_count} missing values found"
                }

            # 4. 중복된 날짜(index) 확인
            duplicate_count = df.index.duplicated().sum()
            ticker_result["checks"]["no_duplicate_dates"] = {
                "pass": ensure_bool(duplicate_count == 0),
                "details": f"{duplicate_count} duplicate dates found"
            }

            # 5. 데이터 범위 확인 (최근 1년 데이터 존재 여부)
            latest_date = df.index.max()
            days_since_latest = (pd.Timestamp.now() - latest_date).days
            ticker_result["checks"]["data_freshness"] = {
                "pass": ensure_bool(days_since_latest <= 7),  # 1주일 이내
                "details": f"Latest data: {latest_date.strftime('%Y-%m-%d')} ({days_since_latest} days ago)"
            }

            # 6. 논리적 검증 수행
            if not missing_columns:
                logic_checks = validate_price_logic(df, ticker)
                ticker_result["logic_checks"] = logic_checks

            # 7. 파일 해시 및 row 수 (재실행시 동일성 체크용)
            ticker_result["file_hash_sha256"] = get_file_hash(file_path)

            # 최종 통과 여부 결정
            basic_checks_passed = all(check["pass"] for check in ticker_result["checks"].values())
            logic_checks_passed = all(check.get("pass", True) for check in ticker_result.get("logic_checks", {}).values())

            ticker_result["pass"] = ensure_bool(basic_checks_passed and logic_checks_passed)

            if ticker_result["pass"]:
                logger.info(f"PASS: All QA checks passed for {ticker}")
            else:
                failed_basic = [k for k, v in ticker_result["checks"].items() if not v["pass"]]
                failed_logic = [k for k, v in ticker_result.get("logic_checks", {}).items() if not v.get("pass", True)]
                logger.warning(f"FAIL: QA issues for {ticker} - Basic: {failed_basic}, Logic: {failed_logic}")

        except Exception as e:
            logger.error(f"QA error for {ticker}: {e}")
            ticker_result["pass"] = False
            ticker_result["error"] = str(e)
            
        qa_results[ticker] = ticker_result

    # 결과 리포트 파일 저장
    report_path = os.path.join(REPORTS_DIR, "qa_prices.json")
    with open(report_path, 'w') as f:
        json.dump(qa_results, f, indent=4)
        
    # 요약 통계
    total_tickers = len(qa_results)
    passed_tickers = sum(1 for result in qa_results.values() if result["pass"])
    failed_tickers = total_tickers - passed_tickers

    logger.info(f"QA process completed: {passed_tickers}/{total_tickers} passed, {failed_tickers} failed")
    logger.info(f"Detailed report saved to {report_path}")

    # 실패한 티커들에 대한 요약 출력
    if failed_tickers > 0:
        failed_list = [ticker for ticker, result in qa_results.items() if not result["pass"]]
        logger.warning(f"Failed QA tickers: {failed_list[:10]}{'...' if len(failed_list) > 10 else ''}")

if __name__ == "__main__":
    if not TICKERS:
        logger.warning("No ticker data found. Please run data_loader.py first.")
    else:
        logger.info(f"Found {len(TICKERS)} tickers to analyze: {TICKERS[:5]}{'...' if len(TICKERS) > 5 else ''}")
        qa_price_data()
