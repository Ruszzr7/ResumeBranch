# ResumeBranch

**English** | [简体中文](README.zh-CN.md)

ResumeBranch is an open-source AI resume assistant for maintaining resumes and preparing job applications. It uses a structured resume as its core data model and provides import, editing, version management, layout controls, PDF/DOCX export, job-description analysis, and conversational optimization. It supports both a local profile for personal computers and a self-hosted multi-user profile.

The current version is **Release 1**. The feature set and architecture are frozen; this document describes the code, configuration, and launch scripts in the repository.

## Main capabilities

- Manage a base resume and job-specific versions, including creation, duplication, import, switching, and undo.
- Edit structured sections such as personal information, education, work experience, projects, skills, publications, and certificates.
- Adjust templates, font sizes, spacing, margins, section order, and content styles while keeping the browser preview, PDF, and editable DOCX as consistent as possible.
- Import PDF or image resumes through the parsing API, map them into the project template, and retain the original files for reference.
- Maintain job descriptions with text or image parsing, structured editing, and targeted analysis.
- Let the intelligent Agent decide whether to answer, ask follow-up questions, read a layout snapshot, or generate a modification preview.
- Use a preview-confirm-save flow for AI changes; stale changes are rejected when the resume has changed, with concurrency protection for multiple windows.
- Save local exports to `output/resumes/`; the multi-user profile downloads files through the browser instead of accumulating them on the server.

## Two runtime profiles

Both profiles share the same Vue frontend, FastAPI backend, and business code. The entry point is selected by startup configuration; the application does not switch profiles dynamically inside the page.

| Item | Local profile | Multi-user profile |
|---|---|---|
| Use case | Personal computer and local resume maintenance | Self-hosting on a LAN or server |
| Authentication | No registration or login | Invite-code registration and email login |
| Database | SQLite file | MySQL |
| Bind address | Loopback only | Configurable for the deployment |
| API settings | Available to the local user | Available to administrators only |
| Export | Saved to project `output/resumes/` | Browser download |
| Entry point | `scripts\start_local.cmd` | Native Windows MySQL or Docker Compose |

SQLite does not require a separate service. Shutting down the application or restarting the computer does not delete `data/resumebranch.db`; the local data remains as long as the `data/` directory is kept. SQLite and MySQL are independent data sources, and the project does not migrate data between them automatically.

## Technical architecture

- Frontend: Vue 3, Vite, Element Plus, and Vue Router.
- Backend: Python 3.11, FastAPI, SQLAlchemy, and Uvicorn/Gunicorn.
- Agent: LangGraph handles graph state and routing; LangChain Core and an OpenAI-compatible client provide message, model, and tool abstractions.
- Data: the local profile uses SQLite, while the multi-user profile uses MySQL; workflow checkpoints are stored separately in a SQLite file.
- Export and rendering: Chromium generates PDFs, `python-docx` generates editable DOCX files, and Poppler generates PDF page snapshots that can be consumed by the AI.
- Communication: regular endpoints use HTTP, while AI responses are streamed over SSE.
- Deployment: Windows launch scripts; the multi-user profile includes Docker Compose, MySQL, Gunicorn, and Nginx configuration.

Reproducible dependency versions are defined by [`backend/requirements.lock.txt`](backend/requirements.lock.txt) and [`frontend/package-lock.json`](frontend/package-lock.json). Patch versions are not duplicated in this README because they become outdated easily.

## Quick start: Windows local profile

### 1. Requirements

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Chrome, Edge, or Chromium (required for PDF export)

### 2. Configure and install

~~~powershell
Copy-Item .env.example .env

python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r backend\requirements.lock.txt

Set-Location frontend
npm ci
Set-Location ..
~~~

For AI chat and resume parsing, configure an OpenAI-compatible API in `.env`, or fill it in through **API settings** in the upper-right corner after startup. Local editing, version management, and export do not require an LLM key.

Do not commit `.env`, `.env.multi_user`, `.env.docker`, or any real credentials.

### 3. Start and stop

~~~powershell
.\scripts\start_local.cmd
~~~

Open <http://127.0.0.1:5173>. The script starts or restarts the backend, starts the shared frontend, and runs health checks. The Vite development server supports hot reload.

~~~powershell
# Stop the frontend and backend without deleting data
.\scripts\stop_app.cmd
~~~

See [Windows local deployment](docs/local-deployment.md) for the complete procedure, backup guidance, and health checks.

## Multi-user profile

### Native MySQL on Windows

Use this profile on a Windows computer without Docker to test login, invite codes, administrator permissions, and user-data isolation:

~~~powershell
Copy-Item .env.multi_user.example .env.multi_user
# Configure the MySQL database and application account, then:
.\scripts\start_multi_user.cmd
~~~

The launcher checks and starts the MySQL service, verifies the database connection, starts or restarts the backend, and reuses the same Vite frontend. Ordinary users must register and sign in with an email address; administrators may use an email address or a dedicated non-email account name. Each account has only one valid login session at a time; a new login invalidates the previous session.

See [Windows native multi-user deployment](docs/multi-user-local.md) for detailed configuration.

### Docker Compose

Use this profile on a Linux server or another environment that supports Docker. Docker is not required to run the project on this computer.

~~~bash
cp .env.docker.example .env.docker
# Replace the JWT, administrator, and MySQL passwords:
docker compose --env-file .env.docker -f docker-compose.multi-user.yml config
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build
~~~

The default address is <http://127.0.0.1:8080>. See [Docker multi-user self-hosting](docs/deployment.md) for the topology, security boundaries, backups, and acceptance checks.

## Launch scripts

