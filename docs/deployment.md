# Docker 多人自托管部署

本文说明如何在 Linux 服务器、支持 Docker 的开发机或 CI 环境中运行多用户版。Docker 入口只用于 `multi_user + MySQL`，不用于本地 SQLite 模式。

当前项目的默认本地方案仍然是：

- Windows 本地单用户：SQLite + `scripts/start_local.cmd`
- Windows 本机多用户：原生 MySQL + `scripts/start_multi_user.cmd`
- Linux/服务器多用户：Docker Compose + MySQL 8.4

Docker Compose 不要求宿主机安装 MySQL、Python、Node.js、Chromium 或 Poppler。后端镜像自带 Chromium、中文字体和 PDF 页面转换工具，前端容器使用 Nginx 提供静态文件并代理 API。

## 部署拓扑

```text
浏览器
  │
  │ HTTP/HTTPS
  ▼
frontend 容器（Nginx，宿主机 8080）
  ├── Vue 静态文件
  └── API/WebSocket 代理
          │
          ▼
backend 容器（FastAPI + Gunicorn + Chromium）
          │
          ▼
mysql 容器（MySQL 8.4，仅 Compose 内部网络）
```

Compose 默认只向宿主机暴露前端的 `8080` 端口，不暴露后端 `8000` 和 MySQL `3306`。

## 前提条件

- Docker Engine 24+
- Docker Compose v2
- Linux 主机或其他支持 Docker 的环境
- 至少 2 GB 可用内存；首次构建需要更多空间
- 如果要开放公网访问，还需要域名、HTTPS 反向代理、防火墙和备份策略

检查版本：

```bash
docker version
docker compose version
```

当前网络环境禁止启用 Hyper-V/WSL 虚拟网卡时，不要在对应 Windows 电脑上启动 Docker Desktop。可以使用 Linux 服务器、另一台支持 Docker 的机器，或提交代码后让 GitHub Actions 执行本文的 CI 验收。

### 无网络环境的操作边界

可以在无网络环境下阅读教程并执行配置检查：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml config --quiet
```

但第一次构建通常不能离线完成，因为 Docker 可能需要下载 MySQL 基础镜像、Debian/Chromium 软件包、Python 依赖和前端 npm 依赖。只有目标机器已经缓存了所需镜像和完整构建层时，才可以直接执行不带 `--build` 的 `up -d`。

如果目标机器不能联网，可以在另一台可联网且支持 Docker 的机器上预构建并导出镜像：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml pull mysql
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml build
docker save -o resumebranch-images.tar \
  mysql:8.4 resumebranch-backend:multi-user resumebranch-frontend:multi-user
```

将项目文件、已填写的 `.env.docker` 和镜像归档传到离线机器后执行：

```bash
docker load -i resumebranch-images.tar
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml up -d
```

不要在你的 Windows 网络环境中为了执行这套部署而重新启用会导致断网的虚拟网卡；离线机器只适合使用已经导入的镜像，GitHub Actions 则需要网络。

## 配置环境

复制 Docker 专用模板：

```bash
cp .env.docker.example .env.docker
```

至少修改：

```dotenv
APP_MODE=multi_user
JWT_SECRET_KEY=替换为至少32字符的随机密钥
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=替换为管理员强密码

MYSQL_DATABASE=resume_assistant
MYSQL_USER=resume_app
MYSQL_PASSWORD=替换为URL安全的应用数据库密码
MYSQL_ROOT_PASSWORD=替换为不同的URL安全根密码
```

生成 JWT 密钥：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`MYSQL_PASSWORD` 和 `MYSQL_ROOT_PASSWORD` 会参与 Compose 连接地址生成，建议只使用字母、数字和少量 URL 安全符号。真实的 `.env.docker` 已被 Git 忽略，不要提交、截图或粘贴其中的密钥。

`CORS_ALLOW_ORIGINS` 通过前端 Nginx 同源访问时保持为空。只有前后端分域时，才填写逗号分隔的可信来源。

## 配置检查

在启动容器前先执行：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml config
```

该命令只解析 Compose 配置，不会启动容器。检查输出中应确认：

- 服务为 `mysql`、`backend`、`frontend`。
- 后端的 `DATABASE_URL` 指向 `mysql:3306`。
- 后端和 MySQL 没有宿主机端口映射。
- 前端映射宿主机 `8080` 到容器 `80`。
- 数据卷包含 MySQL 数据和应用数据。
- 没有把 `.env.docker` 或本地 `data/` 打进镜像上下文。

## 启动

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml up -d --build
```

Compose 会按依赖顺序：

1. 启动 MySQL 8.4。
2. 等待 MySQL 健康检查通过。
3. 启动后端，初始化业务表并创建或升级管理员。
4. 等待后端健康检查通过。
5. 启动前端 Nginx。

查看状态：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml ps
```

查看后端日志：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml logs -f backend
```

访问：

```text
http://服务器地址:8080
```

