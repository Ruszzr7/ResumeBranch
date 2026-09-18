# ResumeBranch

[English](README.en.md) | **简体中文**

**ResumeBranch** 是一个面向简历维护与求职辅导的 AI 简历工作台，支持简历导入、结构化编辑、JD 分支管理、AI 诊断、安全修改与 PDF/DOCX 导出。

与直接让 LLM 改写简历不同，ResumeBranch 将 AI 修改转换为结构化操作，在写入前完成校验、字段差异与排版预览，并由用户确认后再正式应用；结合确定性路由、Agent Skills 与版本化上下文管理，提升修改效率、可控性和可追溯性。项目提供 Windows 单用户安装、源码开发/测试与 Docker Compose 多用户部署。

![ResumeBranch AI 修改预览：请求、Diff、临时预览与确认](docs/images/readme/hero-workspace-confirmation.png)

上图展示了一次完整的 AI 修改预览：用户提出明确请求，系统展示结构化前后变化和右侧临时简历预览；在用户接受前，正式简历不会被写入。

## 核心亮点

- **混合 Agent 路由**：明确且可安全解析的请求走确定性 <code>direct_edit</code>；普通咨询和复杂任务进入 <code>conversation_llm</code>，再按需调用 Agent Skills。
- **安全编辑链路**：用户请求先转换为结构化 operations，经过 Schema 与能力校验，在工作副本上生成候选、Diff 和排版预览，确认后才持久化。
- **三个标准 Agent Skills**：<code>resume-edit</code> 负责生成候选修改，<code>resume-snapshot</code> 提供真实 PDF 管线的视觉证据，<code>resume-coach</code> 管理有来源的多轮证据与编辑授权。
- **上下文与版本管理**：<code>ProjectTask</code>、任务级锁、内容/排版 digest、滚动记忆和 Skill 私有状态共同约束上下文边界与并发修改。
- **评估与交付**：仓库包含 700 条 Agent 核心评测案例，并提供 Windows 安装包、源码测试和 Docker Compose 多用户部署三种交付路径。

## 系统架构

~~~mermaid
flowchart TD
    UI["Vue 3 工作区"] --> API["FastAPI<br/>REST + SSE"]
    API --> SERVICES["简历 / 版本 / 任务服务"]
    API --> ROUTER{"LangGraph<br/>入口路由"}
    ROUTER --> PATHS["direct_edit / conversation_llm"]
    PATHS --> RUNTIME["SkillRuntime<br/>动态发现与调用"]
    RUNTIME --> SKILLS["resume-edit<br/>resume-snapshot<br/>resume-coach"]
    SKILLS --> RESULT["结构化操作 / 视觉证据 / 教练状态"]
    RESULT --> OUTCOME{"处理结果"}
    OUTCOME -->|回复 / 追问| RESPONSE["直接回复 / 视觉分析"]
    OUTCOME -->|修改候选| VALID["Schema 校验 / Diff / 排版预览"]
    VALID --> CONFIRM["用户确认 / 取消<br/>POST /confirm"]
    SERVICES --> MODEL["结构化简历模型"]
    CONFIRM --> MODEL
    MODEL --> DB["SQLite / MySQL"]
    MODEL --> EXPORT["PDF / DOCX 导出"]
    DB --> REV["ResumeRevision / Undo"]
~~~

前端只依赖 REST 接口、SSE 事件和确认结果；Agent 内部节点、Skill 名称和字段路径不会直接暴露给用户。导入、编辑、版本管理和导出都围绕统一的结构化简历模型工作。

## 核心执行流程：AI 修改不会直接覆盖简历

~~~mermaid
flowchart TD
    A["用户请求"] --> B{"是否能安全解析?"}
    B -->|是| C["direct_edit<br/>确定性解析"]
    B -->|否| D["conversation_llm<br/>理解、回复或追问"]
    D --> E{"是否需要 Agent Skill?"}
    E -->|否| F["直接回复 / 追问"]
    E -->|是| G["SkillRuntime 调用对应 Skill"]

    C --> H["结构化 operations"]
    G --> I["结构化 Tool 结果"]
    I --> J{"是否需要修改?"}
    J -->|否| F
    J -->|是| H

    H --> P["获取任务级修改锁"]
    P --> K["resume-edit 在工作副本上应用操作"]
    K --> L["Schema 与排版能力校验"]
    L --> M["生成候选、Change Set、Diff 与页面预览"]
    M --> N{"用户确认?"}
    N -->|取消 / 拒绝| O["清理待确认状态<br/>释放修改锁，正式简历不变"]
    N -->|接受| Q["重新校验 base_version<br/>内容 digest / 排版 digest"]
    Q --> R{"状态仍一致?"}
    R -->|否| S["清理过期候选<br/>释放修改锁并要求重新生成"]
    R -->|是| T["事务提交 ResumeRevision"]
    T --> U["更新正式简历<br/>释放修改锁并保留撤销能力"]
