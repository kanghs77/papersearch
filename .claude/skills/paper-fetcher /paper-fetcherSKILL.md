---
name: paper-fetcher
description: arXiv ID, DOI, 또는 URL이 주어졌을 때 PDF를 다운로드하고 본문 텍스트를 추출. 논문 정독이 필요한 모든 상황에서 사용.
allowed-tools: Bash(curl *), Bash(wget *), Bash(pdftotext *), Bash(python3 *), Read, Write
---

# Paper Fetcher

## 입력 형식
- arXiv ID: `2305.12345` 또는 `2305.12345v2`
- DOI: `10.1109/CVPR.2024.xxxxx`
- URL: 그대로 사용

## 단계
1. **arXiv ID 입력 시**:
```bash
   ID=$1
   curl -L "https://arxiv.org/pdf/${ID}.pdf" -o "/tmp/${ID}.pdf"
   pdftotext -layout "/tmp/${ID}.pdf" "/tmp/${ID}.txt"
```

2. **DOI 입력 시**: 
   - `https://doi.org/{DOI}` 로 redirect 해서 publisher URL 획득
   - paywall이면 명시적으로 "본문 접근 불가, abstract만 가능"을 반환

3. **추출 후 검증**:
   - 텍스트 길이 < 1000자면 OCR 실패로 판단, 사용자에게 알림
   - 정상이면 `/tmp/<id>.txt` 경로 반환

## 출력 형식
{
"paper_id": "...",
"pdf_path": "/tmp/2305.12345.pdf",
"text_path": "/tmp/2305.12345.txt",
"char_count": 45032,
"status": "ok"  // 또는 "abstract_only", "fetch_failed"
}

## 주의
- 동일 ID가 이미 `/tmp/`에 있으면 재다운로드 금지
- arXiv는 분당 ~10건 이상 빠른 요청 금지 (rate limit)
