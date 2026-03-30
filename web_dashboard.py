# -*- coding: utf-8 -*-
from flask import Flask, jsonify, render_template_string, request, send_from_directory, Response
import json
import os
import time
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_FILE = os.path.join(BASE_DIR, 'calibration.json')
PHOTO_DIR = os.path.join(BASE_DIR, 'photos')

if not os.path.exists(PHOTO_DIR): os.makedirs(PHOTO_DIR)

app = Flask(__name__)
# 关闭烦人的 Flask 访问日志，保持终端纯净
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

from config import read_calibration, write_calibration

_brain_context = None

def load_calibration():
    return read_calibration()

def save_calibration(data):
    write_calibration(data)

# 纯净版 HTML 前端（已清洗全部乱码）
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LeLamp 展会全功能控制台</title>
    <style>
        :root { --primary: #007aff; --bg: #f5f5f7; --card-bg: #ffffff; --text: #1d1d1f; --text-light: #86868b; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
        .navbar { background: rgba(255, 255, 255, 0.8); backdrop-filter: saturate(180%) blur(20px); position: sticky; top: 0; z-index: 100; display: flex; justify-content: space-between; align-items: center; padding: 15px 30px; box-shadow: 0 1px 0 rgba(0,0,0,0.05); }
        .nav-title { font-size: 20px; font-weight: 600; }
        .tabs { display: flex; background: #e3e3e8; border-radius: 8px; padding: 3px; }
        .tab { padding: 6px 14px; font-size: 14px; font-weight: 500; color: var(--text-light); cursor: pointer; border-radius: 6px; }
        .tab.active { background: #fff; color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .container { max-width: 900px; margin: 30px auto; padding: 0 20px; }
        .view { display: none; animation: fadeIn 0.3s ease; }
        .view.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .card { background: var(--card-bg); border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
        button { width: 100%; padding: 14px; border-radius: 10px; border: none; font-size: 15px; font-weight: 600; cursor: pointer; color: white; margin-bottom: 10px; transition: 0.2s; }
        button:active { transform: scale(0.98); }
        .btn-orange { background: #ff9500; }
        .btn-blue { background: var(--primary); }
        .btn-green { background: #34c759; }
        .btn-purple { background: #af52de; }
        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 20px; }
        .photo-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        .photo-card img { width: 100%; height: 160px; object-fit: cover; }
        input[type=range] { -webkit-appearance: none; width: 100%; background: transparent; }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; height: 24px; width: 24px; border-radius: 50%; background: var(--primary); cursor: pointer; margin-top: -8px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); }
        input[type=range]::-webkit-slider-runnable-track { width: 100%; height: 8px; cursor: pointer; background: #e3e3e8; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="navbar">
        <div class="nav-title">🚀 LeLamp OS</div>
        <div class="tabs">
            <div class="tab" onclick="switchView('live')">🔴 实时监控</div>
            <div class="tab active" onclick="switchView('remote')">🎮 展会控制</div>
            <div class="tab" onclick="switchView('chat')">🎤 语音对话</div>
            <div class="tab" onclick="switchView('gallery')">📸 时光相册</div>
            <div class="tab" onclick="switchView('persona')">🎭 角色切换</div>
            <div class="tab" onclick="switchView('calibrate')">⚙️ 系统调教</div>
        </div>
    </div>

    <div class="container">
        <div id="view-live" class="view">
            <div class="card" style="text-align: center; background: #000;">
                <img src="/video_feed" style="width: 100%; max-width: 800px; border-radius: 10px; display: block; margin: 0 auto;" onerror="this.src=''; this.alt='摄像头未连接或被占用';">
            </div>
            <div class="card" style="display: flex; gap: 10px;">
                <button class="btn-blue" onclick="postAction('/api/remote_photo')">📸 远程抓拍</button>
            </div>
        </div>

        <div id="view-remote" class="view active">
            <div class="card">
                <h3 style="margin-top: 0;">🔊 扬声器音量调节</h3>
                <div style="display: flex; align-items: center; gap: 15px; margin-top: 15px;">
                    <span style="font-size: 20px;">🔈</span>
                    <input type="range" id="volume_slider" min="0" max="100" step="5" value="100" onchange="setVolume(this.value)" oninput="document.getElementById('vol_val').innerText = this.value + '%'">
                    <span style="font-size: 20px;">🔊</span>
                </div>
                <div style="text-align: center; margin-top: 15px; font-weight: bold; color: var(--primary); font-size: 24px;" id="vol_val">100%</div>
                <div style="display:flex; gap:8px; margin-top:12px;">
                    <button class="btn-orange" onclick="document.getElementById('volume_slider').value=30;setVolume(30);document.getElementById('vol_val').innerText='30%'" style="flex:1; font-size:13px; padding:10px;">低</button>
                    <button class="btn-blue" onclick="document.getElementById('volume_slider').value=70;setVolume(70);document.getElementById('vol_val').innerText='70%'" style="flex:1; font-size:13px; padding:10px;">中</button>
                    <button class="btn-green" onclick="document.getElementById('volume_slider').value=100;setVolume(100);document.getElementById('vol_val').innerText='100%'" style="flex:1; font-size:13px; padding:10px;">满</button>
                </div>
            </div>

            <div class="card">
                <h3 style="margin-top:0;">💃 展会才艺：舞蹈库</h3>
                <button class="btn-blue" onclick="postAction('/api/action/dance')">🎵 经典舞蹈</button>
                <button class="btn-green" onclick="postAction('/api/action/dance_cute')">💖 可爱撒娇</button>
                <button class="btn-orange" onclick="postAction('/api/action/dance_playful')">✨ 俏皮摇摆</button>
                <button class="btn-purple" onclick="postAction('/api/action/dance_long')">🌟 闪耀舞台 (长舞)</button>
                <button class="btn-blue" onclick="postAction('/api/action/dance_random')" style="background:#e91e63;">🎲 随机编排</button>
            </div>
            <div class="card">
                <h3 style="margin-top:0;">🎬 自定义舞蹈</h3>
                <div id="custom-dance-list" style="margin-bottom:10px;"></div>
                <button class="btn-green" onclick="loadCustomDances()" style="width:auto; padding:8px 20px;">🔄 刷新列表</button>
            </div>
            <div class="card">
                <h3>🗣 展会互动</h3>
                <button class="btn-green" onclick="postAction('/api/action/nod')">✅ 赞同点头</button>
                <button class="btn-orange" onclick="postAction('/api/action/shake')">❌ 摇头拒绝</button>
            </div>
        </div>

        <div id="view-chat" class="view">
            <div class="card">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:15px;">
                    <h3 style="margin:0;">🎤 语音交互</h3>
                    <span id="chat-status" style="font-size:13px; color:#86868b; padding:4px 12px; background:#f5f5f7; border-radius:20px;">待命中</span>
                </div>
                <div style="display:flex; gap:10px;">
                    <button id="btn-start-voice" class="btn-green" onclick="startVoice()" style="font-size:18px; padding:18px; flex:1;">🎙️ 开始对话</button>
                    <button id="btn-stop-voice" class="btn-orange" onclick="stopVoice()" style="font-size:18px; padding:18px; flex:1; display:none; background:#ff3b30;">⏹ 结束对话</button>
                </div>
                <p style="color:#86868b; font-size:13px; text-align:center; margin-top:8px;">开始后可持续对话，点击"结束"或说"退下/再见"停止</p>
            </div>
            <div class="card">
                <h3 style="margin-top:0;">💬 对话记录</h3>
                <div id="chat-log" style="max-height:400px; overflow-y:auto; display:flex; flex-direction:column; gap:10px;">
                    <div style="color:#86868b; font-size:14px; text-align:center;">暂无对话</div>
                </div>
            </div>
            <div class="card">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
                    <h3 style="margin:0;">🔍 麦克风监听</h3>
                    <div style="display:flex; gap:6px;">
                        <button id="btn-mic-start" class="btn-blue" onclick="startMicMonitor()" style="width:auto; padding:6px 14px; font-size:13px; margin:0;">开始监听</button>
                        <button id="btn-mic-stop" class="btn-orange" onclick="stopMicMonitor()" style="width:auto; padding:6px 14px; font-size:13px; margin:0; display:none; background:#ff3b30;">停止</button>
                    </div>
                </div>
                <p style="color:#86868b; font-size:12px; margin:0 0 10px 0;">实时显示麦克风拾音音量，用来确认硬件是否正常。对着麦克风说话，绿色条应该跳动。</p>
                <div style="background:#1d1d1f; border-radius:10px; padding:12px; position:relative;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="color:#86868b; font-size:12px; white-space:nowrap;">音量</span>
                        <div style="flex:1; height:24px; background:#2a2a2e; border-radius:6px; overflow:hidden; position:relative;">
                            <div id="mic-bar" style="height:100%; width:0%; background:linear-gradient(90deg, #34c759, #ff9500, #ff3b30); border-radius:6px; transition:width 0.1s;"></div>
                        </div>
                        <span id="mic-val" style="color:#fff; font-size:14px; font-weight:bold; min-width:50px; text-align:right;">0</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:6px; padding:0 35px 0 35px;">
                        <span style="color:#555; font-size:10px;">静音</span>
                        <span style="color:#555; font-size:10px;">VAD阈值(200)</span>
                        <span style="color:#555; font-size:10px;">很响</span>
                    </div>
                </div>
            </div>
        </div>

        <div id="view-gallery" class="view">
            <div class="card">
                <button class="btn-blue" style="width: auto; padding: 8px 20px;" onclick="loadPhotos()">🔄 刷新相册</button>
                <div class="gallery" id="photo-grid"></div>
            </div>
        </div>

        <div id="view-persona" class="view">
            <div class="card">
                <h3 style="margin-top:0;">🎭 角色切换</h3>
                <p style="color: #666; font-size: 14px;">选择一个预设角色或创建自定义角色，每个角色有独立的性格和声音。</p>
                <div id="persona-list" style="display: flex; flex-direction: column; gap: 10px;"></div>
            </div>
            <div class="card" id="custom-persona-card" style="display:none;">
                <h3 style="margin-top:0;">✏️ 自定义角色设置</h3>
                <label style="font-size: 14px; font-weight: 600;">角色名称</label>
                <input type="text" id="custom_name" placeholder="如：小助手" style="width:100%; padding:10px; margin: 5px 0 12px 0; border-radius:8px; border:1px solid #ccc; box-sizing:border-box;">
                <label style="font-size: 14px; font-weight: 600;">音色选择</label>
                <select id="custom_voice" style="width:100%; padding:10px; margin: 5px 0 12px 0; border-radius:8px; border:1px solid #ccc; box-sizing:border-box;">
                </select>
                <label style="font-size: 14px; font-weight: 600;">角色设定 (System Prompt)</label>
                <textarea id="custom_prompt" placeholder="描述角色的性格、说话风格、称呼方式等..." style="width:100%; height:120px; padding:10px; margin: 5px 0 12px 0; border-radius:8px; border:1px solid #ccc; box-sizing:border-box; resize:vertical;"></textarea>
                <button class="btn-green" onclick="saveCustomPersona()">💾 保存并切换到此角色</button>
            </div>
        </div>

        <div id="view-calibrate" class="view">
            <div class="card">
                <h3>1. 解锁关节 (物理微调)</h3>
                <p style="color: #666; font-size: 14px;">点击释放力矩后，用手将台灯头部调整到最完美的拍照仰角。</p>
                <button class="btn-orange" onclick="postAction('/api/torque_off')">🔓 释放全部力矩</button>
            </div>
            <div class="card">
                <h3>2. 设定新零点</h3>
                <p style="color: #666; font-size: 14px;">调整好后点击此按钮，机器人将永久记住这个新姿态为默认状态。</p>
                <button class="btn-blue" onclick="postAction('/api/save_home')">🎯 保存为【HOME】零点</button>
            </div>
            <div class="card">
                <h3>3. 录制新动作</h3>
                <input type="text" id="pose_name" placeholder="动作名称 (如: ANGRY)" style="width:100%; padding:10px; margin-bottom:10px; border-radius:8px; border:1px solid #ccc; box-sizing:border-box;">
                <button class="btn-green" onclick="savePose()">💾 保存自定义动作</button>
            </div>
            <div class="card">
                <h3>4. 录制舞蹈</h3>
                <p style="color: #666; font-size: 14px;">先释放力矩，然后按"捕捉帧"逐帧录制动作，最后保存为舞蹈。</p>
                <input type="text" id="dance_name" placeholder="舞蹈名称 (如: 打招呼)" style="width:100%; padding:10px; margin-bottom:10px; border-radius:8px; border:1px solid #ccc; box-sizing:border-box;">
                <div style="display:flex; gap:10px; margin-bottom:10px;">
                    <button class="btn-blue" onclick="captureFrame()" style="flex:1;">📷 捕捉一帧</button>
                    <button class="btn-orange" onclick="undoFrame()" style="flex:1;">↩️ 撤销末帧</button>
                </div>
                <div id="frame-count" style="text-align:center; color:#86868b; font-size:14px; margin-bottom:10px;">已捕捉 0 帧</div>
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                    <span style="font-size:14px; white-space:nowrap;">节奏:</span>
                    <input type="range" id="dance_tempo" min="0.2" max="2.0" step="0.1" value="0.5" oninput="document.getElementById('tempo_val').innerText=this.value+'s'">
                    <span id="tempo_val" style="font-size:14px; white-space:nowrap;">0.5s</span>
                </div>
                <button class="btn-green" onclick="saveDance()">💾 保存舞蹈</button>
                <button class="btn-purple" onclick="previewDance()" style="margin-top:5px;">▶️ 预览回放</button>
            </div>
            <div class="card" style="border:2px solid #ff3b30;">
                <h3 style="color:#ff3b30; margin-top:0;">⚠️ 恢复出厂设置</h3>
                <p style="color: #666; font-size: 14px;">清除所有校准数据、自定义动作、舞蹈、照片和角色配置，恢复到初始状态。此操作不可逆！</p>
                <button onclick="factoryReset()" style="background:#ff3b30; font-size:16px;">🗑 恢复出厂设置</button>
            </div>
        </div>
    </div>

    <script>
        function switchView(name) {
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('view-' + name).classList.add('active');
            event.currentTarget.classList.add('active');
            if(name === 'gallery') loadPhotos();
            if(name === 'persona') loadPersonas();
            if(name === 'chat' && !chatPollTimer) chatPollTimer = setInterval(pollChatStatus, 800);
        }

        function postAction(url) {
            fetch(url, {method: 'POST'}).then(res => res.json()).then(data => {
                if(!data.success) alert("错误: " + (data.error || "未知异常"));
                else if (url.includes('save_home')) alert("✅ 零点覆盖成功！机器人已记住该姿势。");
                else if (url.includes('torque_off')) alert("🔓 舵机力矩已释放，可以手动掰动关节了。");
            }).catch(e => alert("网络请求失败，请检查终端日志"));
        }

        function setVolume(val) {
            fetch('/api/volume', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({volume: val})
            }).then(res => res.json()).then(data => {
                if(!data.success) alert("音量调节失败: " + data.error);
            });
        }

        function savePose() {
            let name = document.getElementById('pose_name').value.trim();
            if(!name) return alert("请先填写动作名称！");
            fetch('/api/save_pose', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name})
            }).then(res => res.json()).then(data => alert(data.success ? "动作录制成功！" : "错误: " + data.error));
        }

        function factoryReset() {
            if (!confirm('⚠️ 确定要恢复出厂设置吗？\\n\\n将清除：\\n• 所有校准数据 (HOME零点)\\n• 自定义动作\\n• 自定义舞蹈\\n• 所有照片\\n• 角色配置\\n\\n此操作不可逆！')) return;
            if (!confirm('再次确认：真的要清除所有数据吗？')) return;
            fetch('/api/factory_reset', {method: 'POST'}).then(res => res.json()).then(data => {
                if (data.success) {
                    alert('✅ 已恢复出厂设置！容器将自动重启。');
                    setTimeout(() => location.reload(), 3000);
                } else {
                    alert('恢复失败: ' + (data.error || ''));
                }
            });
        }

        function loadPhotos() {
            fetch('/api/photos').then(res => res.json()).then(data => {
                const grid = document.getElementById('photo-grid');
                grid.innerHTML = data.photos.map(p => `
                    <div class="photo-card">
                        <img src="/photos/${p}">
                        <div style="padding:10px; font-size:12px; color:#666;">${p}</div>
                    </div>
                `).join('');
            });
        }

        // ===== 舞蹈录制逻辑 =====
        let danceFrames = [];

        function captureFrame() {
            fetch('/api/dance/capture', {method: 'POST'}).then(res => res.json()).then(data => {
                if (data.success) {
                    danceFrames.push(data.frame);
                    document.getElementById('frame-count').innerText = '已捕捉 ' + danceFrames.length + ' 帧';
                } else {
                    alert('捕捉失败: ' + (data.error || ''));
                }
            });
        }

        function undoFrame() {
            if (danceFrames.length > 0) {
                danceFrames.pop();
                document.getElementById('frame-count').innerText = '已捕捉 ' + danceFrames.length + ' 帧';
            }
        }

        function saveDance() {
            const name = document.getElementById('dance_name').value.trim();
            const tempo = parseFloat(document.getElementById('dance_tempo').value);
            if (!name) return alert('请填写舞蹈名称！');
            if (danceFrames.length < 2) return alert('至少需要录制 2 帧动作！');

            fetch('/api/dance/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name, frames: danceFrames, tempo: tempo})
            }).then(res => res.json()).then(data => {
                if (data.success) {
                    alert('舞蹈 "' + name + '" 保存成功！共 ' + danceFrames.length + ' 帧');
                    danceFrames = [];
                    document.getElementById('frame-count').innerText = '已捕捉 0 帧';
                    document.getElementById('dance_name').value = '';
                } else {
                    alert('保存失败: ' + (data.error || ''));
                }
            });
        }

        function previewDance() {
            if (danceFrames.length < 2) return alert('至少需要 2 帧才能预览！');
            const tempo = parseFloat(document.getElementById('dance_tempo').value);
            fetch('/api/dance/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({frames: danceFrames, tempo: tempo})
            }).then(res => res.json()).then(data => {
                if (!data.success) alert('预览失败: ' + (data.error || ''));
            });
        }

        function loadCustomDances() {
            fetch('/api/dance/list').then(res => res.json()).then(data => {
                const container = document.getElementById('custom-dance-list');
                if (!data.dances || Object.keys(data.dances).length === 0) {
                    container.innerHTML = '<div style="color:#86868b; font-size:14px;">暂无自定义舞蹈，去"系统调教"录制吧！</div>';
                    return;
                }
                container.innerHTML = Object.entries(data.dances).map(([name, frameCount]) => `
                    <div style="display:flex; align-items:center; justify-content:space-between; padding:10px 14px; background:#f5f5f7; border-radius:10px; margin-bottom:8px;">
                        <div>
                            <span style="font-weight:600;">${name}</span>
                            <span style="color:#86868b; font-size:12px; margin-left:8px;">${frameCount} 帧</span>
                        </div>
                        <div style="display:flex; gap:6px;">
                            <button onclick="postAction('/api/action/custom_dance_${name}')" style="width:auto; padding:6px 14px; font-size:13px;" class="btn-blue">▶️ 播放</button>
                            <button onclick="deleteDance('${name}')" style="width:auto; padding:6px 14px; font-size:13px; background:#ff3b30;" class="btn-orange">🗑</button>
                        </div>
                    </div>
                `).join('');
            });
        }

        function deleteDance(name) {
            if (!confirm('确定要删除舞蹈 "' + name + '" 吗？')) return;
            fetch('/api/dance/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name})
            }).then(res => res.json()).then(data => {
                if (data.success) loadCustomDances();
                else alert('删除失败');
            });
        }

        // ===== 语音交互逻辑 =====
        let chatPollTimer = null;

        function startVoice() {
            const btn = document.getElementById('btn-start-voice');
            const stopBtn = document.getElementById('btn-stop-voice');
            btn.disabled = true;
            btn.style.display = 'none';
            stopBtn.style.display = 'block';

            fetch('/api/voice/start', {method: 'POST'}).then(res => res.json()).then(data => {
                if (!data.success) {
                    alert(data.error || '启动失败');
                    btn.disabled = false;
                    btn.style.display = 'block';
                    stopBtn.style.display = 'none';
                }
            });

            // 开始轮询状态和对话记录
            if (!chatPollTimer) {
                chatPollTimer = setInterval(pollChatStatus, 800);
            }
        }

        function stopVoice() {
            fetch('/api/voice/stop', {method: 'POST'});
            const btn = document.getElementById('btn-start-voice');
            const stopBtn = document.getElementById('btn-stop-voice');
            btn.disabled = false;
            btn.style.display = 'block';
            stopBtn.style.display = 'none';
        }

        function pollChatStatus() {
            fetch('/api/voice/status').then(res => res.json()).then(data => {
                // 更新状态标签
                const statusEl = document.getElementById('chat-status');
                const btn = document.getElementById('btn-start-voice');
                const stopBtn = document.getElementById('btn-stop-voice');
                const statusMap = {
                    'idle': '待命中',
                    'listening': '🟠 正在听...',
                    'thinking': '🟡 思考中...',
                    'speaking': '🟢 播报中...'
                };
                statusEl.innerText = statusMap[data.status] || data.status;

                if (data.status === 'idle') {
                    btn.disabled = false;
                    btn.style.display = 'block';
                    stopBtn.style.display = 'none';
                } else {
                    btn.style.display = 'none';
                    stopBtn.style.display = 'block';
                }

                // 更新对话记录
                const logEl = document.getElementById('chat-log');
                if (data.chat_log && data.chat_log.length > 0) {
                    logEl.innerHTML = data.chat_log.map(msg => {
                        const isUser = msg.role === 'user';
                        return `<div style="display:flex; justify-content:${isUser ? 'flex-end' : 'flex-start'};">
                            <div style="max-width:75%; padding:10px 14px; border-radius:${isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px'}; background:${isUser ? '#ff9500' : '#f5f5f7'}; color:${isUser ? '#fff' : '#1d1d1f'}; font-size:14px; line-height:1.5;">
                                ${msg.text}
                            </div>
                        </div>`;
                    }).join('');
                    logEl.scrollTop = logEl.scrollHeight;
                }
            }).catch(() => {});
        }

        // ===== 麦克风监听逻辑 =====
        let micPollTimer = null;

        function startMicMonitor() {
            fetch('/api/mic/start', {method: 'POST'}).then(res => res.json()).then(data => {
                if (data.success) {
                    document.getElementById('btn-mic-start').style.display = 'none';
                    document.getElementById('btn-mic-stop').style.display = 'inline-block';
                    if (!micPollTimer) {
                        micPollTimer = setInterval(pollMicLevel, 150);
                    }
                } else {
                    alert('启动失败: ' + (data.error || ''));
                }
            });
        }

        function stopMicMonitor() {
            fetch('/api/mic/stop', {method: 'POST'});
            document.getElementById('btn-mic-start').style.display = 'inline-block';
            document.getElementById('btn-mic-stop').style.display = 'none';
            if (micPollTimer) { clearInterval(micPollTimer); micPollTimer = null; }
            document.getElementById('mic-bar').style.width = '0%';
            document.getElementById('mic-val').innerText = '0';
        }

        function pollMicLevel() {
            fetch('/api/mic/level').then(res => res.json()).then(data => {
                const level = data.level || 0;
                const pct = Math.min(100, (level / 3000) * 100);
                document.getElementById('mic-bar').style.width = pct + '%';
                document.getElementById('mic-val').innerText = level;
            }).catch(() => {});
        }

        // ===== 角色切换逻辑 =====
        function loadPersonas() {
            fetch('/api/personas').then(res => res.json()).then(data => {
                const list = document.getElementById('persona-list');
                list.innerHTML = data.personas.map(p => `
                    <div onclick="${p.id === 'custom' ? 'showCustomPanel()' : "switchPersona('" + p.id + "')"}"
                         style="display:flex; align-items:center; justify-content:space-between; padding:14px 18px; background:${p.active ? '#e8f5e9' : '#f5f5f7'}; border-radius:12px; cursor:pointer; border:2px solid ${p.active ? '#34c759' : 'transparent'}; transition:0.2s;">
                        <div>
                            <div style="font-weight:600; font-size:16px;">${p.display_name}</div>
                            <div style="font-size:12px; color:#86868b;">${p.id === 'custom' ? '点击自定义设置' : '预设角色'}</div>
                        </div>
                        ${p.active ? '<span style="color:#34c759; font-weight:bold;">● 当前</span>' : '<span style="color:#86868b;">切换 →</span>'}
                    </div>
                `).join('');

                // 加载可用音色到下拉框
                const voiceSelect = document.getElementById('custom_voice');
                if (data.voices && voiceSelect.options.length <= 1) {
                    voiceSelect.innerHTML = data.voices.map(v =>
                        `<option value="${v.id}">${v.name} (${v.gender === 'female' ? '女' : '男'})</option>`
                    ).join('');
                }

                // 如果当前是自定义角色，展开自定义面板
                const customActive = data.personas.find(p => p.id === 'custom' && p.active);
                if (customActive) {
                    document.getElementById('custom-persona-card').style.display = 'block';
                }
            });
        }

        function switchPersona(id) {
            fetch('/api/persona/switch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({persona_id: id})
            }).then(res => res.json()).then(data => {
                if (data.success) {
                    loadPersonas();
                    alert('角色已切换为: ' + data.display_name);
                } else {
                    alert('切换失败: ' + (data.error || '未知错误'));
                }
            });
        }

        function showCustomPanel() {
            document.getElementById('custom-persona-card').style.display = 'block';
        }

        function saveCustomPersona() {
            const name = document.getElementById('custom_name').value.trim();
            const voice = document.getElementById('custom_voice').value;
            const prompt = document.getElementById('custom_prompt').value.trim();
            if (!name || !prompt) return alert('请填写角色名称和角色设定！');

            fetch('/api/persona/switch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    persona_id: 'custom',
                    custom_config: {
                        display_name: name,
                        voice_id: voice,
                        system_prompt: prompt,
                        vision_prompt: '用简短幽默的口吻点评这张照片，40字以内。'
                    }
                })
            }).then(res => res.json()).then(data => {
                if (data.success) {
                    loadPersonas();
                    alert('自定义角色已激活: ' + name);
                } else {
                    alert('保存失败: ' + (data.error || '未知错误'));
                }
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/photos/<filename>')
def serve_photo(filename): return send_from_directory(PHOTO_DIR, filename)

@app.route('/api/photos')
def api_get_photos():
    files = sorted([f for f in os.listdir(PHOTO_DIR) if f.endswith('.jpg')], reverse=True)
    return jsonify({"photos": files})

def generate_video_stream(brain):
    while True:
        if brain and hasattr(brain, 'camera'):
            frame_bytes = brain.camera.get_frame_bytes()
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.06)

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(_brain_context), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/remote_photo', methods=['POST'])
def api_remote_photo():
    if _brain_context and hasattr(_brain_context, 'camera'):
        success, msg = _brain_context.camera.take_photo()
        return jsonify({"success": success, "error": msg if not success else ""})
    return jsonify({"success": False, "error": "摄像头系统未就绪"})

@app.route('/api/volume', methods=['POST'])
def api_set_volume():
    if _brain_context and hasattr(_brain_context, 'voice'):
        vol = request.json.get('volume', 100)
        _brain_context.voice.set_volume(int(vol))
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "语音系统未就绪"})

