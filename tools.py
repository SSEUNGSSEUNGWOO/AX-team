# 에이전트 도구 정의 및 실행 — read_file, list_files, search_memory

import os
import rag

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "워크스페이스 내 특정 파일 내용 읽기. 코드나 문서를 직접 확인할 때 사용.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "워크스페이스 기준 상대 경로 (예: code/main.py, docs/01_요구사항정의서.md)"
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "워크스페이스 내 생성된 파일 목록 조회.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_memory",
        "description": "과거 유사 프로젝트 기억 검색. 이전에 비슷한 태스크에서 어떤 결정을 했는지 확인.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색 쿼리"
                }
            },
            "required": ["query"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict, workspace: str = "") -> str:
    """도구 실행 후 결과 문자열 반환."""
    try:
        if tool_name == "read_file":
            path = tool_input.get("path", "")
            # 보안: workspace 없이는 파일 접근 불가
            if not workspace:
                return "[오류] workspace 없이 read_file 사용 불가"
            actual = os.path.join(workspace, path) if not os.path.isabs(path) else path

            # 보안: workspace 외부 접근 차단
            if workspace:
                abs_ws = os.path.abspath(workspace)
                abs_path = os.path.abspath(actual)
                if not abs_path.startswith(abs_ws + os.sep) and abs_path != abs_ws:
                    return f"[오류] workspace 외부 경로 접근 차단: {path}"

            if not os.path.isfile(actual):
                return f"[오류] 파일 없음: {path}"

            with open(actual, encoding="utf-8") as f:
                content = f.read()
            return content[:3000] + ("\n...(이하 생략)" if len(content) > 3000 else "")

        elif tool_name == "list_files":
            ws = workspace
            if not os.path.isdir(ws):
                return "[오류] 워크스페이스 디렉토리 없음"
            files = []
            for root, _, fnames in os.walk(ws):
                for fname in fnames:
                    rel = os.path.relpath(os.path.join(root, fname), ws)
                    files.append(rel)
            return "\n".join(sorted(files)) or "(파일 없음)"

        elif tool_name == "search_memory":
            query = tool_input.get("query", "")
            return rag.search(query) or "관련 과거 프로젝트 없음"

        else:
            return f"[오류] 알 수 없는 도구: {tool_name}"

    except Exception as e:
        return f"[오류] {tool_name} 실행 실패: {e}"
