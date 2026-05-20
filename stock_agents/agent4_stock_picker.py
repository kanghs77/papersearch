"""
Agent 4: 영업이익 증가 추세 + PER ≤ 10 최종 종목 선별

선별 기준:
  ① 전 기간 영업이익 양수 (흑자 유지)
  ② 연속 증가 최소 3개년 (데이터 부족 시 2년으로 완화)
  ③ 최근 PER ≤ 10
  ④ 영업이익 성장률 계산 및 종합 점수 산출
"""
import pandas as pd
import numpy as np
from config import DATA_DIR, PER_MAX, MIN_GROWTH_YEARS, ANALYSIS_YEARS
from utils import logger

INPUT_FILE = DATA_DIR / 'agent2_financial_data.csv'
OUTPUT_FILE = DATA_DIR / 'agent4_final_picks.csv'
OUTPUT_EXCEL = DATA_DIR / 'agent4_final_picks.xlsx'


def _parse_year(year_str: str):
    """'2023', '2023.12', '2023/12' 등 다양한 연도 표기 처리"""
    try:
        return int(str(year_str).split('.')[0].split('/')[0].strip())
    except (ValueError, AttributeError):
        return None


def _calc_cagr(start: float, end: float, years: int):
    """복합연간성장률 계산"""
    if start <= 0 or end <= 0 or years <= 0:
        return None
    try:
        return (end / start) ** (1 / years) - 1
    except Exception:
        return None


def _consecutive_growth(values: list):
    """연속 증가 구간 수 계산"""
    count = 0
    for i in range(1, len(values)):
        if values[i] > values[i-1]:
            count += 1
        else:
            break   # 첫 번째 감소에서 연속 끊김
    return count


def _all_increasing(values: list):
    """전 구간 증가 여부"""
    return all(values[i] > values[i-1] for i in range(1, len(values)))


def _analyze_ticker(df_code: pd.DataFrame, min_growth_years: int):
    """단일 종목 분석 → 통과 시 분석 결과 딕셔너리 반환, 미통과 시 None"""
    df_code = df_code.copy()
    df_code['year_num'] = df_code['year'].apply(_parse_year)
    df_code = df_code.dropna(subset=['year_num']).sort_values('year_num')

    if 'operating_profit' not in df_code.columns:
        return None

    op_df = df_code[df_code['operating_profit'].notna()].copy()
    if len(op_df) < 2:
        return None

    op_vals = op_df['operating_profit'].tolist()
    yr_vals = op_df['year_num'].tolist()

    # ① 전 기간 흑자
    if not all(v > 0 for v in op_vals):
        return None

    # ② 연속 증가 확인
    consec = _consecutive_growth(op_vals)
    if consec < min_growth_years - 1:
        return None

    # ③ PER 확인
    per_df = df_code[df_code['per'].notna() & (df_code['per'] > 0)] if 'per' in df_code.columns else pd.DataFrame()
    current_per = per_df['per'].iloc[-1] if not per_df.empty else None

    if current_per is None or current_per > PER_MAX:
        return None

    # ④ 지표 산출
    n_years = len(op_vals)
    op_cagr = _calc_cagr(op_vals[0], op_vals[-1], n_years - 1)
    all_up = _all_increasing(op_vals)

    # 수익성 지표 (최근 연도)
    latest = df_code.iloc[-1]
    roe = latest.get('roe') if 'roe' in df_code.columns else None
    roa = latest.get('roa') if 'roa' in df_code.columns else None
    revenue_latest = latest.get('revenue') if 'revenue' in df_code.columns else None
    net_income_latest = latest.get('net_income') if 'net_income' in df_code.columns else None

    return {
        'ticker': df_code.iloc[0]['ticker'],
        'name': df_code.iloc[0].get('name', ''),
        'current_per': round(current_per, 2),
        'op_latest': round(op_vals[-1], 1),
        'op_oldest': round(op_vals[0], 1),
        'op_cagr_pct': round(op_cagr * 100, 1) if op_cagr is not None else None,
        'consecutive_growth_yrs': consec,
        'all_years_increasing': all_up,
        'data_years': n_years,
        'year_range': f"{int(yr_vals[0])}~{int(yr_vals[-1])}",
        'op_trend': ' → '.join(f"{v:,.0f}" for v in op_vals),
        'pbr': round(float(df_code['pbr'].iloc[-1]), 2)
               if 'pbr' in df_code.columns and pd.notna(df_code['pbr'].iloc[-1]) else None,
        'roe': round(float(roe), 2) if roe is not None and pd.notna(roe) else None,
        'roa': round(float(roa), 2) if roa is not None and pd.notna(roa) else None,
        'revenue_latest': round(float(revenue_latest), 1)
                          if revenue_latest is not None and pd.notna(revenue_latest) else None,
        'net_income_latest': round(float(net_income_latest), 1)
                             if net_income_latest is not None and pd.notna(net_income_latest) else None,
    }


