// ── Example chips ──────────────────────────────────────────────
function setExample(text) {
  const input = document.getElementById('task-input');
  input.value = text;
  input.focus();
}

// ── File attachment ─────────────────────────────────────────────
let currentAttachment = null;

function onFileSelect(input) {
  const file = input.files[0];
  if (!file) return;

  const allowed = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'];
  if (!allowed.includes(file.type)) {
    alert('이미지(JPG, PNG, GIF, WebP) 또는 PDF만 첨부 가능합니다.');
    input.value = '';
    return;
  }

  const reader = new FileReader();
  reader.onload = e => {
    const base64 = e.target.result.split(',')[1];
    currentAttachment = { data: base64, media_type: file.type, name: file.name };
    document.getElementById('attach-name').textContent = file.name;
    document.getElementById('attach-name').classList.remove('hidden');
    document.getElementById('attach-remove').classList.remove('hidden');
  };
  reader.readAsDataURL(file);
}

function clearAttachment() {
  currentAttachment = null;
  document.getElementById('file-input').value = '';
  document.getElementById('attach-name').classList.add('hidden');
  document.getElementById('attach-remove').classList.add('hidden');
}

// ── Positions ──────────────────────────────────────────────────
const DESK_POS = {
  lead:    { x: 40, y: 32 },
  jimin:   { x: 19, y: 42 },
  junhyuk: { x: 58, y: 42 },
  yujin:   { x: 19, y: 54 },
  suyoung: { x: 58, y: 54 },
  mina:    { x: 40, y: 60 },
};


// ── State ──────────────────────────────────────────────────────
let mode = 'team';
let selectedAgent = null;
let chatHistory = [];
let isRunning = false;
let isFollowupMode = false;
let currentTask = '';
let currentWorkspace = '';
let bubbleTimers = {};
const charPos = {};  // 현재 캐릭터 위치 추적

function getCurrentPos(id) { return charPos[id] || DESK_POS[id]; }

// ── Move ───────────────────────────────────────────────────────
function moveCharacter(agentId, pos) {
  return new Promise(resolve => {
    const el = document.getElementById(`char-${agentId}`);
    if (!el) { resolve(); return; }

    const cur = getCurrentPos(agentId);
    if (pos.x > cur.x + 2)      el.classList.add('flip');
    else if (pos.x < cur.x - 2) el.classList.remove('flip');

    charPos[agentId] = pos;
    el.classList.add('walking');
    el.style.left = pos.x + '%';
    el.style.top  = pos.y + '%';

    const done = (e) => {
      if (e.propertyName !== 'left' && e.propertyName !== 'top') return;
      el.classList.remove('walking');
      el.removeEventListener('transitionend', done);
      resolve();
    };
    el.addEventListener('transitionend', done);
    setTimeout(resolve, 1400);
  });
}

// ── Bubble ─────────────────────────────────────────────────────
function showBubble(agentId, text) {
  const bubble = document.getElementById(`bubble-${agentId}`);
  const btext  = document.getElementById(`btext-${agentId}`);
  if (!bubble) return;
  const agent = AGENTS[agentId];
  const flat = text.replace(/\n+/g, ' ').trim();
  btext.textContent = flat.length > 80 ? flat.slice(0, 80) + '…' : flat;
  bubble.style.borderColor = agent.color + '90';
  bubble.classList.add('show');
  clearTimeout(bubbleTimers[agentId]);
  bubbleTimers[agentId] = setTimeout(() => hideBubble(agentId), 9000);
}

function hideBubble(id) {
  document.getElementById(`bubble-${id}`)?.classList.remove('show');
}

// ── State classes ──────────────────────────────────────────────
function setState(id, state) {
  const el    = document.getElementById(`char-${id}`);
  const think = document.getElementById(`think-${id}`);
  if (!el) return;
  el.classList.remove('thinking', 'talking');
  think?.classList.remove('show');
  if (state === 'thinking') { el.classList.add('thinking'); think?.classList.add('show'); hideBubble(id); }
  else if (state === 'talking') { el.classList.add('talking'); }
}

// ── Toast ──────────────────────────────────────────────────────
let toastTimer;
function showToast(text) {
  const t = document.getElementById('decision-toast');
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 4000);
}


// ── Team Task ──────────────────────────────────────────────────
function onSubmit() {
  if (isFollowupMode) startFollowup();
  else startTeamTask();
}

