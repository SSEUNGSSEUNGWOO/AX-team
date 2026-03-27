# SpotMind

## 실행 방법

### 사전 요구사항
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 7+

### 환경 변수 설정
cp .env.example .env

### 백엔드 실행
cd code
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

### 프론트엔드 실행
cd static
npm install
npm run dev

### DB 마이그레이션
alembic upgrade head

### 접속
http://localhost:3000