# 🚀 修复点：恢复被乱码注释掉的动作路由接口！
@app.route('/api/action/<action_name>', methods=['POST'])
def api_do_action(action_name):
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"success": False, "error": "动作引擎未就绪"})
    
    def run_action():
        if action_name == 'dance':
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.dance()
        elif action_name == 'dance_cute':
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.dance_cute()
        elif action_name == 'dance_playful':
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.dance_playful()
        elif action_name == 'dance_long':
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.dance_long()
        elif action_name == 'dance_random':
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.dance_random()
        elif action_name.startswith('custom_dance_'):
            dance_name = action_name[len('custom_dance_'):]
            _brain_context.led.set_effect("rainbow")
            _brain_context.motion.play_dance(dance_name)
        elif action_name == 'nod':
            _brain_context.motion.nod()
        elif action_name == 'shake':
            _brain_context.motion.shake_head()
        
        # 动作结束后恢复原位
        _brain_context.motion.go_home(duration=1.0)
        _brain_context.led.set_effect("warm_lamp")

    threading.Thread(target=run_action, daemon=True).start()
    return jsonify({"success": True})

@app.route('/api/torque_off', methods=['POST'])
def api_torque_off():
    if _brain_context and hasattr(_brain_context, 'motion'):
        _brain_context.motion.free_torque() 
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "动作引擎未就绪"})

