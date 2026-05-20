"""설정 파일 — 데이터 소스, 임계값, 경로"""
from pathlib import Path

# ── 경로 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / 'agent2_details').mkdir(exist_ok=True)

# ── 모드 ────────────────────────────────────────────────────────
# 'production': 실제 웹 스크래핑 (로컬 실행 권장)
# 'demo': 현실적인 가상 데이터 (네트워크 없이 시스템 구조 시연)
DATA_MODE = 'demo'   # 환경에 따라 'production'으로 변경

# ── 필터 기준 ────────────────────────────────────────────────────
PER_MAX = 10.0           # PER 상한
MIN_GROWTH_YEARS = 3     # 영업이익 연속 증가 최소 연수
ANALYSIS_YEARS = [2020, 2021, 2022, 2023, 2024]

# ── 스크래핑 설정 ────────────────────────────────────────────────
SCRAPE_MAX_WORKERS = 15
SCRAPE_DELAY = 0.3
VERIFY_SAMPLE_SIZE = 20
ACCURACY_THRESHOLD = 0.80

# ── pykrx 설정 ──────────────────────────────────────────────────
# 최신 pykrx(1.2.8+)는 환경변수 KRX_ID, KRX_PW 필요
# 없으면 Naver Finance 직접 스크래핑으로 대체
YEAR_END_DATES = {
    2020: '20201230',
    2021: '20211230',
    2022: '20221229',
    2023: '20231228',
    2024: '20241227',
}
