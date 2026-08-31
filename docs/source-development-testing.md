# 源码开发/测试版

本文对应第一种交付方式：从 GitHub 拉取项目源码，安装开发依赖，通过 Windows 启动脚本运行。该方式面向开发者、测试人员和维护者，不是普通用户的安装方式，也不使用 Docker。

## 适用范围

同一份源码提供两种测试配置：

| 配置 | 启动方式 | 数据库 | 用户模型 | 用途 |
|---|---|---|---|---|
| 单用户源码测试 | scripts\start_local.cmd | SQLite | 免注册、免登录 | 测试单用户功能 |
| 多用户源码测试 | scripts\start_multi_user.cmd | Windows 原生 MySQL | 注册、登录、邀请码、管理员和数据隔离 | 测试多用户功能 |

两种配置共用前端和后端业务代码，但使用独立的数据源。同一时间只运行一种配置。现有内部配置值 APP_MODE=local 和脚本名称保持不变；“单用户”是文档中的用户模型名称。

## 通用环境与依赖

### 环境要求

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Chrome、Edge 或 Chromium，用于源码模式的 PDF 导出
- Poppler，视觉快照 Skill 需要其中的 `pdfinfo` 和 `pdftoppm`；请将其可执行文件目录加入系统 `PATH`，或通过 `POPPLER_PATH` 指定 Poppler 的 `bin` 目录
- 多用户源码测试还需要已安装的 MySQL 8.x

本交付方式不要求 Docker、WSL 或 Hyper-V 虚拟网卡。

### 安装项目依赖

在项目根目录执行：

~~~powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r backend\requirements.lock.txt

Set-Location frontend
npm ci
Set-Location ..
~~~

不要提交 .env、.env.multi_user、.env.docker 或任何真实密钥。

## 单用户源码测试

### 配置

复制单用户配置模板：

~~~powershell
Copy-Item .env.example .env
~~~

单用户配置应使用 SQLite 和回环地址：

~~~dotenv
APP_MODE=local
LOCAL_USER_EMAIL=local@localhost
DATABASE_URL=sqlite:///./data/resumebranch.db
LOCAL_EXPORT_DIR=./output/resumes
HOST=127.0.0.1
~~~

如需 AI 对话或简历解析，在 .env 或页面的 API 设置中填写对应配置。单用户编辑、版本管理和导出不依赖 LLM 密钥。

### 启动、停止与验活

启动：

~~~powershell
.\scripts\start_local.cmd
~~~

访问 http://127.0.0.1:5173。停止前端和后端：

~~~powershell
.\scripts\stop_app.cmd
~~~

检查运行配置：

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
~~~

预期包含：

~~~text
app_mode: local
authentication_required: false
database_backend: sqlite
local_export_enabled: true
~~~

单用户数据主要位于 data/，导出文件位于 output/resumes/。备份前先停止后端，再复制整个 data/ 和 output/resumes/ 目录。

## 多用户源码测试

### 准备 MySQL

使用 MySQL Workbench 或管理员命令行创建数据库和应用账号：

~~~sql
CREATE DATABASE resume_assistant
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER 'resume_app'@'127.0.0.1'
  IDENTIFIED BY 'replace-with-your-database-password';

GRANT ALL PRIVILEGES
  ON resume_assistant.*
  TO 'resume_app'@'127.0.0.1';

FLUSH PRIVILEGES;
~~~

如果数据库或账号已经存在，只需确认账号权限和密码正确。可用以下命令查看 MySQL 服务名：

~~~powershell
Get-Service *MySQL*
~~~

如果服务名不是 MySQL84，启动前设置实际服务名：

~~~powershell
$env:MYSQL_SERVICE_NAME = '实际的服务名'
~~~

### 配置

复制多用户配置模板：

~~~powershell
Copy-Item .env.multi_user.example .env.multi_user
~~~

至少检查以下配置：

~~~dotenv
APP_MODE=multi_user
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=替换为管理员密码

MYSQL_DATABASE=resume_assistant
MYSQL_USER=resume_app
MYSQL_PASSWORD=替换为 MySQL 应用账号密码
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
~~~

JWT 密钥必须至少 32 个字符。管理员可使用邮箱或专用账号名登录，普通用户必须使用邮箱注册和登录。真实密码、JWT 密钥和 LLM API Key 不得提交到 Git。

### 启动、停止与验活

一键启动：

~~~cmd
scripts\start_multi_user.cmd
~~~

脚本会检查 MySQL 服务、验证数据库连接、启动多用户后端和共用前端，并确认后端处于 multi_user + mysql 配置。

分别启动：

~~~cmd
scripts\start_mysql.cmd
scripts\start_backend_multi_user.cmd
scripts\start_frontend.cmd
~~~

停止前端和后端：

~~~cmd
scripts\stop_app.cmd
~~~

停止 MySQL：

~~~cmd
scripts\stop_mysql.cmd
~~~

检查运行配置：

~~~powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/app/config
~~~

预期包含：

~~~text
app_mode: multi_user
authentication_required: true
database_backend: mysql
~~~

### 多用户验收

至少验证以下流程：

1. 管理员登录并创建邀请码。
2. 普通用户使用邮箱和邀请码注册、登录。
3. 管理员可以使用管理员配置；普通用户不能访问管理员接口和 API 设置。
4. 两个普通用户只能看到各自的简历、岗位版本和对话数据。
5. 同一账号在另一设备重新登录后，旧会话失效。

## 与其他交付方式的边界

- Windows 单用户安装包：见 [Windows 单用户安装](windows-single-user-installation.md)。安装包不要求用户配置 Python、Node.js 或 npm。
- 多用户 Docker 部署：见 [多用户 Docker 部署](docker-multi-user-deployment.md)。Docker 文档不属于本源码脚本测试流程。
