# 제너레이터 제어 신호 — 워크플로우 generator 내부 통신용 타입 정의
# dict 마법 키(__consensus__ 등) 대신 이 dataclass 인스턴스를 yield한다.

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsensusSignal:
    """deliberate() → 호출자: 합의문 전달."""
    consensus: str


@dataclass(frozen=True)
class GateSignal:
    """team_gate() → _run_team_gate(): 투표 결과 전달."""
    can_proceed: bool
    block_reasons: list
    summary: str


@dataclass(frozen=True)
class GateResultSignal:
    """_run_team_gate() → 워크플로우: 최종 게이트 결과 전달."""
    can_proceed: bool
    block_reasons: list


@dataclass(frozen=True)
class DocsSignal:
    """write_project_docs() → 워크플로우: 생성된 문서 딕셔너리 전달."""
    docs: dict  # {filename: {"agent": aid, "content": str}}


@dataclass(frozen=True)
class CodeSignal:
    """write_code_files() → 워크플로우: 파일 플랜 + 생성된 코드 딕셔너리 전달."""
    file_plan: list
    generated: dict  # {filepath: code_str}


@dataclass(frozen=True)
class BriefSignal:
    """_collect_team_brief() → 호출자: 팀 전체 의견 요약 전달."""
    brief: str
    results: dict  # {agent_id: text}
