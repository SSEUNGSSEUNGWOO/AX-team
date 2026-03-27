# RAG — 과거 워크스페이스 벡터화 및 유사 프로젝트 검색 (chromadb 로컬 저장)

import os
import threading
import chromadb

_collection = None
_lock = threading.Lock()


def _get_collection():
    global _collection
    if _collection is None:
        with _lock:
            if _collection is None:  # double-checked locking
                client = chromadb.PersistentClient(path="./rag_store")
                _collection = client.get_or_create_collection(
                    name="workspaces",
                    metadata={"hnsw:space": "cosine"},
                )
    return _collection


def index_workspace(workspace: str, task: str, workflow_type: str = "") -> None:
    """태스크 완료 후 결과물을 벡터 DB에 저장."""
    col = _get_collection()
    docs, ids, metas = [], [], []

    def _add(doc_id: str, content: str, doc_type: str):
        trimmed = content.strip()[:2000]
        if trimmed:
            docs.append(trimmed)
            ids.append(doc_id)
            metas.append({
                "workspace": workspace,
                "task": task,
                "workflow": workflow_type,
                "type": doc_type,
            })

    # 최종 결론
    for fname in ("00_결론.md", "00_리뷰결론.md", "00_팀장결론.md"):
        fpath = os.path.join(workspace, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                _add(f"{workspace}::{fname}", f.read(), "conclusion")
            break

    # 기획 문서
    docs_dir = os.path.join(workspace, "docs")
    if os.path.isdir(docs_dir):
        for fname in sorted(os.listdir(docs_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(docs_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    _add(f"{workspace}::{fname}", f.read(), "doc")
            except Exception:
                pass

    if docs:
        col.upsert(documents=docs, ids=ids, metadatas=metas)


def search(query: str, n: int = 2) -> str:
    """유사한 과거 프로젝트 검색 → 프롬프트 주입용 문자열 반환. 결과 없으면 빈 문자열."""
    try:
        col = _get_collection()
        total = col.count()
        if total == 0:
            return ""

        results = col.query(query_texts=[query], n_results=min(n, total))
        docs_list = results["documents"][0]
        metas_list = results["metadatas"][0]

        if not docs_list:
            return ""

        lines = ["【과거 유사 프로젝트 참고 — 아래 사례를 현재 태스크에 활용하세요】"]
        seen: set[str] = set()
        for doc, meta in zip(docs_list, metas_list):
            task_name = meta.get("task", "")
            if task_name not in seen:
                seen.add(task_name)
                wf = meta.get("workflow", "")
                lines.append(f"\n태스크: {task_name}" + (f" ({wf})" if wf else ""))
            lines.append(doc[:500])

        return "\n".join(lines)
    except Exception as e:
        print(f"[RAG] 검색 실패: {e}")
        return ""
