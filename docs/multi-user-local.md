# Windows 本机多用户部署

本文说明如何在 Windows 上使用已安装的 MySQL 启动多用户模式。该模式用于本机测试注册、邮箱登录、管理员、邀请码和用户数据隔离，不需要 Docker 或 WSL，也不会启用虚拟网卡。

本模式与默认的 SQLite 本地版是两套独立数据源：

| 模式 | 数据库 | 登录 | 整体启动脚本 |
|------|--------|------|--------------|
| 本地版 | `data/deepagents.db` | 免登录 | `scripts\start_local.cmd` |
| 多用户版 | 本机 MySQL | 必须登录 | `scripts\start_multi_user.cmd` |

同一时间只运行一种模式。两种模式共用同一个前端和页面代码，前端根据后端 `/app/config` 的运行配置显示登录界面或本地工作区。

## 运行要求

- Windows 10/11
- Python 3.11+
- Node.js 20+
- 已安装 MySQL 8.x，并能看到对应的 Windows 服务，例如 `MySQL84`
- Chrome、Edge 或其他 Chromium 浏览器（PDF 导出需要）
- 已完成后端和前端依赖安装

如果尚未安装项目依赖，请先执行：

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r backend\requirements.txt

Set-Location frontend
npm install
Set-Location ..
```

## 一次性准备 MySQL

使用 MySQL Workbench 或管理员命令行连接 MySQL，执行以下 SQL。请将示例密码替换为自己的密码，不要将真实密码写入文档或提交到 Git：

```sql
CREATE DATABASE resume_assistant
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'resume_app'@'127.0.0.1'
  IDENTIFIED BY 'replace-with-your-database-password';

GRANT ALL PRIVILEGES
  ON resume_assistant.*
  TO 'resume_app'@'127.0.0.1';

FLUSH PRIVILEGES;
```

如果数据库或账号已经存在，不要重复执行创建语句；只需确认账号对 `resume_assistant` 具有完整权限，并让 `.env.multi_user` 中的密码与 MySQL 实际密码一致。

可以查看本机 MySQL 服务：

```powershell
Get-Service *MySQL*
```

如果服务名不是 `MySQL84`，启动前设置：

```powershell
$env:MYSQL_SERVICE_NAME = '实际的服务名'
```

## 配置多用户环境

复制示例配置：

```powershell
Copy-Item .env.multi_user.example .env.multi_user
```

至少检查并修改以下配置：

```dotenv
APP_MODE=multi_user
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=替换为管理员密码

MYSQL_DATABASE=resume_assistant
MYSQL_USER=resume_app
MYSQL_PASSWORD=替换为 MySQL 应用账号密码
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

`DATABASE_URL` 可以留空，`run_multi_user_backend.py` 会根据上述 MySQL 配置自动生成连接地址，并对密码中的特殊字符进行编码。如果已经有一条可用的完整 SQLAlchemy 连接地址，也可以直接填写 `DATABASE_URL`。

JWT 密钥必须至少 32 个字符，建议使用随机字符串。由于需要兼容既有配置，管理员变量仍然命名为 `ADMIN_EMAIL`；管理员可以使用邮箱或专用账号名，普通用户注册和登录必须使用邮箱。

`.env.multi_user` 已被 Git 忽略，不要提交真实密码、JWT 密钥或 LLM API Key。

## 启动方式

### 一键启动

```cmd
scripts\start_multi_user.cmd
```

启动器会依次执行：

1. 检查并启动 MySQL Windows 服务。
2. 检查 MySQL 应用账号是否可以连接。
3. 如果后端已运行，重启后端以加载最新 Python 代码；如果未运行则直接启动。
4. 启动共用的 Vite 前端；前端已运行时直接复用，继续支持热更新。
5. 检查后端是否确实处于 `multi_user + mysql` 模式。

启动成功后访问：

- 前端：<http://127.0.0.1:5173>
- 后端：<http://127.0.0.1:8000>
- 健康检查：<http://127.0.0.1:8000/health>

### 分别启动

```cmd
scripts\start_mysql.cmd
scripts\start_backend_multi_user.cmd
scripts\start_frontend.cmd
```

通常推荐使用整体入口，因为它会按依赖顺序启动并执行完整检查。

## 停止方式

停止前端和后端：

```cmd
scripts\stop_app.cmd
```

停止 MySQL 服务：

```cmd
scripts\stop_mysql.cmd
```

建议先停止前端和后端，再停止 MySQL。 `stop_app.cmd` 不会删除 MySQL 数据，也不会自动停止 MySQL；这样可以避免影响其他使用同一 MySQL 服务的项目。 `stop_mysql.cmd` 需要管理员权限时会弹出 UAC。

## 验证运行模式

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
```

`/app/config` 应包含：

```text
app_mode: multi_user
authentication_required: true
database_backend: mysql
```

验收登录流程：

1. 使用 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 登录管理员。
2. 管理员创建邀请码。
3. 使用邮箱注册普通用户。
4. 普通用户使用邮箱登录。
5. 管理员可以使用配置的账号名登录。
6. 不同用户只能看到自己的简历、岗位版本和对话数据。

## 常见问题

### MySQL access denied

确认以下内容一致：

- `.env.multi_user` 中的 `MYSQL_USER`。
- `.env.multi_user` 中的 `MYSQL_PASSWORD`。
- MySQL 中对应账号的实际密码。
- 账号是否被授权访问 `resume_assistant` 数据库。
- `MYSQL_HOST` 和 `MYSQL_PORT` 是否正确。

启动器会在停止旧后端之前预检 MySQL；如果凭据错误，当前正在运行的后端不会被停止。

### 找不到 MySQL 服务

执行：

```powershell
Get-Service *MySQL*
```

然后设置正确的 `MYSQL_SERVICE_NAME`，再重新运行 `scripts\start_multi_user.cmd`。

### 端口被占用

- `8000` 被占用：停止旧后端或其他使用该端口的程序。
- `5173` 被占用：确认是否已有 Vite 前端；如果是项目自己的前端，启动器会复用它。
- `3306` 被占用：确认监听者是否就是目标 MySQL 服务。

### 页面仍然显示本地版

先执行：

```cmd
scripts\stop_app.cmd
scripts\start_multi_user.cmd
```

再检查 `/app/config`。前端本身只有一套，显示哪种入口由后端运行配置决定。

## 与 Docker 部署的关系

本教程使用 Windows 原生 MySQL，不依赖 Docker、WSL 或 Hyper-V 虚拟网卡。Docker Compose 文件用于后续 Linux 服务器或其他支持 Docker 的环境，不是本机多用户模式的必要条件。服务器部署请参考 [Docker 多人自托管部署](deployment.md)。
