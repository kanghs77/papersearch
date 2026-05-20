"""
코스닥 주식 멀티 에이전트 분석 파이프라인 오케스트레이터

실행:
  python orchestrator.py            # demo 모드 (기본)
  python orchestrator.py production # production 모드 (로컬 네트워크 필요)

Production 모드 요구사항:
  - 네트워크 접근: finance.naver.com, navercomp.wisereport.co.kr
  - (선택) pykrx 사용: 환경변수 KRX_ID, KRX_PW 설정
"""
import sys
import time
from pathlib import Path

# 모드 설정
_mode_arg = sys.argv[1] if len(sys.argv) > 1 else 'demo'
if _mode_arg not in ('demo', 'production'):
    print(f"[경고] 알 수 없는 모드 '{_mode_arg}' → demo 모드로 실행")
    _mode_arg = 'demo'

# config 모듈이 로드되기 전에 DATA_MODE 패치
import config as _cfg
_cfg.DATA_MODE = _mode_arg

sys.path.insert(0, str(Path(__file__).parent))
from utils import logger


def _banner(step: int, title: str):
    logger.info("\n" + "─" * 60)
    logger.info(f"  STEP {step}  |  {title}")
    logger.info("─" * 60 + "\n")


def main():
    t0 = time.time()
    mode = _cfg.DATA_MODE

    logger.info("\n" + "=" * 60)
    logger.info("  코스닥 주식 멀티 에이전트 분석 파이프라인")
    logger.info(f"  모드: {mode.upper()}")
    logger.info(f"  결과 저장: {_cfg.DATA_DIR}")
    logger.info("=" * 60)

    # ── Agent 1: 코스닥 영업이익 흑자 기업 선별 ───────────────────
    _banner(1, "코스닥 영업이익 흑자 기업 선별 (Agent 1)")
    import agent1_kosdaq_screener as a1
    result_a1 = a1.run()
    if isinstance(result_a1, tuple):
        df_a1, companies = result_a1
    else:
        df_a1, companies = result_a1, None
    if df_a1 is None or df_a1.empty:
        logger.error("Agent 1 실패 — 파이프라인 중단")
        sys.exit(1)
    logger.info(f"\n✓ Agent 1 완료: 영업이익 흑자 {len(df_a1)}개 종목\n")
    time.sleep(0.5)

    # ── Agent 2: 5개년 재무제표 수집 ──────────────────────────────
    _banner(2, "5개년 재무제표 및 주요 지표 수집 (Agent 2)")
    import agent2_financial_downloader as a2
    df_a2 = a2.run(df_agent1=df_a1, companies=companies)
    if df_a2 is None or df_a2.empty:
        logger.error("Agent 2 실패 — 파이프라인 중단")
        sys.exit(1)
    logger.info(f"\n✓ Agent 2 완료: {len(df_a2)}행 재무 데이터 ({df_a2['ticker'].nunique()}개 종목)\n")
    time.sleep(0.5)

    # ── Agent 3: 데이터 정확성 검증 ───────────────────────────────
    _banner(3, "재무 데이터 정확성 검증 (Agent 3)")
    import agent3_data_verifier as a3
    verified = a3.run()
    logger.info(f"\n{'✓' if verified else '!'} Agent 3 완료: {'검증 통과' if verified else '검증 미달 — 주의 필요'}\n")
    time.sleep(0.5)

    # ── Agent 4: 영업이익 증가 + PER ≤ 10 선별 ───────────────────
    _banner(4, f"영업이익 증가 & PER ≤ {_cfg.PER_MAX} 최종 선별 (Agent 4)")
    import agent4_stock_picker as a4
    df_final = a4.run()

    # ── 파이프라인 완료 요약 ─────────────────────────────────────
    elapsed = time.time() - t0
    logger.info("\n" + "=" * 60)
    logger.info(f"  파이프라인 완료 — {elapsed:.0f}초 ({elapsed/60:.1f}분)")
    logger.info("=" * 60)
    logger.info(f"  [결과 파일]")
    logger.info(f"    Agent1 : {_cfg.DATA_DIR}/agent1_positive_op.csv")
    logger.info(f"    Agent2 : {_cfg.DATA_DIR}/agent2_financial_data.xlsx")
    logger.info(f"    Agent3 : {_cfg.DATA_DIR}/agent3_verification_report.csv")
    logger.info(f"    Agent4 : {_cfg.DATA_DIR}/agent4_final_picks.xlsx  ← 최종 결과")

    if df_final is not None and not df_final.empty:
        logger.info(f"\n  최종 선별 종목: {len(df_final)}개")
        logger.info(f"  조건: 영업이익 연속증가 {_cfg.MIN_GROWTH_YEARS}년+ & PER ≤ {_cfg.PER_MAX}")
    else:
        logger.info("\n  최종 선별 종목: 0개 (조건 강화 또는 데이터 부족)")


if __name__ == '__main__':
    main()
