# ResumeBranch

**English** | [简体中文](README.md)

ResumeBranch is an open-source AI resume assistant for maintaining resumes and preparing job applications. It uses a structured resume as its core data model and provides import, editing, version management, layout controls, PDF/DOCX export, job-description analysis, and conversational optimization. It is distributed through three paths: source development/testing, multi-user Docker deployment, and a Windows single-user installation package.

## Main capabilities

- Manage a base resume and job-specific versions, including creation, duplication, import, switching, and undo.
- Edit structured sections such as personal information, education, work experience, projects, skills, publications, and certificates.
- Adjust templates, font sizes, spacing, margins, section order, and content styles while keeping the browser preview, PDF, and editable DOCX as consistent as possible.
- Import PDF or image resumes through the parsing API, map them into the project template, and retain the original files for reference.
- Maintain job descriptions with text or image parsing, structured editing, and targeted analysis.
- Let the intelligent Agent decide whether to answer, ask follow-up questions, read a layout snapshot, or generate a modification preview.
- Use a preview-confirm-save flow for AI changes; stale changes are rejected when the resume has changed, with concurrency protection for multiple windows.
- Save single-user exports to `output/resumes/`; the multi-user profile downloads files through the browser instead of accumulating them on the server.

## Interface demos

### Project homepage

![ResumeBranch workspace](docs/images/readme/cover.png)

### Resume import

![Create or import a resume](docs/images/readme/import-resume.png)

### Main workspace

![Resume workspace](docs/images/readme/main-page.png)

### Content editing

![Structured resume content editing](docs/images/readme/edit-content.png)

### Layout ordering

![Module order editing](docs/images/readme/edit-order.png)

### Conversational editing

![AI edit preview and confirmation](docs/images/readme/conversation-edit.png)

## Three delivery paths

The three paths share the same Vue frontend, FastAPI backend, and business code, but they target different users and operational environments. The application does not switch between single-user and multi-user profiles dynamically inside the page.

| Delivery path | Obtain and run | User model | Purpose |
|---|---|---|---|
| Source development/testing | Clone the GitHub repository, install dependencies, and use Windows scripts | Single-user or multi-user test configuration | Development, testing, and acceptance |
| Multi-user Docker deployment | Obtain the source and Docker Compose configuration, then run Docker Compose | Multi-user only | Local deployment validation or server deployment |
| Windows single-user installation | Download `ResumeBranch-Setup-v1.2.0-x64.exe` from GitHub Releases and install it | Single-user only | Direct local use on Windows |

The source path provides two configurations: single-user uses SQLite and `scripts\start_local.cmd`; multi-user testing uses MySQL and `scripts\start_multi_user.cmd`. The existing internal configuration value `APP_MODE=local` and script names remain unchanged; “single-user” is the user-facing description.

Single-user SQLite does not require a separate service. Shutting down the application or restarting the computer does not delete `data/resumebranch.db`; the data remains as long as the `data/` directory is kept. SQLite and MySQL are independent data sources, and the project does not migrate data between them automatically.

## Technical architecture

- Frontend: Vue 3, Vite, Element Plus, and Vue Router.
- Backend: Python 3.11, FastAPI, SQLAlchemy, and Uvicorn/Gunicorn.
- Agent: LangGraph handles graph state and routing; repository-local Agent Skill packages provide discoverable resume-edit, resume-snapshot, and resume-coach capabilities; LangChain Core and an OpenAI-compatible client provide message, model, and tool abstractions.
- Data: the single-user profile uses SQLite, while the multi-user profile uses MySQL; private multi-turn Skill state is stored separately from ordinary conversation memory.
- Export and rendering: Chromium generates PDFs, `python-docx` generates editable DOCX files, and Poppler generates PDF page snapshots that can be consumed by the AI.
- Communication: regular endpoints use HTTP, while AI responses are streamed over SSE.
- Delivery and deployment: the source path includes Windows launch scripts; the multi-user Docker path includes Compose, MySQL, Gunicorn, and Nginx configuration.