function startTeamTask() {
  if (isRunning) return;
  const taskInput = document.getElementById('task-input');
  const task = taskInput.value.trim();
  if (!task) { taskInput.focus(); return; }

  currentTask = task;
  currentWorkspace = '';
  isRunning = true;
  document.getElementById('start-btn').disabled = true;
  document.getElementById('start-btn').textContent = '협업 중...';
  taskInput.disabled = true;

  clearLog();
  resetPhases();
  Object.keys(AGENTS).forEach(id => {
    setState(id, 'idle');
    hideBubble(id);
    charPos[id] = DESK_POS[id];
    const el = document.getElementById(`char-${id}`);
    if (el) {
      el.classList.remove('flip');
      el.style.left = DESK_POS[id].x + '%';
      el.style.top  = DESK_POS[id].y + '%';
    }
  });

  const body = { task };
  if (currentAttachment) body.attachment = currentAttachment;
  streamTask('/api/team-task', body);
  clearAttachment();
}

function startFollowup() {
  if (isRunning) return;
  const taskInput = document.getElementById('task-input');
  const feedback = taskInput.value.trim();
  if (!feedback) { taskInput.focus(); return; }

  isRunning = true;
  document.getElementById('start-btn').disabled = true;
  document.getElementById('start-btn').textContent = '수정 중...';
  taskInput.disabled = true;

  resetPhases();

  streamTask('/api/team-followup', { task: currentTask, workspace: currentWorkspace, feedback });
}

function resetAll() {
  if (isRunning) return;
  isFollowupMode = false;
  currentTask = '';
  currentWorkspace = '';

  const taskInput = document.getElementById('task-input');
  taskInput.value = '';
  taskInput.placeholder = '태스크를 입력하세요... (예: 구독형 AI 음악 앱 기획)';
  taskInput.disabled = false;

  const btn = document.getElementById('start-btn');
  btn.textContent = '🚀 자율 협업 시작';
  btn.classList.remove('followup');
  btn.disabled = false;

  document.getElementById('reset-btn').classList.add('hidden');

  clearLog();
  resetPhases();
  Object.keys(AGENTS).forEach(id => {
    setState(id, 'idle');
    hideBubble(id);
    charPos[id] = DESK_POS[id];
    const el = document.getElementById(`char-${id}`);
    if (el) {
      el.classList.remove('flip');
      el.style.left = DESK_POS[id].x + '%';
      el.style.top  = DESK_POS[id].y + '%';
    }
  });
}

async function streamTask(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { await handleEvent(JSON.parse(line.slice(6))); } catch {}
      }
    }
  }

  isRunning = false;
  Object.keys(AGENTS).forEach(id => setState(id, 'idle'));
  // done 이벤트에서 모드 전환 처리. 혹시 done 없이 끊기면 버튼만 복구
  const btn = document.getElementById('start-btn');
  if (btn.disabled) {
    btn.disabled = false;
    if (!isFollowupMode) btn.textContent = '🚀 자율 협업 시작';
    document.getElementById('task-input').disabled = false;
  }
}

