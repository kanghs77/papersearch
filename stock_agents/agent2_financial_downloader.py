"""
Agent 2: 흑자 기업 5개년 재무제표 + 주요 지표 수집

데이터 소스: yfinance (.KQ) → Naver Finance 순서
수집 항목: 매출액, 영업이익, 순이익, ROE, ROA, EPS, PER, PBR
"""
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import DATA_DIR, DATA_MODE, SCRAPE_MAX_WORKERS
from utils import get_request, logger

INPUT_FILE  = DATA_DIR / 'agent1_positive_op.csv'
OUTPUT_FILE = DATA_DIR / 'agent2_financial_data.csv'
OUTPUT_EXCEL = DATA_DIR / 'agent2_financial_data.xlsx'
DETAIL_DIR  = DATA_DIR / 'agent2_details'
DETAIL_DIR.mkdir(exist_ok=True)

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}

_NAVER_METRICS = {
    '매출액': 'revenue',
    '영업이익': 'operating_profit',
    '영업이익률': 'operating_margin',
    '당기순이익': 'net_income',
    'ROE': 'roe', 'ROA': 'roa',
    'EPS': 'eps', 'BPS': 'bps',
}


# ── yfinance 수집 ────────────────────────────────────────────────

def _fetch_yfinance(code: str):
    """yfinance로 연간 재무제표 + 주요 지표 수집"""
    try:
        import yfinance as yf
        t = yf.Ticker(f"{code}.KQ")

        # ① 손익계산서
        fin = t.financials    # 컬럼=연도, 행=지표
        if fin is None or fin.empty:
            return None

        records = []
        for date in fin.columns:
            yr = str(date.year)
            row = {'ticker': code, 'year': yr}

            def get_field(names):
                for n in names:
                    if n in fin.index and pd.notna(fin.loc[n, date]):
                        return float(fin.loc[n, date]) / 1e8   # KRW → 억원
                return None

            row['revenue']          = get_field(['Total Revenue', 'Revenue'])
            row['operating_profit'] = get_field(['Operating Income', 'Operating Profit', 'EBIT'])
            row['net_income']       = get_field(['Net Income', 'Net Income Common Stockholders'])

            if row['revenue'] and row['operating_profit'] and row['revenue'] > 0:
                row['operating_margin'] = round(row['operating_profit'] / row['revenue'] * 100, 2)

            records.append(row)

        if not records:
            return None

        # ② 현재 PER/PBR/ROE
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        latest_year = str(fin.columns[0].year)
        for rec in records:
            if rec['year'] == latest_year:
                rec['per'] = info.get('trailingPE') or info.get('forwardPE')
                rec['pbr'] = info.get('priceToBook')
                rec['roe'] = round(info.get('returnOnEquity', 0) * 100, 2) if info.get('returnOnEquity') else None
                rec['roa'] = round(info.get('returnOnAssets', 0) * 100, 2) if info.get('returnOnAssets') else None

        return records
    except Exception as e:
        logger.debug(f"{code} yfinance 실패: {e}")
        return None


def _fetch_yfinance_with_retry(code: str, max_retries: int = 3):
    """Rate limit 대응: 실패 시 대기 후 재시도"""
    for attempt in range(max_retries):
        result = _fetch_yfinance(code)
        if result is not None:
            return result
        wait = 5 * (attempt + 1)   # 5s → 10s → 15s
        logger.debug(f"{code} yfinance 재시도 {attempt+1}/{max_retries} ({wait}s 대기)")
        time.sleep(wait)
    return None


# ── Naver Finance fallback ───────────────────────────────────────

