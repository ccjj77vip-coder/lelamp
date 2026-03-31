#!/bin/bash
# ============================================================
#  LeLamp 一键部署脚本 — 树莓派专用
#  用法: bash deploy.sh
#  功能: 自动安装 Docker、配置硬件、构建镜像、首次启动
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "========================================"
echo "  LeLamp 一键部署脚本 v2.0"
echo "========================================"
echo ""

# ---- 1. 检查是否为树莓派 ----
if ! grep -q "Raspberry\|BCM" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}[警告] 未检测到树莓派硬件，部分功能可能不可用${NC}"
fi

# ---- 2. 系统依赖 ----
echo -e "${YELLOW}[系统] 等待 apt 锁释放...${NC}"
while sudo fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend 2>/dev/null; do
    echo -e "  ${YELLOW}其他进程正在使用 apt，等待 5 秒...${NC}"
    sleep 5
done

# 配置 apt 国内镜像源（加速系统包下载）
if ! grep -q "mirrors.tuna.tsinghua.edu.cn" /etc/apt/sources.list.d/debian.sources 2>/dev/null \
   && ! grep -q "mirrors.tuna.tsinghua.edu.cn" /etc/apt/sources.list 2>/dev/null; then
    echo -e "${YELLOW}[系统] 配置 apt 清华镜像源...${NC}"
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then
        sudo sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources
    fi
    if [ -f /etc/apt/sources.list.d/raspi.list ]; then
        sudo sed -i 's|archive.raspberrypi.org|mirrors.tuna.tsinghua.edu.cn/raspberrypi|g' /etc/apt/sources.list.d/raspi.list
        sudo sed -i 's|archive.raspberrypi.com|mirrors.tuna.tsinghua.edu.cn/raspberrypi|g' /etc/apt/sources.list.d/raspi.list
    fi
    echo -e "${GREEN}[OK] apt 镜像源已切换到清华${NC}"
fi

echo -e "${YELLOW}[系统] 检查基础依赖...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq curl git python3 > /dev/null 2>&1
echo -e "${GREEN}[OK] 系统依赖就绪${NC}"

# ---- 3. 安装 Docker ----
if command -v docker &>/dev/null; then
    echo -e "${GREEN}[OK] Docker 已安装: $(docker --version | head -1)${NC}"
else
    echo -e "${YELLOW}[安装] 正在安装 Docker (使用清华镜像源)...${NC}"
    sudo apt-get install -y -qq ca-certificates curl gnupg > /dev/null 2>&1
    sudo install -m 0755 -d /etc/apt/keyrings
    # 使用清华镜像源，避免国内无法访问 download.docker.com
    curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1
    sudo usermod -aG docker "$USER"
    echo -e "${GREEN}[OK] Docker 安装完成${NC}"
fi

# 确保 docker compose 可用
if ! docker compose version &>/dev/null 2>&1; then
    echo -e "${YELLOW}[安装] 正在安装 docker-compose-plugin...${NC}"
    sudo apt-get install -y -qq docker-compose-plugin > /dev/null 2>&1
fi
echo -e "${GREEN}[OK] Docker Compose: $(docker compose version --short 2>/dev/null || echo 'ready')${NC}"

# ---- 4. 配置 Docker 国内镜像源 (防止拉取基础镜像 429 限流) ----
DAEMON_JSON="/etc/docker/daemon.json"
if [ ! -f "$DAEMON_JSON" ] || ! grep -q "mirror" "$DAEMON_JSON" 2>/dev/null; then
    echo -e "${YELLOW}[配置] 设置 Docker 国内镜像加速...${NC}"
    sudo mkdir -p /etc/docker
    sudo tee "$DAEMON_JSON" > /dev/null <<'MIRROR_EOF'
{
    "registry-mirrors": [
        "https://docker.m.daocloud.io",
        "https://docker.1panel.live"
    ]
}
MIRROR_EOF
    sudo systemctl daemon-reload
    sudo systemctl restart docker
    echo -e "${GREEN}[OK] Docker 镜像加速已配置${NC}"
else
    echo -e "${GREEN}[OK] Docker 镜像加速已存在${NC}"
fi