Reproducible dependency versions are defined by [`backend/requirements.lock.txt`](backend/requirements.lock.txt) and [`frontend/package-lock.json`](frontend/package-lock.json). Patch versions are not duplicated in this README because they become outdated easily.

## Windows single-user installation package

For a normal Windows user, download `ResumeBranch-Setup-v1.2.0-x64.exe` from GitHub Releases and run the installer. It includes the frozen single-user application, the production frontend bundle, a private Python runtime and dependencies, Nginx, Poppler, and the PDF rendering browser. It does not require Python, Node.js, npm, Docker, MySQL, or Inno Setup on the target computer, and it does not modify the system `PATH`.

The installer uses a per-user installation location by default. After installation, the optional desktop shortcut points to `ResumeBranch.exe`; the launcher starts the private single-user backend and frontend, then opens `http://127.0.0.1:5173` in the default browser. The SQLite database and exports are stored below the installed `app/` directory. Initial user data and API settings are empty and must be configured by the user when needed.

The single-user installer has no updater. Multi-user use remains a separate source-testing or Docker-deployment path.

The installer is a generated release artifact. Maintainers can rebuild it on Windows x64 with:

~~~powershell
.\packaging\build-installer.ps1
~~~

The generated file is written to `output/installer/ResumeBranch-Setup-v1.2.0-x64.exe`. See [Windows single-user installation package](packaging/README.md) for packaging details.

## Source development/testing on Windows

The following procedure is for developers or users who clone the repository directly. It describes the single-user source configuration; the multi-user source configuration is covered below. If you use the installation package above, do not install these development dependencies separately.

### Single-user source test: requirements

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Chrome, Edge, or Chromium (required for PDF export)

### Single-user source test: configure and install

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

### Single-user source test: start and stop

~~~powershell
.\scripts\start_local.cmd
~~~

Open <http://127.0.0.1:5173>. The script starts or restarts the backend, starts the shared frontend, and runs health checks. The Vite development server supports hot reload.

~~~powershell
# Stop the frontend and backend without deleting data
.\scripts\stop_app.cmd
~~~

See [Source development and testing](docs/source-development-testing.md) for the complete source procedure, backup guidance, and health checks.

### Multi-user source test: Windows native MySQL

Use this source configuration on a Windows computer without Docker to test login, invite codes, administrator permissions, and user-data isolation:

~~~powershell
Copy-Item .env.multi_user.example .env.multi_user
# Configure the MySQL database and application account, then:
.\scripts\start_multi_user.cmd
~~~

The Windows multi-user entry script checks and starts the MySQL service, verifies the database connection, starts or restarts the backend, and reuses the same Vite frontend. Ordinary users must register and sign in with an email address; administrators may use an email address or a dedicated non-email account name. Each account has only one valid login session at a time; a new login invalidates the previous session.

See [Source development and testing](docs/source-development-testing.md) for detailed configuration.

## Multi-user Docker deployment

Use this path on a Linux server or another environment that supports Docker. It can also be run locally for deployment acceptance. Docker is not required for the source single-user or source multi-user Windows tests.

~~~bash
cp .env.docker.example .env.docker
# Replace the JWT, administrator, and MySQL passwords:
docker compose --env-file .env.docker -f docker-compose.multi-user.yml config
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build
~~~

The default address is <http://127.0.0.1:8080>. See [Multi-user Docker deployment](docs/docker-multi-user-deployment.md) for the topology, security boundaries, backups, and acceptance checks.

## Launch scripts

| Script | Purpose |
|---|---|
| `scripts/start_local.cmd` | Start the single-user SQLite backend and shared frontend |
| `scripts/start_multi_user.cmd` | Start native MySQL, the multi-user backend, and the shared frontend |
| `scripts/start_backend_local.cmd` | Start or restart the single-user backend |
| `scripts/start_backend_multi_user.cmd` | Start or restart the multi-user backend |
| `scripts/start_frontend.cmd` | Start the shared Vite frontend |
| `scripts/start_mysql.cmd` | Start the Windows MySQL service only |
| `scripts/stop_mysql.cmd` | Stop the Windows MySQL service only |
| `scripts/stop_app.cmd` | Stop the frontend and backend while preserving SQLite/MySQL data and the MySQL service |

