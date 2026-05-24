# GoalFlow 容器镜像
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ssh \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制项目文件
COPY pyproject.toml README.md ./
COPY goalflow/ ./goalflow/
COPY config/ ./config/

# 安装依赖
RUN uv sync --no-dev

# 暴露 API 端口
EXPOSE 8000

# 默认启动 API 服务
CMD ["uv", "run", "uvicorn", "goalflow.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
