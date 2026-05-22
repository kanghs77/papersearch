"""
데이터 소스 진단 스크립트
CMD에서: python test_sources.py
"""
import sys

print("=" * 50)
print("코스닥 데이터 소스 진단")
print("=" * 50)

# 1. finance-datareader 테스트
print("\n[1] FinanceDataReader 테스트...")
try:
    import FinanceDataReader as fdr
    df = fdr.StockListing('KOSDAQ')
    print(f"    ✓ 성공: {len(df)}개 종목 수집됨")
    print(f"    컬럼: {list(df.columns)}")
    print(f"    예시:\n{df.head(3).to_string()}")
except ImportError:
    print("    ✗ 미설치 → pip install finance-datareader 실행 필요")
except Exception as e:
    print(f"    ✗ 오류: {e}")

# 2. Naver Finance 접속 테스트
print("\n[2] Naver Finance 접속 테스트...")
try:
    import requests
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    r = requests.get('https://finance.naver.com/item/coinfo.naver',
                     params={'code': '005930', 'target': 'finsum_more'},
                     headers=headers, timeout=10)
    r.encoding = 'euc-kr'
    if '영업이익' in r.text:
        print(f"    ✓ 성공 (status={r.status_code}, 영업이익 데이터 존재)")
    else:
        print(f"    △ 접속됨 (status={r.status_code}) 그러나 영업이익 없음")
        print(f"    응답 앞부분: {r.text[:200]}")
except Exception as e:
    print(f"    ✗ 오류: {e}")

# 3. pykrx 테스트
print("\n[3] pykrx 테스트...")
try:
    from pykrx import stock
    tickers = stock.get_market_ticker_list('20241227', market='KOSDAQ')
    print(f"    ✓ 성공: {len(tickers)}개 종목")
except Exception as e:
    print(f"    ✗ 오류: {e}")

print("\n" + "=" * 50)
print("진단 완료. 위 결과를 붙여넣어 주세요.")
print("=" * 50)
