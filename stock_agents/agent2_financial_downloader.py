"""
Agent 2: 영업이익 흑자 기업 5개년 재무제표 + 주요 지표 수집

[Production 모드]
  - Naver Finance / Wisereport 스크래핑
  - pykrx (KRX_ID/KRX_PW) 또는 직접 파싱으로 PER 수집
  - 병렬 처리로 수백 종목 처리

[Demo 모드]
  - demo_generator의 합성 데이터 사용
"""
import os
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import DATA_DIR, DATA_MODE, SCRAPE_MAX_WORKERS, ANALYSIS_YEARS, YEAR_END_DATES
from utils import get_request, logger

INPUT_FILE = DATA_DIR / 'agent1_positive_op.csv'
OUTPUT_FILE = DATA_DIR / 'agent2_financial_data.csv'
OUTPUT_EXCEL = DATA_DIR / 'agent2_financial_data.xlsx'
DETAIL_DIR = DATA_DIR / 'agent2_details'
DETAIL_DIR.mkdir(exist_ok=True)

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}

METRIC_MAP = {
    '매출액': 'revenue',
    '영업이익': 'operating_profit',
    '영업이익률': 'operating_margin',
    '당기순이익': 'net_income',
    'ROE': 'roe',
    'ROA': 'roa',
    'EPS': 'eps',
    'BPS': 'bps',
}


# ══════════════════════════════════════════════════════════════
#  Production 모드 스크래핑 함수
# ══════════════════════════════════════════════════════════════

def _scrape_finsum(code: str):
    """Naver Finance finsum_more에서 연간 재무 요약 파싱"""
    from bs4 import BeautifulSoup
    url = 'https://finance.naver.com/item/coinfo.naver'
    params = {'code': code, 'target': 'finsum_more'}
    headers = {**_HEADERS, 'Referer': f'https://finance.naver.com/item/main.naver?code={code}'}
    resp = get_request(url, params=params, headers=headers, encoding='euc-kr', timeout=12)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    table = soup.find('table', class_='tb_type1')
    if not table:
        return None

    years = []
    thead = table.find('thead')
    if thead:
        for th in thead.find_all('th'):
            txt = th.text.strip()
            if txt and txt != '구분':
                years.append(txt)
    if not years:
        return None

    result = {yr: {} for yr in years}
    tbody = table.find('tbody')
    if not tbody:
        return None

    for tr in tbody.find_all('tr'):
        th = tr.find('th')
        if not th:
            continue
        label = th.text.strip()
        for kor, eng in METRIC_MAP.items():
            if kor in label:
                for i, td in enumerate(tr.find_all('td')):
                    if i >= len(years):
                        break
                    raw = td.text.strip().replace(',', '').replace('\xa0', '').replace('%', '')
                    try:
                        result[years[i]][eng] = float(raw)
                    except ValueError:
                        pass
    return result if any(result.values()) else None


def _get_per_pykrx(code: str):
    """pykrx로 연도별 PER 수집 (KRX 인증 필요)"""
    krx_id = os.environ.get('KRX_ID')
    krx_pw = os.environ.get('KRX_PW')
    if not (krx_id and krx_pw):
        return {}
    try:
        from pykrx import stock
        fund_data = {}
        for year, date_str in YEAR_END_DATES.items():
            df = stock.get_market_fundamental(date_str, ticker=code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                fund_data[str(year)] = {
                    'per': round(float(row.get('PER', 0) or 0), 2),
                    'pbr': round(float(row.get('PBR', 0) or 0), 2),
                }
            time.sleep(0.05)
        return fund_data
    except Exception as e:
        logger.debug(f"{code} pykrx 실패: {e}")
        return {}


def _process_one_ticker_production(row):
    """단일 종목 실제 스크래핑"""
    code = row['ticker']
    name = row.get('name', '')
    income = _scrape_finsum(code)
    per_data = _get_per_pykrx(code)

    records = []
    all_years = set()
    if income:
        all_years.update(income.keys())
    if per_data:
        all_years.update(per_data.keys())

    for yr_str in sorted(all_years):
        rec = {'ticker': code, 'name': name, 'year': yr_str}
        if income and yr_str in income:
            rec.update(income[yr_str])
        yr_key = yr_str.split('.')[0]
        if per_data and yr_key in per_data:
            rec.update(per_data[yr_key])
        records.append(rec)
    return records


def _run_production(df_input):
    all_records = []
    success, fail = 0, 0

    with ThreadPoolExecutor(max_workers=SCRAPE_MAX_WORKERS) as ex:
        futures = {ex.submit(_process_one_ticker_production, row): row['ticker']
                   for _, row in df_input.iterrows()}
        done = 0
        for f in as_completed(futures):
            done += 1
            code = futures[f]
            records = f.result()
            if records:
                all_records.extend(records)
                pd.DataFrame(records).to_csv(
                    DETAIL_DIR / f'{code}.csv', index=False, encoding='utf-8-sig')
                success += 1
            else:
                fail += 1
            if done % 50 == 0:
                logger.info(f"진행: {done}/{len(df_input)} | 성공: {success} | 실패: {fail}")
            time.sleep(0.1)

    return pd.DataFrame(all_records)


# ══════════════════════════════════════════════════════════════
#  Demo 모드
# ══════════════════════════════════════════════════════════════

def _run_demo(df_input, companies):
    from demo_generator import build_agent2_output
    logger.info("[DEMO] 5개년 가상 재무 데이터 생성 중...")
    df = build_agent2_output(companies, df_input)
    return df


# ══════════════════════════════════════════════════════════════
#  메인 진입점
# ══════════════════════════════════════════════════════════════

def run(df_agent1=None, companies=None):
    logger.info("=" * 55)
    logger.info(f"Agent 2: 5개년 재무제표 수집 [{DATA_MODE.upper()} 모드]")
    logger.info("=" * 55)

    if df_agent1 is None:
        if not INPUT_FILE.exists():
            logger.error(f"Agent 1 결과 없음: {INPUT_FILE}")
            return None
        df_agent1 = pd.read_csv(INPUT_FILE)

    logger.info(f"대상 종목: {len(df_agent1)}개")

    if DATA_MODE == 'production':
        df_out = _run_production(df_agent1)
    else:
        df_out = _run_demo(df_agent1, companies)

    if df_out is None or df_out.empty:
        logger.error("재무 데이터 수집 실패")
        return None

    # 컬럼 정렬
    cols_priority = ['ticker', 'name', 'year', 'revenue', 'operating_profit',
                     'operating_margin', 'net_income', 'roe', 'roa',
                     'eps', 'bps', 'per', 'pbr']
    ordered = [c for c in cols_priority if c in df_out.columns]
    rest = [c for c in df_out.columns if c not in ordered]
    df_out = df_out[ordered + rest]

    df_out.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    df_out.to_excel(OUTPUT_EXCEL, index=False)

    logger.info(f"\n[결과] 수집 완료: {len(df_out)}행 ({df_out['ticker'].nunique()}개 종목)")
    logger.info(f"[저장] {OUTPUT_FILE}")
    logger.info(f"[저장] {OUTPUT_EXCEL}")
    return df_out


if __name__ == '__main__':
    run()
