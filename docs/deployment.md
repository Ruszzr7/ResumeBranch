# 多人自托管部署（可选）

多人版保留项目原有的登录、注册、邀请码、JWT 和 MySQL 能力，适用于内网、个人服务器或受控环境中的多账号演示。它与本地版共用一套前后端业务代码，通过部署配置选择，不提供页面内运行模式开关。

> 当前实现适合作为可部署的开源/作品集版本，但不宣称已经满足开放公网的完整生产安全要求。若直接面向公众，还需结合网关增加 HTTPS、限流、登录审计、密码找回、邮件验证和更完整的安全运维。

## 推荐拓扑

```text
浏览器
  └─ HTTP/HTTPS → 前端 Nginx :8080
                    ├─ 静态 Vue 页面
                    └─ /api、/auth 等 → FastAPI :8000
                                          └─ MySQL 8.4 :3306
```

Compose 默认不向宿主机暴露 MySQL 和后端端口，浏览器只访问 Nginx。业务表由 SQLAlchemy 初始化，管理员账号在后端容器启动前自动创建或升级为管理员。

## 前提条件

- Docker Engine 24+
- Docker Compose v2
- 至少 2 GB 可用内存
- 如跨公网访问，另行配置 HTTPS 反向代理和域名

## 配置

复制多人配置模板：

```bash
cp .env.multi_user.example .env.multi_user
```

至少修改：

```env
APP_MODE=multi_user
JWT_SECRET_KEY=<至少32字符的随机密钥>
ADMIN_EMAIL=<管理员邮箱>
ADMIN_PASSWORD=<管理员强密码>
MYSQL_PASSWORD=<仅含URL安全字符的数据库密码>
MYSQL_ROOT_PASSWORD=<不同的MySQL根密码>
```

可生成 JWT 密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

多人模式缺少合格 `JWT_SECRET_KEY` 时会拒绝启动，不再回退到仓库内置密钥。`CORS_ALLOW_ORIGINS` 默认留空，因为 Compose 通过 Nginx 同源访问；前后端分域部署时才填写逗号分隔的可信源。

`.env.multi_user` 已被 Git 忽略，不要提交、截图或粘贴其中的真实密钥。

## 启动

```bash
docker compose \
  --env-file .env.multi_user \
  -f docker-compose.multi-user.yml \
  up -d --build
```

查看状态和日志：

```bash
docker compose --env-file .env.multi_user -f docker-compose.multi-user.yml ps
docker compose --env-file .env.multi_user -f docker-compose.multi-user.yml logs -f backend
```

访问 `http://服务器地址:8080`。多人模式未登录时会进入暗色登录页；登录后回到与本地版相同的简历首页，右上角显示用户菜单。管理员菜单额外提供邀请码管理，普通用户请求管理员接口会返回 403。

停止容器但保留数据卷：

```bash
docker compose --env-file .env.multi_user -f docker-compose.multi-user.yml down
```

不要对已有数据的部署执行 `down -v`，该参数会删除 MySQL 和应用持久卷。

## 账号流程

1. 使用 `ADMIN_EMAIL` / `ADMIN_PASSWORD` 登录。
2. 从右上角用户菜单进入邀请码管理。
3. 创建一次性邀请码。
4. 新用户通过注册页填写邮箱、至少 8 位密码和邀请码。
5. 邀请码消费与用户创建在同一数据库事务中；普通用户不能读取或创建邀请码。

管理员身份存储在 `users.is_admin`，前端只负责显示入口，最终授权由后端检查。旧数据库启动时会自动补充该字段；配置中的管理员账号会被创建或升级，不会删除原用户数据。

## 数据与导出

多人版推荐 MySQL，持久数据位于 Compose 卷：

- `multi_user_mysql`：用户、简历、岗位版本、JD、对话等业务数据
- `multi_user_app_data`：上传原文件、模型配置和工作流检查点

本地 SQLite 与多人 MySQL 是独立数据源，项目不会自动双向迁移。切换配置不会删除任何一方，但也不会自动显示另一方的数据。

多人版导出默认只通过浏览器下载，不把每位用户的 PDF/DOCX 长期写入服务器文件系统，以降低隐私泄露和磁盘增长风险。文件名仍为 `简历组名_版本名_导出日期.ext`。

### 备份

业务数据应使用 `mysqldump` 或托管平台提供的 MySQL 备份能力；同时备份 `multi_user_app_data` 卷。恢复演练应在独立环境中执行，确认管理员、用户隔离、上传原件和简历版本均可读取。

## 验收

```bash
curl -X POST http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/app/config
```

预期配置包含：

- `app_mode: multi_user`
- `authentication_required: true`
- `account_management_enabled: true`
- `database_backend: mysql`
- `local_export_enabled: false`

还应人工验证：

- 未登录访问首页会跳转登录页。
- 管理员可创建邀请码；普通用户访问邀请码接口得到 403。
- 用户 A 无法看到或访问用户 B 的简历项目与岗位版本。
- 退出后 Token 和用户缓存被清除，再访问业务页回到登录页。
- 导出只触发当前浏览器下载，服务器不出现 `output/resumes` 用户文件堆积。

自动化双模式检查见 [测试清单](testing.md)。

## 安全边界

- JWT 默认 24 小时有效，可通过 `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` 调整。
- 密码使用 bcrypt 哈希，数据库不保存明文密码。
- CORS 使用显式允许列表，不允许通配来源携带凭据。
- MySQL 仅在 Compose 内部网络可达。
- 当前前端将 Bearer Token 保存在 `localStorage`，因此必须持续防止 XSS，并建议公开部署时进一步评估 HttpOnly Cookie、刷新 Token 和会话撤销机制。
- 本项目不会自动配置公网防火墙、TLS 证书、WAF、备份保留或告警。

Windows 本机个人使用请优先采用 [本地 SQLite 部署](local-deployment.md)，多人版不提供 Windows 一键启动脚本。
