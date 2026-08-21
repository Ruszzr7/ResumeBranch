# ResumeBranch Dockerfile
# 多用户版 - 简历助手

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装 Chromium、PDF 页面转换工具、健康检查工具和中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-sandbox \
    curl \
    fonts-noto-cjk \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制锁定依赖，保证不同时间和机器上的镜像依赖一致
COPY backend/requirements.lock.txt ./backend/requirements.lock.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r backend/requirements.lock.txt

# 复制应用代码
COPY . .

# Chromium 由非 root 用户运行，以保留浏览器沙箱。
RUN useradd --create-home --uid 10001 resumeapp \
    && mkdir -p data output/resumes \
    && chown -R resumeapp:resumeapp /app

ENV RESUME_PDF_BROWSER=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1
USER resumeapp

# 暴露端口
EXPOSE 8000

# 使用 Gunicorn（生产环境推荐）
CMD ["gunicorn", "backend.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "1", "--access-logfile", "-", "--error-logfile", "-"]