如果前面已经配置了 HTTPS 反向代理，则应通过域名访问，而不是直接把 `8080` 暴露到公网。

## 运行验证

健康检查：

```bash
curl -X POST http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/app/config
```

预期配置包含：

```text
app_mode: multi_user
authentication_required: true
account_management_enabled: true
database_backend: mysql
local_export_enabled: false
```

人工验收：

1. 未登录访问首页时进入暗色登录页。
2. 使用 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 登录。
3. 管理员可以打开邀请码管理。
4. 管理员创建一次性邀请码。
5. 普通用户使用邮箱和邀请码注册。
6. 普通用户使用邮箱登录。
7. 在另一台设备或另一套浏览器配置中再次登录同一账号，旧登录应在下一次请求时失效；同一浏览器的多个标签页继续共享当前登录。
8. 普通用户访问邀请码接口得到 403。
9. 创建两个用户，确认双方只能看到自己的项目和简历版本。
10. 退出登录后重新访问业务页，回到登录页。
11. 进行一次 PDF/DOCX 导出，并触发一次简历视觉快照，确认 Chromium 和 PDF 页面转换均可用。

管理员可以使用邮箱或专用账号名登录；普通用户注册和登录必须使用邮箱。

升级到带服务端会话校验的版本后，升级前签发的旧 Token 不含会话标识，会被安全拒绝；用户重新登录一次即可。新登录会替换该账号此前的活跃会话，但同一浏览器内共享当前 Token 的多个标签页可继续使用。

## 停止、重启与数据

停止容器但保留数据卷：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml down
```

重新启动：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml up -d
```

不要对已有数据的环境使用：

```bash
docker compose down -v
```

`down -v` 会删除 Compose 管理的 MySQL 和应用数据卷。

持久化内容：

- `multi_user_mysql`：用户、简历、岗位版本、JD、对话等业务数据。
- `multi_user_app_data`：上传原件、模型配置和 LangGraph 检查点。

本地 SQLite 与 Docker MySQL 相互独立，项目不会自动迁移或合并两边数据。

## 备份建议

备份 MySQL：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml exec -T mysql \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines --events "$MYSQL_DATABASE"' > resume_assistant.sql
```

执行备份时，`MYSQL_ROOT_PASSWORD` 和 `MYSQL_DATABASE` 应从安全的 shell 环境或密码管理方式读取，不要写入脚本并提交。

同时备份应用数据卷中的：

- `source_documents/`
- `llm_profiles.json`
- `langgraph_checkpoints.sqlite`

恢复前应在独立环境中演练，确认管理员、用户隔离、上传原件和简历版本均可读取。

## 常见问题

### 后端不断重启

查看日志：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml logs --tail=200 backend
```

重点检查：

- JWT 密钥是否至少 32 个字符。
- MySQL 密码是否正确。
- MySQL 密码是否包含未编码的 URL 特殊字符。
- MySQL 健康检查是否通过。
- LLM 配置是否缺少必要密钥。

### 前端能打开但接口失败

确认：

- `backend` 健康检查为 `healthy`。
- 浏览器访问的是前端 `8080`，不是后端 `8000`。
- 没有修改 Nginx 中的 `proxy_pass http://backend:8000`。
- WebSocket 路径仍然使用 `/ws/`。

### PDF 导出失败

查看后端日志并确认镜像中 Chromium 存在：

```bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml exec backend \
  /usr/bin/chromium --version
```

容器不依赖宿主机 Chrome；宿主机是否安装浏览器不会改变容器内 PDF 渲染。

### 数据丢失风险

不要使用 `down -v`，也不要删除 Compose 项目对应的数据卷。生产环境还应定期执行 MySQL 备份，并保存应用数据卷。

## 自动验收

项目提供 Linux GitHub Actions 工作流，对 Docker Compose 进行：

- Compose 配置解析。
- 前后端镜像构建。
- MySQL、后端和前端健康检查。
- 管理员登录、邀请码、邮箱注册和用户隔离检查。
- 核心任务、会话、排版和工作流 API 的 Nginx 代理检查。
- Chromium PDF 导出、Poppler 页面转换和容器内视觉快照检查。
- 前端工作区路由刷新仍返回 SPA 页面。
- 容器重启后的数据持久化检查。
- 临时环境清理。

工作流文件为：

```text
.github/workflows/docker-multi-user.yml
```

Docker 部署只有在该 Linux CI 或实际 Linux 主机完成上述验收后，才应视为可用。

## 安全边界

当前配置适合内网、个人服务器和受控演示环境，不等同于完整公网生产方案。公开部署前仍需补充：

- HTTPS/TLS 和安全响应头。
- 防火墙、反向代理和访问控制。
- 登录限流、审计、密码找回和邮件验证。
- JWT 刷新、更安全的 Cookie 策略，以及面向公网的异常登录检测。
- MySQL 与应用数据的备份保留和恢复演练。
- 日志、监控和告警。