// ── Event Handler ──────────────────────────────────────────────
async function handleEvent(ev) {
  switch (ev.type) {

    case 'phase':
      activatePhase(ev.phase);
      addLogPhase(ev.label);
      break;

    case 'working':
      // 자리에서 혼자 작업 중
      setState(ev.agent, 'thinking');
      showWorkingBubble(ev.agent);
      break;

    case 'intention':
      // 상대방 책상 쪽으로 먼저 걸어감
      setState(ev.agent, 'idle');
      hideBubble(ev.agent);
      const targetDesk = DESK_POS[ev.target];
      if (targetDesk) {
        // 상대 책상 바로 옆으로 접근
        const approachPos = { x: targetDesk.x + 4, y: targetDesk.y + 2 };
        moveCharacter(ev.agent, approachPos);
        await sleep(400);
        showBubble(ev.agent, `"${AGENTS[ev.target]?.name}야, 잠깐 얘기할 수 있어?"`);
        await sleep(600);
      }
      break;

    case 'lead_thinking':
      setState('lead', 'thinking');
      break;

    case 'lead_decision': {
      setState('lead', 'idle');
      const actionLabel = {
        bilateral:    '1:1 대화',
        small_group:  '소그룹 토론',
        full_meeting: '전체 회의',
        assign:       '작업 할당',
        done:         '협업 완료',
      }[ev.action] || ev.action;
      const names = (ev.participants || []).map(id => AGENTS[id]?.name).filter(Boolean).join(', ');
      const toast = names ? `${actionLabel} → ${names} · ${ev.topic}` : `${actionLabel} · ${ev.topic}`;
      showToast(`💡 팀장 판단: ${toast}`);
      addLogDecision(ev);
      await sleep(300);
      break;
    }

    case 'thinking':
      setState(ev.agent, 'thinking');
      break;

    case 'response':
      setState(ev.agent, 'talking');
      showBubble(ev.agent, ev.content);
      addLogEntry(ev.agent, ev.content, ev.ctx, ev.intention);
      await sleep(500);
      setState(ev.agent, 'idle');
      break;

    case 'consensus':
      setState(ev.agent, 'talking');
      showBubble(ev.agent, `✅ ${ev.content}`);
      addLogConsensus(ev.content);
      await sleep(800);
      setState(ev.agent, 'idle');
      break;

    case 'workflow':
      addLogWorkflowBadge(ev.workflow_type);
      break;

    case 'round':
      activatePhase(ev.round + 1);
      addLogPhase(`Round ${ev.round}: ${ev.label}`);
      break;

    case 'gate': {
      if (ev.passed) donePhase(ev.round + 1);
      addLogGate(ev);
      break;
    }

    // ── Bilateral ──
    case 'round_start':
      addLogRound(ev.round, ev.max);
      break;

    case 'review_start':
      addLogPhase(`🔍 라운드 ${ev.round} 검토`);
      break;

    case 'review': {
      setState(ev.agent, ev.satisfied ? 'talking' : 'thinking');
      showBubble(ev.agent, ev.satisfied ? `✅ ${ev.feedback}` : `🔄 ${ev.feedback}`);
      addLogReview(ev.agent, ev.feedback, ev.satisfied, ev.files_to_fix);
      await sleep(400);
      setState(ev.agent, 'idle');
      break;
    }

    case 'phase_note':
      addLogPhase(ev.msg);
      break;

    case 'evaluation': {
      setState('lead', 'talking');
      const isDone = ev.decision === 'done';
      showBubble('lead', isDone ? `STOP. ${ev.reason}` : `CONTINUE. ${ev.reason}`);
      showToast(isDone ? `🛑 STOP — ${ev.reason}` : `🔄 CONTINUE — ${ev.reason}`);
      addLogEvaluation(ev);
      await sleep(600);
      setState('lead', 'idle');
      break;
    }

    case 'doc_review': {
      const isPass = ev.decision === 'pass';
      setState('lead', isPass ? 'talking' : 'thinking');
      showBubble('lead', isPass ? `✅ 문서 승인. ${ev.feedback}` : `🔄 수정 필요. ${ev.feedback}`);
      showToast(isPass
        ? `✅ 승우: 문서 승인 (${ev.attempt}차)`
        : `🔄 승우: 문서 수정 요청 (${ev.attempt}차) — ${ev.feedback}`);
      addLogDocReview(ev);
      await sleep(600);
      setState('lead', 'idle');
      break;
    }

    case 'bilateral_start':
      activatePhase(2);
      await goToLounge(ev.participants);
      break;

    case 'bilateral_end':
      await returnFromLounge(ev.participants);
      break;

    // ── Assign ──
    case 'assign_start':
      // 자기 자리에서 작업 — 하이라이트만
      document.getElementById(`char-${ev.agent}`)?.classList.add('talking');
      break;

    // ── Meeting ──
    case 'meeting_start':
      activatePhase(2);
      await goToMeeting(ev.participants);
      break;

    case 'meeting_end':
      await returnFromMeeting(ev.participants);
      break;

    // ── Synthesis ──
    case 'workspace_created':
      showToast(`📁 워크스페이스 생성: ${ev.path}`);
      addLogPhase(`📁 ${ev.path}`);
      break;

    case 'error':
      showToast(`❌ ${ev.msg}`);
      addLogPhase(`❌ 에러: ${ev.msg}`);
      break;

    case 'code_structure': {
      const fileList = ev.files.join('\n  ');
      addLogPhase(`📁 코드 구조 확정:\n  ${fileList}`);
      showToast(`📁 ${ev.files.length}개 파일 생성 예정`);
      break;
    }

    case 'writing_doc':
      setState(ev.agent, 'thinking');
      showWorkingBubble(ev.agent);
      addLogPhase(`✍️ ${AGENTS[ev.agent]?.name} → ${ev.doc}`);
      break;

    case 'doc_saved':
      setState(ev.agent, 'talking');
      showBubble(ev.agent, `📄 ${ev.file} 저장됨`);
      addLogDocSaved(ev);
      await sleep(300);
      setState(ev.agent, 'idle');
      break;

    case 'code_running':
      setState('yujin', 'thinking');
      showToast(`🔧 유진: 코드 실행 중... (시도 ${ev.attempt})`);
      break;

    case 'code_result':
      setState('yujin', 'talking');
      showBubble('yujin', ev.success ? `✅ 코드 실행 성공` : `❌ 에러 발생 — 수영한테 전달`);
      addLogCodeResult(ev);
      await sleep(400);
      setState('yujin', 'idle');
      break;

    case 'synthesis':
      setState('lead', 'talking');
      showBubble('lead', ev.content);
      addLogSynthesis(ev.content);
      donePhase(1); donePhase(2); donePhase(3);
      await sleep(600);
      setState('lead', 'idle');
      break;

    case 'done':
      donePhase(4);
      if (ev.workspace) {
        currentWorkspace = ev.workspace;
        showToast(`✅ 완료! 결과물: ${ev.workspace}`);
      }
      // 피드백 모드로 전환
      isFollowupMode = true;
      {
        const taskInput = document.getElementById('task-input');
        taskInput.value = '';
        taskInput.placeholder = '추가 피드백을 입력하세요... (예: 결제 기능 추가해줘, 보안 강화해줘)';
        taskInput.disabled = false;
        const btn = document.getElementById('start-btn');
        btn.textContent = '💬 디벨롭';
        btn.classList.add('followup');
        btn.disabled = false;
        document.getElementById('reset-btn').classList.remove('hidden');
      }
      break;
  }
}

