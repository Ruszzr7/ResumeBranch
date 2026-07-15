# DeepAgents 部署指南

## 目录

- [系统架构](#系统架构)
- [前提条件](#前提条件)
- [快速部署](#快速部署)
- [详细配置](#详细配置)
- [HTTPS 证书配置](#https-证书配置)
- [运维管理](#运维管理)
- [故障排查](#故障排查)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       阿里云 ECS (Ubuntu)                    │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                   Docker Compose                     │   │
│   │                                                    │   │
│   │   ┌──────────────┐  ┌──────────────┐              │   │
│   │   │    Nginx     │  │   Backend    │              │   │
│   │   │  (80, 443)   │◄─┤  (8000)      │              │   │
│   │   │  + SSL       │  │              │              │   │
│   │   └──────────────┘  └──────────────┘              │   │
│   │          │                                           │   │
│   │          ▼                                           │   │
│   │   ┌──────────────┐                                  │   │
│   │   │   Frontend   │  (Vue.js 静态文件)               │   │
│   │   └──────────────┘                                  │   │
│   │                                                    │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                              │
│   数据持久化: ./data (SQLite)                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 前提条件

### 1. 服务器要求

| 配置项 | 最低要求 | 推荐配置 |
|--------|----------|----------|
| CPU | 1 核 | 2 核 |
| 内存 | 1 GB | 2 GB |
| 带宽 | 1 Mbps | 5 Mbps |
| 磁盘 | 20 GB | 50 GB SSD |

### 2. 服务器已安装

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

### 3. 域名配置

1. 在阿里云域名控制台添加 A 记录：
   - 记录类型: A
   - 主机记录: @ (或 www)
   - 记录值: 你的 ECS 公网 IP
   - TTL: 600

2. 等待 DNS 生效（通常 10-60 分钟）

---

## 快速部署

### 步骤 1: 服务器准备

```bash
# 登录服务器
ssh your_username@your_server_ip

# 创建部署目录
mkdir -p ~/deepagents
cd ~/deepagents

# 创建必要目录
mkdir -p data nginx/ssl nginx/html
```

### 步骤 2: 获取代码

```bash
# 方法一: Git 克隆
git clone https://github.com/your-username/resume_assistant.git .
git checkout develop

# 方法二: 上传压缩包
# 本地打包: tar -czvf deepagents.tar.gz .
# 上传到服务器并解压
```

### 步骤 3: 配置环境变量

```bash
# 创建环境变量文件
cat > .env << 'EOF'
# JWT 配置
JWT_SECRET_KEY=your-super-secret-jwt-key-here

# LLM API 配置
LLM_API_KEY=your-openai-api-key
BASE_URL=https://api.openai.com/v1

# Tavily 搜索 API（可选）
TAVILY_API_KEY=your-tavily-api-key

# 服务器配置
DOMAIN=your-domain.com
EOF

# 生成强随机密钥
openssl rand -base64 32
```

### 步骤 4: 部署服务

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 步骤 5: 验证部署

```bash
# 测试后端 API
curl http://localhost:8000/health

# 测试前端页面
curl http://localhost/

# 查看端口监听
netstat -tlnp | grep -E ':(80|443|8000)'
```

---

## 详细配置

### 1. docker-compose.yml

```yaml
version: '3.8'

services:
  # 前端构建服务
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: deepagents-frontend:latest
    container_name: deepagents-frontend
    restart: unless-stopped
    volumes:
      - ./nginx/html:/usr/share/nginx/html:ro
    depends_on:
      - backend

  # 后端 API 服务
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    image: deepagents-backend:latest
    container_name: deepagents-backend
    ports:
      - "127.0.0.1:8000:8000"  # 只监听本地，Nginx 代理访问
    volumes:
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///./data/deepagents.db
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - USE_SQLITE_CHECKPOINTER=true
      - LLM_API_KEY=${LLM_API_KEY}
      - BASE_URL=${BASE_URL:-https://api.openai.com/v1}
      - TAVILY_API_KEY=${TAVILY_API_KEY}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Nginx 反向代理
  nginx:
    image: nginx:alpine
    container_name: deepagents-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/html:/usr/share/nginx/html:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped

volumes:
  data:
```

### 2. 前端 Dockerfile

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package*.json ./
RUN npm ci

# 复制源代码
COPY . .

# 构建生产版本
ENV NODE_ENV=production
RUN npm run build

# 生产镜像
FROM nginx:alpine

# 复制构建文件
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 3. 前端 nginx.conf

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Vue Router History 模式支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理 - 转发到后端
    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # WebSocket 支持（如果需要）
    location /ws/ {
        proxy_pass http://backend:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

### 4. 后端 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（WeasyPrint 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libharfbuzz0a \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p data && touch data/deepagents.db

EXPOSE 8000

# 使用 Gunicorn（生产环境推荐）
CMD ["gunicorn", "mcp_service_simple:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-"]
```

### 5. 更新 requirements.txt

```
# 确保包含生产环境依赖
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
gunicorn>=21.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
aiosqlite>=0.19.0
langgraph>=0.0.20
weasyprint>=60.0
openai>=1.0.0
python-multipart>=0.0.6
```

---

## HTTPS 证书配置

### 方案一：使用 Certbot 自动获取（推荐）

#### 1. 安装 Certbot

```bash
# Ubuntu
sudo apt update
sudo apt install certbot python3-certbot-nginx

# 验证安装
certbot --version
```

#### 2. 获取证书

```bash
# 交互式获取（推荐）
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 或使用 DNS 验证（适用于没有 80 端口的服务器）
sudo certbot certonly --manual --preferred-challenges dns -d your-domain.com
```

#### 3. 自动续期

```bash
# 测试续期
sudo certbot renew --dry-run

# 添加 crontab 任务
sudo crontab -e
# 添加以下行：
0 0,12 * * * certbot renew --quiet
```

#### 4. 更新 Nginx 配置

```nginx
# nginx/nginx.conf
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # 重定向到 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL 安全配置
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    
    # 现代加密套件
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;
    
    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/your-domain.com/chain.pem;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # 其他配置...
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 方案二：使用阿里云 SSL 证书（免费）

1. 登录阿里云 SSL 证书控制台
2. 申请免费 DV 证书
3. 下载 Nginx 版本
4. 上传到服务器 `nginx/ssl/` 目录
5. 配置：

```nginx
ssl_certificate /etc/nginx/ssl/domain.pem;
ssl_certificate_key /etc/nginx/ssl/domain.key;
```

### 方案三：自签名证书（测试用）

```bash
# 生成自签名证书
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/server.key \
  -out nginx/ssl/server.crt \
  -subj "/C=CN/ST=Beijing/L=Beijing/O=DeepAgents/CN=your-domain.com"

# 警告：仅用于测试环境
```

---

## 运维管理

### 日常操作

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f
docker-compose logs -f backend  # 只看后端日志

# 查看实时状态
docker stats

# 更新并重启
docker-compose pull
docker-compose up -d --no-deps backend
```

### 备份与恢复

```bash
# 备份数据库
cp data/deepagents.db data/deepagents.db.backup.$(date +%Y%m%d)

# 自动备份脚本
cat > ~/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=~/backups
mkdir -p $BACKUP_DIR

# 备份数据库
cp ~/deepagents/data/deepagents.db $BACKUP_DIR/deepagents_$DATE.db

# 保留最近 7 天备份
find $BACKUP_DIR -name "*.db" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/deepagents_$DATE.db"
EOF

chmod +x ~/backup.sh

# 添加定时任务
crontab -e
# 添加：
0 3 * * * ~/backup.sh
```

### 日志管理

```bash
# 查看后端日志
docker-compose logs backend | tail -100

# 实时日志
docker logs -f deepagents-backend

# 清理日志文件
# 修改 docker-compose.yml 添加日志大小限制
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 系统监控

```bash
# 查看资源使用
docker stats

# 查看磁盘使用
df -h
du -sh ~/deepagents/*

# 查看服务健康状态
curl http://localhost/health
curl http://localhost/api/v1/users/me  # 需要认证
```

---

## 故障排查

### 常见问题

#### 1. 后端启动失败

```bash
# 查看错误日志
docker-compose logs backend

# 常见错误：
# - 端口被占用: lsof -i:8000
# - 数据库权限: chmod 777 data/
# - 环境变量缺失: 检查 .env 文件
```

#### 2. 前端页面空白

```bash
# 检查前端构建
docker logs deepagents-frontend

# 检查 Nginx 配置
docker exec deepagents-nginx nginx -t

# 检查静态文件
docker exec deepagents-nginx ls -la /usr/share/nginx/html/
```

#### 3. API 请求超时

```bash
# 检查后端状态
curl http://localhost:8000/health

# 检查 LLM API 配置
docker exec deepagents-backend env | grep API

# 检查网络连接
docker exec deepagents-backend ping api.openai.com
```

#### 4. 数据库错误

```bash
# 检查数据库文件
ls -la data/

# 重置数据库（危险！）
rm data/deepagents.db
docker-compose restart backend
```

#### 5. SSL 证书问题

```bash
# 检查证书是否过期
openssl x509 -enddate -noout -in /etc/letsencrypt/live/your-domain.com/fullchain.pem

# 手动续期
sudo certbot renew

# 检查证书权限
sudo chmod 600 /etc/letsencrypt/live/your-domain.com/privkey.pem
```

### 调试模式

```bash
# 后端开启调试模式
# 在 docker-compose.yml 中添加：
environment:
  - DEBUG=true

# 或直接进入容器
docker exec -it deepagents-backend bash

# 查看 Python 日志
tail -f /var/log/app.log
```

### 重置部署

```bash
# 危险！此操作会删除所有数据
docker-compose down
rm -rf data/*
docker-compose up -d --build
```

---

## 性能优化

### 1. Docker 优化

```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 2. Nginx 优化

```nginx
# 增加文件描述符限制
worker_rlimit_nofile 65535;

events {
    worker_connections 10240;
}

http {
    # 开启缓存
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m inactive=60m;
}
```

### 3. 数据库优化

```python
# 在启动时添加索引
# 连接到 SQLite
sqlite3 data/deepagents.db

# 添加常用索引
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_resumes_user_id ON resumes(user_id);
```

---

## 安全建议

1. **定期更新**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

2. **防火墙配置**
   ```bash
   sudo ufw allow 80
   sudo ufw allow 443
   sudo ufw allow 22
   sudo ufw enable
   ```

3. **监控异常**
   ```bash
   # 查看登录日志
   tail -f /var/log/auth.log
   
   # 查看 Docker 事件
   docker events --filter 'container=deepagents-backend'
   ```

---

## 联系与支持

如有问题，请检查：
1. 日志文件：`docker-compose logs`
2. 阿里云安全组：确保 80/443 端口开放
3. 域名解析：`dig your-domain.com`
