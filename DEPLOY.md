# LeLamp 部署指南

## 硬件准备

- 树莓派 4B/5（推荐 4GB 以上）
- USB 舵机控制板（接 `/dev/ttyUSB0`）
- USB 摄像头
- USB 扬声器 + USB 麦克风
- SD 卡（16GB 以上，推荐 32GB）

---

## 方法一：一键部署（全新机器，从零开始）

适用于：第一次部署，没有其他 LeLamp 机器可参考。

```bash
# 1. 获取代码
git clone https://github.com/ccjj77vip-coder/lelamp.git ~/run

# 2. 创建密钥文件
cat > ~/run/.env << 'EOF'
# ---- 智谱 AI (GLM 视觉/对话) ----
ZHIPU_API_KEY=你的智谱API密钥

# ---- 火山引擎 (TTS/ASR 语音服务) ----
VOLC_APP_ID=你的火山引擎AppID
VOLC_ACCESS_TOKEN=你的火山引擎AccessToken
VOLC_AK_ID=你的火山引擎AK_ID
VOLC_AK_SECRET=你的火山引擎AK_Secret

# ---- 阿里云 NLS (语音兜底) ----
ALI_AK_ID=你的阿里云AK_ID
ALI_AK_SECRET=你的阿里云AK_Secret
ALI_NLS_APP_KEY=你的阿里云NLS_AppKey
EOF

# 3. 一键部署
cd ~/run && bash deploy.sh
```

> 如果提示 "需要先重启树莓派"，执行 `sudo reboot`，重启后再跑一次 `bash deploy.sh`。
> 首次构建镜像约需 10-20 分钟。

---

## 方法二：拉取预编译镜像（最快，推荐）

适用于：已有一台部署好的机器，新机器想跳过构建直接用。

```bash
# 1. 获取代码
git clone https://github.com/ccjj77vip-coder/lelamp.git ~/run

# 2. 创建密钥文件（同方法一，或从已有机器拷贝）
#    如果能 SSH 到已有机器：
#    scp 用户名@已有机器IP:~/run/.env ~/run/.env

# 3. 运行部署脚本安装 Docker 和配置硬件
cd ~/run && bash deploy.sh
#    脚本会自动安装 Docker、配置 SPI/音频/串口
#    构建镜像这一步会自动执行，如果想跳过构建直接用预编译镜像：
#    按 Ctrl+C 中止构建，然后执行下面的步骤

# 4. 登录 GitHub 镜像仓库
echo '你的GitHub_Classic_Token' | sudo docker login ghcr.io -u ccjj77vip-coder --password-stdin

# 5. 拉取预编译镜像（几分钟搞定，不用编译）
sudo docker pull ghcr.io/ccjj77vip-coder/lelamp:latest
sudo docker tag ghcr.io/ccjj77vip-coder/lelamp:latest lelamp:latest

# 6. 启动
sudo docker compose -f docker-compose.yml up -d
```

---

## 方法三：局域网拷贝（两台机器在同一网络）

适用于：新旧机器在同一局域网内，直接拷贝最省事。

```bash
# 在新机器上执行，假设旧机器 IP 为 192.168.x.x

# 1. 拷贝整个项目（含密钥）
scp -r 用户名@旧机器IP:~/run ~/run

# 2. 一键部署
cd ~/run && bash deploy.sh
```

---

## 方法四：离线镜像导入（最快，国内推荐）

适用于：国内网络环境，从网盘/U盘获取预编译镜像文件。

**维护者导出镜像（在已部署的机器上执行一次）：**

```bash
sudo docker save lelamp:latest | gzip > lelamp-image.tar.gz
# 文件约 313MB，上传到百度网盘/阿里云盘/U盘
```

**新机器部署：**

