# scripts/config.py

import os
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

class Config:
    """프로젝트 전체 설정 관리 클래스"""

    # 디렉토리 경로
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")
    RAG_DB = os.getenv("RAG_DB", "./ragdb")
    RULE_DB = os.getenv("RULE_DB", "./ragdb/rules.sqlite")
    SIGNALS_DIR = os.getenv("SIGNALS_DIR", "./signals")

    # 시장 설정
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    FEE_BPS = float(os.getenv("FEE_BPS", "1.0"))
    SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "2.0"))

    # API 키 (선택사항)
    STOCK_API_KEY = os.getenv("STOCK_API_KEY")
    ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
    POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

    # 데이터베이스 연결 (선택사항)
    DB_CONNECTION = os.getenv("DB_CONNECTION")

    # 기본 티커 그룹
    DEFAULT_TICKERS = {
        "etfs": ["SPY", "QQQ", "DIA", "IWM", "VTI", "VEA", "VWO", "AGG", "TLT", "GLD"],
        "mega_caps": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B"],
        "sectors": ["XLK", "XLF", "XLV", "XLI", "XLE", "XLB", "XLP", "XLY", "XLU", "XLRE"]
    }

    # 데이터 검증 임계값
    VALIDATION_THRESHOLDS = {
        "max_daily_return": 0.5,  # 50% 일일 최대 변동률
        "max_price_gap": 0.3,     # 30% 최대 가격 간격
        "volume_outlier_multiplier": 50,  # 거래량 이상치 배수
        "data_freshness_days": 7,  # 데이터 신선도 (일)
        "extreme_move_threshold": 0.01,  # 극단적 움직임 허용 비율
        "large_gap_threshold": 0.02      # 큰 가격 간격 허용 비율
    }

    # 로깅 설정
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = "logs"

    @classmethod
    def ensure_directories(cls) -> None:
        """필요한 디렉토리들을 생성합니다."""
        directories = [
            cls.DATA_DIR,
            cls.REPORTS_DIR,
            cls.RAG_DB,
            cls.SIGNALS_DIR,
            cls.LOG_DIR
        ]

        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    @classmethod
    def get_config_summary(cls) -> Dict[str, Any]:
        """설정 요약을 반환합니다."""
        return {
            "directories": {
                "data": cls.DATA_DIR,
                "reports": cls.REPORTS_DIR,
                "ragdb": cls.RAG_DB,
                "signals": cls.SIGNALS_DIR
            },
            "market": {
                "timezone": cls.TIMEZONE,
                "fee_bps": cls.FEE_BPS,
                "slippage_bps": cls.SLIPPAGE_BPS
            },
            "data_validation": cls.VALIDATION_THRESHOLDS,
            "api_keys_configured": {
                "stock_api": cls.STOCK_API_KEY is not None,
                "alpha_vantage": cls.ALPHA_VANTAGE_KEY is not None,
                "polygon": cls.POLYGON_API_KEY is not None
            }
        }