# ---- 5. 开启 SPI (灯环 GPIO10 需要) ----
NEED_REBOOT=0
CONFIG_FILE=""
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if [ -n "$CONFIG_FILE" ]; then
    if grep -q "^dtparam=spi=on" "$CONFIG_FILE"; then
        echo -e "${GREEN}[OK] SPI 已启用${NC}"
    elif grep -q "^#dtparam=spi=on" "$CONFIG_FILE"; then
        echo -e "${YELLOW}[配置] 正在启用 SPI (灯环需要)...${NC}"
        sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG_FILE"
        echo -e "${GREEN}[OK] SPI 已启用 (重启后生效)${NC}"
        NEED_REBOOT=1
    else
        echo -e "${YELLOW}[配置] 添加 SPI 配置...${NC}"
        echo "dtparam=spi=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
        NEED_REBOOT=1
    fi
fi

# ---- 6. 开启音频 ----
if [ -n "$CONFIG_FILE" ]; then
    if ! grep -q "^dtparam=audio=on" "$CONFIG_FILE"; then
        echo -e "${YELLOW}[配置] 启用板载音频...${NC}"
        echo "dtparam=audio=on" | sudo tee -a "$CONFIG_FILE" > /dev/null
        NEED_REBOOT=1
    fi
fi

# ---- 7. 串口权限 (舵机 /dev/ttyUSB0) ----
if ! groups "$USER" | grep -q "dialout"; then
    echo -e "${YELLOW}[配置] 添加串口权限...${NC}"
    sudo usermod -aG dialout "$USER"
fi

# ---- 8. 重置校准数据 (新机器需要重新校准) ----
CALIB_FILE="$PROJECT_DIR/calibration.json"
HAS_HOME=0
if [ -f "$CALIB_FILE" ]; then
    HAS_HOME=$(python3 -c "
import json
try:
    d = json.load(open('$CALIB_FILE'))
    print(len(d.get('HOME_OFFSET', {})))
except:
    print(0)
" 2>/dev/null || echo "0")

    if [ "$HAS_HOME" -ge 5 ]; then
        echo -e "${GREEN}[OK] 检测到已有校准数据，保留${NC}"
    else
        echo -e "${YELLOW}[配置] 未检测到校准数据，初始化空配置${NC}"
        echo '{"HOME_OFFSET": {}, "CUSTOM_POSES": {}, "CUSTOM_DANCES": {}}' > "$CALIB_FILE"
    fi
else
    echo -e "${YELLOW}[配置] 创建空校准文件${NC}"
    echo '{"HOME_OFFSET": {}, "CUSTOM_POSES": {}, "CUSTOM_DANCES": {}}' > "$CALIB_FILE"
fi

# 确保照片目录存在
mkdir -p "$PROJECT_DIR/photos"

# ---- .env 文件检查 ----
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}[警告] 未找到 .env 文件，AI 对话功能需要 API 密钥${NC}"
    echo "  请创建: echo 'ZHIPU_API_KEY=你的密钥' > $PROJECT_DIR/.env"
fi

# ---- 9. 如果需要重启，先提示 ----
if [ "$NEED_REBOOT" = "1" ]; then
    echo ""
    echo -e "${YELLOW}========================================"
    echo "  硬件配置已更改，需要先重启树莓派！"
    echo "========================================${NC}"
    echo ""
    echo "  请执行:"
    echo "    sudo reboot"
    echo ""
    echo "  重启后再次运行本脚本完成部署:"
    echo "    cd $PROJECT_DIR && bash deploy.sh"
    echo ""
    exit 0
fi

# ---- 10. 构建 Docker 镜像 ----
echo ""
cd "$PROJECT_DIR"
IMAGE_TAR="$PROJECT_DIR/lelamp-image.tar.gz"
if [ -f "$IMAGE_TAR" ]; then
    echo -e "${YELLOW}[镜像] 检测到离线镜像文件，直接导入...${NC}"
    sudo docker load < "$IMAGE_TAR"
    echo -e "${GREEN}[OK] 镜像导入完成${NC}"
else
    echo -e "${YELLOW}[构建] 未找到离线镜像，开始构建 (首次约需10-20分钟)...${NC}"
    # 显式指定 compose 文件，避免 override.yml 被自动加载 (override 仅用于开发)
    sudo docker compose -f docker-compose.yml build
fi

