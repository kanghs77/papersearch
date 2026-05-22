"""
Agent 1: 코스닥 종목 중 영업이익 흑자 기업 선별

종목 코드: FinanceDataReader (확인됨)
영업이익:  yfinance (.KQ 접미사) → Naver Finance 순서로 시도
"""
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import DATA_DIR, DATA_MODE, SCRAPE_MAX_WORKERS
from utils import get_request, logger

OUTPUT_FILE = DATA_DIR / 'agent1_positive_op.csv'

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}


# ── 종목 코드 수집 ───────────────────────────────────────────────

def _get_tickers_fdr():
    import FinanceDataReader as fdr
    df = fdr.StockListing('KOSDAQ')
    code_col = 'Code' if 'Code' in df.columns else df.columns[0]
    name_col = 'Name' if 'Name' in df.columns else df.columns[1]
    result = {str(r[code_col]).zfill(6): str(r[name_col]) for _, r in df.iterrows()}
    logger.info(f"FinanceDataReader: {len(result)}개 종목")
    return result


# ── 영업이익 수집 ────────────────────────────────────────────────

def _op_from_yfinance(code: str):
    """yfinance로 최근 연도 영업이익(억원) 수집"""
    try:
        import yfinance as yf
        t = yf.Ticker(f"{code}.KQ")
        fin = t.financials   # 연간 손익계산서
        if fin is None or fin.empty:
            return None
        for field in ['Operating Income', 'Operating Profit', 'EBIT']:
            if field in fin.index:
                for date, val in fin.loc[field].items():
                    if pd.notna(val):
                        return code, float(val) / 1e8, str(date.year)
    except Exception:
        pass
    return None


def _op_from_naver(code: str):
    """Naver Finance에서 영업이익 파싱 (fallback)"""
    from bs4 import BeautifulSoup
    url = 'https://finance.naver.com/item/coinfo.naver'
    params = {'code': code, 'target': 'finsum_more'}
    headers = {**_HEADERS, 'Referer': f'https://finance.naver.com/item/main.naver?code={code}'}
    resp = get_request(url, params=params, headers=headers, encoding='euc-kr', timeout=10)
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, 'html.parser')
    # 여러 테이블 선택자 시도
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
    for tr in (table.find('tbody') or table).find_all('tr'):
        th = tr.find('th')
        if not th:
            continue
        label = th.text.strip()
        if '영업이익' in label and '률' not in label:
            for i, td in enumerate(tr.find_all('td')):
                raw = td.text.strip().replace(',', '').replace('\xa0', '')
                try:
                    val = float(raw)
                    yr = years[i] if i < len(years) else 'N/A'
                    return code, val, yr
                except ValueError:
                    continue
    return None


def _get_operating_profit(code: str):
    """yfinance → Naver Finance 순으로 영업이익 수집"""
    result = _op_from_yfinance(code)
    if result is None:
        result = _op_from_naver(code)
    return result


# ── Production 실행 ──────────────────────────────────────────────

def _run_production():
    ticker_map = _get_tickers_fdr()

    tickers = list(ticker_map.keys())
    logger.info(f"영업이익 수집 시작: {len(tickers)}개 (병렬 {SCRAPE_MAX_WORKERS})")

    results = []
    workers = min(SCRAPE_MAX_WORKERS, 10)   # yfinance 레이트 리밋 고려
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_get_operating_profit, t): t for t in tickers}
        done = 0
        for f in as_completed(futures):
            done += 1
            code = futures[f]
            try:
                res = f.result()
                if res:
                    code_, op, year = res
                    results.append({
                        'ticker': code_,
                        'name': ticker_map.get(code_, ''),
                        'operating_profit': round(op, 1),
                        'year': year,
                        'positive': op > 0,
                    })
            except Exception as e:
                logger.debug(f"{code}: {e}")
            if done % 100 == 0:
                logger.info(f"  진행: {done}/{len(tickers)} (수집 성공: {len(results)})")
            time.sleep(0.3 / workers)

    if not results:
        raise RuntimeError(
            "영업이익 데이터 수집 실패.\n"
            "yfinance 설치 확인: pip install yfinance"
        )

    df = pd.DataFrame(results)
    return df[df['positive'] == True].sort_values('operating_profit', ascending=False)


# ── Demo 모드 ────────────────────────────────────────────────────

def _run_demo():
    from demo_generator import generate_kosdaq_universe, build_agent1_output
    logger.info("[DEMO] 코스닥 가상 유니버스 생성 중...")
    companies = generate_kosdaq_universe(1500)
    return build_agent1_output(companies), companies


# ── 메인 ─────────────────────────────────────────────────────────

def run():
    logger.info("=" * 55)
    logger.info(f"Agent 1: 코스닥 영업이익 흑자 기업 선별 [{DATA_MODE.upper()} 모드]")
    logger.info("=" * 55)

    if DATA_MODE == 'production':
        df_positive = _run_production()
        companies = None
    else:
        df_positive, companies = _run_demo()

    df_positive.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    logger.info(f"\n[결과] 영업이익 흑자 기업: {len(df_positive)}개")
    logger.info(f"[저장] {OUTPUT_FILE}")
    logger.info("\n상위 10개:")
    logger.info(df_positive[['ticker', 'name', 'operating_profit', 'year']].head(10).to_string())
    return df_positive, companies


if __name__ == '__main__':
    run()