// ── Mode ───────────────────────────────────────────────────────
function setMode(m) {
  mode = m;
  document.getElementById('btn-team').classList.toggle('active', m === 'team');
  document.getElementById('btn-individual').classList.toggle('active', m === 'individual');
  document.getElementById('log-panel').classList.toggle('hidden', m === 'individual');
  document.getElementById('chat-panel').classList.toggle('hidden', m === 'team');
  document.getElementById('input-bar').classList.toggle('hidden', m === 'individual');
  if (m === 'individual' && !selectedAgent) selectAgent(Object.keys(AGENTS)[0]);
}

function onClickChar(id) { if (mode === 'individual') selectAgent(id); }

function selectAgent(id) {
  selectedAgent = id;
  chatHistory = [];
  const agent = AGENTS[id];
  document.querySelectorAll('.chibi').forEach(c => c.style.filter = '');
  document.getElementById(`char-${id}`).style.filter = `drop-shadow(0 0 8px ${agent.color})`;
  document.getElementById('chat-title').innerHTML = `
    <span style="display:flex;align-items:center;gap:7px">
      <span style="width:20px;height:20px;border-radius:50%;background:${agent.color};display:inline-flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;color:white">${agent.initial}</span>
      ${agent.name} <span style="font-weight:400;color:#888;font-size:10px">${agent.role}</span>
    </span>`;
  document.getElementById('chat-history').innerHTML = '';
  document.getElementById('chat-input').focus();
}

// ── Individual chat ────────────────────────────────────────────
async function sendChat() {
  if (!selectedAgent || isRunning) return;
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  appendChatMsg('user', message);
  setState(selectedAgent, 'thinking');
  const agent = AGENTS[selectedAgent];
  try {
    const res = await fetch('/api/individual-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: selectedAgent, message, history: chatHistory }),
    });
    const data = await res.json();
    chatHistory.push({ role: 'user', content: message });
    chatHistory.push({ role: 'assistant', content: data.response });
    setState(selectedAgent, 'talking');
    showBubble(selectedAgent, data.response);
    appendChatMsg('agent', data.response, agent);
    await sleep(300);
    setState(selectedAgent, 'idle');
  } catch {
    setState(selectedAgent, 'idle');
    appendChatMsg('agent', '오류가 발생했습니다.', agent);
  }
}

function appendChatMsg(type, text, agent = null) {
  const history = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = `chat-msg ${type}`;
  if (type === 'agent' && agent) {
    div.innerHTML = `<div class="chat-msg-label" style="color:${agent.color}">${agent.name}</div>${escapeHtml(text)}`;
  } else {
    div.textContent = text;
  }
  history.appendChild(div);
  history.scrollTop = history.scrollHeight;
}

// ── Log ────────────────────────────────────────────────────────
function clearLog() { document.getElementById('log-list').innerHTML = ''; }

