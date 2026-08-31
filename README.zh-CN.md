# ResumeBranch

[English](README.md) | **简体中文**

ResumeBranch 是一个面向个人简历维护与求职准备的开源 AI 简历助手。项目以结构化简历为核心，提供导入、编辑、版本管理、排版、PDF/DOCX 导出、JD 分析和对话式优化，并提供源码开发/测试、多用户 Docker 部署和 Windows 单用户安装三种交付方式。

当前版本为 **Release 1.1.1**。功能与架构已冻结，本文档以仓库当前代码、配置和启动脚本为准。

## 主要能力

- 管理主简历与岗位版本，支持创建、复制、导入、切换和撤销。
- 结构化编辑基本信息、教育、工作、项目、技能、论文、证书等栏目。
- 调整模板、字号、间距、页边距、栏目顺序与内容形式，并保持页面预览、PDF 和可编辑 DOCX 尽可能一致。
- 导入 PDF 或图片简历，通过解析 API 注入项目模板，并保留原文件供查看。
- 维护岗位 JD，支持文本或图片解析、结构化编辑和针对性分析。
- 由智能 Agent 根据请求决定直接回复、追问、读取排版快照或生成修改预览。
- AI 修改采用“预览—确认—保存”流程；简历已变化时拒绝过期修改，并对多窗口修改做并发兜底。
- 单用户版导出到 `output/resumes/`；多用户版通过浏览器下载，不在服务器长期堆积导出文件。

## 三种交付方式

三种方式共用同一套 Vue 前端、FastAPI 后端和业务代码，但面向的用户和运行环境不同。单用户与多用户配置通过启动配置选择，页面内不能动态切换。

| 交付方式 | 获取与运行 | 用户模型 | 主要用途 |
|---|---|---|---|
| 源码开发/测试 | 从 GitHub 拉取源码，安装依赖并运行 Windows 脚本 | 单用户或多用户测试配置 | 开发、测试和验收 |
| 多用户 Docker 部署 | 获取源码和 Docker Compose 配置并启动容器 | 仅多用户 | 本地部署验收或服务器部署 |
| Windows 单用户安装 | 从 GitHub Releases 下载 `ResumeBranch-Setup-x64.exe` 并安装 | 仅单用户 | Windows 本地直接使用 |

源码方式包含两种配置：单用户使用 SQLite 和 `scripts\start_local.cmd`；多用户测试使用 MySQL 和 `scripts\start_multi_user.cmd`。现有内部配置值 `APP_MODE=local` 和脚本名称保持不变；面向用户的说明统一使用“单用户”。

单用户 SQLite 不需要单独启动。关闭项目或重启电脑不会删除 `data/resumebranch.db`；只要保留 `data/`，数据就会保留。SQLite 与 MySQL 是独立数据源，项目不会自动在两者之间迁移数据。

## 技术架构

- 前端：Vue 3、Vite、Element Plus、Vue Router。
- 后端：Python 3.11、FastAPI、SQLAlchemy、Uvicorn/Gunicorn。
- Agent：LangGraph 负责状态图与路由；LangChain Core/OpenAI 兼容客户端负责消息、模型和工具抽象。
- 数据：单用户版使用 SQLite，多用户版使用 MySQL；工作流检查点独立存放于 SQLite 文件。
- 导出与渲染：Chromium 生成 PDF，`python-docx` 生成可继续编辑的 DOCX，Poppler 用于 AI 可读的 PDF 页面快照。
- 通信：普通接口使用 HTTP，AI 回复使用 SSE 流式传输。
- 交付与部署：源码方式使用 Windows 启动脚本；多用户 Docker 方式提供 Compose、MySQL、Gunicorn 和 Nginx 配置。

依赖的可复现版本以 [`backend/requirements.lock.txt`](backend/requirements.lock.txt) 和 [`frontend/package-lock.json`](frontend/package-lock.json) 为准，不在 README 中重复维护容易过期的补丁版本。

## Windows 单用户安装

普通 Windows 用户应从 GitHub Releases 下载 `ResumeBranch-Setup-x64.exe` 并运行安装程序。安装包已经包含冻结后的单用户版程序、前端生产文件、私有 Python 运行环境及依赖、Nginx、Poppler 和 PDF 渲染浏览器。目标电脑不需要另外安装 Python、Node.js、npm、Docker、MySQL 或 Inno Setup，也不会修改系统 `PATH`。

安装程序默认使用当前用户的安装位置。安装时可以选择创建桌面快捷方式，快捷方式直接指向 `ResumeBranch.exe`。启动器会启动安装包内的单用户后端和前端，并在默认浏览器打开 `http://127.0.0.1:5173`。SQLite 数据库和导出文件位于安装目录下的 `app/` 中。首次安装时用户数据和 API 配置为空，需要使用时再自行配置。

