# 多用户 Docker 部署版

本文对应第二种交付方式：从 GitHub 获取项目源码和 Docker Compose 配置，通过 Docker 运行多用户版本。该方式只支持 multi_user + MySQL，适用于本地部署验收或服务器部署，不用于单用户 SQLite 版本。

本文不说明 Windows 脚本和安装包。对应文档：

- [源码开发/测试版](source-development-testing.md)
- [Windows 单用户安装版](windows-single-user-installation.md)

## 部署组成

Docker Compose 启动三个服务：

~~~text
浏览器
  │
  ▼
frontend 容器：Nginx、Vue 静态文件、API/SSE 代理
  │
  ▼
backend 容器：FastAPI、Gunicorn、Chromium、Poppler
  │
  ▼
mysql 容器：MySQL 8.4
~~~

宿主机默认只暴露前端 8080 端口。后端 8000 和 MySQL 3306 只在 Compose 内部网络中使用。

## 适用环境

- Linux 服务器、支持 Docker 的开发机或 CI 环境
- Docker Engine 24+
- Docker Compose v2
- 至少 2 GB 可用内存；首次构建还需要镜像和依赖缓存空间

宿主机运行项目不需要单独安装 Python、Node.js、npm、MySQL、Chrome 或 Poppler。容器内已包含运行所需内容。生成随机 JWT 密钥时也可以使用系统已有的 Python 或 OpenSSL；这只是配置辅助工具，不是项目运行依赖。

Docker 可以在本地运行，用于验证多用户部署；正式公网使用还需要域名、HTTPS 反向代理、防火墙、密钥管理和备份策略。

## 获取源码与配置

从 GitHub 获取项目源码，进入项目根目录后复制 Docker 配置模板：

~~~bash
cp .env.docker.example .env.docker
~~~

至少修改以下配置：

~~~dotenv
APP_MODE=multi_user
JWT_SECRET_KEY=替换为至少32字符的随机密钥
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=替换为管理员强密码

MYSQL_DATABASE=resume_assistant
MYSQL_USER=resume_app
MYSQL_PASSWORD=替换为URL安全的应用数据库密码
MYSQL_ROOT_PASSWORD=替换为不同的URL安全根密码
~~~

生成 JWT 密钥（任选一种宿主机已有的工具）：

~~~bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

也可以使用 OpenSSL：

~~~bash
openssl rand -base64 48
~~~

真实的 .env.docker 不得提交到 Git。CORS_ALLOW_ORIGINS 通过前端 Nginx 同源访问时保持为空；只有前后端分域时才填写可信来源。

## 配置检查

启动前只解析 Compose 配置，不启动容器：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml config
~~~

检查以下内容：

- 服务包含 mysql、backend 和 frontend。
- backend 的数据库地址指向 Compose 内的 mysql:3306。
- frontend 将宿主机 8080 映射到容器 80。
- MySQL 和应用数据使用命名卷。
- 没有将真实配置或本地 data/ 打入镜像上下文。

## 启动

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml up -d --build
~~~

Compose 会依次启动 MySQL、后端和前端，并执行健康检查。查看状态和日志：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml ps

docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml logs -f backend
~~~

本地访问：

~~~text
http://127.0.0.1:8080
~~~

服务器访问时先使用服务器地址进行内网验收；配置 HTTPS 反向代理后再通过域名访问。

## 多用户验收

检查运行配置：

~~~bash
curl -X POST http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/app/config
~~~

预期包含：

~~~text
app_mode: multi_user
authentication_required: true
account_management_enabled: true
database_backend: mysql
local_export_enabled: false
~~~

至少完成以下验收：

1. 未登录访问首页时进入登录页。
2. 管理员登录并创建邀请码。
3. 普通用户使用邮箱和邀请码注册、登录。
4. 普通用户不能访问邀请码和管理员 API 设置。
5. 两个用户只能看到各自的简历、岗位版本和对话数据。
6. 同一账号在另一设备登录后，旧会话失效。
7. 完成一次 PDF/DOCX 导出和一次简历页面快照。
8. 重启容器后，用户、简历、上传文件和检查点仍然存在。

## 停止、重启与数据

停止容器但保留数据：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml down
~~~

重新启动：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml up -d
~~~

不要对已有数据的环境执行：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml down -v
~~~

down -v 会删除 Compose 管理的 MySQL 和应用数据卷。

主要持久化内容：

- `multi_user_mysql`：Compose 文件中的 MySQL 数据卷，保存用户、简历、岗位版本、JD 和对话。
- `multi_user_app_data`：Compose 文件中的应用数据卷，保存上传原件、模型配置和 LangGraph 检查点。实际 Docker 卷名可能带有 Compose 项目前缀。

多用户 Docker 数据与单用户 SQLite 数据相互独立，项目不会自动迁移或合并两边数据。

## 备份

备份 MySQL：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml exec -T mysql \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --routines --events "$MYSQL_DATABASE"' > resume_assistant.sql
~~~

同时备份应用数据卷中的 `source_documents/`、`llm_profiles.json` 和 `langgraph_checkpoints.sqlite`。可先查看实际卷名：

~~~bash
docker volume ls --filter name=multi_user_app_data
~~~

再按照实际卷名执行归档或使用 Docker Volume 备份工具。恢复前应在独立环境演练管理员、用户隔离、上传原件和简历版本。

## 公网部署前提

Docker 容器启动成功，只能说明多用户部署链路在当前环境通过了基础验收，不等于已经完成公网生产配置。正式上线前还需要：

- 将服务器 IP 解析到正式域名。
- 使用 Nginx、Caddy 或云负载均衡配置 HTTPS/TLS。
- 仅开放必要端口，避免直接暴露后端 8000 和 MySQL 3306。
- 使用强密码和随机 JWT 密钥，并限制配置文件权限。
- 建立 MySQL 与应用数据的定期备份、保留和恢复演练。
- 配置日志、监控、告警和故障恢复流程。

当前 Release 1.1.2 不提供在线更新器。重新部署前先备份 MySQL 和应用数据。

## 常见问题

### 后端不断重启

查看 backend 日志，重点检查 JWT 密钥长度、MySQL 密码、数据库地址和 MySQL 健康检查。

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml logs --tail=200 backend
~~~

### 前端能打开但接口失败

确认访问的是 frontend 的 8080 端口，backend 健康检查为 healthy，且 Nginx 仍然代理到 backend:8000。

### PDF 导出失败

容器使用内置 Chromium，不依赖宿主机浏览器。检查后端日志和容器内 Chromium：

~~~bash
docker compose --env-file .env.docker \
  -f docker-compose.multi-user.yml exec backend \
  /usr/bin/chromium --version
~~~

### 数据丢失风险

不要使用 down -v，不要删除 Compose 对应的数据卷，并按本页备份流程定期导出 MySQL 和应用数据。