function addLogPhase(label) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-phase-header';
  div.textContent = `— ${label}`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogDecision(ev) {
  const list = document.getElementById('log-list');
  const actionLabel = { bilateral:'1:1 대화', small_group:'소그룹', full_meeting:'전체 회의', assign:'작업 할당', done:'완료' }[ev.action] || ev.action;
  const names = (ev.participants||[]).map(id=>AGENTS[id]?.name).filter(Boolean).join(', ');
  const div = document.createElement('div');
  div.className = 'log-decision';
  div.innerHTML = `<span class="log-decision-icon">💡</span> <b>${actionLabel}</b>${names ? ' · '+names : ''}${ev.topic ? ' — '+ev.topic : ''}`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

const WORK_EMOJIS = ['⌨️', '📊', '🔍', '✏️', '📋', '💡'];
let workEmojiIdx = 0;

function showWorkingBubble(agentId) {
  const bubble = document.getElementById(`bubble-${agentId}`);
  const btext  = document.getElementById(`btext-${agentId}`);
  if (!bubble) return;
  const emoji = WORK_EMOJIS[workEmojiIdx++ % WORK_EMOJIS.length];
  btext.textContent = emoji + ' 작업 중...';
  bubble.style.borderColor = '#ccc';
  bubble.classList.add('show');
  clearTimeout(bubbleTimers[agentId]);
  bubbleTimers[agentId] = setTimeout(() => hideBubble(agentId), 3000);
}

function showIntentionBubble(agentId, intention) {
  if (!intention) return;
  const bubble = document.getElementById(`bubble-${agentId}`);
  const btext  = document.getElementById(`btext-${agentId}`);
  if (!bubble) return;
  let text = '';
  if (intention.action === 'want') {
    const target = AGENTS[intention.target];
    text = target ? `💬 ${target.name}한테 얘기하고 싶어` : `💬 이야기하고 싶어`;
  } else if (intention.action === 'meeting') {
    text = `📢 전체 회의 필요해`;
  }
  if (!text) return;
  btext.textContent = text;
  bubble.style.borderColor = '#FFD700';
  bubble.classList.add('show');
  clearTimeout(bubbleTimers[agentId]);
  bubbleTimers[agentId] = setTimeout(() => hideBubble(agentId), 3000);
}

function addLogEntry(agentId, content, ctx = null, intention = null) {
  const agent = AGENTS[agentId];
  const list = document.getElementById('log-list');
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.style.borderLeftColor = agent.color;

  const ctxLabel = ctx === 'work' ? '💻 작업' : ctx === 'bilateral' ? '💬 대화' : ctx === 'debate' ? '🗣 토론' : '';

  let intentHtml = '';
  if (intention && intention.action === 'want') {
    const tname = AGENTS[intention.target]?.name || intention.target;
    intentHtml = `<div class="log-intent"><span class="intent-badge want">→ ${tname}와 얘기하러 감</span></div>`;
  }

  entry.innerHTML = `
    <div class="log-entry-header">
      <div class="log-avatar-mini" style="background:${agent.color}">${agent.initial}</div>
      <span class="log-name">${agent.name}</span>
      <span class="log-role">${agent.role}</span>
      ${ctxLabel ? `<span class="log-ctx">${ctxLabel}</span>` : ''}
    </div>
    <div class="log-content">${escapeHtml(content)}</div>
    ${intentHtml}`;
  list.appendChild(entry);
  list.scrollTop = list.scrollHeight;
}

function addLogRound(round, max) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-round-header';
  div.innerHTML = `<span>라운드 ${round}</span><span class="log-round-max">/ 최대 ${max}</span>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogReview(agentId, feedback, satisfied, filesToFix) {
  const agent = AGENTS[agentId];
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-review';
  const fixHtml = (filesToFix && filesToFix.length)
    ? `<div class="log-review-files">🔧 수정 대상: ${filesToFix.map(f => `<code>${f}</code>`).join(', ')}</div>`
    : '';
  div.innerHTML = `
    <span class="log-review-icon">${satisfied ? '✅' : '🔄'}</span>
    <span class="log-review-name" style="color:${agent.color}">${agent.name}</span>
    <span class="log-review-text">${escapeHtml(feedback)}</span>
    ${fixHtml}`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogEvaluation(ev) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = `log-evaluation ${ev.decision}`;
  const bar = Math.round((ev.satisfied_count / ev.total) * 100);
  div.innerHTML = `
    <div class="eval-header">
      <span>${ev.decision === 'done' ? '🛑 STOP' : '🔄 CONTINUE'}</span>
      <span class="eval-score">${ev.satisfied_count}/${ev.total}</span>
    </div>
    <div class="eval-bar"><div class="eval-bar-fill" style="width:${bar}%"></div></div>
    <div class="eval-reason">${escapeHtml(ev.reason)}</div>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogConsensus(content) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-consensus';
  div.innerHTML = `
    <div class="log-consensus-header">✅ 팀 합의</div>
    <div class="log-consensus-body">${escapeHtml(content)}</div>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogWorkflowBadge(type) {
  const labels = { build:'🔨 개발', feedback:'💬 피드백', review:'🔍 리뷰', discuss:'🗣 토론', plan:'📋 기획' };
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-workflow-badge';
  div.innerHTML = `<span class="log-workflow-label">${labels[type] || type}</span> 워크플로우`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogGate(ev) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = `log-gate ${ev.passed ? 'passed' : 'blocked'}`;
  const reasonsHtml = (ev.block_reasons && ev.block_reasons.length)
    ? `<div class="log-gate-reasons">${ev.block_reasons.map(r => `<div>⛔ ${escapeHtml(r)}</div>`).join('')}</div>`
    : '';
  div.innerHTML = `
    <div class="log-gate-header">
      <span>${ev.passed ? '✅ PASS' : '🔄 BLOCK'}</span>
      <span class="log-gate-summary">${escapeHtml(ev.summary)}</span>
      ${ev.attempt ? `<span class="log-gate-attempt">${ev.attempt}차</span>` : ''}
    </div>
    ${reasonsHtml}`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogSynthesis(content) {
  const list = document.getElementById('log-list');
  const entry = document.createElement('div');
  entry.className = 'log-synthesis';
  entry.innerHTML = `<div class="log-phase-header">✅ 최종 결론</div><div class="log-content" style="margin-top:7px">${escapeHtml(content)}</div>`;
  list.appendChild(entry);
  list.scrollTop = list.scrollHeight;
}

// ── Phase bar ──────────────────────────────────────────────────
function resetPhases() {
  [1,2,3].forEach(n => document.getElementById(`phase-${n}`).classList.remove('active','done'));
  document.querySelectorAll('.phase-line').forEach(l => l.classList.remove('done'));
}
function activatePhase(n) {
  document.getElementById(`phase-${n}`).classList.add('active');
  document.getElementById(`phase-${n}`).classList.remove('done');
}
function donePhase(n) {
  const el = document.getElementById(`phase-${n}`);
  el.classList.remove('active'); el.classList.add('done');
  document.querySelectorAll('.phase-line')[n-1]?.classList.add('done');
}

function addLogDocReview(ev) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = `log-doc-review ${ev.decision}`;
  div.innerHTML = `
    <span class="log-doc-review-icon">${ev.decision === 'pass' ? '✅' : '🔄'}</span>
    <span class="log-doc-review-label">${ev.decision === 'pass' ? '문서 승인' : '문서 수정 요청'}</span>
    <span class="log-doc-review-attempt">${ev.attempt}차</span>
    <div class="log-doc-review-feedback">${escapeHtml(ev.feedback)}</div>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogDocSaved(ev) {
  const agent = AGENTS[ev.agent];
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = 'log-doc-saved';
  div.innerHTML = `
    <span class="log-doc-icon">📄</span>
    <span class="log-doc-name">${ev.file}</span>
    <span class="log-doc-author" style="color:${agent?.color}">${agent?.name}</span>`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

function addLogCodeResult(ev) {
  const list = document.getElementById('log-list');
  const div = document.createElement('div');
  div.className = `log-code-result ${ev.success ? 'success' : 'fail'}`;
  div.innerHTML = `
    <div class="code-result-header">
      <span>${ev.success ? '✅ 테스트 통과' : '❌ 테스트 실패'} (시도 ${ev.attempt})</span>
    </div>
    ${ev.stderr ? `<pre class="code-result-pre">${escapeHtml(ev.stderr.slice(0,200))}</pre>` : ''}
    ${ev.stdout ? `<pre class="code-result-pre">${escapeHtml(ev.stdout.slice(0,200))}</pre>` : ''}`;
  list.appendChild(div);
  list.scrollTop = list.scrollHeight;
}

// ── Utils ──────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/\n/g,'<br>');
}