~~~

- <code>resume-edit</code> 只生成经过校验的候选，不直接保存正式简历。
- 对 AI 候选而言，<code>/confirm</code> 是应用候选、写入简历/排版、记录修订和释放锁的统一入口。
- 确认时只校验候选实际涉及的内容或排版范围，避免无关修改制造冲突。
- 如果其他窗口已经修改了同一范围，旧候选会被拒绝，前端重新加载数据库中的正式版本。

## 评测证据

评测数据位于 [tests/agent_core_eval/total/cases.json](tests/agent_core_eval/total/cases.json)，评测脚本位于 [tests/agent_core_eval/total/run_eval.py](tests/agent_core_eval/total/run_eval.py)，完整结果见 [results/report.md](tests/agent_core_eval/total/results/report.md)。当前数据集包含 700 条唯一案例：路由 200 条、Skill 选择 400 条、修改安全 100 条。

评测设置：离线路由与安全评测不调用 LLM，由当前代码确定性计算；Skill 选择的 400 条评测使用项目当前对话 API 配置运行，provider/model 记录在结果 JSON 中。

| 评测项 | 案例 | 结果 |
|---|---:|---|
| Intent Routing | 200 | 100%（200/200） |
| Skill Selection | 400 | <code>resume-edit</code> P99.23% / R97.73%；<code>resume-snapshot</code> P100% / R97.83%；<code>resume-coach</code> P96.77% / R100% |
| Safe Edit | 100 | 确认前写入 0/100；连带修改 0/100 |
| Structured Edit Outcome | 74 | 100%（74/74） |
| Executable Edit Operations | 135 | 100%（135/135） |
| Non-target Leaf Fields | 31,556 | 0 个发生非目标变化 |
| Stale Confirmation | 19 | 100% 拦截（19/19） |
| Cancel Preservation | 19 | 100% 保持原数据（19/19） |

## Agent Skills

项目级 Skill 位于 <code>.agents/skills/</code>，由 <code>backend/skill_runtime.py</code> 在启动时发现，并按输入/输出 Schema 执行。

| Skill | 职责 | 是否直接写入正式简历 |
|---|---|---|
| <code>resume-edit</code> | 将明确意图编译为结构化内容或排版 operations，生成候选和变更集合 | 否 |
| <code>resume-snapshot</code> | 使用与正式 PDF 导出相同的渲染源生成有限页数的彩色 PNG，回答分页、留白、对齐和溢出问题 | 否，只读 |
| <code>resume-coach</code> | 管理具体问题、证据来源、追问、结论和编辑授权，并在授权后交接给 <code>resume-edit</code> | 否 |

## 关键工程设计

### 确定性路径与 LLM 路径

架构图与核心执行流程展示了两条路径如何汇入统一的 Skill 调用、候选生成与确认协议。

### 上下文与状态隔离

- 每个工作区请求必须携带 <code>X-Task-ID</code>，并绑定当前用户拥有的 <code>ProjectTask</code>。
- 主对话、命令对话、JD、简历版本和浏览器标签页使用明确的上下文边界。
- Harness 保存最近的完整结构化轮次，并将更早内容压缩为有界摘要。
- <code>resume-coach</code> 的当前问题、证据和授权状态保存在独立的 Skill 私有状态中，不混入普通对话摘要。

### 版本、摘要与并发

候选预览会记录内容 digest、排版 digest 和状态序列。确认时重新读取任务状态，根据候选实际影响的范围进行校验；数据库级任务锁负责串行化不同窗口、标签页和后端进程的正式写入。锁解决“谁可以提交”，digest 和 <code>base_version</code> 解决“候选是否基于当前数据生成”。

## 功能展示

下面的截图覆盖简历版本管理、完整工作区、AI 修改确认、简历导入，以及结构化内容和模块顺序编辑。

### 简历版本首页

![ResumeBranch 简历版本首页](docs/images/readme/cover.png)

### 完整工作区

![简历预览与 AI 对话工作区](docs/images/readme/main-page.png)

### 排版修改预览

![排版修改预览与确认](docs/images/readme/conversation-edit.png)

### 简历导入

![创建或导入简历](docs/images/readme/import-resume.png)

### 结构化内容编辑

![结构化编辑简历内容](docs/images/readme/edit-content.png)

### 模块顺序编辑