@app.route('/api/save_home', methods=['POST'])
def api_save_home():
    if _brain_context and hasattr(_brain_context, 'motion'):
        pos = {}
        for sid in [1,2,3,4,5]:
            p = _brain_context.motion.driver.read_pos(sid)
            if p != -1: pos[str(sid)] = p
        if len(pos) < 5: return jsonify({"success": False, "error": "部分舵机读取失败，请检查线路"})
        
        data = load_calibration()
        data["HOME_OFFSET"] = pos
        save_calibration(data)
        
        # 重新锁住力矩，防止机器人瘫倒
        _brain_context.motion.enable_torque()
        # 热加载新零点并回到 HOME
        _brain_context.motion._load_calibration()
        _brain_context.motion.go_home(duration=1.0)
        _brain_context.led.set_effect("warm_lamp")
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "动作引擎未就绪"})

@app.route('/api/save_pose', methods=['POST'])
def api_save_pose():
    name = request.json.get('name')
    if _brain_context and name and hasattr(_brain_context, 'motion'):
        pos = {}
        for sid in [1,2,3,4,5]:
            p = _brain_context.motion.driver.read_pos(sid)
            if p != -1: pos[str(sid)] = p
            
        data = load_calibration()
        if "CUSTOM_POSES" not in data: data["CUSTOM_POSES"] = {}
        data["CUSTOM_POSES"][name] = pos
        
        if name == "THINKING":
            _brain_context.custom_thinking_pose = pos
        save_calibration(data)

        _brain_context.motion.enable_torque()
        # 热加载校准数据并回到 HOME
        _brain_context.motion._load_calibration()
        _brain_context.motion.go_home(duration=1.0)
        _brain_context.led.set_effect("warm_lamp")
        if hasattr(_brain_context, 'intent_engine') and hasattr(_brain_context.intent_engine, 'load_dynamic_poses'):
            _brain_context.intent_engine.load_dynamic_poses()
            
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "系统未就绪或名称为空"})

