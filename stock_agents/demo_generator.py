"""
데모용 현실적인 코스닥 가상 데이터 생성기
실제 코스닥 종목 수·업종 분포·재무 특성을 반영한 합성 데이터
"""
import random
import numpy as np
import pandas as pd
from config import DATA_DIR, ANALYSIS_YEARS

random.seed(42)
np.random.seed(42)

# 실제 코스닥 업종 분포 참고
SECTORS = [
    ('IT서비스', 0.12), ('반도체', 0.10), ('바이오/제약', 0.14),
    ('소프트웨어', 0.08), ('전기전자', 0.09), ('기계/장비', 0.07),
    ('화학', 0.06), ('유통/소매', 0.05), ('건설', 0.04),
    ('미디어/엔터', 0.05), ('의료기기', 0.06), ('소재', 0.05),
    ('자동차부품', 0.04), ('에너지', 0.03), ('기타', 0.02),
]

COMPANY_SUFFIXES = ['테크', '시스템즈', '바이오', '솔루션', '홀딩스',
                    '엔터테인먼트', '코퍼레이션', '이노베이션', '파트너스', '글로벌']

# 시가총액 분포 (억원) - 로그정규분포 근사
MARKET_CAP_PARAMS = {'mean': 7.5, 'sigma': 1.2}   # log scale


def _random_ticker():
    """6자리 코스닥 종목코드 생성 (실제 범위 참고)"""
    return str(random.randint(100000, 999999))


def _generate_company_name(sector):
    chars = '가나다라마바사아자차카타파하'
    base = ''.join(random.choices(chars, k=random.randint(2, 3)))
    suffix = random.choice(COMPANY_SUFFIXES)
    return base + suffix


def _generate_financials(years, seed_revenue, profile):
    """
    profile: 'growing' / 'mixed' / 'declining' / 'loss'
    연도별 재무 지표 생성
    """
    records = {}
    rev = seed_revenue
    op_margin_base = random.uniform(0.04, 0.18)
    roe_base = random.uniform(0.05, 0.20)

    for i, yr in enumerate(years):
        if profile == 'growing':
            rev_growth = random.uniform(0.05, 0.25)
            op_margin_delta = random.uniform(0.005, 0.025)
        elif profile == 'mixed':
            rev_growth = random.uniform(-0.05, 0.15)
            op_margin_delta = random.uniform(-0.02, 0.02)
        elif profile == 'declining':
            rev_growth = random.uniform(-0.15, 0.02)
            op_margin_delta = random.uniform(-0.03, 0.0)
        else:   # loss
            rev_growth = random.uniform(-0.10, 0.10)
            op_margin_delta = random.uniform(-0.05, -0.01)

        rev = rev * (1 + rev_growth)
        op_margin = max(-0.20, op_margin_base + op_margin_delta * i)
        op = rev * op_margin
        net_margin = op_margin * random.uniform(0.5, 0.9)
        net_income = rev * net_margin

        equity = rev * random.uniform(0.8, 1.5)
        assets = equity * random.uniform(1.2, 2.0)
        roe = (net_income / equity * 100) if equity > 0 else 0
        roa = (net_income / assets * 100) if assets > 0 else 0
        eps = net_income / random.uniform(0.05, 0.3) * 10   # 주당 EPS (원)
        bps = equity / random.uniform(0.05, 0.3) * 10

        records[str(yr)] = {
            'revenue': round(rev, 1),
            'operating_profit': round(op, 1),
            'operating_margin': round(op_margin * 100, 2),
            'net_income': round(net_income, 1),
            'roe': round(roe, 2),
            'roa': round(roa, 2),
            'eps': round(eps, 0),
            'bps': round(bps, 0),
        }
    return records


def _assign_per(profile, op_latest):
    """프로파일에 따라 현실적인 PER 부여"""
    if profile == 'loss':
        return None   # 적자 기업 PER 없음
    if profile == 'growing':
        base_per = random.uniform(8, 35)
    elif profile == 'mixed':
        base_per = random.uniform(6, 25)
    else:
        base_per = random.uniform(4, 15)
    return round(base_per, 1)


