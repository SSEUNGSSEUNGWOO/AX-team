# 워크스페이스 유틸 — 작업 폴더 생성, 파일 저장, LLM 응답에서 코드 추출/잘림 감지

import os, re, py_compile


def slugify_task(task: str) -> str:
    slug = task.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:40] or "project"


def create_workspace(task: str, workflow_type: str = "") -> str:
    try:
        slug = slugify_task(task)
    except Exception:
        slug = re.sub(r'[^a-z0-9]', '-', task.lower())[:30].strip('-') or "project"

    ws_root = "workspace"
    next_num = 1
    if os.path.isdir(ws_root):
        for name in os.listdir(ws_root):
            m = re.match(r'^(\d+)-', name)
            if m:
                next_num = max(next_num, int(m.group(1)) + 1)

    prefix = f"{next_num:02d}"
    type_tag = f"{workflow_type}-" if workflow_type else ""
    folder = os.path.join(ws_root, f"{prefix}-{type_tag}{slug}")
    os.makedirs(os.path.join(folder, "docs"), exist_ok=True)
    os.makedirs(os.path.join(folder, "code"), exist_ok=True)
    return folder


def write_workspace(folder: str, filename: str, content: str) -> str:
    abs_folder = os.path.abspath(folder)
    path = os.path.abspath(os.path.join(abs_folder, filename))
    if not path.startswith(abs_folder + os.sep):
        raise ValueError(f"경로 이탈 차단: {filename!r}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path



def extract_code(text: str) -> str:
    # 완전한 블록: 여는 ``` + 닫는 ``` 모두 있는 경우
    blocks = re.findall(r'```(?:[a-zA-Z]*)?\n?(.*?)```', text, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip()

    # 잘린 블록: 여는 ```만 있고 닫는 ``` 없는 경우 (LLM 출력 중단)
    partial = re.search(r'```(?:[a-zA-Z]*)?\n?(.*)', text, re.DOTALL)
    if partial:
        return partial.group(1).strip()

    PROSE_PATTERNS = (
        r'^\s*#\s*code/',
        r'^\s*[>\-\*]',
        r'^\s*\*\*',
        r'^\s*---',
        r'^[가-힣]',
        r'^\s*$',
    )
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if any(re.match(p, line) for p in PROSE_PATTERNS):
            continue
        return '\n'.join(lines[i:]).strip()

    return text.strip()


def is_truncated(code: str) -> bool:
    stripped = code.rstrip()
    if not stripped:
        return True
    last_line = stripped.split('\n')[-1].rstrip()

    # 마지막 줄이 미완성 표현으로 끝남
    if last_line.endswith(('(', ',', '\\', ':', '+', '=', '_')):
        return True
    # 마지막 줄이 식별자/키워드 중간에 끊김 (영문자·숫자로 끝나지만 완결 구문 아님)
    if re.search(r'(return|import|from|if|while|for|=)\s+[\w\.]+$', last_line):
        return True

    # 중괄호·괄호 불균형 → 블록이 열린 채로 잘림
    if stripped.count('{') != stripped.count('}'):
        return True
    if stripped.count('(') != stripped.count(')'):
        return True

    if last_line.count('"""') % 2 != 0 or last_line.count("'''") % 2 != 0:
        return True
    if re.search(r'def \w+\([^)]*\)\s*:\s*$', last_line):
        return True
    return False


def check_syntax(workspace: str) -> list[dict]:
    """워크스페이스 내 Python 파일 문법 검사. 에러 목록 반환."""
    errors = []
    for root, _, files in os.walk(workspace):
        for fname in sorted(files):
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, workspace)
            try:
                py_compile.compile(fpath, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append({"file": rel, "error": str(e)})
    return errors