# ============ 角色切换 API ============
@app.route('/api/personas')
def api_get_personas():
    from subsystems.persona import get_persona_manager
    pm = get_persona_manager()
    return jsonify({
        "personas": pm.list_personas(),
        "voices": pm.get_available_voices()
    })

@app.route('/api/persona/switch', methods=['POST'])
def api_switch_persona():
    from subsystems.persona import get_persona_manager
    data = request.json
    persona_id = data.get("persona_id")
    custom_config = data.get("custom_config")

    if not persona_id:
        return jsonify({"success": False, "error": "缺少 persona_id"})

    pm = get_persona_manager()
    result = pm.switch(persona_id, custom_config)
    if not result:
        return jsonify({"success": False, "error": "无效的角色ID"})

    # 同步更新 LLM 引擎的角色
    if _brain_context and hasattr(_brain_context, 'llm'):
        _brain_context.llm.switch_persona(persona_id, custom_config)

    return jsonify({
        "success": True,
        "display_name": result.get("display_name", "未知角色")
    })

@app.route('/api/persona/current')
def api_current_persona():
    from subsystems.persona import get_persona_manager
    pm = get_persona_manager()
    return jsonify({
        "id": pm.current_id,
        "config": pm.current
    })

# ============ 语音交互 API ============
@app.route('/api/voice/start', methods=['POST'])
def api_voice_start():
    if not _brain_context or not hasattr(_brain_context, 'trigger_voice'):
        return jsonify({"success": False, "error": "语音系统未就绪"})
    ok = _brain_context.trigger_voice()
    if not ok:
        return jsonify({"success": False, "error": "正在对话中，请稍候"})
    return jsonify({"success": True})