单用户安装包不包含更新器。多用户使用仍然通过源码测试或 Docker 部署完成。

安装程序是构建生成的发布文件。维护者可以在 Windows x64 上从项目根目录重新构建：

```powershell
.\packaging\build-installer.ps1
```

生成的文件位于 `output/installer/ResumeBranch-Setup-x64.exe`。具体打包说明见 [Windows 安装包构建说明](packaging/README.md)。

## 源码开发/测试：Windows

下面的步骤适用于开发者或直接拉取仓库的用户，先说明单用户源码配置，后文再说明多用户源码配置。如果使用上面的安装包，不需要另外安装这些开发依赖。

### 单用户源码测试：环境要求

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Chrome、Edge 或 Chromium（PDF 导出需要）

### 单用户源码测试：配置与安装

```powershell
Copy-Item .env.example .env

python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r backend\requirements.lock.txt

Set-Location frontend
npm ci
Set-Location ..
```

如需 AI 对话和简历解析，在 `.env` 中配置对应的 OpenAI 兼容 API，或启动后从右上角“API 设置”填写。单用户编辑、版本管理和导出不依赖 LLM 密钥。

不要把 `.env`、`.env.multi_user`、`.env.docker` 或任何真实密钥提交到仓库。

### 单用户源码测试：启动与停止

```powershell
.\scripts\start_local.cmd
```

访问 <http://127.0.0.1:5173>。脚本会启动或重启后端、启动共用前端并执行健康检查；前端开发服务器支持热更新。

```powershell
# 停止前端和后端，不删除数据
.\scripts\stop_app.cmd
```

完整步骤、数据备份与验活方式见 [源码开发与测试](docs/source-development-testing.md)。

### 多用户源码测试：Windows 原生 MySQL

适合在不使用 Docker 的 Windows 电脑上测试登录、邀请码、管理员权限和用户数据隔离：

```powershell
Copy-Item .env.multi_user.example .env.multi_user
# 完成 MySQL 数据库/应用账号配置后：
.\scripts\start_multi_user.cmd
```

Windows 多用户入口脚本会检查并启动 MySQL 服务、验证数据库连接、启动或重启后端，并复用同一个 Vite 前端。普通用户必须使用邮箱注册和登录；管理员可按配置使用邮箱或专用账号名。一个账号同时只保留一个有效登录会话，新登录会使旧会话失效。

详细配置见 [源码开发与测试](docs/source-development-testing.md)。

## 多用户 Docker 部署

适合 Linux 服务器或支持 Docker 的环境，也可以在本地进行部署验收。源码测试不要求本机安装 Docker。

```bash
cp .env.docker.example .env.docker
# 修改 JWT、管理员和 MySQL 密码后：
docker compose --env-file .env.docker -f docker-compose.multi-user.yml config
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build
```

默认访问地址为 <http://127.0.0.1:8080>。部署拓扑、安全边界、备份和验收见 [多用户 Docker 部署](docs/docker-multi-user-deployment.md)。

## 启动脚本

| 脚本 | 作用 |
|---|---|
| `scripts/start_local.cmd` | 启动单用户 SQLite 后端和共用前端 |
| `scripts/start_multi_user.cmd` | 启动本机 MySQL、多用户后端和共用前端 |
| `scripts/start_backend_local.cmd` | 启动或重启单用户后端 |
| `scripts/start_backend_multi_user.cmd` | 启动或重启多用户后端 |
| `scripts/start_frontend.cmd` | 启动共用的 Vite 前端 |
| `scripts/start_mysql.cmd` | 单独启动 Windows MySQL 服务 |
| `scripts/stop_mysql.cmd` | 单独停止 Windows MySQL 服务 |
| `scripts/stop_app.cmd` | 停止前端和后端，保留 SQLite/MySQL 数据及 MySQL 服务 |

运行日志位于 `.local-run/`，该目录不会提交到 Git。

## Agent 与修改安全

ResumeBranch 不是把所有请求写死为固定流程。入口路由会结合当前对话模式和请求类型选择：

- 普通咨询或复杂简历任务：交给 Agent 判断是否回复、追问或调用技能。
- 明确且可安全解析的字段、字号、排版或局部加粗请求：进入确定性的直接修改路径。
- 面试诊断、深度挖掘和 JD 复盘：进入相应的求职辅导节点。
- 需要视觉排版信息时：按需渲染与正式 PDF 同源的简历页面快照。
- 需要修改简历时：生成结构化候选结果，先展示预览，确认后才持久化。

