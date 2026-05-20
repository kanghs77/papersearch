---
name: citation-formatter
description: 논문 메타데이터를 BibTeX, IEEE, APA 형식으로 변환. 보고서 작성 시 자동으로 인용 형식 통일에 사용.
allowed-tools: Read, Write
---

# Citation Formatter

입력: filtered_papers.json의 한 항목
출력: 요청한 형식의 인용 string

## BibTeX 형식
@article{firstauthor_keyword_year,
title = {...},
author = {Last, First and Last2, First2},
journal = {...},
year = {YYYY},
volume = {...},
pages = {...}
}
key는 `firstauthorlastname_titlekeyword_year` 패턴. 모두 lowercase.

## IEEE 형식
`[N] A. Author, B. Author, "Title," in *Venue*, vol. X, pp. Y-Z, YYYY.`

## 출력 위치
`outputs/references.bib` (BibTeX 모음)
`outputs/references_ieee.md` (텍스트 인용 목록)
