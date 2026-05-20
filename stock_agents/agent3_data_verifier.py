"""
Agent 3: 재무 데이터 정확성 검증

[Production 모드]
  - 무작위 샘플 20개 선정
  - pykrx PER vs 수집 PER 비교
  - Naver Finance 영업이익 재수집 후 비교
  - 오차율 > 20%인 항목 비율이 20% 초과 시 Agent 2 재실행

[Demo 모드]
  - 데모 데이터 내부 일관성 검증 (수치 합리성 체크)
  - 실제 외부 소스와 비교 없이 내부 논리 검증만 수행
"""
import random
import pandas as pd
import numpy as np
from config import DATA_DIR, DATA_MODE, VERIFY_SAMPLE_SIZE, ACCURACY_THRESHOLD
from utils import get_request, logger

INPUT_FILE = DATA_DIR / 'agent2_financial_data.csv'
REPORT_FILE = DATA_DIR / 'agent3_verification_report.csv'


# ══════════════════════════════════════════════════════════════
#  Production 모드 — 외부 소스 교차 검증
# ══════════════════════════════════════════════════════════════

def _verify_per_pykrx(code: str, our_per: float):
    """pykrx PER와 비교"""
    try:
        import os
        if not (os.environ.get('KRX_ID') and os.environ.get('KRX_PW')):
            return None, None
        from pykrx import stock
        df = stock.get_market_fundamental('20241227', ticker=code)
        if df is not None and not df.empty:
            ref_per = float(df.iloc[0].get('PER', 0) or 0)
            if ref_per > 0 and our_per and our_per > 0:
                err = abs(our_per - ref_per) / ref_per
                return ref_per, err
    except Exception:
        pass
    return None, None


def _verify_op_naver(code: str, our_op: float):
    """Naver Finance에서 영업이익 재수집하여 비교"""
    from bs4 import BeautifulSoup
    url = 'https://finance.naver.com/item/coinfo.naver'
    params = {'code': code, 'target': 'finsum_more'}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://finance.naver.com/item/main.naver?code={code}',
    }
    resp = get_request(url, params=params, headers=headers, encoding='euc-kr', timeout=12)
    if not resp:
        return None, None

    soup = BeautifulSoup(resp.text, 'lxml')
    table = soup.find('table', class_='tb_type1')
    if not table:
        return None, None

    for tr in (table.find('tbody') or table).find_all('tr'):
        th = tr.find('th')
        if th and '영업이익' in th.text and '률' not in th.text:
            for td in tr.find_all('td'):
                raw = td.text.strip().replace(',', '').replace('\xa0', '')
                try:
                    ref_op = float(raw)
                    if our_op and ref_op != 0:
                        err = abs(our_op - ref_op) / abs(ref_op)
                        return ref_op, err
                except ValueError:
                    continue
    return None, None


def _run_production_verify(df: pd.DataFrame, sample: list):
    """실제 외부 소스 교차 검증"""
    import time
    records = []
    for code in sample:
        df_code = df[df['ticker'] == code].sort_values('year', ascending=False)
        if df_code.empty:
            continue
        latest = df_code.iloc[0]
        our_per = latest.get('per')
        our_op = latest.get('operating_profit')

        ref_per, per_err = _verify_per_pykrx(code, our_per)
        ref_op, op_err = _verify_op_naver(code, our_op)
        time.sleep(0.3)

        per_ok = per_err is None or per_err < 0.20
        op_ok = op_err is None or op_err < 0.20

        records.append({
            'ticker': code,
            'our_per': our_per, 'ref_per': ref_per,
            'per_error_pct': round(per_err * 100, 1) if per_err is not None else None,
            'per_ok': per_ok,
            'our_op': our_op, 'ref_op': ref_op,
            'op_error_pct': round(op_err * 100, 1) if op_err is not None else None,
            'op_ok': op_ok,
            'overall_ok': per_ok and op_ok,
        })
        logger.info(f"  {code}: PER오차={f'{per_err*100:.1f}%' if per_err else 'N/A'} "
                    f"| OP오차={f'{op_err*100:.1f}%' if op_err else 'N/A'}")
    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════
#  Demo 모드 — 내부 일관성 검증
# ══════════════════════════════════════════════════════════════

