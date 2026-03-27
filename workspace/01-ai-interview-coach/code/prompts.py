설계 검토 완료. 질문 생성/피드백 파이프라인 분리, 프롬프트 버전 관리 구조로 작성합니다.

```python
# code/prompts.py
"""
LLM 프롬프트 템플릿 관리 모듈
- 질문 생성 / 피드백 생성 파이프라인 분리
- 버전 관리 및 확장 가능한 구조
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────
# Enums
# ──────────────────────────────────────────

class JobRole(str, Enum):
    DEVELOPER   = "개발"
    MARKETING   = "마케팅"
    PLANNER     = "기획"
    DESIGNER    = "디자인"


class CareerLevel(str, Enum):
    JUNIOR  = "신입"
    MID     = "3년차"
    SENIOR  = "5년차 이상"


# ──────────────────────────────────────────
# Prompt 버전 메타데이터
# ──────────────────────────────────────────

PROMPT_VERSION = {
    "question_generation": "v1.0",
    "answer_feedback":     "v1.0",
}


# ──────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────

@dataclass
class QuestionGenerationInput:
    job_role:     JobRole
    career_level: CareerLevel
    count:        int = 10          # 10 ~ 20 범위 권장
    focus_areas:  Optional[list[str]] = None  # 추가 키워드 (선택)


@dataclass
class AnswerFeedbackInput:
    question:     str
    answer:       str
    job_role:     JobRole
    career_level: CareerLevel


# ──────────────────────────────────────────
# 질문 생성 프롬프트
# ──────────────────────────────────────────

QUESTION_SYSTEM_PROMPT = """\
당신은 10년 경력의 채용 전문가입니다.
주어진 직군과 경력 레벨에 맞는 면접 예상 질문을 생성합니다.

[출력 규칙]
- 반드시 JSON 배열로만 응답하세요. 다른 텍스트 없이.
- 형식: ["질문1", "질문2", ...]
- 질문은 구체적이고 실무 중심이어야 합니다.
- 인성/직무/상황별 질문을 균형 있게 포함하세요.
"""


def build_question_prompt(data: QuestionGenerationInput) -> str:
    """질문 생성 유저 프롬프트 생성"""
    focus = ""
    if data.focus_areas:
        focus = f"\n중점 영역: {', '.join(data.focus_areas)}"

    return (
        f"직군: {data.job_role.value}\n"
        f"경력 레벨: {data.career_level.value}\n"
        f"생성 개수: {data.count}개{focus}\n\n"
        f"위 조건에 맞는 면접 예상 질문 {data.count}개를 JSON 배열로 생성하세요."
    )


# ──────────────────────────────────────────
# 답변 피드백 프롬프트
# ──────────────────────────────────────────

FEEDBACK_SYSTEM_PROMPT = """\
당신은 면접 코칭 전문가입니다.
지원자의 답변을 STAR 구조(Situation/Task/Action/Result) 기반으로 분석합니다.

[출력 규칙]
- 반드시 아래 JSON 형식으로만 응답하세요.
- 점수는 1~10 정수, 피드백은 2~3문장으로 작성하세요.

{
  "scores": {
    "logic":        <int>,   // 논리성
    "specificity":  <int>,   // 구체성
    "job_fit":      <int>    // 직무적합성
  },
  "star_analysis": {
    "situation": "<분석>",
    "task":      "<분석>",
    "action":    "<분석>",
    "result":    "<분석>"
  },
  "overall_feedback": "<종합 피드백>",
  "improvement":      "<개선 제안>"
}
"""


def build_feedback_prompt(data: AnswerFeedbackInput) -> str:
    """답변 피드백 유저 프롬프트 생성"""
    return (
        f"[지원자 정보]\n"
        f"직군: {data.job_role.value} / 경력: {data.career_level.value}\n\n"
        f"[면접 질문]\n{data.question}\n\n"
        f"[지원자 답변]\n{data.answer}\n\n"
        f"위 답변을 STAR 구조 기반으로 분석하고 JSON 형식으로 피드백을 제공하세요."
    )


# ──────────────────────────────────────────
# 프롬프트 팩토리 (외부 진입점)
# ──────────────────────────────────────────

class PromptFactory:
    """
    AI 파이프라인에서 사용하는 단일 진입점.
    system / user 프롬프트 쌍을 반환합니다.
    """

    @staticmethod
    def question_generation(
        job_role:     JobRole,
        career_level: CareerLevel,
        count:        int = 10,
        focus_areas:  Optional[list[str]] = None,
    ) -> dict[str, str]:
        data = QuestionGenerationInput(
            job_role=job_role,
            career_level=career_level,
            count=count,
            focus_areas=focus_areas,
        )
        return {
            "version": PROMPT_VERSION["question_generation"],
            "system":  QUESTION_SYSTEM_PROMPT,
            "user":    build_question_prompt(data),
        }

    @staticmethod
    def answer_feedback(
        question:     str,
        answer:       str,
        job_role:     JobRole,
        career_level: CareerLevel,
    ) -> dict[str, str]:
        data = AnswerFeedbackInput(
            question=question,
            answer=answer,
            job_role=job_role,
            career_level=career_level,
        )
        return {
            "version": PROMPT_VERSION["answer_feedback"],
            "system":  FEEDBACK_SYSTEM_PROMPT,
            "user":    build_feedback_prompt(data),
        }


# ──────────────────────────────────────────
# 사용 예시 (직접 실행 시 확인용)
# ──────────────────────────────────────────

if __name__ == "__main__":
    import json

    # 질문 생성 프롬프트 확인
    q_prompt = PromptFactory.question_generation(
        job_role=JobRole.DEVELOPER,