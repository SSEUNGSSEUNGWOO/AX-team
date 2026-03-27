# code/ai_pipeline.py
"""
AI 면접 코치 — LLM 파이프라인
질문 생성 / STAR 피드백 / 항목별 채점
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 도메인 상수
# ---------------------------------------------------------------------------

class CareerLevel(str, Enum):
    ENTRY = "신입"
    MID = "3년"
    SENIOR = "5년+"


class JobRole(str, Enum):
    DEVELOPER = "개발"
    MARKETING = "마케팅"
    PLANNER = "기획"
    DESIGNER = "디자인"


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class InterviewQuestion:
    index: int
    content: str
    category: str  # 직무/인성/상황


@dataclass
class STARFeedback:
    situation: str
    task: str
    action: str
    result: str
    missing_elements: list[str]
    overall_comment: str


@dataclass
class AnswerScore:
    logic: int          # 논리성  0~100
    specificity: int    # 구체성  0~100
    job_fit: int        # 직무적합성 0~100
    total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = round((self.logic + self.specificity + self.job_fit) / 3)


@dataclass
class FeedbackResult:
    star: STARFeedback
    score: AnswerScore
    improvement_tips: list[str]


# ---------------------------------------------------------------------------
# 프롬프트 템플릿
# ---------------------------------------------------------------------------

_QUESTION_SYSTEM = """당신은 채용 전문가입니다.
주어진 직군과 경력 수준에 맞는 면접 예상 질문을 JSON 배열로 반환하세요.

출력 형식 (반드시 준수):
[
  {"index": 1, "content": "질문 내용", "category": "직무|인성|상황"},
  ...
]
설명 텍스트 없이 JSON만 출력하세요."""

_QUESTION_USER = """직군: {role}
경력: {level}
질문 수: {count}개
직무 키워드: {keywords}"""


_FEEDBACK_SYSTEM = """당신은 면접 코치입니다.
지원자의 답변을 STAR 구조로 분석하고 항목별 점수를 매겨 JSON으로 반환하세요.

출력 형식 (반드시 준수):
{{
  "star": {{
    "situation": "상황 분석",
    "task": "과제 분석",
    "action": "행동 분석",
    "result": "결과 분석",
    "missing_elements": ["누락 요소1", ...],
    "overall_comment": "종합 코멘트"
  }},
  "score": {{
    "logic": 0~100,
    "specificity": 0~100,
    "job_fit": 0~100
  }},
  "improvement_tips": ["개선 팁1", "개선 팁2", ...]
}}
설명 텍스트 없이 JSON만 출력하세요."""

_FEEDBACK_USER = """직군: {role} / 경력: {level}
질문: {question}
답변: {answer}"""


# ---------------------------------------------------------------------------
# AI 파이프라인
# ---------------------------------------------------------------------------

class InterviewAIPipeline:
    """LLM 기반 면접 코치 파이프라인."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ) -> None:
        self._client = OpenAI(api_key=api_key)  # 없으면 env OPENAI_API_KEY 자동 사용
        self._model = model
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_questions(
        self,
        role: JobRole | str,
        level: CareerLevel | str,
        count: int = 15,
        keywords: str = "",
    ) -> list[InterviewQuestion]:
        """직군·경력 기반 예상 질문 생성."""
        role_str = role.value if isinstance(role, JobRole) else role
        level_str = level.value if isinstance(level, CareerLevel) else level

        prompt = _QUESTION_USER.format(
            role=role_str,
            level=level_str,
            count=count,
            keywords=keywords or "없음",
        )

        raw = self._chat(system=_QUESTION_SYSTEM, user=prompt)
        return self._parse_questions(raw)

    def evaluate_answer(
        self,
        question: str,
        answer: str,
        role: JobRole | str,
        level: CareerLevel | str,
    ) -> FeedbackResult:
        """답변 STAR 분석 + 항목별 채점."""
        role_str = role.value if isinstance(role, JobRole) else role
        level_str = level.value if isinstance(level, CareerLevel) else level

        prompt = _FEEDBACK_USER.format(
            role=role_str,
            level=level_str,
            question=question,
            answer=answer,
        )

        raw = self._chat(system=_FEEDBACK_SYSTEM, user=prompt, temperature=0.3)
        return self._parse_feedback(raw)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _chat(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
    ) -> str:
        temp = temperature if temperature is not None else self._temperature
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=temp,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or ""
        logger.debug("LLM raw response: %s", content[:200])
        return content

    @staticmethod
    def _parse_questions(raw: str) -> list[InterviewQuestion]:
        try:
            data: list[dict] = json.loads(raw)
            return [
                InterviewQuestion(
                    index=item["index"],
                    content=item["content"],
                    category=item.get("category", "직무"),
                )
                for item in data
            ]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("질문 파싱 실패: %s | raw=%s", exc, raw[:300])
            raise ValueError("LLM 질문 응답 파싱 오류") from exc

    @staticmethod
    def _parse_feedback(raw: str) -> FeedbackResult:
        try:
            data: dict = json.loads(raw)

            star_data = data["star"]
            star = STARFeedback(
                situation=star_data.get("situation", ""),
                task=star_data.get("task", ""),
                action=star_data.get("action", ""),
                result=star_data.get("result", ""),
                missing_elements=star_data.get("missing_elements", []),
                overall_comment=star_data.get("overall_comment", ""),
            )

            score_data = data["score"]
            score = AnswerScore(
                logic=int(score_data.get("logic", 50)),
                specificity=int(score_data.get("specificity", 50)),
                job_fit=int(score_data.get("job_fit", 50)),
            )

            return FeedbackResult(
                star=star,
                score=score,
                improvement_tips=data.get("improvement_tips", []),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("피드백 파싱 실패: %s | raw=%s", exc, raw[:300])
            raise ValueError("LLM 피드백 응답 파싱 오류") from exc