![模块顺序编辑](docs/images/readme/edit-order.png)

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、Element Plus、Vue Router |
| 后端 | Python 3.11、FastAPI、SQLAlchemy、Uvicorn/Gunicorn |
| Agent | LangGraph、LangChain Core、OpenAI 兼容客户端、Agent Skills |
| 数据 | SQLite（单用户）、MySQL（多用户） |
| 导出与视觉 | Chromium、<code>python-docx</code>、Poppler |
| 通信 | HTTP REST、SSE |

## 项目启动

### 方式 A — Windows 单用户安装

从 GitHub Releases 获取当前 <code>ResumeBranch-Setup-v1.2.0-x64.exe</code> 并运行安装程序，目标电脑不需要另外安装 Python、Node.js、npm、Docker、MySQL 或 Inno Setup；安装包启动后默认访问 <http://127.0.0.1:5173>，数据保存在安装目录的 <code>app/data/</code> 中。

### 方式 B — Docker Compose 多用户部署

适用于 Linux 服务器或支持 Docker 的环境：

~~~bash
cp .env.docker.example .env.docker
# 修改 JWT、管理员和 MySQL 密码
docker compose --env-file .env.docker -f docker-compose.multi-user.yml config
docker compose --env-file .env.docker -f docker-compose.multi-user.yml up -d --build
~~~

默认访问 <http://127.0.0.1:8080>，详细拓扑、安全边界、备份和验收见[多用户 Docker 部署](docs/docker-multi-user-deployment.md)。

### 方式 C — Windows 源码开发/测试

环境要求：Windows 10/11、Python 3.11+、Node.js 20+，以及用于 PDF 导出的 Chrome、Edge 或 Chromium。

~~~powershell
Copy-Item .env.example .env

python -m venv .venv-win
.\\.venv-win\\Scripts\\python.exe -m pip install -r backend\\requirements.lock.txt

Set-Location frontend
npm ci
Set-Location ..

.\\scripts\\start_local.cmd
~~~

访问 <http://127.0.0.1:5173>，多用户 Windows 原生 MySQL 测试见[源码开发与测试](docs/source-development-testing.md)。

### 自动化测试

~~~powershell
# 后端：使用测试 SQLite，不继承当前 .env 中的 MySQL
$env:APP_MODE = "local"
$env:LOCAL_USER_EMAIL = "local@localhost"
$env:DATABASE_URL = "sqlite:///./.local-run/test-suite.db"
.\\.venv-win\\Scripts\\python.exe -m unittest discover -s tests

# 前端
Set-Location frontend
npm test
npm run build
~~~

完整测试前置条件、MySQL 集成测试、Docker 验收和人工回归见[测试与验收](docs/testing.md)。

## 项目结构

~~~text
ResumeBranch/
├── backend/
│   ├── resume_agent.py       # LangGraph 路由与 Agent 编排
│   ├── harness/              # 上下文、记忆、持久化、可观测性
│   ├── skill_runtime.py      # Skill 发现与调用
│   ├── resume_changes.py     # Diff、digest、候选变更
│   └── main.py               # REST/SSE 与确认接口
├── .agents/skills/           # resume-edit / resume-snapshot / resume-coach
├── frontend/                 # Vue 3 工作区与简历预览
├── tests/                    # 回归测试与 Agent 核心评测
├── scripts/                  # Windows 启动、停止与验活脚本
├── docs/                     # 架构、部署、测试文档和 README 图片
├── packaging/                # Windows 安装包构建
├── docker-compose.multi-user.yml
├── README.md
└── README.en.md
~~~

## 数据与隐私

单用户版的主要持久化内容如下：

~~~text
data/resumebranch.db                  # 简历、JD、对话与业务状态
data/source_documents/                # 导入简历的原文件
data/llm_profiles.json                # 本机 API 配置（如使用页面设置）
output/resumes/                       # 单用户导出的 PDF/DOCX
~~~

项目不会要求将简历上传到 ResumeBranch 官方服务器；但启用第三方 LLM 或解析 API 后，请自行确认服务商的数据处理与隐私政策。建议停止后端后备份整个 <code>data/</code> 目录。

## 文档

- [文档索引](docs/README.md)
- [Agent 架构与状态边界](docs/agent-architecture.md)
- [源码开发与测试](docs/source-development-testing.md)
- [多用户 Docker 部署](docs/docker-multi-user-deployment.md)
- [Windows 单用户安装](docs/windows-single-user-installation.md)
- [Windows 安装包构建说明](packaging/README.md)
- [测试与验收](docs/testing.md)

## License

本项目采用 [MIT License](LICENSE)。