@app.route('/api/voice/stop', methods=['POST'])
def api_voice_stop():
    if _brain_context and hasattr(_brain_context, 'stop_voice'):
        _brain_context.stop_voice()
    return jsonify({"success": True})

@app.route('/api/mic/start', methods=['POST'])
def api_mic_start():
    if _brain_context and hasattr(_brain_context, 'voice'):
        _brain_context.voice.start_mic_monitor()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "语音系统未就绪"})

@app.route('/api/mic/stop', methods=['POST'])
def api_mic_stop():
    if _brain_context and hasattr(_brain_context, 'voice'):
        _brain_context.voice.stop_mic_monitor()
    return jsonify({"success": True})

@app.route('/api/mic/level')
def api_mic_level():
    if _brain_context and hasattr(_brain_context, 'voice'):
        return jsonify({"level": _brain_context.voice.get_mic_level()})
    return jsonify({"level": 0})

@app.route('/api/voice/status')
def api_voice_status():
    if not _brain_context or not hasattr(_brain_context, 'get_status'):
        return jsonify({"status": "idle", "chat_log": []})
    return jsonify({
        "status": _brain_context.get_status(),
        "chat_log": _brain_context.get_chat_log()
    })

# ============ 舞蹈录制/回放 API ============
@app.route('/api/dance/capture', methods=['POST'])
def api_dance_capture():
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"success": False, "error": "动作引擎未就绪"})
    frame = _brain_context.motion.record_dance_frame()
    if len(frame) < 5:
        return jsonify({"success": False, "error": "部分舵机读取失败"})
    return jsonify({"success": True, "frame": frame})

