# Windows 本地部署

本项目当前采用 Windows 原生本地运行方式：

- 前端：Vue/Vite，`http://127.0.0.1:5173`
- 后端：FastAPI/Uvicorn，`http://127.0.0.1:8000`
- 数据库：本机 MySQL 8.4，数据库 `resume_assistant`
- PDF：优先调用本机 Chrome/Edge 的无界面打印；WeasyPrint 69 + 隔离的 MSYS2/Pango 作为兼容回退
- LLM：默认禁用，配置密钥后启用

PDF 导出会依次查找 Chrome、Edge 或 Chromium。通常无需配置；如需指定浏览器，可将
`RESUME_PDF_BROWSER` 设为浏览器可执行文件的绝对路径。浏览器不可用或打印失败时，
后端会自动使用 WeasyPrint，不改变 `/export_pdf` 接口。

## 应用模式

本机默认使用单用户模式：

```env
APP_MODE=local
LOCAL_USER_EMAIL=local@localhost
```

该模式会直接进入简历工作区，不需要登录或 JWT；注册、邀请码和管理员入口会被隐藏，
对应后端接口也会停用。数据仍通过 `User` 记录归属，以便以后切回多用户模式，并不需要
修改数据库结构。

如需恢复原有的登录、注册、邀请码和多用户隔离功能，将 `.env` 改为：

```env
APP_MODE=multi_user
```

然后重启后端和前端。`LOCAL_USER_EMAIL` 只用于本地模式，不是实际邮箱，也不会发送邮件。

## 环境隔离

- Python 3.11 安装在当前用户的独立目录，未加入系统 PATH。
- Python 依赖仅位于项目的 `.venv-win`。
- npm 依赖仅位于 `frontend/node_modules`。
- Pango 位于 `C:\resume-tools\msys64`，未加入系统 PATH。
- 密钥和本地密码仅位于被 Git 忽略的 `.env`。

## 启动与停止

脚本位于 `scripts/` 目录，按需选择：

| 脚本 | 作用 |
|------|------|
| `start_db_local.cmd` | 双击启动本机 MySQL 服务 |
| `start_backend_local.cmd` | 后端未运行时启动，已运行时自动重启 |
| `start_frontend_local.cmd` | 双击并在后台启动前端 |
| `start_local.cmd` | 双击一键后台启动数据库 + 后端 + 前端，全程无需按键 |
| `stop_local.cmd` | 双击停止前端、后端和 MySQL，并清理端口残留进程 |

Windows 下直接使用 `.cmd` 文件即可，启动与停止过程不依赖 PowerShell 脚本。

后端代码更新后直接运行 `scripts\start_backend_local.cmd`。也可以运行
`scripts\start_local.cmd`：它只重启必须重新加载 Python 代码的后端；数据库
保持运行，前端继续由 Vite 热更新处理。

### 首次设置

复制 `.env.example` 为 `.env`，填写 MySQL 连接信息，然后按“安装依赖”章节准备
`.venv-win` 和 `frontend/node_modules`。启动脚本不会覆盖现有配置或数据库。

### 一键启动全部

```powershell
.\scripts\start_local.cmd
```

一键脚本默认采用非交互模式：数据库、后端、前端和健康检查会连续执行，后台
FastAPI/Vite 进程不会读取启动窗口的键盘输入。如需让最终结果停留在窗口中，可运行
`.\scripts\start_local.cmd --pause`。

启动成功后会输出：

```
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
App mode: local
Logs:     C:\...\resume_assistant\.local-run
```

### 停止

```powershell
.\scripts\stop_local.cmd
```

`start_local.cmd` 默认在输出最终结果后自动退出，其他单项脚本仍会保留结果提示，
按任意键后关闭窗口。启动或停止 MySQL Windows 服务时会自动请求管理员授权；
前端和后端通过实际监听端口定位并停止，不依赖可能已经失效的历史 PID。

### 分别启动

在三个“命令提示符”窗口分别执行：

```powershell
.\scripts\start_db_local.cmd
.\scripts\start_backend_local.cmd
.\scripts\start_frontend_local.cmd
```

前后端运行日志写入 `.local-run/`，无需停留在服务自身的交互提示中。

应用模式通过 `.env` 中的 `APP_MODE=local` 或 `APP_MODE=multi_user` 设置，修改后重新启动。

## 多用户模式账号

只有 `APP_MODE=multi_user` 时才需要管理员账号。邮箱与密码分别读取 `.env` 中的
`ADMIN_EMAIL` 和 `ADMIN_PASSWORD`。不要将 `.env` 提交到 Git，也不要在聊天或日志中
粘贴密码。

## 验收

```powershell
.\.venv-win\Scripts\python.exe scripts\smoke_test.py
```

脚本会识别当前应用模式，验证前端、健康检查、认证策略、MySQL 简历与 JD 读写、
PDF 导出和 LLM 禁用保护，并在结束时删除临时测试数据。本地模式下，为防止误删真实
本地数据，完整冒烟测试应使用启动参数临时指定 `smoke-*@local.test` 邮箱。

## 启用 LLM

在 `.env` 中配置：

```env
LLM_API_KEY=<your-key>
BASE_URL=<openai-compatible-base-url>
LLM_MODEL=<supported-model-name>
```

修改后重启后端。未配置密钥时，AI 相关接口返回 HTTP 503，其他本地功能不受影响。

## 数据库

应用使用专用账户 `resume_app@127.0.0.1`，权限仅限 `resume_assistant` 数据库。
连接池启用了 `pool_pre_ping` 和 `pool_recycle`，不会修改本机其他数据库。
