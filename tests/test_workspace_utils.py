import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workspace_utils import slugify_task, extract_code, is_truncated


# ── slugify_task ──────────────────────────────────────────────────────────────

def test_slugify_korean_becomes_project():
    # 한글은 [^a-z0-9]에 걸려 제거되므로 빈 slug → "project" 반환
    assert slugify_task("할 일 앱 만들기") == "project"

def test_slugify_english():
    assert slugify_task("Build a Todo App") == "build-a-todo-app"

def test_slugify_special_chars():
    result = slugify_task("Hello, World! (2024)")
    assert result == "hello-world-2024"

def test_slugify_empty():
    assert slugify_task("") == "project"

def test_slugify_truncates_at_40():
    long_task = "a" * 100
    assert len(slugify_task(long_task)) <= 40


# ── extract_code ──────────────────────────────────────────────────────────────

def test_extract_code_with_fence():
    text = "설명\n```python\nprint('hello')\n```\n끝"
    assert extract_code(text) == "print('hello')"

def test_extract_code_picks_longest_block():
    text = "```\nshort\n```\n\n```python\nlong_code_here\nmore_lines\n```"
    result = extract_code(text)
    assert "long_code_here" in result

def test_extract_code_no_fence_returns_text():
    text = "def hello():\n    return 1"
    assert "def hello" in extract_code(text)


# ── is_truncated ──────────────────────────────────────────────────────────────

def test_is_truncated_empty():
    assert is_truncated("") is True

def test_is_truncated_ends_with_colon():
    assert is_truncated("def foo():") is True

def test_is_truncated_complete_function():
    code = "def hello():\n    return 1"
    assert is_truncated(code) is False

def test_is_truncated_ends_with_comma():
    assert is_truncated("x = foo(a,") is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