简历内容、排版规则、JD、对话摘要和必要记忆由上下文层按需组装。工作流检查点只保存控制状态，业务数据仍以 SQLAlchemy 数据库为准。

确认修改时会校验简历修订版本和内容摘要。若等待确认期间简历已被其他窗口修改，旧建议会被拒绝，前端重新加载数据库中的正式版本。不同对话窗口、浏览器标签页和后端进程之间通过数据库锁做修改串行化；咨询类对话不受影响。

更完整的当前实现说明见 [Agent 架构与状态边界](docs/agent-architecture.md)。

## 数据与隐私

单用户版的主要持久化内容：

```text
data/resumebranch.db                  # 简历、JD、对话与业务状态
data/source_documents/                # 导入简历的原文件
data/langgraph_checkpoints.sqlite     # Agent 控制状态检查点
data/llm_profiles.json                # 本机 API 配置（如使用页面设置）
output/resumes/                       # 单用户导出的 PDF/DOCX
```

建议停止后端后备份整个 `data/`，而不是在 SQLite 运行时只复制单个 `.db` 文件。多用户 Docker 数据存放在命名卷中，备份方法见部署文档。

项目不会要求将简历上传到 ResumeBranch 的官方服务器；但启用第三方 LLM 或解析 API 后，请自行确认服务商的数据处理与隐私政策。

## API 与运行检查

后端启动后，可通过以下地址检查运行状态：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
```

开发环境完整接口契约由 FastAPI 自动生成：

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

主要接口分为运行配置、认证与邀请码、简历与版本、JD、对话、导入解析、PDF/DOCX 导出、AI 设置和确认保存。`POST /chat` 使用 SSE 返回流式事件。认证接口只在多用户模式开放，打开导出目录的接口只在单用户模式开放。

## 测试

```powershell
# 后端：显式使用测试 SQLite，避免继承当前 .env 中的 MySQL
$env:APP_MODE = "local"
$env:LOCAL_USER_EMAIL = "local@localhost"
$env:DATABASE_URL = "sqlite:///./.local-run/test-suite.db"
$env:AGENT_CHECKPOINTER_ENABLED = "true"
$env:AGENT_CHECKPOINT_DB_PATH = ".local-run/test-checkpoints.sqlite"
.\.venv-win\Scripts\python.exe -m unittest discover -s tests

# 前端
Set-Location frontend
npm test
npm run build
```

以上命令强制普通测试使用 `.local-run/` 下的测试 SQLite。默认不会执行真实 MySQL 集成测试，也不会调用真实 LLM。MySQL 集成测试、真实 LLM 冒烟测试、Docker 验收、环境变量清理和人工回归的前置条件见 [测试与验收](docs/testing.md)。GitHub Actions 会在 push 和 Pull Request 时执行核心后端测试、前端测试和生产构建，并单独验证多用户 Docker 方案。

## 项目结构

```text
ResumeBranch/
├── backend/                       # FastAPI、Agent、数据模型、导出与导入
│   ├── harness/                   # 上下文、记忆、工作流状态与可观测性
│   ├── skills/                    # 简历修改、PDF 页面快照等技能
│   ├── Dockerfile
│   ├── main.py
│   ├── resume_agent.py
│   ├── requirements.txt           # 依赖声明
│   └── requirements.lock.txt      # 锁定依赖
├── frontend/                      # Vue 单页应用与 Nginx 容器配置
├── scripts/                       # Windows 启停、验活与冒烟脚本
├── launcher/                      # 单用户安装包的图形启动器源码
├── installer/                     # Windows 安装程序配置
├── packaging/                     # 安装器构建脚本与运行时配置
├── tests/                         # 后端自动化测试
├── docs/                          # 部署、架构、测试和参考资料
├── data/                          # 本地运行数据（默认不提交）
├── output/resumes/                # 本地导出文件（默认不提交）
├── output/installer/               # 构建生成的 Windows 安装程序
├── docker-compose.multi-user.yml  # 多用户容器编排
├── .env*.example                  # 配置模板
├── README.md                     # English default README
└── README.zh-CN.md                # 简体中文说明
```

## 文档

- [文档索引](docs/README.md)
- [Windows 单用户安装](docs/windows-single-user-installation.md)
- [源码开发与测试](docs/source-development-testing.md)
- [多用户 Docker 部署](docs/docker-multi-user-deployment.md)
- [Windows 安装包构建说明](packaging/README.md)
- [测试与验收](docs/testing.md)
- [Agent 架构与状态边界](docs/agent-architecture.md)

## License

本项目采用 [MIT License](LICENSE)。