def _fetch_naver(code: str):
    """Naver Finance finsum_more에서 연간 재무 파싱 (fallback)"""
    from bs4 import BeautifulSoup
    url = 'https://finance.naver.com/item/coinfo.naver'
    params = {'code': code, 'target': 'finsum_more'}
    headers = {**_HEADERS, 'Referer': f'https://finance.naver.com/item/main.naver?code={code}'}
    resp = get_request(url, params=params, headers=headers, encoding='euc-kr', timeout=12)
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    table = (soup.find('table', class_='tb_type1') or
             soup.find('table', attrs={'class': lambda c: c and 'tb_type1' in str(c)}))
    if not table:
        return None

    years = []
    thead = table.find('thead')
    if thead:
        for th in thead.find_all('th'):
            t_ = th.text.strip()
            if t_ and t_ != '구분':
                years.append(t_)
    if not years:
        return None

    data = {yr: {'ticker': code, 'year': yr} for yr in years}
    for tr in (table.find('tbody') or table).find_all('tr'):
        th = tr.find('th')
        if not th:
            continue
        label = th.text.strip()
        for kor, eng in _NAVER_METRICS.items():
            if kor in label:
                for i, td in enumerate(tr.find_all('td')):
                    if i >= len(years):
                        break
                    raw = td.text.strip().replace(',', '').replace('\xa0', '').replace('%', '')
                    try:
                        data[years[i]][eng] = float(raw)
                    except ValueError:
                        pass

    records = [v for v in data.values() if len(v) > 2]
    return records if records else None


# ── 종목 처리 ────────────────────────────────────────────────────

def _process(row):
    code = str(row['ticker']).zfill(6)
    name = row.get('name', '')
    records = _fetch_yfinance_with_retry(code) or _fetch_naver(code)
    if records:
        for r in records:
            r.setdefault('ticker', code)
            r.setdefault('name', name)
    return code, records


# ── Production 실행 ──────────────────────────────────────────────

def _run_production(df_input):
    all_records = []
    success = fail = 0
    failed_codes = []

    # yfinance Rate Limit 대응: 워커 3개, 요청 간격 1.5초
    WORKERS = 3
    REQUEST_DELAY = 1.5

    logger.info(f"  (워커 {WORKERS}개 / 요청 간격 {REQUEST_DELAY}s — Yahoo Finance Rate Limit 방지)")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(_process, row): row['ticker'] for _, row in df_input.iterrows()}
        done = 0
        for f in as_completed(futures):
            done += 1
            code = futures[f]
            code_, records = f.result()
            if records:
                all_records.extend(records)
                pd.DataFrame(records).to_csv(
                    DETAIL_DIR / f'{code_}.csv', index=False, encoding='utf-8-sig')
                success += 1
            else:
                fail += 1
                failed_codes.append(code_)
            if done % 50 == 0:
                logger.info(f"  진행: {done}/{len(df_input)} | 성공: {success} | 실패: {fail}")
            time.sleep(REQUEST_DELAY)

    # 실패 종목 재시도 (30초 대기 후)
    if failed_codes:
        logger.info(f"\n실패 {len(failed_codes)}개 재시도 중... (30초 대기)")
        time.sleep(30)
        retry_success = 0
        for code in failed_codes:
            row = df_input[df_input['ticker'].astype(str).str.zfill(6) == code]
            if row.empty:
                continue
            _, records = _process(row.iloc[0])
            if records:
                all_records.extend(records)
                retry_success += 1
            time.sleep(2.0)
        logger.info(f"재시도 결과: {retry_success}/{len(failed_codes)} 추가 성공")

    return pd.DataFrame(all_records)


# ── Demo 모드 ────────────────────────────────────────────────────

def _run_demo(df_input, companies):
    from demo_generator import build_agent2_output
    logger.info("[DEMO] 5개년 가상 재무 데이터 생성 중...")
    return build_agent2_output(companies, df_input)


# ── 메인 ─────────────────────────────────────────────────────────

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

    cols_priority = ['ticker', 'name', 'year', 'revenue', 'operating_profit',
                     'operating_margin', 'net_income', 'roe', 'roa',
                     'eps', 'bps', 'per', 'pbr']
    ordered = [c for c in cols_priority if c in df_out.columns]
    rest = [c for c in df_out.columns if c not in ordered]
    df_out = df_out[ordered + rest]

    df_out.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    df_out.to_excel(OUTPUT_EXCEL, index=False)

    logger.info(f"\n[결과] {len(df_out)}행 ({df_out['ticker'].nunique()}개 종목)")
    logger.info(f"[저장] {OUTPUT_FILE}")
    logger.info(f"[저장] {OUTPUT_EXCEL}")
    return df_out


if __name__ == '__main__':
    run()
