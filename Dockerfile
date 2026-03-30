# ============================================================
#  LeLamp Docker Image — Raspberry Pi (ARM64) 专用
#  基础: Python 3.13-slim-bookworm
#  包含: OpenCV, Flask, 全部硬件驱动依赖
# ============================================================

FROM python:3.13-slim-bookworm

LABEL maintainer="LeLamp Team"
LABEL description="LeLamp embodied AI desk lamp — Raspberry Pi Docker image"

# ---- 1. 系统级依赖 (使用清华 apt 镜像加速) ----
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        mpg123 \
        alsa-utils \
        portaudio19-dev \
        gcc \
        python3-dev \
        libgpiod2 \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Python 依赖 (使用清华 pip 镜像 + piwheels 预编译) ----
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --extra-index-url https://www.piwheels.org/simple \
        -r requirements.txt

# ---- 3. 拷贝项目代码 ----
COPY . .

# 确保运行时目录存在
RUN mkdir -p /app/photos

# ---- 4. 运行配置 ----
# Flask dashboard 端口 (main.py:5000, showcase_master.py:8080)
EXPOSE 5000 8080

# 不缓冲 Python 输出, 方便 docker logs 实时看日志
ENV PYTHONUNBUFFERED=1

# 默认入口: main.py (日常模式)
# 展示模式: docker run ... lelamp python showcase_master.py
CMD ["python", "main.py"]
