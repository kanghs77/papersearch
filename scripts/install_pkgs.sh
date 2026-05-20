#!/bin/bash
# SessionStart hook - 매 session마다 실행, cloud + local 공통
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

# cloud에서만 필요한 추가 패키지
pip install --break-system-packages --quiet arxiv semanticscholar
mkdir -p /tmp /home/claude-runs outputs/papers
exit 0
