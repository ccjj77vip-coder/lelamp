# ============================================================
#  LeLamp Docker Image — Raspberry Pi (ARM64) 专用
#  基础: Python 3.13-slim-bookworm
#  包含: OpenCV, Flask, 全部硬件驱动依赖
# ============================================================

FROM python:3.13-slim-bookworm

LABEL maintainer="LeLamp Team"
LABEL description="LeLamp embodied AI desk lamp — Raspberry Pi Docker image"

# ---- 1. 系统级依赖 ----
# OpenCV 运行时库 + 音频工具 + 串口 + GPIO
RUN apt-get update && apt-get install -y --no-install-recommends \
        # OpenCV 运行时依赖
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        # 音频: mpg123 播放 TTS, alsa-utils 录音/调音量
        mpg123 \
        alsa-utils \
        # PyAudio 编译依赖
        portaudio19-dev \
        # RPi.GPIO / NeoPixel 编译依赖
        gcc \
        python3-dev \
        libgpiod2 \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Python 依赖 ----
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
