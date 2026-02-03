# scripts/logger_config.py

import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def setup_logger(name: str, log_level: str = "INFO") -> logging.Logger:
    """
    구조화된 로거를 설정합니다.

    Args:
        name: 로거 이름
        log_level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        구성된 로거 인스턴스
    """
    # 로그 디렉토리 생성
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # 이미 핸들러가 있으면 제거 (중복 방지)
    if logger.handlers:
        logger.handlers.clear()

    # 파일 핸들러 설정
    log_filename = f"{log_dir}/{name}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 핸들러 추가
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger