from supabase import create_client, Client
from datetime import datetime, timezone
import os

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY 환경변수 없음")
        _client = create_client(url, key)
    return _client


def create_session(task: str, workflow_type: str = "") -> str:
    result = get_client().table("sessions").insert({
        "task": task,
        "workflow_type": workflow_type,
    }).execute()
    return result.data[0]["id"]


def save_message(session_id: str, agent_id: str, agent_name: str,
                 agent_role: str, content: str, msg_type: str,
                 participants: list[str] | None = None):
    get_client().table("messages").insert({
        "session_id":  session_id,
        "agent_id":    agent_id,
        "agent_name":  agent_name,
        "agent_role":  agent_role,
        "content":     content,
        "msg_type":    msg_type,
        "participants": participants or [],
    }).execute()


def complete_session(session_id: str, summary: str):
    get_client().table("sessions").update({
        "final_summary": summary,
        "completed_at":  datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()


def get_sessions(limit: int = 20) -> list[dict]:
    result = (get_client().table("sessions")
              .select("id, task, workflow_type, created_at, completed_at")
              .order("created_at", desc=True)
              .limit(limit)
              .execute())
    return result.data


def get_messages(session_id: str) -> list[dict]:
    result = (get_client().table("messages")
              .select("*")
              .eq("session_id", session_id)
              .order("created_at")
              .execute())
    return result.data