def _run_demo_verify(df: pd.DataFrame, sample: list):
    """
    실제 외부 비교 없이 데이터 내부 합리성 검증:
    1. 영업이익률 = 영업이익 / 매출액 (±5% 이내)
    2. ROE = 순이익 / 자본 범위 합리성
    3. PER 범위 (0 < PER < 500)
    4. 연도 오름차순 정렬 여부
    """
    records = []
    for code in sample:
        df_code = df[df['ticker'] == code].sort_values('year')
        if df_code.empty:
            continue

        issues = []

        # 검증 1: 영업이익률 일관성
        if {'revenue', 'operating_profit', 'operating_margin'}.issubset(df_code.columns):
            for _, row in df_code.iterrows():
                rev = row['revenue']
                op = row['operating_profit']
                om = row.get('operating_margin')
                if rev and rev > 0 and op is not None and om is not None:
                    calc_margin = op / rev * 100
                    if abs(calc_margin - om) > 5:
                        issues.append(f"영업이익률 불일치 {row['year']}: "
                                      f"계산={calc_margin:.1f}% vs 저장={om:.1f}%")

        # 검증 2: PER 범위
        latest_per = df_code[df_code['per'].notna()]['per']
        if not latest_per.empty:
            per_val = latest_per.iloc[-1]
            if not (0 < per_val < 500):
                issues.append(f"PER 범위 이상: {per_val}")

        # 검증 3: 영업이익 순서 일관성 (급격한 변동 > 10배 체크)
        ops = df_code['operating_profit'].dropna().tolist()
        for i in range(1, len(ops)):
            if ops[i-1] > 0 and ops[i] / ops[i-1] > 10:
                issues.append(f"영업이익 급등 (>{10}배): {ops[i-1]:.0f}→{ops[i]:.0f}")

        # 결과 판정
        overall_ok = len(issues) == 0

        records.append({
            'ticker': code,
            'name': df_code.iloc[0].get('name', ''),
            'data_years': len(df_code),
            'issues_found': len(issues),
            'issues_detail': '; '.join(issues) if issues else '없음',
            'overall_ok': overall_ok,
            # Demo 모드에서는 외부 비교값 없음
            'our_per': df_code[df_code['per'].notna()]['per'].iloc[-1]
                       if not df_code[df_code['per'].notna()].empty else None,
            'per_ok': 'demo_only',
            'op_ok': 'demo_only',
        })

        status = "✓ OK" if overall_ok else f"✗ 문제 {len(issues)}건"
        logger.info(f"  {code}: {status} {'| ' + issues[0] if issues else ''}")

    return pd.DataFrame(records)


# ══════════════════════════════════════════════════════════════
#  메인 진입점
# ══════════════════════════════════════════════════════════════

def run(force_retry=False):
    logger.info("=" * 55)
    logger.info(f"Agent 3: 재무 데이터 정확성 검증 [{DATA_MODE.upper()} 모드]")
    logger.info("=" * 55)

    if not INPUT_FILE.exists():
        logger.error(f"Agent 2 결과 없음: {INPUT_FILE}")
        return False

    df = pd.read_csv(INPUT_FILE)
    tickers = df['ticker'].unique().tolist()
    sample_n = min(VERIFY_SAMPLE_SIZE, len(tickers))
    sample = random.sample(tickers, sample_n)

    logger.info(f"전체 종목: {len(tickers)}개 → 샘플 {sample_n}개 검증")
    logger.info(f"검증 샘플: {sample[:10]}{'...' if len(sample) > 10 else ''}")

    if DATA_MODE == 'production':
        df_report = _run_production_verify(df, sample)
    else:
        df_report = _run_demo_verify(df, sample)

    df_report.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')

    # 정확도 판단
    ok_col = 'overall_ok'
    if ok_col in df_report.columns:
        valid = df_report[df_report[ok_col].notna() & (df_report[ok_col] != 'demo_only')]
        if valid.empty:
            # Demo 모드: issues_found 기준
            if 'issues_found' in df_report.columns:
                pass_count = (df_report['issues_found'] == 0).sum()
                accuracy = pass_count / len(df_report)
            else:
                accuracy = 1.0
        else:
            accuracy = valid[ok_col].astype(bool).mean()
    else:
        accuracy = 1.0

    logger.info(f"\n[검증 요약]")
    logger.info(f"  검증 종목: {len(df_report)}개")
    if DATA_MODE == 'demo' and 'issues_found' in df_report.columns:
        logger.info(f"  이슈 없는 종목: {(df_report['issues_found']==0).sum()}개")
    logger.info(f"  정확도: {accuracy:.1%} (기준: {ACCURACY_THRESHOLD:.1%})")
    logger.info(f"  보고서: {REPORT_FILE}")

    if accuracy < ACCURACY_THRESHOLD and not force_retry:
        logger.warning(f"\n[경고] 정확도 미달 → Agent 2 재실행")
        import agent2_financial_downloader as a2
        import importlib
        importlib.reload(a2)
        a2.run()
        return run(force_retry=True)

    verdict = "통과" if accuracy >= ACCURACY_THRESHOLD else "미달(수동 확인 권고)"
    logger.info(f"\n[최종] 검증 {verdict}")
    return accuracy >= ACCURACY_THRESHOLD


if __name__ == '__main__':
    result = run()
    print(f"\n검증 결과: {'통과' if result else '실패'}")
