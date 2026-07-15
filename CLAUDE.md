# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DeepAgents is an AI-powered resume assistant built with **LangGraph + Vue3 + FastAPI**. It enables users to optimize their resumes through conversational AI, supports job description (JD) matching analysis, and exports resumes to PDF.

## Common Commands

### Frontend (Vue3)
```bash
cd frontend
npm install           # Install dependencies
npm run dev           # Start dev server (http://localhost:5173)
npm run build         # Build for production
npm run preview       # Preview production build
```

### Backend (FastAPI)
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend
python mcp_service_simple.py

# Or use the startup script
./start_backend.sh
```

### Docker Deployment
```bash
docker-compose up -d --build
```

### Database
```bash
# Create admin user (default: admin@qq.com / admin123)
python create_admin.py
```

### Database Query (Docker)

容器内无 sqlite3 命令，可用 Python 查询：

```bash
# 查看所有用户
docker exec -it deepagents-backend python -c "import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT id, email, invite_code, created_at FROM users'); print(cursor.fetchall()); conn.close()"
```

> **项目统计（截至2026-03-05）：**
> - 用户总数：162个
> - 测试用户：19个
> - 查询用户名的指令：
> ```python
> import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT user_id, resume_data FROM resumes'); import json; rows = [(r[0], json.loads(r[1]).get('basics',{}).get('name','N/A')) for r in cursor.fetchall()]; print('\n'.join([f"简历ID: {r[0]}, 用户名: {r[1]}" for r in rows])); conn.close()
> ```

```bash
# 查看所有用户
docker exec -it deepagents-backend python -c "import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT id, email, invite_code, created_at FROM users'); print(cursor.fetchall()); conn.close()"

# 查看简历表
docker exec -it deepagents-backend python -c "import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT id, user_id, name, parsing_status FROM resumes'); print(cursor.fetchall()); conn.close()"

# 查看对话表
docker exec -it deepagents-backend python -c "import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT id, user_id, session_id, created_at FROM conversations'); print(cursor.fetchall()); conn.close()"

# 查看JD表
docker exec -it deepagents-backend python -c "import sqlite3; conn = sqlite3.connect('/app/data/deepagents.db'); cursor = conn.cursor(); cursor.execute('SELECT id, user_id, company, position FROM job_descriptions'); print(cursor.fetchall()); conn.close()"

# 拷贝数据库到本地查看
docker cp deepagents-backend:/app/data/deepagents.db ./deepagents.db
sqlite3 ./deepagents.db "SELECT * FROM users;"
```

### macOS (WeasyPrint dependency)
```bash
brew install pango harfbuzz cairo fontconfig
```

## Architecture

### Tech Stack
- **Frontend**: Vue 3.5+, Vite 7.x, Element Plus, Vue Router, marked
- **Backend**: FastAPI, Uvicorn, SQLAlchemy, LangGraph, LangChain
- **Database**: SQLite (data/deepagents.db)
- **PDF**: WeasyPrint (server-side), html2pdf.js (client-side backup)
- **AI**: LangGraph with dual-LLM design (conversation + formatter)

### Key Files
| File | Purpose |
|------|---------|
| `mcp_service_simple.py` | FastAPI entry point, all API endpoints |
| `resume_agent.py` | LangGraph StateGraph for AI conversation |
| `database.py` | SQLAlchemy models (User, Resume, JD, Conversation) |
| `auth.py` | JWT authentication |
| `pdf_generator.py` | WeasyPrint PDF generation |
| `tools.py` | Utility functions |

### LangGraph Workflow
The AI agent uses a StateGraph with three main nodes:
1. **conversation_llm** - Handles user dialogue, calls tools (temperature=0.1)
2. **formatter_llm** - Generates formatted JSON for resume updates (temperature=0.0)
3. **tool_node** - Executes read/write tools on resume.json

State flows through `messages` (conversation history) and `resume_data` (current resume). Uses `MemorySaver` for state persistence via `thread_id`.

### Data Models
- **User**: Authentication, multi-user isolation
- **Resume**: Structured JSON (basics, education, work experience, projects, skills)
- **JobDescription**: JD parsing and storage
- **Conversation**: Chat history with context compression

### API Endpoints
- `/auth/*` - Login, register, invite codes
- `/chat` - SSE streaming conversation
- `/confirm` - Handle user confirmations
- `/load_resume`, `/save_resume` - Resume CRUD
- `/load_jd`, `/save_jd`, `/parse_jd` - JD management
- `/export_pdf` - PDF generation

## Environment Variables
```
JWT_SECRET_KEY=<required>
LLM_API_KEY=<required>
BASE_URL=https://api.bltcy.ai/v1 (or similar LLM endpoint)
TAVILY_API_KEY=<optional>
DOMAIN=<your-domain>
```

## Development Notes

- Default LLM model is `gemini-3-flash-preview` via compatible API
- User data is stored per-thread in MemorySaver (in-memory, not persisted to DB)
- Resume files are stored as JSON per-user in `data/` directory
- Frontend proxies API requests to localhost:8000 via Vite config
