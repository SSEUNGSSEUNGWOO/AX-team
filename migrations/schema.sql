-- AX Team Office - Supabase Schema
-- Supabase 대시보드 > SQL Editor에서 실행하세요

CREATE TABLE IF NOT EXISTS sessions (
  id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  task          TEXT        NOT NULL,
  workflow_type TEXT,                    -- build | plan | feedback | discuss | review
  final_summary TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  completed_at  TIMESTAMPTZ
);

-- 기존 테이블에 컬럼 추가 (이미 생성된 경우)
-- ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workflow_type TEXT;

CREATE TABLE IF NOT EXISTS messages (
  id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  session_id   UUID        REFERENCES sessions(id) ON DELETE CASCADE,
  agent_id     TEXT        NOT NULL,
  agent_name   TEXT        NOT NULL,
  agent_role   TEXT,
  content      TEXT        NOT NULL,
  msg_type     TEXT        NOT NULL, -- kickoff | bilateral | assign | meeting | synthesis
  participants TEXT[],               -- 참여자 agent_id 목록
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 개발용: RLS 비활성화 (배포 시 정책 추가 권장)
ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