Runtime logs are written to `.local-run/`, which is ignored by Git.

## Agent and modification safety

ResumeBranch does not hard-code every request as a fixed workflow. The entry router combines the current request, active Skill state, and confirmation protocol to choose a path:

- General questions and complex resume tasks are given to the Agent, which decides whether to answer, ask questions, or call a skill.
- Explicit, safely parseable requests for fields, font sizes, layout, or local bold formatting use the deterministic direct-edit path.
- Comprehensive diagnosis remains a one-shot conversation; deep polish explicitly activates the evidence-driven coaching Skill, which can also be activated on demand in other conversations.
- When visual layout information is needed, the system renders resume page snapshots using the same source as the official PDF.
- When a resume change is needed, the system generates a structured candidate, shows a preview, and persists it only after confirmation.

Resume content, layout rules, the JD, conversation summaries, and necessary memory are assembled on demand by the context layer. Coaching evidence is kept in private Skill state, separate from the rolling conversation summary.

Every resume-workspace request is bound to a validated `ProjectTask` through `X-Task-ID`; there is no user-level fallback resume store. When a change is confirmed, the resume revision and affected content/layout digest are checked. If another window changes the same state while confirmation is pending, the stale suggestion is rejected and the frontend reloads the canonical version from the database. Database locks serialize writes across conversation windows, browser tabs, and backend processes; consultation-only conversations are unaffected.

See [Agent architecture and state boundaries](docs/agent-architecture.md) for the current implementation details.

## Data and privacy

Main persistent data in the single-user profile:

~~~text
data/resumebranch.db                  # Resume, JD, conversation, and business state
data/source_documents/                # Original imported resume files
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

The main endpoint groups cover runtime configuration, authentication and invite codes, resumes and versions, JDs, conversations, imports, PDF/DOCX export, AI settings, and confirmation saves. `POST /chat` streams events over SSE. Authentication endpoints are available only in the multi-user profile; the open-export-directory endpoint is available only in the single-user profile.

## Tests

~~~powershell
# Backend: explicitly use test SQLite instead of inheriting MySQL from .env
$env:APP_MODE = "local"
$env:LOCAL_USER_EMAIL = "local@localhost"
$env:DATABASE_URL = "sqlite:///./.local-run/test-suite.db"
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
├── .agents/skills/                 # Discoverable Agent Skill packages and their schemas/scripts
├── backend/                       # FastAPI, Agent, data models, import and export
│   ├── harness/                   # Context, memory, persistence, and observability
│   ├── skill_runtime.py           # Skill discovery, activation, schema loading, and invocation
│   ├── Dockerfile
│   ├── main.py
│   ├── resume_agent.py
│   ├── requirements.txt           # Dependency declarations
│   └── requirements.lock.txt      # Locked dependencies
├── frontend/                      # Vue SPA and Nginx container configuration
├── scripts/                       # Windows startup, shutdown, health, and smoke scripts
├── launcher/                      # GUI launcher source for the single-user installer
├── installer/                     # Inno Setup recipe for the Windows installer
├── packaging/                     # Installer build scripts and bundled runtime configuration
├── tests/                         # Backend automated tests
├── docs/                          # Deployment, architecture, testing, references, and README images
├── data/                          # Local runtime data (not committed by default)
├── output/resumes/                # Local exports (not committed by default)
├── output/installer/               # Generated Windows installer artifact
├── docker-compose.multi-user.yml  # Multi-user Compose definition
├── .env*.example                  # Configuration templates
├── README.md                      # Simplified Chinese default README
└── README.en.md                   # English README
~~~

## Documentation

- [Documentation index](docs/README.md)
- [Windows single-user installation](docs/windows-single-user-installation.md)
- [Source development and testing](docs/source-development-testing.md)
- [Multi-user Docker deployment](docs/docker-multi-user-deployment.md)
- [Windows installation package build](packaging/README.md)
- [Testing and acceptance](docs/testing.md)
- [Agent architecture and state boundaries](docs/agent-architecture.md)

## License

This project is released under the [MIT License](LICENSE).
