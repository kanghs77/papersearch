"""
Paper Survey Pipeline (5-agent)
================================
Stage 1: agent1 → 키워드 100개 수집
Stage 2: agent2 → 키워드 40개를 7개 클러스터로 묶고 쿼리 생성
Stage 3-4: agent3 + agent4 → 7개 토픽 각각에 대해 (검색 → 분석) 반복
Stage 5: agent5 → 7개 분석 결과를 학부생 친화 서베이로 통합

설계 노트:
- CrewAI 단일 Crew + Process.hierarchical는 8B 모델로 안정적 동작 불가.
- 그래서 Python 외부 루프로 stage를 명시적으로 분리하고,
  각 stage 안에서만 작은 sequential Crew를 돌린다.
- 각 stage 산출물을 intermediate/ 폴더에 저장 → 디버깅과 재개 가능.
"""

import os
import re
from datetime import datetime
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
import arxiv

# ============================================================
# 1. Tools
# ============================================================
_arxiv_client = arxiv.Client(page_size=20, delay_seconds=3, num_retries=3)
_CUTOFF_YEAR = datetime.now().year - 5

@tool("ArXiv Paper Search")
def arxiv_search(query: str) -> str:
    """
    arXiv에서 영문 쿼리로 논문을 검색합니다.
    최근 5년(현재 연도 - 5) 이후 발표된 논문을 우선 반환합니다.
    상위 8편의 Title, Authors, Published, arXiv ID, Categories, URL, Abstract을 반환합니다.
    검색은 관련도(Relevance) 순으로 정렬됩니다.
    """
    try:
        search = arxiv.Search(
            query=query,
            max_results=25,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        out = []
        for p in _arxiv_client.results(search):
            if p.published.year < _CUTOFF_YEAR:
                continue
            authors = ", ".join(a.name for a in p.authors[:4])
            if len(p.authors) > 4:
                authors += f" et al. (total {len(p.authors)})"
            abstract = " ".join(p.summary.split())  # 줄바꿈 제거
            arxiv_id = p.entry_id.rsplit("/", 1)[-1]
            out.append(
                f"Title: {p.title.strip()}\n"
                f"Authors: {authors}\n"
                f"Published: {p.published.strftime('%Y-%m-%d')}\n"
                f"arXiv ID: {arxiv_id}\n"
                f"Categories: {', '.join(p.categories)}\n"
                f"URL: {p.entry_id}\n"
                f"Abstract: {abstract[:1000]}{'...' if len(abstract) > 1000 else ''}"
            )
            if len(out) >= 8:
                break
        return "\n\n---\n\n".join(out) if out else (
            f"No papers found from {_CUTOFF_YEAR} onwards for query: '{query}'. "
            f"Try a different query."
        )
    except Exception as e:
        return f"arXiv search failed: {e}. Try a simpler query."


# ============================================================
# 2. LLM
# ============================================================
local_llama = LLM(
    model="ollama/llama3.1-8k",   # Modelfile로 만든 8K context 모델
    base_url="http://localhost:11434",
    temperature=0.2,
)


# ============================================================
# 3. Helpers
# ============================================================
PROMPTS_DIR = "prompts"
INTERMEDIATE_DIR = "intermediate"
os.makedirs(INTERMEDIATE_DIR, exist_ok=True)


def load_prompt(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_intermediate(name: str, content: str) -> str:
    path = os.path.join(INTERMEDIATE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"   💾 saved → {path}")
    return path


# agent2의 출력 파싱.  `## Topic N: 이름 / Keywords: ... / Query: ...` 블록 추출.
TOPIC_PATTERN = re.compile(
    r"##\s*Topic\s*(\d+)\s*:\s*(.+?)\s*\n+"
    r"\s*Keywords\s*:\s*(.+?)\s*\n+"
    r"\s*Query\s*:\s*(.+?)(?=\n+##\s*Topic|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def parse_topics(text: str):
    matches = TOPIC_PATTERN.findall(text)
    topics = []
    for num, name, kws, query in matches:
        topics.append({
            "num": int(num),
            "name": name.strip(),
            "keywords": [k.strip() for k in kws.split(",") if k.strip()],
            "query": query.strip().split("\n")[0].strip(),  # 첫 줄만
        })
    return topics


def safe_filename(s: str, maxlen: int = 30) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")[:maxlen] or "topic"


# ============================================================
# 4. Agents
# ============================================================
agent1_harvester = Agent(
    role="Keyword Harvester",
    goal="주제와 관련된 학술 영문 키워드 100개를 arXiv 다회 검색으로 수집",
    backstory=load_prompt("agent1.md"),
    llm=local_llama,
    tools=[arxiv_search],
    verbose=True,
    allow_delegation=False,
    max_iter=20,   # 검색을 많이 해야 하므로 여유 부여
)

agent2_clusterer = Agent(
    role="Keyword Clusterer",
    goal="100개 키워드 중 핵심 40개를 7개 의미 클러스터로 묶고 쿼리 생성",
    backstory=load_prompt("agent2.md"),
    llm=local_llama,
    tools=[],     # 도구 사용 금지
    verbose=True,
    allow_delegation=False,
    max_iter=4,
)

agent3_searcher = Agent(
    role="Paper Searcher",
    goal="주어진 쿼리로 최근 5년 핵심 논문 5~8편을 arXiv에서 수집",
    backstory=load_prompt("agent3.md"),
    llm=local_llama,
    tools=[arxiv_search],
    verbose=True,
    allow_delegation=False,
    max_iter=8,
)

agent4_analyzer = Agent(
    role="Paper Analyzer",
    goal="수집된 논문 컬렉션의 발전 흐름, 기술 조합, 신기술, 발표처 분석",
    backstory=load_prompt("agent4.md"),
    llm=local_llama,
    tools=[],
    verbose=True,
    allow_delegation=False,
    max_iter=5,
)

agent5_editor = Agent(
    role="Technical Editor",
    goal="7개 토픽 분석을 학부생 친화적 서베이 문서로 통합",
    backstory=load_prompt("agent5.md"),
    llm=local_llama,
    tools=[],
    verbose=True,
    allow_delegation=False,
    max_iter=5,
)


# ============================================================
# 5. Pipeline stages
# ============================================================
USER_TOPIC = "최근 5년간의 ANN과 결합된 SNN(Spiking Neural Network) 모델"


def stage1_harvest_keywords() -> str:
    print("\n" + "=" * 60)
    print("📥 Stage 1 — Keyword Harvesting (agent1)")
    print("=" * 60)
    task = Task(
        description=f"""
주제: {USER_TOPIC}

위 주제와 관련하여 최근 5년({_CUTOFF_YEAR}년 이후) 학계와 산업계에서 사용되는
영문 키워드를 **정확히 100개** 수집하시오.

수행 방법:
1. 주제에서 씨앗 키워드 5~10개를 추출.
2. 'ArXiv Paper Search' 도구를 **최소 10회** 호출하여 다양한 각도에서 검색.
   - 1차: 씨앗 키워드 그대로
   - 2차 이후: 1차 결과에서 발견한 새 용어로 확장 검색
3. 검색 결과의 제목/초록/카테고리에서 다음을 추출:
   모델 아키텍처, 알고리즘 이름, 데이터셋, 평가지표, 하드웨어 플랫폼, 기법 명사구.
4. 중복 제거 후 정확히 100개의 영문 키워드를 번호 매겨 출력.

agent1.md의 output_format을 글자 그대로 따르시오.
부가 설명, 카테고리 헤더, "여기 키워드들입니다" 같은 문장 일체 금지.
""",
        expected_output="정확히 100개의 영문 키워드가 1~100번 번호로 매겨진 평면 리스트",
        agent=agent1_harvester,
    )
    crew = Crew(
        agents=[agent1_harvester], tasks=[task],
        process=Process.sequential, verbose=True,
    )
    result = str(crew.kickoff())
    save_intermediate("01_keywords.md", result)
    return result


def stage2_cluster_keywords(keywords_text: str) -> str:
    print("\n" + "=" * 60)
    print("🗂️  Stage 2 — Keyword Clustering (agent2)")
    print("=" * 60)
    task = Task(
        description=f"""
아래는 agent1이 수집한 키워드 리스트입니다. 이 키워드만 사용하시오. 검색 금지.

---
{keywords_text}
---

이 키워드들 중 학술적으로 가장 중요한 **40개를 선별**하여,
**정확히 7개의 의미 클러스터**로 그룹화하시오.
각 클러스터에 대해 arXiv 검색용 영문 쿼리(3~5단어)를 생성하시오.

agent2.md의 output_format을 글자 그대로 따르시오.
헤더 '## Topic N:', 라벨 'Keywords:', 'Query:'가 정확해야 후속 파서가 동작합니다.
부가 텍스트(도입부, 결론) 절대 금지.
""",
        expected_output="정확히 7개의 '## Topic N: 이름\\nKeywords: ...\\nQuery: ...' 블록",
        agent=agent2_clusterer,
    )
    crew = Crew(
        agents=[agent2_clusterer], tasks=[task],
        process=Process.sequential, verbose=True,
    )
    result = str(crew.kickoff())
    save_intermediate("02_clusters.md", result)
    return result


def stage3_4_per_topic(topic: dict) -> str:
    print("\n" + "-" * 60)
    print(f"🔬 Topic {topic['num']} — {topic['name']}")
    print(f"   Query: {topic['query']}")
    print("-" * 60)

    search_task = Task(
        description=f"""
연구 토픽: {topic['name']}
관련 키워드: {', '.join(topic['keywords'])}
1차 검색 쿼리: {topic['query']}

'ArXiv Paper Search' 도구를 사용하여 이 토픽에 대한 최근 5년 핵심 논문 **5~8편**을 수집하시오.
1차 검색이 부족하면 쿼리를 변형하여 최대 4회까지 추가 검색하시오.

agent3.md의 output_format을 글자 그대로 따르고,
도구 출력에 없는 논문은 절대 추가하지 마시오. arXiv ID는 도구 출력 그대로 복사.
""",
        expected_output="5~8편의 논문 메타데이터(Title, Authors, Published, arXiv ID, Categories, URL, Abstract)",
        agent=agent3_searcher,
    )

    analyze_task = Task(
        description=f"""
agent3_searcher가 '{topic['name']}' 토픽에 대해 수집한 논문 컬렉션을 분석하시오.

분석 항목 (agent4.md의 5단계 SOP 준수):
1. 시간순 발전 흐름 (각 문장마다 arXiv ID 인용)
2. 각 논문이 어떤 기술 A + 기술 B의 조합인지
3. 최근 1~2년 새로 등장한 기술
4. arXiv 카테고리/학회 분포 (학회 정보 없으면 '발표처 미확인')
5. 한 줄 요약

추가 검색 금지. 입력 자료에만 기반.
agent4.md의 output_format을 글자 그대로 따르시오.
""",
        expected_output="agent4.md 5섹션 포맷에 따른 분석 보고서",
        agent=agent4_analyzer,
        context=[search_task],  # 이전 task 결과 자동 주입
    )

    crew = Crew(
        agents=[agent3_searcher, agent4_analyzer],
        tasks=[search_task, analyze_task],
        process=Process.sequential,
        verbose=True,
    )
    result = str(crew.kickoff())
    fname = f"03_topic_{topic['num']:02d}_{safe_filename(topic['name'])}.md"
    save_intermediate(fname, result)
    return result


def stage5_synthesize(per_topic_summaries: list) -> str:
    print("\n" + "=" * 60)
    print("📝 Stage 5 — Final Synthesis (agent5)")
    print("=" * 60)

    combined = "\n\n".join(
        f"### Input Topic {i + 1}: {s['name']}\n\n{s['analysis']}"
        for i, s in enumerate(per_topic_summaries)
    )

    task = Task(
        description=f"""
원본 주제: {USER_TOPIC}

아래는 agent4가 {len(per_topic_summaries)}개 토픽에 대해 만든 분석 보고서입니다.
이 자료만 가지고 작성하시오. 추가 검색이나 외부 지식 주입 금지.

---
{combined}
---

agent5.md의 4단계 SOP를 따라 일반 학부생도 이해 가능한 종합 서베이를 작성하시오.
- 친절한 ~입니다/~습니다 문체
- 7개 토픽을 자연스러운 순서로 배치 (기초→응용)
- 각 챕터에 발전 흐름·대표 논문(arXiv ID 명시)·한계 포함
- 마무리에 공통 트렌드 짚기
- 사용자에게 질문하는 문장 금지
""",
        expected_output="agent5.md 포맷에 따른 최종 마크다운 서베이 (들어가며 + 7개 챕터 + 마치며)",
        agent=agent5_editor,
    )
    crew = Crew(
        agents=[agent5_editor], tasks=[task],
        process=Process.sequential, verbose=True,
    )
    return str(crew.kickoff())


# ============================================================
# 6. Main
# ============================================================
if __name__ == "__main__":
    print("🚀 Paper Survey Pipeline 시작")
    print(f"   주제      : {USER_TOPIC}")
    print(f"   연도 컷오프: {_CUTOFF_YEAR}\n")

    # --- Stage 1
    keywords_text = stage1_harvest_keywords()

    # --- Stage 2
    clusters_text = stage2_cluster_keywords(keywords_text)

    # --- Parse clusters
    topics = parse_topics(clusters_text)
    print(f"\n✅ 파싱된 토픽 수: {len(topics)}")
    for t in topics:
        print(f"   {t['num']}. {t['name']:<35s} | query = '{t['query']}'")

    if len(topics) == 0:
        print("\n❌ 토픽 파싱 실패. intermediate/02_clusters.md의 포맷을 확인하세요.")
        print("   agent2가 '## Topic N: / Keywords: / Query:' 포맷을 지키지 않았을 가능성.")
        raise SystemExit(1)

    if len(topics) != 7:
        print(f"\n⚠️  토픽이 7개가 아닙니다 ({len(topics)}개). 파싱된 토픽으로 계속 진행합니다.")

    # --- Stage 3-4: per-topic loop
    per_topic_summaries = []
    for topic in topics:
        try:
            analysis = stage3_4_per_topic(topic)
            per_topic_summaries.append({"name": topic["name"], "analysis": analysis})
        except Exception as e:
            print(f"\n⚠️  Topic {topic['num']} ({topic['name']}) 실패: {e}")
            print("   다음 토픽으로 계속 진행합니다.")
            continue

    if not per_topic_summaries:
        print("\n❌ 모든 토픽 처리 실패. 종료합니다.")
        raise SystemExit(1)

    # --- Stage 5
    final = stage5_synthesize(per_topic_summaries)

    out_path = "final_paper_survey.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final)

    print("\n" + "=" * 60)
    print(f"✅ 완료! '{out_path}' 를 확인하세요.")
    print(f"   중간 산출물: {INTERMEDIATE_DIR}/ 폴더")
    print("=" * 60)