# ---- 11. 启动服务 ----
echo ""
echo -e "${YELLOW}[启动] 正在启动 LeLamp...${NC}"
sudo docker compose -f docker-compose.yml down 2>/dev/null || true
# 清理可能残留的同名容器 (旧版 compose 或手动创建的)
if sudo docker inspect lelamp &>/dev/null; then
    echo -e "${YELLOW}[清理] 发现残留容器，强制移除...${NC}"
    sudo docker rm -f lelamp 2>/dev/null || true
fi
sudo docker compose -f docker-compose.yml up -d

# ---- 12. 等待容器启动 ----
echo -e "${YELLOW}[等待] 容器启动中...${NC}"
CONTAINER_UP=0
for i in $(seq 1 10); do
    if sudo docker compose -f docker-compose.yml ps | grep -q "running"; then
        CONTAINER_UP=1
        break
    fi
    sleep 2
done
if [ "$CONTAINER_UP" = "1" ]; then
    echo -e "${GREEN}[OK] 容器运行中${NC}"
else
    echo -e "${RED}[异常] 容器未正常启动，请检查日志:${NC}"
    echo "    sudo docker compose -f docker-compose.yml logs -f"
    exit 1
fi

# ---- 13. 设置开机自启 ----
SYSTEMD_FILE="/etc/systemd/system/lelamp.service"
if [ ! -f "$SYSTEMD_FILE" ]; then
    echo -e "${YELLOW}[配置] 设置开机自启...${NC}"
    sudo tee "$SYSTEMD_FILE" > /dev/null <<UNIT_EOF
[Unit]
Description=LeLamp AI Desk Lamp
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker compose -f $PROJECT_DIR/docker-compose.yml up -d
ExecStop=/usr/bin/docker compose -f $PROJECT_DIR/docker-compose.yml down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
UNIT_EOF
    sudo systemctl daemon-reload
    sudo systemctl enable lelamp.service
    echo -e "${GREEN}[OK] 开机自启已配置${NC}"
else
    echo -e "${GREEN}[OK] 开机自启已存在${NC}"
fi

# ---- 14. 初始化扬声器音量 ----
echo -e "${YELLOW}[音频] 拉满扬声器音量...${NC}"
# 找到扬声器声卡并拉满
for card in 0 1 2 3; do
    sudo docker compose -f docker-compose.yml exec -T lelamp amixer -c $card sset 'PCM' 100% >/dev/null 2>&1 || true
    sudo docker compose -f docker-compose.yml exec -T lelamp amixer -c $card sset 'Speaker' 100% >/dev/null 2>&1 || true
    sudo docker compose -f docker-compose.yml exec -T lelamp amixer -c $card sset 'Master' 100% >/dev/null 2>&1 || true
    sudo docker compose -f docker-compose.yml exec -T lelamp amixer -c $card sset 'Headphone' 100% >/dev/null 2>&1 || true
done
echo -e "${GREEN}[OK] 音量已拉满${NC}"

# ---- 15. 显示最终结果 ----
echo ""
echo -e "${GREEN}========================================"
echo "  LeLamp 部署完成！"
echo "========================================${NC}"
echo ""

# 获取本机 IP
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo -e "  控制台地址: ${GREEN}http://${LOCAL_IP}:5000${NC}"
echo ""

# 检查是否需要校准
if [ "$HAS_HOME" -lt 5 ] 2>/dev/null; then
    echo -e "${YELLOW}  ┌─────────────────────────────────────┐"
    echo "  │  首次部署 — 请完成校准              │"
    echo "  ├─────────────────────────────────────┤"
    echo "  │  1. 浏览器打开上方网页地址          │"
    echo "  │  2. 进入 ⚙️  系统调教               │"
    echo "  │  3. 点击 🔓 释放全部力矩            │"
    echo "  │  4. 用手掰到理想HOME位置            │"
    echo "  │  5. 点击 🎯 保存为HOME零点          │"
    echo "  │  6. sudo docker compose -f docker-compose.yml restart │"
    echo "  └─────────────────────────────────────┘${NC}"
    echo ""
fi

echo "  常用命令:"
echo "    查看日志:  sudo docker compose -f docker-compose.yml logs -f"
echo "    重启服务:  sudo docker compose -f docker-compose.yml restart"
echo "    停止服务:  sudo docker compose -f docker-compose.yml down"
echo "    更新代码:  git pull && sudo docker compose -f docker-compose.yml build && sudo docker compose -f docker-compose.yml up -d"
echo ""
echo -e "${GREEN}  部署成功！插上电就能用。${NC}"
echo ""