| Script | Purpose |
|---|---|
| `scripts/start_local.cmd` | Start the local SQLite backend and shared frontend |
| `scripts/start_multi_user.cmd` | Start native MySQL, the multi-user backend, and the shared frontend |
| `scripts/start_backend_local.cmd` | Start or restart the local backend |
| `scripts/start_backend_multi_user.cmd` | Start or restart the multi-user backend |
| `scripts/start_frontend.cmd` | Start the shared Vite frontend |
| `scripts/start_mysql.cmd` | Start the Windows MySQL service only |
| `scripts/stop_mysql.cmd` | Stop the Windows MySQL service only |
| `scripts/stop_app.cmd` | Stop the frontend and backend while preserving SQLite/MySQL data and the MySQL service |

Runtime logs are written to `.local-run/`, which is ignored by Git.

## Agent and modification safety

ResumeBranch does not hard-code every request as a fixed workflow. The entry router combines the current conversation mode and request type to choose a path:

- General questions and complex resume tasks are given to the Agent, which decides whether to answer, ask questions, or call a skill.
- Explicit, safely parseable requests for fields, font sizes, layout, or local bold formatting use the deterministic direct-edit path.
- Interview diagnosis, deep discovery, and JD review enter the corresponding job-coaching nodes.
- When visual layout information is needed, the system renders resume page snapshots using the same source as the official PDF.
- When a resume change is needed, the system generates a structured candidate, shows a preview, and persists it only after confirmation.

Resume content, layout rules, the JD, conversation summaries, and necessary memory are assembled on demand by the context layer. Workflow checkpoints store control state only; business data remains governed by the SQLAlchemy database.

When a change is confirmed, the resume revision and content digest are checked. If another window changes the resume while confirmation is pending, the stale suggestion is rejected and the frontend reloads the canonical version from the database. Database locks serialize changes across conversation windows, browser tabs, and backend processes; consultation-only conversations are unaffected.

See [Agent architecture and state boundaries](docs/agent-architecture.md) for the current implementation details.

## Data and privacy

Main persistent data in the local profile:

~~~text
data/resumebranch.db                  # Resume, JD, conversation, and business state
data/source_documents/                # Original imported resume files
data/langgraph_checkpoints.sqlite     # Agent control-state checkpoints
data/llm_profiles.json                # Local API settings, if configured in the UI
output/resumes/                       # Locally exported PDF/DOCX files
~~~

Stop the backend before backing up the entire `data/` directory instead of copying only the database file while SQLite is running. Multi-user Docker data is stored in named volumes; see the deployment documentation for backup instructions.

The project does not require resumes to be uploaded to an official ResumeBranch server. If you enable a third-party LLM or parsing API, review that provider's data-processing and privacy policies.

## API and runtime checks

After the backend starts, check its status with:

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
~~~

FastAPI generates the complete development API contract:

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

The main endpoint groups cover runtime configuration, authentication and invite codes, resumes and versions, JDs, conversations, imports, PDF/DOCX export, AI settings, and confirmation saves. `POST /chat` streams events over SSE. Authentication endpoints are available only in the multi-user profile; the local open-export-directory endpoint is available only in the local profile.

## Tests

~~~powershell
# Backend: explicitly use test SQLite instead of inheriting MySQL from .env
$env:APP_MODE = "local"
$env:LOCAL_USER_EMAIL = "local@localhost"
$env:DATABASE_URL = "sqlite:///./.local-run/test-suite.db"
$env:AGENT_CHECKPOINTER_ENABLED = "true"
$env:AGENT_CHECKPOINT_DB_PATH = ".local-run/test-checkpoints.sqlite"
.\.venv-win\Scripts\python.exe -m unittest discover -s tests

# Frontend
Set-Location frontend
npm test
npm run build
~~~

These commands force the regular tests to use SQLite under `.local-run/`. They do not run real MySQL integration tests or call a real LLM by default. Prerequisites for MySQL integration tests, real-LLM smoke tests, Docker acceptance, environment cleanup, and manual regression are listed in [Testing and acceptance](docs/testing.md). GitHub Actions runs the core backend tests, frontend tests, and production build on pushes and pull requests, and separately validates the multi-user Docker profile.

## Project structure

~~~text
ResumeBranch/
├── backend/                       # FastAPI, Agent, data models, import and export
│   ├── harness/                   # Context, memory, workflow state, and observability
│   ├── skills/                    # Resume modification and PDF snapshot skills
│   ├── Dockerfile
│   ├── main.py
│   ├── resume_agent.py
│   ├── requirements.txt           # Dependency declarations
│   └── requirements.lock.txt      # Locked dependencies
├── frontend/                      # Vue SPA and Nginx container configuration
├── scripts/                       # Windows startup, shutdown, health, and smoke scripts
├── tests/                         # Backend automated tests
├── docs/                          # Deployment, architecture, testing, and reference docs
├── data/                          # Local runtime data (not committed by default)
├── output/resumes/                # Local exports (not committed by default)
├── docker-compose.multi-user.yml  # Multi-user Compose definition
├── .env*.example                  # Configuration templates
├── README.md                      # English default README
└── README.zh-CN.md                # Simplified Chinese README
~~~

## Documentation

- [Documentation index](docs/README.md)
- [Windows local deployment](docs/local-deployment.md)
- [Windows native multi-user deployment](docs/multi-user-local.md)
- [Docker multi-user self-hosting](docs/deployment.md)
- [Testing and acceptance](docs/testing.md)
- [Agent architecture and state boundaries](docs/agent-architecture.md)

## License

This project is released under the [MIT License](LICENSE).