@app.route('/api/dance/save', methods=['POST'])
def api_dance_save():
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"success": False, "error": "动作引擎未就绪"})
    data = request.json
    name = data.get("name", "").strip()
    frames = data.get("frames", [])
    tempo = data.get("tempo", 0.5)
    if not name or len(frames) < 2:
        return jsonify({"success": False, "error": "名称为空或帧数不足"})
    _brain_context.motion.save_dance(name, frames, tempo)
    # 热加载校准数据并回到 HOME
    _brain_context.motion.enable_torque()
    _brain_context.motion._load_calibration()
    _brain_context.motion.go_home(duration=1.0)
    _brain_context.led.set_effect("warm_lamp")
    return jsonify({"success": True})

@app.route('/api/dance/preview', methods=['POST'])
def api_dance_preview():
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"success": False, "error": "动作引擎未就绪"})
    data = request.json
    frames = data.get("frames", [])
    tempo = data.get("tempo", 0.5)
    if len(frames) < 2:
        return jsonify({"success": False, "error": "帧数不足"})

    def run_preview():
        _brain_context.motion.enable_torque()
        for frame in frames:
            target = {int(k): v for k, v in frame.items()}
            _brain_context.motion.move_to(target, duration=tempo)
            time.sleep(tempo)
        _brain_context.motion.go_home(duration=1.0)

    threading.Thread(target=run_preview, daemon=True).start()
    return jsonify({"success": True})