```bash
# 1. 获取代码
git clone https://github.com/ccjj77vip-coder/lelamp.git ~/run

# 2. 创建密钥文件（同方法一）

# 3. 运行部署脚本安装 Docker 和配置硬件
cd ~/run && bash deploy.sh
#    首次会提示重启（开启 SPI），重启后再跑一次
#    到 "正在构建 Docker 镜像" 时按 Ctrl+C 中止

# 4. 导入镜像（从网盘下载或 U 盘拷贝的文件）
sudo docker load < lelamp-image.tar.gz

# 5. 启动
cd ~/run && sudo docker compose -f docker-compose.yml up -d
```

> 导入镜像只需几秒钟，完全不需要联网下载或编译。

---

## 方法五：烧卡预装（批量部署最佳）

适用于：批量生产或重装系统，把一切预装进 SD 卡，开机即用。

**制作步骤（在电脑上操作）：**

1. 用 Raspberry Pi Imager 烧录系统到 SD 卡
2. 烧录完成后，SD 卡会挂载出 `bootfs` 和 `rootfs` 两个分区
3. 在 `rootfs` 分区的用户目录下放入项目文件：

```
rootfs/home/用户名/run/           ← 整个项目代码（git clone 或直接拷贝）
rootfs/home/用户名/run/.env       ← 密钥文件
rootfs/home/用户名/run/lelamp-image.tar.gz  ← 离线镜像（313MB）
```

4. SD 卡插入树莓派，开机后只需：

```bash
cd ~/run && bash deploy.sh
```

脚本会自动检测到 `lelamp-image.tar.gz`，直接导入镜像（几秒钟），跳过漫长的构建过程。
首次运行会安装 Docker + 配置硬件，可能需要重启一次，重启后再跑一次即可。

5. 启动
cd ~/run && sudo docker compose -f docker-compose.yml up -d

---

## 部署后：首次校准

部署完成后，浏览器打开 `http://树莓派IP:5000`，进行舵机校准：

1. 进入 **系统调教** 页面
2. 点击 **释放全部力矩**（舵机卸力）
3. 用手将台灯掰到理想的 HOME 位置
4. 点击 **保存为 HOME 零点**
5. 重启容器生效：
   ```bash
   sudo docker compose -f docker-compose.yml restart
   ```

---

## 日常操作

| 操作 | 命令 |
|------|------|
| 查看日志 | `sudo docker compose -f docker-compose.yml logs -f` |
| 重启服务 | `sudo docker compose -f docker-compose.yml restart` |
| 停止服务 | `sudo docker compose -f docker-compose.yml down` |
| 更新代码 | `cd ~/run && git pull && sudo docker compose -f docker-compose.yml build && sudo docker compose -f docker-compose.yml up -d` |
| 修改密钥 | 编辑 `~/run/.env`，然后 `sudo docker compose -f docker-compose.yml restart` |

---

## 更新镜像到 GitHub（维护者操作）

在开发机上修改代码后，推送镜像供其他机器直接拉取：

```bash
# 1. 提交代码
cd ~/run && git add -A && git commit -m "描述" && git push

# 2. 重新构建镜像
sudo docker compose -f docker-compose.yml build

# 3. 推送镜像
sudo docker tag lelamp:latest ghcr.io/ccjj77vip-coder/lelamp:latest
sudo docker push ghcr.io/ccjj77vip-coder/lelamp:latest
```

其他机器更新：

```bash
cd ~/run && git pull
sudo docker pull ghcr.io/ccjj77vip-coder/lelamp:latest
sudo docker tag ghcr.io/ccjj77vip-coder/lelamp:latest lelamp:latest
sudo docker compose -f docker-compose.yml up -d
```

---

## 常见问题

### Docker 安装卡住
国内网络问题。脚本已使用清华镜像源，如果仍然卡住，检查网络是否能访问 `mirrors.tuna.tsinghua.edu.cn`。

### 构建镜像很慢
首次构建需要下载基础镜像和编译依赖，约 10-20 分钟。推荐使用 **方法二** 直接拉取预编译镜像。

### 容器启动后舵机不动
检查 USB 舵机控制板是否插好（`ls /dev/ttyUSB0`），确认已完成校准。

### AI 对话没有响应
检查 `.env` 文件中的 API 密钥是否正确填写。
