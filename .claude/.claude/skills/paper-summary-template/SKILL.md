---
name: paper-summary-template
description: 학부생도 이해할 수 있는 논문 해설 작성 시 사용할 표준 템플릿. Agent 3의 deep-explainer가 각 논문을 정리할 때 자동으로 적용.
---

# Undergraduate-Level Paper Summary Template

다음 6개 섹션을 반드시 순서대로 포함합니다. 각 섹션의 길이 가이드를 지킵니다.

## 0. 한 줄 요약 (1문장)
- 비전공자 친구에게 엘리베이터에서 설명할 수준
- 수식·전문용어 금지

## 1. 풀려는 문제 (3~5문장)
- 기존 방법의 구체적 한계 1~2개
- 왜 풀기 어려운가 (직관적 이유)

## 2. 핵심 아이디어 (5~8문장 + 비유 1개)
- "이 논문이 한 일은 결국 X와 비슷하다" 식의 비유로 시작
- 수식은 의미를 먼저 한국어로 쓰고, 그 다음 LaTeX

## 3. 방법 (단계별, Step 1~N)
각 Step은:
- 한 줄 설명
- "왜 이 단계가 필요한가"
- (있으면) 핵심 수식 1개

## 4. 결과 (표 1개 + 산문 3~5문장)
- 데이터셋·벤치마크 명시
- baseline 대비 수치 변화 (절대 "성능 향상" 같은 모호한 표현 금지)
- 의미 있는 차이인지 미미한 차이인지 평가

## 5. 한계와 의의 (3~5문장)
- 이 논문이 못 하는 것 (저자가 밝힌 것 + 비판적 시각)
- 후속 연구에 미친 영향

## 6. 다른 선정 논문과의 연결 (2~4문장)
- `/tmp/filtered_papers.json`의 어느 논문과 무엇이 비슷/다른지

## 용어 처리 규칙
- 전공 용어 첫 등장: `용어명 (한 줄 정의)` 형식
- 수식의 모든 변수: 등장 직후 한국어로 "이건 무엇" 주석

## 산출
- 파일명: `outputs/papers/${PAPER_ID}.md`
- 종합 보고서: `outputs/summary.md`에 subtopic cluster별 narrative

자세한 좋은 예시는 [examples/undergrad_summary.md](examples/undergrad_summary.md) 참고.