@app.route('/api/dance/list')
def api_dance_list():
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"dances": {}})
    return jsonify({"dances": _brain_context.motion.list_dances()})

@app.route('/api/dance/delete', methods=['POST'])
def api_dance_delete():
    if not _brain_context or not hasattr(_brain_context, 'motion'):
        return jsonify({"success": False})
    name = request.json.get("name", "")
    return jsonify({"success": _brain_context.motion.delete_dance(name)})

# ============ 恢复出厂设置 ============
@app.route('/api/factory_reset', methods=['POST'])
def api_factory_reset():
    import shutil, glob as g
    try:
        # 1. 重置 calibration.json
        save_calibration({"HOME_OFFSET": {}, "CUSTOM_POSES": {}, "CUSTOM_DANCES": {}})

        # 2. 清除所有照片
        for f in g.glob(os.path.join(PHOTO_DIR, '*.jpg')):
            os.remove(f)

        # 3. 重置角色到默认
        try:
            from subsystems.persona import get_persona_manager
            pm = get_persona_manager()
            pm.switch("zhuge")
            if _brain_context and hasattr(_brain_context, 'llm'):
                _brain_context.llm.switch_persona("zhuge")
        except:
            pass

        # 4. 热加载
        if _brain_context and hasattr(_brain_context, 'motion'):
            _brain_context.motion._load_calibration()

        print("[系统] 已恢复出厂设置")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

def run_server(brain_instance):
    global _brain_context
    _brain_context = brain_instance
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

# 🚀 修复点：新增独立运行入口
if __name__ == "__main__":
    print("\n🚀 [系统级调度] 正在以独立模式启动全功能控制台...")
    
    # 构造一个独立大脑，激活底层驱动模块，供独立调参使用
    class StandaloneBrain:
        def __init__(self):
            from subsystems.motion import get_motion_system
            from subsystems.led import get_led_engine
            from subsystems.camera import get_camera_system
            print("⏳ 正在唤醒运动与视觉神经元...")
            self.motion = get_motion_system()
            self.led = get_led_engine()
            self.camera = get_camera_system()
            
            self.motion.start()
            self.led.start()
            self.motion.go_home()
            print("✅ 底层驱动加载完毕！")

    try:
        standalone_brain = StandaloneBrain()
        print("\n🌐 网页控制台已在端口 5000 成功暴露！")
        print("💻 请用电脑浏览器访问: http://你的树莓派IP:5000")
        run_server(standalone_brain)
    except Exception as e:
        print(f"\n❌ 控制台启动异常: {e}")
