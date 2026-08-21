# Windows 本地部署（默认）

本地版面向个人电脑上的单用户使用：免注册、免登录、无需安装或启动数据库服务。前端与多人版复用同一套简历工作区，区别由启动配置决定，不在页面内动态切换。

## 运行组成

- 前端：Vue/Vite，`http://127.0.0.1:5173`
- 后端：FastAPI/Uvicorn，`http://127.0.0.1:8000`
- 数据库：SQLite 文件 `data/resumebranch.db`
- 导出：保存到 `output/resumes/`，成功后可在页面中直接打开该文件夹
- PDF：统一使用 Chrome/Edge/Chromium；缺失或执行失败时明确报错
- LLM：可选；未配置密钥时，简历编辑、版本管理和导出仍可使用

SQLite 是嵌入式数据库，不需要单独启动。停止项目、重启电脑或升级依赖不会删除数据库文件；只要保留 `data/resumebranch.db`，数据就会保留。

## 配置

首次运行先复制配置：

```powershell
Copy-Item .env.example .env
```

本地关键配置如下：

```env
APP_MODE=local
LOCAL_USER_EMAIL=local@localhost
DATABASE_URL=sqlite:///./data/resumebranch.db
LOCAL_EXPORT_DIR=./output/resumes
HOST=127.0.0.1
```

本地模式强制绑定回环地址，避免免登录接口被局域网或公网直接访问。`start_backend_local.cmd` 会显式使用以上本地模式、SQLite 和回环地址，不会读取 `.env` 中遗留的 MySQL 地址来启动本地版。

## 安装依赖

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r backend\requirements.lock.txt

Set-Location frontend
npm ci
Set-Location ..
```

## 启动与停止

| 脚本 | 作用 |
|------|------|
| `scripts/start_local.cmd` | 启动后端、前端并完成健康检查 |
| `scripts/start_backend_local.cmd` | 启动或重启本地后端 |
| `scripts/start_frontend.cmd` | 启动本地版与多用户版共用的前端 |
| `scripts/stop_app.cmd` | 停止前端和后端，不删除 SQLite 或 MySQL 数据 |

一键启动：

```powershell
.\scripts\start_local.cmd
```

需要保留结果窗口时：

```powershell
.\scripts\start_local.cmd --pause
```

停止：

```powershell
.\scripts\stop_app.cmd
```

运行日志写入 `.local-run/`。后端代码修改后运行 `scripts\start_backend_local.cmd`，脚本会重启后端以加载新代码。

## 数据与导出

本地数据主要位于：

```text
data/resumebranch.db
data/source_documents/
data/langgraph_checkpoints.sqlite
output/resumes/
```

导出文件命名为：

```text
简历组名_版本名_导出日期.pdf
简历组名_版本名_导出日期.docx
```

同一天重复导出时依次增加 `_01`、`_02`。文件写完后才会发布到输出目录，避免留下半写入文件。多人版默认只返回浏览器下载，不在服务器持续积累用户简历文件。

本地导出成功弹窗提供“打开导出文件夹”按钮。该能力由只在本地模式开放的后端接口调用系统文件管理器；网页不能指定或打开其他任意路径。

### 备份

最稳妥的本地备份方式是先停止后端，再复制整个 `data/` 目录。SQLite 已启用 WAL；后端运行时不要只复制单个 `.db` 文件而忽略可能存在的 `-wal` 文件。

恢复时停止后端，将备份的 `data/` 放回项目目录，再启动项目。现有 MySQL 数据与新建 SQLite 数据源相互独立，本项目不自动迁移或覆盖二者。

## 验活

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
```

预期 `/app/config` 返回：

- `app_mode: local`
- `authentication_required: false`
- `database_backend: sqlite`
- `local_export_enabled: true`

自动回归：

```powershell
.\.venv-win\Scripts\python.exe -m unittest tests.test_local_scripts tests.test_runtime_profiles
Set-Location frontend
npm test
npm run build
```

`scripts/smoke_test.py` 会创建并删除测试数据。为了避免误删真实本地数据，只应在使用临时 `smoke-*@local.test` 本地用户和独立测试数据库时运行完整冒烟测试。

## 启用 AI

在 `.env` 中配置对话与解析服务，或在本地首页右上角打开“API 设置”。密钥只保存在本机被 Git 忽略的配置/数据文件中。未配置对话模型时，相关 AI 接口会返回明确错误，简历编辑、版本管理和导出不受影响；导入解析还需要配置兼容的解析服务。

需要测试注册、登录和用户隔离时，请使用 [本机多用户部署](multi-user-local.md)。Docker 服务器部署请参考 [Docker 多人自托管部署](deployment.md)。
