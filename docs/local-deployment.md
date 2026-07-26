# Windows 本地部署

本项目当前采用 Windows 原生本地运行方式：

- 前端：Vue/Vite，`http://127.0.0.1:5173`
- 后端：FastAPI/Uvicorn，`http://127.0.0.1:8000`
- 数据库：本机 MySQL 8.4，数据库 `resume_assistant`
- PDF：WeasyPrint 69 + 隔离的 MSYS2/Pango
- LLM：默认禁用，配置密钥后启用

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

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
```

停止后台进程：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

也可以临时覆盖 `.env` 中的模式，适合回归测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1 -AppMode multi_user
```

如果希望分别以前台模式观察日志，可在两个 PowerShell 窗口执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend_local.ps1
```

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
