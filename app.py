# Flask 진입점 — HTTP 라우트 정의 (팀 태스크, 팔로업, 1:1 채팅, 히스토리 API)

import os

from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from dotenv import load_dotenv

import db
from agents import AGENTS
from utils import client, MODEL
from runner import run_autonomous_task, run_followup_task

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB — 첨부 파일 DoS 방지

_WORKSPACE_ROOT = os.path.abspath("workspace")  # 허용된 workspace 루트
_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}
_MAX_ATTACHMENT_B64 = 15 * 1024 * 1024   # base64 15MB ≈ 원본 11MB
_MAX_TASK_LEN = 2000
_MAX_HISTORY = 40  # 최대 대화 턴 수


@app.route("/")
def index():
    return render_template("index.html", agents=AGENTS)


@app.route("/api/team-task", methods=["POST"])
def team_task():
    data = request.json
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "task required"}), 400
    if len(task) > _MAX_TASK_LEN:
        return jsonify({"error": f"task가 너무 깁니다 (최대 {_MAX_TASK_LEN}자)"}), 400
    attachment = data.get("attachment")  # {data: base64, media_type: "image/jpeg"|"application/pdf", name: "..."}
    if attachment:
        if attachment.get("media_type") not in _ALLOWED_MEDIA_TYPES:
            return jsonify({"error": "허용되지 않는 파일 형식입니다"}), 400
        if len(attachment.get("data", "")) > _MAX_ATTACHMENT_B64:
            return jsonify({"error": "첨부 파일이 너무 큽니다 (최대 15MB)"}), 400
    return Response(
        stream_with_context(run_autonomous_task(task, attachment)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/team-followup", methods=["POST"])
def team_followup():
    data = request.json
    task = data.get("task", "").strip()
    workspace = data.get("workspace", "").strip()
    feedback = data.get("feedback", "").strip()
    if not task or not feedback:
        return jsonify({"error": "task and feedback required"}), 400
    if len(task) > _MAX_TASK_LEN or len(feedback) > _MAX_TASK_LEN:
        return jsonify({"error": "입력이 너무 깁니다"}), 400
    # Path traversal 방어: workspace가 허용된 루트 하위인지 확인
    if workspace:
        abs_ws = os.path.abspath(workspace)
        if not (abs_ws.startswith(_WORKSPACE_ROOT + os.sep) or abs_ws == _WORKSPACE_ROOT):
            return jsonify({"error": "유효하지 않은 workspace 경로입니다"}), 400
    return Response(
        stream_with_context(run_followup_task(task, workspace, feedback)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_VALID_ROLES = {"user", "assistant"}


@app.route("/api/individual-chat", methods=["POST"])
def individual_chat():
    data = request.json
    agent_id = data.get("agent_id")
    message = data.get("message", "").strip()
    history = data.get("history", [])
    if agent_id not in AGENTS or not message:
        return jsonify({"error": "invalid request"}), 400
    if len(message) > _MAX_TASK_LEN:
        return jsonify({"error": "message가 너무 깁니다"}), 400
    # history 검증: role·content 타입 및 길이 제한 (Prompt Injection 방어)
    if not isinstance(history, list) or len(history) > _MAX_HISTORY:
        return jsonify({"error": "유효하지 않은 history입니다"}), 400
    sanitized = []
    for item in history:
        if (not isinstance(item, dict)
                or item.get("role") not in _VALID_ROLES
                or not isinstance(item.get("content", ""), str)):
            return jsonify({"error": "유효하지 않은 history 형식입니다"}), 400
        sanitized.append({"role": item["role"], "content": item["content"][:2000]})
    messages = sanitized + [{"role": "user", "content": message}]
    resp = client.messages.create(
        model=MODEL, max_tokens=512,
        system=AGENTS[agent_id]["system"],
        messages=messages,
    )
    return jsonify({"response": resp.content[0].text, "agent": agent_id})


@app.route("/api/history")
def history():
    try:
        return jsonify(db.get_sessions())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<session_id>")
def session_detail(session_id):
    try:
        return jsonify(db.get_messages(session_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    debug = os.getenv("FLASK_ENV", "production") == "development"
    app.run(debug=debug, port=5001, threaded=True)
