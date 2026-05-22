"""
Agent 1: 코스닥 종목 중 영업이익 흑자 기업 선별

[Production 모드]
  - Naver Finance (finsum_more) 스크래핑
  - 병렬 요청으로 ~1,500개 종목 처리
  - 로컬 실행 필요 (네트워크 접근)

[Demo 모드]
  - 현실적인 합성 데이터 사용 (네트워크 불필요)
"""
import os
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import DATA_DIR, DATA_MODE, SCRAPE_MAX_WORKERS, SCRAPE_DELAY
from utils import get_request, logger

OUTPUT_FILE = DATA_DIR / 'agent1_positive_op.csv'

# ── 공통 HTTP 헤더 ──────────────────────────────────────────────
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}


# ══════════════════════════════════════════════════════════════
#  Production 모드 — 실제 스크래핑
# ══════════════════════════════════════════════════════════════

def _get_kosdaq_tickers_naver():
    """Naver Finance 코스닥 시장 요약 페이지에서 종목 코드 수집"""
    from bs4 import BeautifulSoup
    tickers = {}
    for page in range(1, 40):   # 최대 40페이지
        url = 'https://finance.naver.com/sise/sise_market_sum.nhn'
        params = {'sosok': '1', 'page': str(page)}
        resp = get_request(url, params=params, headers=_HEADERS, encoding='euc-kr')
        if not resp:
            break
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('table.type_2 tr[onmouseover]')
        if not rows:
            break
        for row in rows:
            a = row.select_one('td.col_name a')
            if a:
                href = a.get('href', '')
                code = href.split('code=')[-1] if 'code=' in href else ''
                name = a.text.strip()
                if code:
                    tickers[code] = name
        time.sleep(SCRAPE_DELAY)
    return tickers


def _get_kosdaq_tickers_pykrx():
    """pykrx로 코스닥 종목 코드 수집 (KRX_ID/KRX_PW 환경변수 필요)"""
    krx_id = os.environ.get('KRX_ID')
    krx_pw = os.environ.get('KRX_PW')
    if not (krx_id and krx_pw):
        return None
    try:
        from pykrx import stock
        tickers = stock.get_market_ticker_list(market='KOSDAQ')
        names = {t: stock.get_market_ticker_name(t) for t in tickers}
        return names
    except Exception as e:
        logger.warning(f"pykrx 실패: {e}")
        return None


def _scrape_op_naver(code: str):
    """Naver Finance finsum_more에서 최근 영업이익 파싱"""
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

    # 연도 헤더 추출
    years = []
    thead = table.find('thead')
    if thead:
        for th in thead.find_all('th'):
            txt = th.text.strip()
            if txt and txt != '구분':
                years.append(txt)

    tbody = table.find('tbody')
    if not tbody:
        return None

    for tr in tbody.find_all('tr'):
        th = tr.find('th')
        if not th:
            continue
        label = th.text.strip()
        if '영업이익' in label and '률' not in label and 'E' not in label:
            for i, td in enumerate(tr.find_all('td')):
                raw = td.text.strip().replace(',', '').replace('\xa0', '')
                try:
                    val = float(raw)
                    year = years[i] if i < len(years) else 'N/A'
                    return code, val, year
                except ValueError:
                    continue
    return None


def _run_production():
    """실제 스크래핑 실행"""
    logger.info("종목 코드 수집 중...")
    ticker_map = _get_kosdaq_tickers_pykrx() or _get_kosdaq_tickers_naver()
    if not ticker_map:
        raise RuntimeError("종목 코드 수집 실패")

    tickers = list(ticker_map.keys())
    logger.info(f"코스닥 종목 수: {len(tickers)}개")
    logger.info(f"영업이익 스크래핑 시작 (병렬 {SCRAPE_MAX_WORKERS})")

    results = []
    with ThreadPoolExecutor(max_workers=SCRAPE_MAX_WORKERS) as ex:
        futures = {ex.submit(_scrape_op_naver, t): t for t in tickers}
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
                        'operating_profit': op,
                        'year': year,
                        'positive': op > 0,
                    })
            except Exception as e:
                logger.debug(f"{code} 실패: {e}")
            if done % 200 == 0:
                logger.info(f"진행: {done}/{len(tickers)}")
            time.sleep(SCRAPE_DELAY / SCRAPE_MAX_WORKERS)

    df = pd.DataFrame(results)
    return df[df['positive'] == True].sort_values('operating_profit', ascending=False)


# ══════════════════════════════════════════════════════════════
#  Demo 모드 — 합성 데이터
# ══════════════════════════════════════════════════════════════

def _run_demo():
    """데모 데이터 생성"""
    from demo_generator import generate_kosdaq_universe, build_agent1_output
    logger.info("[DEMO] 코스닥 가상 유니버스 생성 중...")
    companies = generate_kosdaq_universe(1500)
    df = build_agent1_output(companies)
    return df, companies


# ══════════════════════════════════════════════════════════════
#  메인 진입점
# ══════════════════════════════════════════════════════════════

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
    logger.info("\n상위 10개 종목:")
    logger.info(df_positive[['ticker', 'name', 'operating_profit', 'year']].head(10).to_string())

    # demo 모드에서 companies 객체를 반환해 Agent 2가 재사용할 수 있게 함
    return df_positive, companies


if __name__ == '__main__':
    run()
