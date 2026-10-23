FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    DB_PATH=/data/data.db

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# SQLite 文件放在挂载卷里，容器重建后缓存和任务记录不丢
VOLUME ["/data"]
EXPOSE 8000

# 任务线程池在进程内，只跑 1 个 worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
