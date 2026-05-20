"""공통 유틸리티: HTTP 요청, 로깅"""
import requests
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# DATA_DIR은 config.py에서 관리 (순환 import 방지)
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)

_DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def get_request(url, params=None, headers=None, encoding=None,
                timeout=15, max_retries=3, delay=1.0):
    """재시도 로직 포함 HTTP GET 요청"""
    h = headers if headers is not None else _DEFAULT_HEADERS.copy()
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=h, timeout=timeout)
            resp.raise_for_status()
            if encoding:
                resp.encoding = encoding
            return resp
        except Exception as e:
            logger.warning(f"요청 실패 ({attempt+1}/{max_retries}): {url} — {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
    return None