def generate_kosdaq_universe(n_companies=1500):
    """코스닥 전체 종목 유니버스 생성"""
    sector_pool = []
    for sector, weight in SECTORS:
        sector_pool.extend([sector] * int(weight * 1000))

    # 프로파일 분포 (실제 코스닥 특성 반영)
    profiles = (
        ['growing'] * 250 +    # 성장 기업 ~17%
        ['mixed'] * 500 +      # 혼재 ~33%
        ['declining'] * 350 +  # 하락 ~23%
        ['loss'] * 400         # 적자 ~27%
    )
    random.shuffle(profiles)

    tickers_used = set()
    companies = []

    for i in range(n_companies):
        # 중복 없는 종목코드
        while True:
            ticker = _random_ticker()
            if ticker not in tickers_used:
                tickers_used.add(ticker)
                break

        sector = random.choice(sector_pool)
        profile = profiles[i % len(profiles)]
        seed_rev = np.exp(np.random.normal(MARKET_CAP_PARAMS['mean'],
                                           MARKET_CAP_PARAMS['sigma']))
        seed_rev = max(10, seed_rev)

        fin = _generate_financials(ANALYSIS_YEARS, seed_rev, profile)
        per_latest = _assign_per(profile, fin[str(ANALYSIS_YEARS[-1])]['operating_profit'])

        companies.append({
            'ticker': ticker,
            'name': _generate_company_name(sector),
            'sector': sector,
            'profile': profile,
            'financials': fin,
            'per_2024': per_latest,
        })

    return companies


def build_agent1_output(companies):
    """Agent1 형식: 영업이익 흑자 기업 리스트"""
    rows = []
    for c in companies:
        latest_year = str(ANALYSIS_YEARS[-1])
        op = c['financials'].get(latest_year, {}).get('operating_profit', None)
        if op is not None and op > 0:
            rows.append({
                'ticker': c['ticker'],
                'name': c['name'],
                'operating_profit': round(op, 1),
                'year': latest_year,
                'positive': True,
            })
    df = pd.DataFrame(rows).sort_values('operating_profit', ascending=False)
    return df


def build_agent2_output(companies, df_agent1):
    """Agent2 형식: 흑자 기업 5개년 재무 데이터"""
    positive_tickers = set(df_agent1['ticker'].tolist())
    rows = []
    for c in companies:
        if c['ticker'] not in positive_tickers:
            continue
        per_2024 = c['per_2024']
        for yr in ANALYSIS_YEARS:
            yr_str = str(yr)
            fin = c['financials'].get(yr_str, {})
            if not fin:
                continue
            row = {
                'ticker': c['ticker'],
                'name': c['name'],
                'year': yr_str,
                **fin,
                'per': per_2024 if yr == ANALYSIS_YEARS[-1] else None,
                'pbr': round(random.uniform(0.5, 3.0), 2) if yr == ANALYSIS_YEARS[-1] else None,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def save_demo_data():
    """전체 데모 데이터 생성 및 저장"""
    print("데모 데이터 생성 중...")
    companies = generate_kosdaq_universe(1500)

    df1 = build_agent1_output(companies)
    df1.to_csv(DATA_DIR / 'agent1_positive_op.csv', index=False, encoding='utf-8-sig')
    print(f"  Agent1: 흑자 기업 {len(df1)}개")

    df2 = build_agent2_output(companies, df1)
    df2.to_csv(DATA_DIR / 'agent2_financial_data.csv', index=False, encoding='utf-8-sig')
    df2.to_excel(DATA_DIR / 'agent2_financial_data.xlsx', index=False)
    print(f"  Agent2: 재무 레코드 {len(df2)}행")

    print(f"  저장 완료: {DATA_DIR}")
    return df1, df2, companies


if __name__ == '__main__':
    save_demo_data()