def run():
    logger.info("=" * 55)
    logger.info("Agent 4: 영업이익 증가 + PER ≤ 10 최종 종목 선별")
    logger.info("=" * 55)
    logger.info(f"  필터 ① 전 기간 영업이익 > 0")
    logger.info(f"  필터 ② 연속 증가 ≥ {MIN_GROWTH_YEARS}개년")
    logger.info(f"  필터 ③ 현재 PER ≤ {PER_MAX}")

    if not INPUT_FILE.exists():
        logger.error(f"Agent 2 결과 없음: {INPUT_FILE}")
        return None

    df = pd.read_csv(INPUT_FILE)
    tickers = df['ticker'].unique().tolist()
    logger.info(f"\n분석 대상: {len(tickers)}개 종목")

    # 1차 필터링 (기준 연수)
    picks = []
    for t in tickers:
        result = _analyze_ticker(df[df['ticker'] == t], MIN_GROWTH_YEARS)
        if result:
            picks.append(result)

    # 결과가 없으면 연속 증가 기준 완화
    if not picks:
        relaxed = MIN_GROWTH_YEARS - 1
        logger.warning(f"기준 미달 — 연속증가 {relaxed}년으로 완화 재시도")
        for t in tickers:
            result = _analyze_ticker(df[df['ticker'] == t], relaxed)
            if result:
                picks.append(result)

    if not picks:
        logger.warning("최종 선별 종목 없음 (데이터 부족 가능성)")
        return pd.DataFrame()

    df_result = pd.DataFrame(picks)

    # 정렬: PER 낮은 순 → CAGR 높은 순
    df_result.sort_values(
        ['current_per', 'op_cagr_pct'],
        ascending=[True, False],
        inplace=True,
    )
    df_result.reset_index(drop=True, inplace=True)
    df_result.index += 1

    # 저장
    df_result.to_csv(OUTPUT_FILE, index=True, index_label='rank', encoding='utf-8-sig')
    df_result.to_excel(OUTPUT_EXCEL, index=True, index_label='rank')

    # ── 결과 출력 ──────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"  최종 선별 결과: {len(df_result)}개 종목")
    logger.info(f"{'='*60}")

    cols_show = ['ticker', 'name', 'current_per', 'op_latest',
                 'op_cagr_pct', 'consecutive_growth_yrs', 'roe', 'year_range']
    avail = [c for c in cols_show if c in df_result.columns]
    logger.info("\n" + df_result[avail].rename(columns={
        'ticker': '종목코드', 'name': '종목명', 'current_per': 'PER',
        'op_latest': '영업이익(최근,억)', 'op_cagr_pct': '영업이익CAGR%',
        'consecutive_growth_yrs': '연속증가년', 'roe': 'ROE%', 'year_range': '기간'
    }).to_string())

    logger.info(f"\n{'='*60}")
    logger.info("  TOP 10 상세")
    logger.info(f"{'='*60}")
    for rank, row in df_result.head(10).iterrows():
        logger.info(
            f"\n  [{rank:>2}위] {row['ticker']} {row['name']}\n"
            f"       PER: {row['current_per']:.1f}  |  "
            f"영업이익 CAGR: {row.get('op_cagr_pct', 'N/A')}%  |  "
            f"연속증가: {row['consecutive_growth_yrs']}년\n"
            f"       영업이익 추이({row['year_range']}): {row['op_trend']} (억원)\n"
            f"       ROE: {row.get('roe','N/A')}%  |  PBR: {row.get('pbr','N/A')}"
        )

    logger.info(f"\n[저장] {OUTPUT_FILE}")
    logger.info(f"[저장] {OUTPUT_EXCEL}")
    return df_result


if __name__ == '__main__':
    run()
